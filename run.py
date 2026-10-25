# -*- coding: utf-8 -*-
"""
定时任务执行体（与仓库对外用途无关的命名）。

职责：
1. 从运行环境读取加密分片 NB_POOL_1..5（每条 = [{ck, song, added, name}, ...]），
   本文件/仓库不落任何明文 cookie。
2. 校验每个账号是否存活（account/get），丢弃失效会话。
3. 过滤"当天新加入"的号（added == 今天 不参与，满足第 2 天入池）。
4. 当前 job 只处理自己分片 (i % NS == SLICE) 的账号；每个账号随机挑
   PLAYS_PER_ACCOUNT 个"别人的歌"播放，绝不播自己的歌。
   带有 noListen 标记的号（如群主大号）只进歌池被别人听，自己不播放。
5. 复用已验证可用的上报通道（weapi + eapi 双通道，time>=31s）。

配置见 cfg.json。运行参数来自环境变量 NS / SLICE（matrix 注入）。
"""
import json
import os
import sys
import time
import random
import base64
import gzip
import hashlib
import math
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import requests
from Crypto.Cipher import AES

BASE_URL = "https://music.163.com"

# ===== 加密参数（与历史实现一致，公开已知） =====
_NONCE = "0CoJUm6Qyw8W8jud"
_SECRETKEY = "TA3YiYCfY2dDJQgg"
_VI = "0102030405060708"
_ENCSECKEY = "84ca47bca10bad09a6b04c5c927ef077d9b9f1e37098aa3eac6ea70eb59df0aa28b691b7e75e4f1f9831754919ea784c8f74fbfadf2898b0be17849fd656060162857830e241aba44991601f137624094c114ea8d17bce815b0cd4e5b8e2fbaba978c6d1d14dc3d1faf852bdd28818031ccdaaa13a6018e1024e2aae98844210"

MOBILE_UAS = [
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.73 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Samsung Galaxy S22) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.71 Mobile Safari/537.36",
]

# 混听来源：云音乐热歌榜（公开歌单，真实在榜歌曲，随官方榜单变化）
MIX_HOT_PID = 3778678
# 登记页 Worker 地址（失效账号清理上报用）
WORKER_URL = "https://dingzhi.xx1031.xyz"   # 2026-10-23：dz.xx1031.xyz 已泄露到用户手上，弃用
# 有效计数门槛：单曲播放进度需超过整首的一半，后台才计一次「有效计数」。
# 2026-10-20 修正：此前按 0.2~0.3 倍时长上报（4 分钟歌只报 48-72s），歌曲页 playCount 会涨，
# 但创作者后台「近30日有效计数」一直是 0 —— 这是成员反馈「计数增长、目标任务进度不涨」的直接原因。
# 绝对保底秒数：只用于极短歌（防报出过小的值），实际时长按下面的比例算，
# 且永不报超过歌曲自身时长（报超时长是最典型的机器特征）。
MIN_PLAY_SECONDS = 35
# 播放进度占比区间：过半即可，留少量随机（0.55~0.70）避免恒定比例成为机器特征
PLAY_RATIO_MIN, PLAY_RATIO_MAX = 0.55, 0.70

# 跨群（2026-10-20）：只向对端群拉「歌曲 id 列表」，双方的 KV 账号池、人数、上限完全独立。
# 鉴权复用本群已有的群口令 NB_PASS：对端 worker 的 PEER_PASS 键里存的就是本群口令（管理员写成对穿的），
# 所以不需要新建任何 GitHub Secret。PEER_PASS 环境变量留作以后手工覆盖用。
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PEER_WORKER_URL = os.environ.get("PEER_WORKER_URL", "").strip()
PEER_PASS = os.environ.get("PEER_PASS", "").strip() or os.environ.get("NB_PASS", "").strip()

# ---- D1 每日轮转分配（2026-10-22）----
# 由本群 worker 从 D1 统一计算「本班跑哪些号、每个号听哪 31 首」，替代 GitHub Secrets 分片。
# 每天全池重算：账号池增加/减少、换歌、过期剔除都会自动反映，不需要人工同步分片。
# 任何失败（网络/口令/D1 未绑定）都自动回退到旧的 Secrets 分片，绝不会因为新通道挂掉而停跑。
# 关闭开关：在 run.yml 里把 ASSIGN_ON 设为 0。
ASSIGN_ON = os.environ.get("ASSIGN_ON", "1").strip() not in ("0", "false", "no", "off")
ASSIGN_URL = os.environ.get("ASSIGN_URL", "").strip() or (WORKER_URL.rstrip("/") + "/api/assign")
ASSIGN_PASS = os.environ.get("ASSIGN_PASS", "").strip() or os.environ.get("NB_PASS", "").strip()
# 整轮任务的「日期锚点」：由 plan job 统一算好下发。账号池大到一晚分多波跑时，
# 若各波跨过午夜会算出不同的轮转偏移（有的歌被听两遍、有的没人听），锚定同一个日期就不会。
ASSIGN_DAY = os.environ.get("ASSIGN_DAY", "").strip()

