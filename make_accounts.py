# -*- coding: utf-8 -*-
"""为本片生成 accounts.json（signin.py / notes.py 消费）。

账号来源（2026-10-22 起改为 D1 优先）：
  1. 首选：向 worker 的 /api/assign 要「本片该跑哪些号」（D1 每日轮转分配，与 run.py 同源）。
     - 号线与播放线天然一致（此前播放按 run.py 一套分片、日常按本文件另一套分片，两套规则
       各自算一遍，容易出现"号播了但没日常 / 日常了但没播"）。
     - 容量交给 D1（1800+ 号），不再受 GitHub Secrets 12 槽 ≈550 号 + 每次登记 12 次加密
       PUT 的限制。
  2. 回退：/api/assign 不可用（D1 未绑定 / 口令错 / 网络异常 / 返回空）时，退回读 Secrets
     分片 NB_POOL_1..12（gzip+base64，兼容旧纯 JSON），行为与旧版完全一致，不影响当晚任务。

切片口径与 run.py 一致：先过滤"当天新加入"的号（次日入池），再按 i % NS 分片；
每个号只会被一个片处理，日常/内容全局恰好执行一次，不会重复。

角色：signin（每日日常+云贝+云豆） + notes（每 6 天发一条内容）。
"""
import base64
import gzip
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

WORKER_URL = (os.environ.get("WORKER_URL") or "https://dingzhi.xx1031.xyz").rstrip("/")
ASSIGN_ON = (os.environ.get("ASSIGN_ON", "1").strip().lower() not in ("0", "false", "no", ""))
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


# ---- 复用 run.py 的分配结果（2026-10-29）----
# 播放已经向 /api/assign 要过一批号并写在 assign_cache.json；这里优先直接读，
# 不再二次请求。只有缓存缺失/跨天/分片对不上时才走网络（行为与旧版完全一致）。
ASSIGN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assign_cache.json")


def load_cached_assign(ns, slice_idx):
    """读 run.py 落地的分配结果；不适用返回 None。"""
    try:
        if not os.path.exists(ASSIGN_CACHE_FILE):
            return None
        with open(ASSIGN_CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        day = (os.environ.get("ASSIGN_DAY") or "").strip()
        cached_day = str(d.get("day") or "")
        if day and cached_day and cached_day != day:
            print(f"[assign] 缓存日期 {cached_day} 与本轮 {day} 不符，忽略缓存")
            return None
        try:
            if int(d.get("ns") or 0) != int(ns) or int(d.get("slice", -1)) != int(slice_idx):
                print(f"[assign] 缓存分片 {d.get('slice')}/{d.get('ns')} 与本班 {slice_idx}/{ns} 不符，忽略缓存")
                return None
        except Exception:
            return None
        accs = [a for a in (d.get("accounts") or []) if (a.get("ck") or "").strip()]
        if not accs:
            return None
        return accs
    except Exception as e:
        print(f"[assign] 读缓存失败（回退网络请求）: {e}")
        return None


def load_assign(ns, slice_idx):
    """问 worker 要本片账号（D1 轮转）。任何异常返回 None，调用方回退 Secrets。"""
    if not ASSIGN_ON:
        return None

    cached = load_cached_assign(ns, slice_idx)
    if cached:
        print(f"[assign] 复用 run.py 本班的分配结果：{len(cached)} 个号"
              f"（job {slice_idx}/{ns}，不再二次请求）")
        return cached
    pw = (os.environ.get("ASSIGN_PASS") or os.environ.get("NB_PASS") or "").strip()
    if not pw:
        print("[assign] 缺口令（NB_PASS），签到/笔记账号回退 Secrets 分片")
        return None
    try:
        params = {"job": slice_idx, "jobs": ns, "pass": pw}
        day = (os.environ.get("ASSIGN_DAY") or "").strip()
        if day:
            params["day"] = day
        url = WORKER_URL + "/api/assign?" + urllib.parse.urlencode(params)
        # 必须带浏览器 UA：Cloudflare 浏览器完整性检查会拦 python-urllib 默认 UA（403 / 1010）
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8"))
        if not d.get("ok"):
            print(f"[assign] 服务端返回失败（{d.get('message')}），签到/笔记账号回退 Secrets 分片")
            return None
        accs = [a for a in (d.get("accounts") or []) if (a.get("ck") or "").strip()]
        # 只收不听的号（no_listen）同样是本片要日常的成员：服务端按 i%jobs 分到各片，
        # 以前完全不进 assign → 在 D1 模式下既不日常也不发内容。
        n_idle = len([a for a in (d.get("idle") or []) if (a.get("ck") or "").strip()])
        accs += [a for a in (d.get("idle") or []) if (a.get("ck") or "").strip()]
        if not accs:
            print("[assign] 本片没分配到账号，签到/笔记账号回退 Secrets 分片")
            return None
        print(f"[assign] 签到/笔记用 D1 分配：全池 {d.get('m')} 号 / {d.get('l')} 首，"
              f"本片 {len(accs) - n_idle} 个号 + 只收不听 {n_idle} 个（job {slice_idx}/{ns}）")
        return accs
    except Exception as e:
        print(f"[assign] 请求失败（{e}），签到/笔记账号回退 Secrets 分片")
        return None


def load_pool():
    """回退路径：读 Secrets 分片 NB_POOL_1..12（gzip+base64，兼容旧纯 JSON 分片）。"""
    entries = []
    for i in range(1, 13):
        raw = os.environ.get(f"NB_POOL_{i}")
        if not raw:
            continue
        try:
            data = base64.b64decode(raw)
            if data[:2] == bytes([0x1f, 0x8b]):
                data = gzip.decompress(data)
            chunk = json.loads(data.decode("utf-8"))
            if isinstance(chunk, list):
                entries.extend(chunk)
        except Exception:
            pass
    return entries


def _account(name, cookie, email):
    return {
        "name": name or "unknown",
        "cookie": cookie,
        "email": email or "",          # 2026-10-17：号主邮箱，账号不能正常刷播放时直邮提醒本人
        "roles": "signin,notes",
        "is_musician": True,           # 互助群成员均为音乐人账号；非音乐人会被接口自动跳过
        "enabled": True,
    }


def main():
    ns = max(1, int(os.environ.get("NS", "1") or 1))
    slice_idx = int(os.environ.get("SLICE", "0") or 0)

    accounts = []
    source = ""

    assigned = load_assign(ns, slice_idx)
    if assigned:
        source = "D1"
        for a in assigned:
            accounts.append(_account(a.get("name") or str(a.get("uid") or ""),
                                     (a.get("ck") or "").strip(),
                                     (a.get("email") or "").strip()))
    else:
        source = "Secrets"
        entries = load_pool()
        pool_total = len(entries)
        # 与 run.py 完全一致的口径：北京时间"今天"之前加入的号才参与（次日入池）
        today = (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()
        entries = [e for e in entries if e.get("added", "") < today]
        mine = [e for i, e in enumerate(entries) if i % ns == slice_idx]
        for e in mine:
            cookie = (e.get("ck") or "").strip()
            if not cookie:
                continue
            accounts.append(_account(e.get("name", "unknown"), cookie, e.get("email", "")))
        print(f"[slice {slice_idx}] 号池总数 {pool_total}, 入池 {len(entries)}, NS={ns}")

    with open("accounts.json", "w", encoding="utf-8") as f:
        json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=2)

    print(f"[slice {slice_idx}] 本片签到/笔记账号 {len(accounts)} 个（来源 {source}, NS={ns}）")


if __name__ == "__main__":
    main()