# ---- 进阶控制台每日快照（2026-10-22）----
# 播放时段顺带查一次创作者后台（同 CK 同 IP 同会话，只读，不新增任何独立查询通道），
# 每个分片跑完把本片所有号的指标打包上报到主站 KV（两群统一归口 xx1031.xyz），控制台 /console 聚合展示。
SNAP_URL = os.environ.get("SNAP_URL", "https://xx1031.xyz").strip()
# 2026-10-23：原来靠 "dz." in WORKER_URL 猜池标签，换域名 dingzhi.xx1031.xyz 后会误判成 hz
#（/api/snap 的 pool 归属、控制台两群分栏全错）。定制群固定写死 dz。
POOL_TAG = os.environ.get("POOL_TAG", "dz").strip() or "dz"

_EAPI_KEY = "e82ckenh8dichen8"   # eapi 公开已知密钥
_EAPI_SALT = "36cd479b6b5"       # eapi 固定 salt


def _eapi_gk(key_bytes):
    """eapi 的 key 消化：前 16 字节直接取，后续按位折叠进前 16 字节。"""
    g = bytearray(16)
    g[: min(16, len(key_bytes))] = key_bytes[:16]
    for i in range(16, len(key_bytes)):
        g[i % 16] ^= key_bytes[i]
    return bytes(g)


def eapi_encrypt(path, text):
    msg = f"nobody{path}use{text}md5forencrypt"
    md5 = hashlib.md5(msg.encode("utf-8")).hexdigest()
    data = f"{path}-{_EAPI_SALT}-{text}-{_EAPI_SALT}-{md5}"
    cipher = AES.new(_eapi_gk(_EAPI_KEY.encode("utf-8")), AES.MODE_ECB)
    return {"params": cipher.encrypt(_pad(data).encode("utf-8")).hex().upper()}


def _pad(s):
    pad_len = 16 - len(s) % 16
    return s + chr(pad_len) * pad_len


def _aes_encrypt(text, key):
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, _VI.encode("utf-8"))
    return base64.b64encode(cipher.encrypt(_pad(text).encode("utf-8"))).decode("utf-8")


def weapi_encrypt(data):
    text = json.dumps(data)
    p = _aes_encrypt(text, _NONCE)
    p = _aes_encrypt(p, _SECRETKEY)
    return {"params": p, "encSecKey": _ENCSECKEY}


class Client:
    def __init__(self, cookie, device_id=None):
        self.s = requests.Session()
        self.uid = None
        self.nickname = None
        self.account_name = ""
        if not device_id:
            # 设备身份必须跨次运行稳定：此前用随机串，等于每个号每天换一部新手机，
            # 是风控最容易命中的特征（同账号+同IP+每天新设备）。改为按 cookie 派生、永久不变。
            device_id = "YD-" + hashlib.md5(cookie.encode("utf-8")).hexdigest()[:32]
        enriched = (
            f"{cookie}; deviceId={device_id}; os=pc; appver=2.10.11.200601; "
            f"osver=Microsoft-Windows-10-Professional-build-19045-64bit; channel=netease; MUSIC_A_T=1"
        )
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://music.163.com",
            "Origin": "https://music.163.com",
            "Cookie": enriched,
        })

    def _weapi_post(self, url, data):
        r = self.s.post(url, data=weapi_encrypt(data), timeout=30)
        try:
            return r.json()
        except Exception:
            return {"_raw": r.text[:200], "status_code": r.status_code}

    def login_by_cookie(self, cookie, name=""):
        """三态判定：True=活号 / False=明确失效 / None=网络异常无法判定。
        2026-10-13 修复：此前任何异常都返回 False，一次超时/连接错误就会把活号
        误报成死号并被 Worker 从 KV+Secrets 真删，成员得重新登记。"""
        self.account_name = name
        try:
            info = self._weapi_post(f"{BASE_URL}/weapi/w/nuser/account/get", {})
        except Exception:
            return None
        # _weapi_post 请求层失败时返回无 code 的 dict（含 _raw/status_code）→ 网络问题，不是号的问题
        if "code" not in info:
            return None
        prof = (info.get("profile") or info.get("data", {}).get("profile") or {})
        self.uid = prof.get("userId")
        self.nickname = prof.get("nickname")
        if info.get("code") == 200 and self.uid:
            return True
        # 明确未登录的业务码，直接判死，不必再试
        if info.get("code") in (301, 302):
            return False
        # 受限会话：profile 隐藏但会话可能仍活，用每日推荐二次验证。
        # 注意必须用 api v1 明文接口：weapi v3 对未登录会话也返回歌单（2026-10-11 实测，
        # 匿名/死号 v3 照样有歌 → 无区分度会把死号误判成活号）；v1 实测活号 30+ 首、死号/匿名 0 首。
        try:
            r1 = self.s.get(f"{BASE_URL}/api/v1/discovery/recommend/songs", timeout=20)
            d1 = r1.json()
        except Exception:
            return None  # 二次验证也网络失败，无法判定
        return d1.get("code") == 200 and len((d1.get("data") or {}).get("dailySongs") or []) > 0

    def song_detail(self, ids):
        out = {}
        # 分批，避免单请求过大
        for i in range(0, len(ids), 200):
            batch = ids[i:i + 200]
            try:
                r = self._weapi_post(f"{BASE_URL}/weapi/v3/song/detail", {"c": json.dumps([{"id": x} for x in batch])})
                for t in (r.get("songs") or []):
                    out[str(t.get("id"))] = (t.get("dt") or 0) // 1000
            except Exception:
                pass
            time.sleep(random.uniform(0.5, 1.5))
        return out

    def workbench_info(self):
        """创作者后台只读查询（eapi）：目标任务 rate / rpc30 / 全部子任务进度（含内容任务）。
        返回 {'rate': int|None, 'rpc30': int|None, 'missions': {code: 进度}}，网络/接口失败返回 None。
        2026-10-22 新增：供进阶控制台每日快照，与播放同会话顺带查询。"""
        path = "/api/nmusician/workbench/special/right/vip/info"
        try:
            p = eapi_encrypt(path, "{}")
            r = self.s.post(
                BASE_URL + path.replace("/api/", "/eapi/", 1), data=p, timeout=30
            ).json()
        except Exception:
            return None
        if r.get("code") != 200:
            return None
        d = r.get("data") or {}
        kids = (d.get("furtherTask") or {}).get("children") or []
        missions = {}
        rate = None
        for k in kids:
            code = str(k.get("missionCode") or "")
            pr = k.get("progressRate")
            if not code or pr is None:
                continue
            try:
                pr = int(pr)
            except (TypeError, ValueError):
                continue
            missions[code] = pr
            if code == "mission_code_recently_play_effect_count_v2":
                rate = pr
        return {"rate": rate, "rpc30": d.get("recentPlayCount30"), "missions": missions}

    def playlist_tracks(self, pid, limit=200):
        """公开歌单的前 limit 首歌。返回 [(id, 时长秒)]，失败返回 []。"""
        try:
            r = self._weapi_post(f"{BASE_URL}/weapi/v6/playlist/detail", {"id": pid, "n": limit})
            pl = r.get("playlist") or {}
            ids = [str(t.get("id")) for t in (pl.get("trackIds") or [])[:limit] if t.get("id")]
            if not ids:
                return []
            durs = self.song_detail(ids)
            return [(i, durs.get(i) or 240) for i in ids]
        except Exception:
            return []

    def scrobble(self, tid, t, pid=None, page="playlist"):
        """模拟一次完整播放：startplay → 等够 t 秒 → play(time=t) → playend。

        2026-10-20 修正两处（解决「计数增长、创作者目标任务进度不涨」）：
          ① 此前 startplay 与 play 是同一秒连发的，time 字段却写 48-72 秒，时间戳自相矛盾；
             现在按上报时长真实等待，请求时间与 time 对得上，与真实客户端一致。
          ② 补发 playend：真实播放器播完会发结束事件，此前只发 play，行为链不完整。
        """
        csrf = ""
        try:
            csrf = self.s.headers.get("Cookie", "").split("__csrf=")[-1].split(";")[0].strip()
        except Exception:
            pass
        try:
            start = [{"action": "startplay", "json": {"id": str(tid), "type": "song", "content": f"id={tid}"}}]
            self._weapi_post(f"{BASE_URL}/weapi/feedback/weblog", {"logs": json.dumps(start), "csrf_token": csrf})
            time.sleep(t + random.uniform(1, 3))
            play = [{"action": "play", "json": {
                "download": "0", "end": "playend", "id": str(tid),
                "sourceId": str(pid) if pid else str(tid), "time": str(t),
                "type": "song", "wifi": "0", "resource": f"R_SO_4_{tid}",
                "resourceid": str(tid), "page": page, "is_autoplay": "0",
                "mainsite": "1", "mainsiteWeb": "1", "content": f"id={tid}"}}]
            res = self._weapi_post(f"{BASE_URL}/weapi/feedback/weblog", {"logs": json.dumps(play), "csrf_token": csrf})
            end = [{"action": "playend", "json": {"id": str(tid), "type": "song", "content": f"id={tid}"}}]
            self._weapi_post(f"{BASE_URL}/weapi/feedback/weblog", {"logs": json.dumps(end), "csrf_token": csrf})
            return res.get("code") == 200
        except Exception:
            return False


def load_pool():
    # 2026-10-22：分片改 gzip+base64（worker 端超过 48KB 的 Secret 会被 GitHub 422 拒绝），
    # 按 gzip 魔数 1f8b 自动识别，兼容旧版纯 base64+JSON 格式；槽位扩到 NB_POOL_1..12
    entries = []
    for i in range(1, 13):
        raw = os.environ.get(f"NB_POOL_{i}")
        if not raw:
            continue
        try:
            data = base64.b64decode(raw)
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            chunk = json.loads(data.decode("utf-8"))
            if isinstance(chunk, list):
                entries.extend(chunk)
        except Exception:
            pass
    return entries


def load_assign(ns, slice_idx):
    """向 worker 要「本班跑哪些号、每号听哪几首」（D1 每日轮转分配）。

    返回 [{name, uid, ck, plays:[歌曲id...]}, ...]；任何失败返回 None，
    调用方自动回退到 Secrets 分片，不影响当晚任务。
    """
    if not ASSIGN_ON or not ASSIGN_PASS:
        return None
    try:
        params = {"job": slice_idx, "jobs": ns, "pass": ASSIGN_PASS}
        if ASSIGN_DAY:
            params["day"] = ASSIGN_DAY
        r = requests.get(ASSIGN_URL, params=params,
                         timeout=90, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
        d = r.json()
        if not d.get("ok"):
            print(f"[assign] 服务端返回失败（{d.get('message')}），回退 Secrets 分片")
            return None
        accs = []
        for a in d.get("accounts") or []:
            if not a.get("ck"):
                continue
            accs.append({
                "name": a.get("name") or str(a.get("uid")),
                "uid": a.get("uid"),
                "ck": a.get("ck"),
                # 2026-10-22：服务端已下发 song。/api/assign 以前不带这个字段，导致控制台「时长」
                # 列在 D1 模式下恒空、客户端「绝不听自己」的二次兜底也失效。
                "song": str(a.get("song") or ""),
                "email": a.get("email") or "",
                "plays": [str(s) for s in (a.get("plays") or [])],
            })
        # 只收不听的号（no_listen）：服务端按同一套 i%jobs 分片下发，同样要日常/发内容/
        # 查工作台/验活，只是不参与播放（下面的 my_accounts 会按 noListen 过滤掉）。
        # 2026-10-22 之前它们完全不进 assign，等于在 D1 模式下彻底掉队。
        n_idle = 0
        for a in d.get("idle") or []:
            if not a.get("ck"):
                continue
            n_idle += 1
            accs.append({
                "name": a.get("name") or str(a.get("uid")),
                "uid": a.get("uid"),
                "ck": a.get("ck"),
                "song": str(a.get("song") or ""),
                "email": a.get("email") or "",
                "plays": [],
                "noListen": True,
            })
        print(f"[assign] D1 轮转：全池 {d.get('m')} 号 / {d.get('l')} 首，每号 {d.get('p')} 首，"
              f"本班 {len(accs) - n_idle} 个号 + 只收不听 {n_idle} 个"
              f"（job {slice_idx}/{ns}，来源 {d.get('src') or 'd1'}，服务端 {d.get('ms')}ms）")
        if not accs:
            print("[assign] 本班没有分配到账号，回退 Secrets 分片")
            return None
        return accs
    except Exception as e:
        print(f"[assign] 请求失败（{e}），回退 Secrets 分片")
        return None


def load_peer_songs():
    """拉对端群「可以被听到的歌曲 id」（不含任何账号/cookie 信息）。

    失败/未配置时返回空列表，本群照常跑 —— 跨群是锦上添花，绝不能因为它挂掉整个任务。
    """
    if not PEER_WORKER_URL or not PEER_PASS:
        print("[peer] 未配置跨群互听（缺 PEER_WORKER_URL / PEER_PASS），本次只听本群")
        return []
    try:
        # 必须带浏览器 UA：Cloudflare 的浏览器完整性检查会拦 Python-requests 的默认 UA（403 / error 1010）
        r = requests.get(PEER_WORKER_URL.rstrip("/") + "/api/songs",
                         params={"pass": PEER_PASS}, timeout=45,
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
        d = r.json()
        songs = [str(s) for s in (d.get("songs") or []) if s]
        print(f"[peer] 对端群可听歌曲 {len(songs)} 首（HTTP {r.status_code}）")
        return songs
    except Exception as e:
        print(f"[peer] 拉取对端歌单失败，本次只听本群: {e}")
        return []


def _mail_dead(name, email, sent):
    """播放前验活判定失效时直邮号主（2026-10-23 新增）。

    以前这里只上报 /api/report_dead 把号清出账号池，号主全程收不到任何通知，
    只能自己发现「怎么我的歌没人听了」。signin.py 虽然也会直邮，但它的判定更宽
    （只看 dailyTask，code 200 就认为活着），「code 200 但 profile 缺失、每日推荐 0 首」
    这类掉线号它根本看不出来——而这正是实测中最常见的死号类型。

    未登记邮箱的号直接跳过；发信失败只打印，绝不影响播放主流程。
    sent 里记下真正发出去的号，随后写进 dead_sent.json，供同 job 的 signin.py 去重。
    """
    if not (email or "").strip():
        return
    try:
        import notify
        if not notify.mail_ready():
            return
        if notify.notify_relogin(email, "", name):
            sent.append(str(name))
            print(f"  [{name}] 已直邮号主：账号信息过期")
    except Exception as ex:
        print(f"  [{name}] 直邮号主失败（不影响主流程）: {ex}")


def confirm_dead(ck, name):
    """失效复核（2026-10-23 新增）：单次验活失败不再直接判死。

    调用前提：调用方刚拿到一次明确失效（login_by_cookie 返回 False）。
    这里隔几秒再复查最多 2 次，3 次里至少 2 次明确失效才算确认（再中 1 次即确认）。
    网络异常（None/抛错）不算明确失效 —— 一次抖动不能把活号清出账号池。
    返回 True=确认失效 / False=未确认（按网络异常处理，不上报、不删号、不发邮件）。
    """
    for _ in range(2):
        try:
            time.sleep(random.uniform(4, 8))
            if Client(ck).login_by_cookie(ck, name) is False:
                return True
        except Exception:
            pass
    return False


def main():
    cfg = json.load(open("cfg.json", encoding="utf-8"))
    plays = int(cfg.get("plays_per_account", 28))
    skip_prob = float(cfg.get("skip_prob", 0.08))
    mixed_min = int(cfg.get("mixed_plays_min", 6))
    mixed_max = int(cfg.get("mixed_plays_max", 10))
    ns = max(1, int(os.environ.get("NS", "1")))
    slice_idx = int(os.environ.get("SLICE", "0"))

    # 0) 账号来源：优先向 worker 要 D1 每日轮转分配；失败则回退旧的 Secrets 分片
    entries = load_assign(ns, slice_idx)
    assigned = entries is not None
    if not assigned:
        entries = load_pool()
    if not entries:
        print(f"[slice {slice_idx}] 号池为空，跳过")
        return

    # 1) 校验存活（三态：True=活 / False=明确死 / None=网络异常无法判定）。
    # None 时本次跳过该号：不播放，也绝不上报死号——一次网络抖动不该把活号清理出池（2026-10-13 修复）
    active = []
    dead = 0
    unknown = 0
    dead_names = []
    dead_emails = {}     # name -> email：上报删除成功后按它发「账号信息过期」邮件
    mailed = []          # 本片已经直邮过的失效号，结束时写 dead_sent.json 给 signin.py 去重
    for e in entries:
        c = Client(e.get("ck", ""))
        v = c.login_by_cookie(e.get("ck", ""), e.get("name", "?"))
        if v is True:
            active.append(e)
        elif v is False:
            # 2026-10-23：单次失败不再直接判死，先复核；确认后才进入上报删除名单。
            # 过期邮件也不再在这里发 —— 改到 worker 真正删号成功之后（见第 5 步），
            # 避免「邮件说过期了、号其实还挂在池子里」的乌龙。
            if confirm_dead(e.get("ck", ""), e.get("name", "?")):
                dead += 1
                nm = e.get("name", "")
                dead_names.append(nm)
                dead_emails[nm] = e.get("email", "")
            else:
                unknown += 1
                print(f"  [{e.get('name','?')}] 复核未确认失效，本次跳过（不报失效）")
        else:
            unknown += 1
            print(f"  [{e.get('name','?')}] 网络异常无法判定，本次跳过（不报失效）")
        time.sleep(random.uniform(1, 3))

    # 2) 过滤当天新加入（第 2 天入池）
    # "今天"必须按北京时间算：runner 时区是 UTC，定时任务常被 GitHub 延迟到 UTC 晚间执行
    # （实测延迟 4.5h），此时 UTC 日期比北京晚一天，曾导致全池被误判"当天新号"而白跑（2026-10-11 实锤）
    today = (datetime.utcnow() + timedelta(hours=8)).date().isoformat()
    if not assigned:
        active = [e for e in active if e.get("added", "") < today]
        # 有效期（exp）到期剔除：'YYYY-MM-DD' 过了北京时间当天即不再参与；'forever'/缺省 = 永久
        expired = [e for e in active if e.get("exp") and e.get("exp") != "forever" and str(e["exp"]) < today]
        if expired:
            active = [e for e in active if not (e.get("exp") and e.get("exp") != "forever" and str(e["exp"]) < today)]
            print(f"[slice {slice_idx}] 另有 {len(expired)} 个账号已过有效期（exp），自动剔除")
        print(f"[slice {slice_idx}] 总数 {len(entries)} 存活 {len(active)} 失效 {dead} 网络异常 {unknown} 今日新号剔除后 {len(active)}")
    else:
        print(f"[slice {slice_idx}] D1 分配 {len(entries)} 个号：存活 {len(active)} 失效 {dead} 网络异常 {unknown}"
              f"（新号/过期号已由服务端剔除）")

    n = len(active)
    if n < (1 if assigned else 2):
        print("活跃号不足，无法继续")
        return

    # noListen 号（如群主大号）仍留在 active 里：它的歌继续进别人的跨群歌池、CK 照常验活，
    # 但不分配"去听别人"的播放任务 —— 只收不听。
    if assigned:
        my_accounts = [e for e in active if not e.get("noListen")]
    else:
        my_accounts = [active[i] for i in range(n) if i % ns == slice_idx and not active[i].get("noListen")]
    n_listen = sum(1 for e in active if e.get("noListen"))
    print(f"[slice {slice_idx}] 本片处理 {len(my_accounts)}/{n} 个号 (NS={ns}，其中只收不听 {n_listen} 个不参与播放)")

    # 3) 跨群：拉对端群的歌曲 id（只有 id、不含任何账号信息），与本群歌曲合并成一个歌池。
    #    两个群的 KV 账号池、人数、上限完全独立 —— 这里只共享「听谁的歌」，不合并「谁是谁的号」。
    #    D1 分配模式下，服务端已经把两群的歌一起排进环里，这里直接用分配结果，不再重复拉对端。
    if assigned:
        peer_songs = []
        own_songs = [s for e in active for s in (e.get("plays") or [])]
        song_pool = sorted(set(own_songs))
        print(f"[slice {slice_idx}] 歌池：D1 分配 {len(song_pool)} 首（已含跨群歌曲）")
    else:
        peer_songs = load_peer_songs()
        own_songs = [str(e["song"]) for e in active if e.get("song")]
        song_pool = sorted(set(own_songs) | {s for s in peer_songs if s})
        print(f"[slice {slice_idx}] 歌池：本群 {len(set(own_songs))} 首 + 对端 {len(peer_songs)} 首 → 去重后 {len(song_pool)} 首")

    # 3.1) 预取所有歌时长（换号重试：单个号的会话受限/请求失败就换下一个，不再静默全空）
    # 2026-10-23 修复「控制台时长列一半为空」：D1 分配模式下 song_pool 只含本片「要听的歌」，
    # 而分配规则是绝不听自己 → 本片各号自己登记的那首歌根本不在 song_pool 里；下面第 4.5 步
    # 写 dur 时取的却正是「自己登记的那首」→ 取不到 → 约一半的号时长为空（实测 hz 命中 54%）。
    # 这里单独拼一个查询列表 dur_ids（**不动 song_pool**，避免 idle 号走 cand 随机抽样时
    # 听到的歌集被改变），把本片各号登记的歌一并查出来。每片只多查 5~6 首，成本可忽略。
    dur_ids = list(song_pool)
    if assigned:
        _have = set(dur_ids)
        for e in active:
            s = str(e.get("song") or "")
            if s and s not in _have:
                dur_ids.append(s)
                _have.add(s)
    dur_map = {}
    if dur_ids:
        for e in active:
            try:
                dur_map = Client(e["ck"]).song_detail(dur_ids)
            except Exception:
                dur_map = {}
            if dur_map:
                break

    # 3.5) 预取混听歌池（云音乐热歌榜，全片共享一份；只听歌池以外的歌）
    hot = []
    if mixed_max > 0 and active:
        pool_set = set(song_pool)
        for e in active:
            try:
                hot = [(i, d) for (i, d) in Client(e["ck"]).playlist_tracks(MIX_HOT_PID)
                       if i not in pool_set]
            except Exception:
                hot = []
            if hot:
                break
        print(f"[slice {slice_idx}] 混听歌池（热歌榜，剔除群内歌后）{len(hot)} 首")

    # 3.6) 按「每首歌每天要被多少个不同的人听到」反推每个号该听几首。
    #      目标是 30 天累计 + 按天去重 → 每首歌每天约 22 次就够，留余量取 28。
    #      账号池扩大时这个数不会膨胀（听众和歌曲同步增长），但它防止 cfg 里的值被无脑放大：
    #      plays_per_account 只作为上限，这里只会调小、绝不调大，避免单号时长失控。
    target = int(cfg.get("target_plays_per_song", 0))
    listeners = n + len(set(peer_songs))     # 本群号数 + 对端号数（对端每号一首歌）
    if (not assigned) and target > 0 and song_pool and listeners > 0:
        derived = max(8, math.ceil(target * len(song_pool) / listeners))
        if derived < plays:
            print(f"[slice {slice_idx}] 每号听歌数 {plays} → {derived} 首"
                  f"（{listeners} 个听众共享 {len(song_pool)} 首歌，按每首每天 {target} 次反推）")
            plays = derived

    parallel = max(1, int(os.environ.get("ACCOUNT_PARALLEL", "3")))
    metrics = {}   # uid -> {rate, rpc30, missions}：进阶控制台每日快照（进程内共享，赋值线程安全）
    ran_uids = []  # 本片真正跑到有效播放的号：供 /api/coverage 核对「应跑 vs 实跑」（list.append 原子）
    # 2026-10-23：uid -> 登记歌曲时长(秒)。与 workbench 解耦单独上报 —— 以前 dur 挂在
    # metrics 条目里，工作台接口偶发失败就整条丢，时长跟着一起没了（占「歌在池内」的约 21%）。
    slice_durs = {}

    def process_account(acc):
        """单个账号的完整播放流程（供线程池并行调用，每号一个独立 Client）。"""
        name = acc.get("name", "?")
        mine = str(acc.get("song") or "")
        client = Client(acc["ck"])
        chk = client.login_by_cookie(acc["ck"], name)
        if chk is None:
            print(f"  [{name}] 播放前复验网络异常，跳过（不报失效）")
            return name, 0, [], False
        if chk is False:
            # 2026-10-23：播放前复验失败同样先复核，确认后才按失效处理。
            if confirm_dead(acc["ck"], name):
                print(f"  [{name}] 复核确认失效，跳过")
                return name, 0, [], True
            print(f"  [{name}] 复核未确认失效，跳过（不报失效）")
            return name, 0, [], False

        # 4) 组建播放任务：跨群（pid=歌曲id）与混听（pid=热歌榜）合并后随机穿插执行，
        #    让"听群内歌"和"听群外热歌"混在一起，而不是先刷完跨群再补混听。
        #    候选来自整个歌池（含对端群），但一定剔除自己的歌 —— 绝不听自己。
        cand = [s for s in song_pool if s != mine]
        if acc.get("plays"):
            # D1 分配模式：服务端已算好「这个号今天该听哪几首」（每日轮转、每首歌恰好 p 个听众），
            # 顺序也按 (uid+日期) 打过乱，这里绝不能再随机抽，否则零遗漏的保证会被破坏。
            picks = [s for s in acc["plays"] if s != mine]
        else:
            picks = random.sample(cand, plays) if len(cand) > plays else cand
        tasks = [(sid, dur_map.get(sid) or 240, sid) for sid in picks]
        if hot:
            n_mix = random.randint(mixed_min, mixed_max)
            for sid, dur in random.sample(hot, min(len(hot), n_mix)):
                tasks.append((sid, dur or 240, MIX_HOT_PID))
        random.shuffle(tasks)

        cnt, secs = 0, []
        for sid, dur, pid in tasks:
            if random.random() < skip_prob:
                continue  # 模拟切歌（切歌即不计有效播放，和真实用户行为一致）
            # 播放进度取整首的 55%~70%：必须越过「听过半才计有效计数」的门槛，
            # 否则 playCount 会涨、创作者后台的有效计数一直是 0。短歌不能报超过自身时长。
            base = dur if dur and dur > 30 else 240
            t = int(base * random.uniform(PLAY_RATIO_MIN, PLAY_RATIO_MAX))
            t = min(t, base - 3)                              # 绝不报超过歌曲自身时长
            t = max(t, min(MIN_PLAY_SECONDS, base - 3))       # 保底 35s，短歌以歌长为界
            if client.scrobble(sid, t, pid=pid, page="playlist"):
                cnt += 1
                secs.append(t)
            time.sleep(random.uniform(1, 3))
        print(f"  [{name}] 完成 {cnt} 次播放" + (f"，平均 {sum(secs)//len(secs)}s/首" if secs else ""))
        if cnt:
            ran_uids.append(str(acc.get("uid") or name))
        # 登记歌曲时长先单独记一份：workbench 查询失败不该把「时长」也一起丢掉
        # （2026-10-23 修复，走 /api/snap 的 durs 通道，与快照行无关）
        my_dur = dur_map.get(str(acc.get("song") or "")) or None
        if my_dur:
            slice_durs[str(acc.get("uid") or name)] = my_dur
        # 4.5) 顺带查一次创作者后台（同 CK 同 IP，只读），失败不影响播放结果
        try:
            wb = client.workbench_info()
            if wb is not None:
                m = dict(wb)
                m["dur"] = my_dur  # 登记歌曲时长(秒)，进控制台「时长」列
                metrics[str(acc.get("uid") or name)] = m
        except Exception:
            pass
        return name, cnt, secs, False

    email_of = {a.get("name", "?"): a.get("email", "") for a in my_accounts}
    done = 0
    reported_secs = []   # 记录实际上报时长，日志里能一眼看出新规则（过半）是否生效
    if my_accounts:
        # 并行处理本片账号：单号绝大部分时间在 sleep 等播放时长，并行不占 CPU。
        # 这是「播放时长提到过半」之后仍能在 6h job 上限内跑完的关键。
        with ThreadPoolExecutor(max_workers=min(parallel, len(my_accounts))) as ex:
            futs = [ex.submit(process_account, acc) for acc in my_accounts]
            for f in as_completed(futs):
                try:
                    name, cnt, secs, is_dead = f.result()
                except Exception as e:
                    print(f"  [线程异常] {e}")
                    continue
                done += cnt
                reported_secs.extend(secs)
                if is_dead:
                    dead_names.append(name)
                    dead_emails[name] = email_of.get(name, "")

    avg = f"，平均上报 {sum(reported_secs)//len(reported_secs)} 秒/首（过半口径）" if reported_secs else ""
    print(f"[slice {slice_idx}] 完成，本次有效上报约 {done} 次{avg}")

    # 4.6) 本片「只收不听」的号：验活 + 查一次工作台（它们的歌进别人的歌池，指标同样要进控制台）。
    #      D1 模式下服务端已按 i%jobs 把它们分到各片，直接取 active 里的 noListen 项；
    #      回退模式沿用老口径（按下标切片）。2026-10-22 起这里也做失效判定 ——
    #      以前这些号既不验活也不上报死号，等于在 D1 模式下彻底掉队。
    if assigned:
        idle_accs = [e for e in active if e.get("noListen")]
    else:
        idle_accs = [active[i] for i in range(n) if i % ns == slice_idx and active[i].get("noListen")]
    for acc in idle_accs:
        try:
            c2 = Client(acc["ck"])
            v = c2.login_by_cookie(acc["ck"], acc.get("name", "?"))
            if v is False:
                # 2026-10-23：只收不听号同样先复核再判死。
                if confirm_dead(acc["ck"], acc.get("name", "?")):
                    print(f"  [{acc.get('name','?')}] 只收不听号复核确认失效")
                    dead_names.append(acc.get("name", ""))
                    dead_emails[acc.get("name", "")] = acc.get("email", "")
                else:
                    print(f"  [{acc.get('name','?')}] 只收不听号复核未确认失效，跳过")
                time.sleep(random.uniform(1, 2))
                continue
            if v is None:
                time.sleep(random.uniform(1, 2))
                continue
            my_dur = dur_map.get(str(acc.get("song") or "")) or None
            if my_dur:
                slice_durs[str(acc.get("uid") or acc.get("name", "?"))] = my_dur
            wb = c2.workbench_info()
            if wb is not None:
                m = dict(wb)
                m["dur"] = my_dur
                metrics[str(acc.get("uid") or acc.get("name", "?"))] = m
        except Exception:
            pass
        time.sleep(random.uniform(1, 2))

    # 5) 把确认失效的账号上报给 Worker（2026-10-23 改版：客户端已复核 ≥2 次明确失效，
    #    带 confirm=true 让服务端立即删号；删号成功后再给号主发「账号信息过期」邮件）。
    #    只有 worker 返回「真删掉了」的号才发邮件，避免「邮件说已删除、号其实还在池里」。
    dead_names = sorted({x for x in dead_names if x})
    if dead_names:
        deleted = []
        try:
            r = requests.post(WORKER_URL + "/api/report_dead", json={
                "pass": os.environ.get("NB_PASS", ""),
                "dead": dead_names,
                "confirm": True,
            }, timeout=30)
            print(f"[slice {slice_idx}] 失效账号清理上报 {len(dead_names)} 个: HTTP {r.status_code} {r.text[:120]}")
            try:
                deleted = [str(x) for x in ((r.json() or {}).get("deleted") or [])]
            except Exception:
                deleted = []
        except Exception as e:
            print(f"[slice {slice_idx}] 失效账号清理上报失败(不影响任务): {e}")
        for nm in deleted:
            _mail_dead(nm, dead_emails.get(nm, ""), mailed)

    # 5.1) 把已直邮名单落盘（同 job 的 signin.py 会读它跳过重复发信）。
    #      以前在验活循环后就写，现在邮件挪到删号成功之后 → 落盘也跟着挪到这里。
    #      写空文件也要写：万一 signin 的失效判定和这里不一致，读到旧内容会漏发。
    try:
        with open("dead_sent.json", "w", encoding="utf-8") as f:
            json.dump(sorted(set(mailed)), f, ensure_ascii=False)
    except Exception as _e:
        print(f"  失效直邮名单落盘失败（不影响主流程）: {_e}")

    # 6) 每日快照上报（进阶控制台用；失败不影响主任务）
    #    date 一律带整轮锚点 ASSIGN_DAY：一轮要跑十几个小时，跨过午夜后若按写入时刻取日期，
    #    同一轮的前半段会记在 D 日、后半段记在 D+1 日，控制台日环比与覆盖率核对全部错位。
    #    ran = 本片真正跑到有效计数的号，供 /api/coverage 核对「应跑 vs 实跑」。
    snap_day = ASSIGN_DAY if ASSIGN_DAY else today
    if metrics or ran_uids or slice_durs:
        try:
            r = requests.post(SNAP_URL.rstrip("/") + "/api/snap", json={
                "pass": os.environ.get("NB_PASS", ""),
                "pool": POOL_TAG,
                "slice": slice_idx,
                "date": snap_day,
                "accs": metrics,
                "ran": ran_uids,
                "durs": slice_durs,
            }, timeout=30)
            print(f"[slice {slice_idx}] 每日快照上报 {len(metrics)} 个号 / 实跑 {len(ran_uids)} 个"
                  f" / 时长 {len(slice_durs)} 个（锚点 {snap_day}）: HTTP {r.status_code} {r.text[:100]}")
        except Exception as e:
            print(f"[slice {slice_idx}] 每日快照上报失败(不影响任务): {e}")

    # 7) 失败可见性（2026-10-22）：以前本文件全程没有 sys.exit(1)，整片播放全挂、job 也是绿的，
    #    于是「应跑 1500 号、实际只跑了 900」这种事永远发现不了。这里只在「整片基本没跑成」时
    #    标红让 guard 补跑该片：平均每号不到 3 次有效计数才算失败（正常每号 28~32 次），
    #    所以不会因为个别号被跳过就重复播一遍。
    if my_accounts and done < len(my_accounts) * 3:
        print(f"[slice {slice_idx}] ⚠️ 有效播放仅 {done} 次（{len(my_accounts)} 个号，"
              f"预期约 {len(my_accounts) * 25}+），判定本片失败，交由 guard 补跑")
        sys.exit(1)


if __name__ == "__main__":
    main()
