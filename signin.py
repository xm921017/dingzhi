# -*- coding: utf-8 -*-
"""
平台日常任务工具

日常项目：
1. 云贝中心签到 (pointmall/user/sign) — 云贝签到，每天 +50 云贝
2. 云贝到账确认 (store/api/point/receipt) — 账单核对当日"签到奖励"
3. 每日日常 (point/dailyTask type=1) — 网页端日常 +2 积分
4. 云贝任务领取 (usertool/task/todo/query + task/point/receive) — 领取已完成任务奖励
5. 黑胶乐签 (eapi/vip-center-bff/task/sign) — 黑胶VIP每日乐签，每天 +3 成长值
6. VIP成长值领取 (weapi/vipnewcenter/app/level/task/reward/getall) — 领取待领成长值
7. 创作者云豆日常 (nmusician/workbench/mission/cycle/list + reward/obtain/new) — 领取云豆

关键技术点：
- weapi 加密：每次请求随机生成 encSecKey（标准方式）
- 云贝签到：pointmall/user/sign，请求体为空，data.sign=true 表示本次签到成功
  （data.yunbeiNum 为本次到账云贝），false 表示今天已签过（幂等，可安全重复调用）。
  2026-10-27 大号实测：签到后账单立即出现 {pointCost:50, fixed:"签到奖励"}。
- 云贝签到状态判据：point/today/get 的 shells 和 signin/v2/progress 的 todaySignedIn
  在云贝已签到后仍然是 0 / False，不能用来判断；只有 store/api/point/receipt 账单可信。
- 历史勘误：原 yunbei_sign() 走 point/dailyTask type=0（返回"功能暂不支持"），那是已下线
  的老积分签到接口，与云贝无关，已废弃。
- 黑胶乐签：只有 eapi 有签到动作，weapi 无对应版本。eapi 加密为 AES-128-ECB(key=
  e82ckenh8dichen8)，明文格式 "URL-36cd479b6b5-JSON-36cd479b6b5-MD5"，其中 URL 必须是
  把路径里第一个 eapi 换成 api 之后的 **URI 路径**（不是完整 URL），否则返回"接口未找到"。
- 黑胶乐签判据：签到接口即使今天已签也返回 data=true，不能当"本次新签"判据。
  必须先查 sign/info 的 today，只有 false 才签，签后再查是否变 true。
- eapi 请求要求：payload 含 deviceId/os/e_r/header，头带 x-mam-custommark=okhttp、
  x-aeapi、cm_no_encrypt_native_tag_20220105=false，UA 必须是安卓客户端 UA。
- 2026-10-27 大号实测：成长值 13847 → 13873（签到 +3、领奖 +23），重复签到不重复加分。
- csrf_token：每次请求从 cookie 提取 __csrf 注入；云贝相关接口不加 csrf 也能通过
- 创作者：status=20(可领取) 和 status=100(已完成)，通过 reward/obtain 领取云豆
- signed 字段：cloudbean/get 的 signed 始终为 False，不代表日常状态


多账号支持：通过 accounts.json 的 roles: signin 控制
"""

import json
import random
import hashlib
import sys
import time
import os
import string
import logging
import traceback
import base64
import binascii
import gzip

import requests
from Crypto.Cipher import AES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("netease-signin")

BASE_URL = "https://music.163.com"

# ========== weapi 加密（标准方式，每次随机 encSecKey）==========
_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7"
    "b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280"
    "104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932"
    "575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b"
    "3ece0462db0a22b8e7"
)
_PUBKEY = "010001"
_NONCE = b"0CoJUm6Qyw8W8jud"
_VI = b"0102030405060708"


def _create_key(size=16):
    return binascii.hexlify(os.urandom(size))[:16]


def _aes_cbc(text_bytes, key):
    pad = 16 - len(text_bytes) % 16
    text_bytes = text_bytes + bytearray([pad] * pad)
    encryptor = AES.new(key, AES.MODE_CBC, _VI)
    return encryptor.encrypt(text_bytes)


def _rsa_encrypt(text, pubkey, modulus):
    text = text[::-1]
    rs = pow(int(binascii.hexlify(text), 16), int(pubkey, 16), int(modulus, 16))
    return format(rs, "x").zfill(256)


def weapi_encrypt(data):
    """标准 weapi 加密，每次随机生成 encSecKey"""
    text = json.dumps(data).encode("utf-8")
    secret = _create_key(16)
    params = base64.b64encode(_aes_cbc(base64.b64encode(_aes_cbc(text, _NONCE)), secret))
    encseckey = _rsa_encrypt(secret, _PUBKEY, _MODULUS)
    return {"params": params.decode("utf-8"), "encSecKey": encseckey}


# ========== eapi 加密（黑胶乐签必须用 eapi，weapi 无签到动作）==========
# 算法来源：chaunsin/netease-cloud-music pkg/crypto/crypto.go:387-404
#   明文 = URL + "-36cd479b6b5-" + JSON + "-36cd479b6b5-" + MD5("nobody"+URL+"use"+JSON+"md5forencrypt")
#   AES-128-ECB(key="e82ckenh8dichen8") + PKCS7，输出大写 HEX
_EAPI_KEY = b"e82ckenh8dichen8"
_EAPI_SEP = "-36cd479b6b5-"
_EAPI_SALT = "nobody%suse%smd5forencrypt"
# 安卓客户端 UA 必须与 appver/buildver 一致，否则服务端按非官方客户端处理
_ANDROID_UA = ("NeteaseMusic/9.2.85.250418145357(9002085);"
               "Dalvik/2.1.0 (Linux; U; Android 9; SM-S9180 Build/PQ3B.190801.10101846)")


def eapi_encrypt(path, data):
    """path 传 URI 路径（如 /eapi/vip-center-bff/task/sign）。

    注意：摘要里的 URL 是把路径中第一个 eapi 替换成 api 后的结果，
    传完整 URL 会导致服务端返回 code=404「接口未找到！」。

    与 run.py 里的同名函数算法完全等价（已用相同输入对拍验证）；
    区别只在签名：run.py 收「/api/ 路径 + 已序列化文本」，本函数收「/eapi/ 路径 + dict」
    并自行完成 eapi→api 替换与序列化，便于 signin 侧直接传业务字典。
    """
    url = path.replace("eapi", "api", 1)
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.md5((_EAPI_SALT % (url, text)).encode("utf-8")).hexdigest()
    plain = url + _EAPI_SEP + text + _EAPI_SEP + digest
    raw = plain.encode("utf-8")
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad
    ct = AES.new(_EAPI_KEY, AES.MODE_ECB).encrypt(raw)
    return binascii.hexlify(ct).decode("ascii").upper()


def eapi_decrypt(cipher_bytes):
    """响应为二进制 AES-ECB 密文；解密后通常是 gzip 压缩的 JSON。"""
    try:
        pt = AES.new(_EAPI_KEY, AES.MODE_ECB).decrypt(cipher_bytes)
        if pt:
            pad = pt[-1]
            if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
                pt = pt[:-pad]
        try:
            pt = gzip.decompress(pt)
        except Exception:
            pass
        return json.loads(pt.decode("utf-8", "replace"))
    except Exception as e:
        return {"code": -1, "message": f"eapi 响应解密失败: {str(e)[:80]}"}


def load_config(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# 2026-10-23：删除了 send_email()/notify_fail() 两个群主告警函数（及 5 处调用）。
# 它们读的是 cfg.json 的 email_config 段，而两个仓库的 cfg.json 里根本没有这一节 →
# enabled 恒为 False，函数一进来就 return，从来没有真正发出过一封邮件，属于死代码。
# 号主本人的提醒统一走 notify.py（凭据从 Secrets 注入，不依赖 cfg.json）；
# 程序级故障由 GitHub Actions 自身标红 + 仓库 owner 通知负责，不再重复告警。
def _already_mailed():
    """run.py 在本片播放前验活时已经把失效号直邮过了，名单落在 dead_sent.json。

    同一个 job 的 workspace 复用，所以这里能读到；读不到（文件不存在/损坏）就当空集，
    退回「每个失效号都发」，宁可多发也不漏发。
    """
    try:
        with open("dead_sent.json", "r", encoding="utf-8") as f:
            return {str(x) for x in (json.load(f) or [])}
    except Exception:
        return set()


class NeteaseClient:
    def __init__(self, cookie, device_id=None):
        self.s = requests.Session()
        self.uid = None
        self.nickname = None
        self.cookie_str = cookie
        # eapi 会话（安卓身份）懒加载：与 weapi 的桌面身份隔离，避免同一 session
        # 里 os=pc / os=android 互相覆盖
        self._eapi_s = None
        # eapi 的 deviceId 必须是 52 位大写 HEX（与安卓客户端生成格式一致），
        # 用 cookie 派生保证同一账号每天稳定（换设备是风控最容易命中的特征）
        self.eapi_device_id = hashlib.sha256(cookie.encode("utf-8")).hexdigest().upper()[:52]

        if not device_id:
            # 2026-10-22：设备身份必须与 run.py 一致。run.py 特意用 md5(cookie) 派生永久稳定的
            # deviceId（注释原话：每天换新手机是风控最容易命中的特征），而本文件原来每次随机 →
            # 同一账号同一天既像"桌面稳定设备"又像"新设备"。改为同一套派生规则。
            device_id = "YD-" + hashlib.md5(cookie.encode("utf-8")).hexdigest()[:32]

        # 解析原始 cookie 并注入到 session cookies 中
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.s.cookies.set(k.strip(), v.strip(), domain="music.163.com", path="/")

        # 注入设备指纹 cookie（日常必须）
        self.s.cookies.set("__remember_me", "true", domain="music.163.com", path="/")
        self.s.cookies.set("deviceId", device_id, domain="music.163.com", path="/")
        self.s.cookies.set("os", "pc", domain="music.163.com", path="/")
        self.s.cookies.set("appver", "2.10.11.200601", domain="music.163.com", path="/")
        self.s.cookies.set("osver",
            "Microsoft-Windows-10-Professional-build-19045-64bit",
            domain="music.163.com", path="/")
        self.s.cookies.set("channel", "netease", domain="music.163.com", path="/")
        self.s.cookies.set("MUSIC_A_T", "1", domain="music.163.com", path="/")

        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://music.163.com",
            "Origin": "https://music.163.com",
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def _get_csrf(self):
        return self.s.cookies.get("__csrf", "")

    def weapi_post(self, path, data=None, with_csrf=True):
        if data is None:
            data = {}
        if with_csrf:
            data["csrf_token"] = self._get_csrf()
        enc = weapi_encrypt(data)
        # 部分 VIP 接口挂在 interface3.music.163.com，允许直接传完整 URL
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        try:
            r = self.s.post(url, data=enc, timeout=30)
            return r.json()
        except Exception as e:
            # 网络/HTTP 异常不再炸穿整个日常循环（2026-10-13 修复：此前 raise_for_status
            # 会让单次 5xx/超时直接抛到 main，导致该片后续所有账号当天不日常）。
            # 统一降级为 code=-1，由调用方按账号粒度处理。
            logger.warning(f"请求失败 {path}: {str(e)[:120]}")
            return {"code": -1, "message": f"请求失败: {str(e)[:120]}"}

    def _eapi_session(self):
        """独立的安卓身份会话。eapi 要求 UA 与 os/appver/buildver cookie 一致。"""
        if self._eapi_s is not None:
            return self._eapi_s
        s = requests.Session()
        s.trust_env = False
        for part in self.cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                s.cookies.set(k.strip(), v.strip(), domain="music.163.com", path="/")
        for k, v in (
            ("__remember_me", "true"),
            ("os", "android"),
            ("appver", "9.2.85"),
            ("osver", "9"),
            ("channel", "xiaomi"),
            ("mobilename", "SM-S9180"),
            ("buildver", "9002085"),
            ("deviceId", self.eapi_device_id),
            ("sDeviceId", self.eapi_device_id),
        ):
            s.cookies.set(k, v, domain="music.163.com", path="/")
        self._eapi_s = s
        return s

    def eapi_post(self, url, data=None, encrypted_resp=True):
        """eapi 请求。url 传完整地址。

        payload 必须含 deviceId/os/e_r/header；e_r=True 时响应是 AES-ECB + gzip。
        """
        from urllib.parse import urlparse
        payload = {
            "deviceId": self.eapi_device_id,
            "os": "android",
            "e_r": bool(encrypted_resp),
            "header": "{}",
        }
        if data:
            payload.update(data)
        params = eapi_encrypt(urlparse(url).path, payload)
        headers = {
            "User-Agent": _ANDROID_UA,
            "Referer": "https://music.163.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Accept-language": "zh-CN,zh-Hans;q=0.9",
            # 下面三个头缺一个都会被判非官方客户端（源码 api/api.go:490-492）
            "x-mam-custommark": "okhttp",
            "cm_no_encrypt_native_tag_20220105": "false",
            "x-aeapi": "true" if encrypted_resp else "false",
        }
        try:
            r = self._eapi_session().post(url, data={"params": params},
                                          headers=headers, timeout=30)
            if encrypted_resp:
                return eapi_decrypt(r.content)
            return r.json()
        except Exception as e:
            logger.warning(f"eapi 请求失败 {url}: {str(e)[:120]}")
            return {"code": -1, "message": f"请求失败: {str(e)[:120]}"}

    def login_check(self, name):
        """验证 cookie 是否有效。返回三态：True=有效 / False=明确失效 / None=网络异常无法判定。"""
        body = self.weapi_post("/weapi/point/dailyTask", {"type": 1})
        code = body.get("code", -1)
        if code == -2:
            logger.info(f"[{name}] Cookie 有效（今日已签到）")
            return True
        if code == 200:
            logger.info(f"[{name}] Cookie 有效，签到接口正常")
            return True
        # 备用验证
        body2 = self.weapi_post("/weapi/act/modules/signin/v2/progress",
                                {"moduleId": "1207signin-1207signin"})
        if body2.get("code") == 200:
            logger.info(f"[{name}] Cookie 有效（云贝进度查询成功）")
            return True
        # 两次请求都 code=-1 = 请求层失败（网络/HTTP 错误），不是 cookie 本身的问题，
        # 返回 None 让主程序跳过本次而非误判过期（2026-10-13 修复）
        if code == -1 and body2.get("code", -1) == -1:
            logger.warning(f"[{name}] 网络异常，无法判定 cookie 状态（明天重试）")
            return None
        logger.error(f"[{name}] Cookie 无效或已过期: code={code}")
        return False

    def daily_sign(self, name):
        """
        每日日常：/weapi/point/dailyTask type=1
        type=0 返回"功能暂不支持"，type=1 才是正确的日常接口
        返回 code=-2 表示"重复日常"（今天已签过）
        """
        body = self.weapi_post("/weapi/point/dailyTask", {"type": 1})
        code = body.get("code", -1)
        msg = body.get("msg", body.get("message", ""))

        if code == 200:
            point = body.get("point", "")
            return True, f"每日签到成功 (+{point}积分)" if point else "每日签到成功"
        elif code == -2:
            return True, "今日已签到（重复签到）"
        else:
            return False, f"每日签到失败: code={code} msg={msg}"

    def yunbei_sign(self, name):
        """
        云贝中心每日签到：/weapi/pointmall/user/sign
        请求体为空，不需要 csrf。

        返回 data.sign：
          true  = 本次签到成功，data.yunbeiNum 为本次到账云贝（通常 50）
          false = 今天已签过（幂等，重复调用安全，不会报错）

        2026-10-27 修正：原实现走 /weapi/point/dailyTask type=0，返回"功能暂不支持"——
        那是已下线的老积分签到接口，和云贝签到毫无关系。真正的云贝签到是 pointmall/user/sign。
        """
        body = self.weapi_post("/weapi/pointmall/user/sign", {}, with_csrf=False)
        code = body.get("code", -1)
        msg = body.get("msg", body.get("message", ""))
        if code != 200:
            return False, f"云贝签到失败: code={code} msg={msg}"

        data = body.get("data") or {}
        if data.get("sign"):
            num = data.get("yunbeiNum", 0)
            return True, f"云贝签到成功 (+{num}云贝)" if num else "云贝签到成功"
        return True, "云贝今日已签到"

    def yunbei_sign_confirm(self, name):
        """
        云贝签到到账确认：查 /store/api/point/receipt 账单

        2026-10-27 实测：point/today/get 的 shells 和 signin/v2/progress 的 todaySignedIn
        在云贝已签到后仍然是 0 / False，都不能当判据，只有账单是准的。
        返回 (signed, status, details)，与 main() 的解包方式保持一致。
        """
        body = self.weapi_post("/store/api/point/receipt", {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return False, f"云贝账单查询失败: code={code}", []

        today = time.strftime("%Y-%m-%d")
        total = 0
        details = []
        for item in body.get("data") or []:
            if (item.get("date") or "") != today:
                continue
            fixed = item.get("fixed") or ""
            if "签到" not in fixed:
                continue
            try:
                amount = int(item.get("pointCost", 0))
            except (TypeError, ValueError):
                amount = 0
            total += amount
            details.append(f"{fixed} +{amount}云贝")

        if total > 0:
            return True, f"云贝签到确认: 今日累计 +{total}云贝", details
        return False, "云贝签到确认: 今日账单无签到记录", details

    def yunbei_task_claim(self, name):
        """
        领取云贝任务奖励
        优先查 todo 列表（已完成待领取），再兜底查全量列表
        """
        claimed = []

        # 方式1：查询 todo 列表（已完成待领取的任务）
        body = self.weapi_post("/weapi/usertool/task/todo/query")
        if body.get("code") == 200:
            for task in body.get("data", []):
                if task.get("userTaskId", 0) > 0:
                    task_name = task.get("taskName", "未知任务")
                    tid = task["userTaskId"]
                    deposit = task.get("depositCode", 0)
                    r = self.weapi_post("/weapi/usertool/task/point/receive",
                                        {"userTaskId": tid, "depositCode": deposit})
                    if r.get("code") == 200:
                        point = task.get("taskPoint", 0)
                        claimed.append(f"{task_name}(+{point}云贝)")
                        logger.info(f"[{name}] 云贝任务已领取: {task_name} +{point}云贝")
                    time.sleep(random.uniform(0.5, 1.5))

        # 方式2：兜底查全量任务列表
        if not claimed:
            body2 = self.weapi_post("/weapi/usertool/task/list/all")
            if body2.get("code") == 200:
                for t in body2.get("data", []):
                    if t.get("status") == 100 and t.get("userTaskId", 0) > 0:
                        task_name = t.get("name", t.get("taskName", "未知"))
                        tid = t["userTaskId"]
                        r = self.weapi_post("/weapi/usertool/task/point/receive",
                                            {"userTaskId": tid, "depositCode": 0})
                        if r.get("code") == 200:
                            claimed.append(task_name)
                            logger.info(f"[{name}] 云贝任务奖励已领取: {task_name}")
                        time.sleep(random.uniform(0.5, 1.5))

        return claimed

    def vip_sign_status(self, name):
        """
        黑胶乐签状态：/weapi/vipnewcenter/app/user/sign/info
        返回 (today_signed, score, msg)；today_signed=None 表示查询失败（无法判定）。

        2026-10-27 实测：签到接口即使今天已签也返回 data=true，所以只能用这里的
        today 字段判断，不能用签到接口的返回值。
        """
        body = self.weapi_post(
            "https://interface3.music.163.com/weapi/vipnewcenter/app/user/sign/info",
            {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return None, 0, f"黑胶签到查询失败: code={code} msg={body.get('message', '')}"
        for row in body.get("data") or []:
            if row.get("today"):
                return True, row.get("score", 0), "今日已签"
        return False, 0, "今日未签"

    def vip_sign(self, name):
        """
        黑胶乐签：POST /eapi/vip-center-bff/task/sign（只有 eapi 有签到动作）

        流程必须是「先查 → 未签才签 → 再查确认」，因为签到接口对已签账号同样返回
        data=true，直接看返回值会把"早就签过了"误报成"本次签到成功"。
        """
        signed, score, msg = self.vip_sign_status(name)
        if signed is None:
            return False, msg
        if signed:
            return True, f"黑胶乐签: 今日已签 (+{score}成长值)"

        body = self.eapi_post("https://interface.music.163.com/eapi/vip-center-bff/task/sign")
        code = body.get("code", -1)
        if code != 200:
            return False, f"黑胶乐签失败: code={code} msg={body.get('message', '')}"

        time.sleep(1.5)
        after_signed, after_score, _ = self.vip_sign_status(name)
        if after_signed:
            return True, f"黑胶乐签成功 (+{after_score}成长值)"
        return False, "黑胶乐签: 接口返回成功但签到状态未变更，需人工核实"

    def _vip_growth_point(self):
        """查当前黑胶成长值（eapi），失败返回 None。"""
        body = self.eapi_post(
            "https://interface3.music.163.com/eapi/vipnewcenter/app/level/growhpoint/basic")
        if body.get("code") != 200:
            return None
        return (body.get("data") or {}).get("userLevel", {}).get("growthPoint")

    def vip_growth_claim(self, name):
        """
        领取黑胶 VIP 待领成长值：/weapi/vipnewcenter/app/level/task/reward/getall
        body 为空，data.result=true 表示领取请求已执行。

        注意：result=true 只代表"执行成功"，不代表本次有增量，所以用签到前后的
        growthPoint 差值报告。服务端结算可能有延迟，差值为 0 时只报当前值。
        """
        before = self._vip_growth_point()
        body = self.weapi_post(
            "/weapi/vipnewcenter/app/level/task/reward/getall", {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return False, f"VIP成长值领取失败: code={code} msg={body.get('message', '')}"
        if not (body.get("data") or {}).get("result"):
            return False, "VIP成长值: 领取未生效"

        time.sleep(2)
        after = self._vip_growth_point()
        if before is not None and after is not None and after > before:
            return True, f"VIP成长值领取成功 (+{after - before}，当前 {after})"
        current = after if after is not None else "未知"
        return True, f"VIP成长值已领取（当前 {current}，到账可能延迟）"

    def musician_sign(self, name):
        """
        创作者日常：领取云豆
        流程：
        1. 验证创作者身份 (/weapi/creator/user/access)
        2. 获取周期任务 (/weapi/nmusician/workbench/mission/cycle/list)
        3. 获取阶段任务 (/weapi/nmusician/workbench/mission/stage/list)
        4. 领取可领取的云豆 (/weapi/nmusician/workbench/mission/reward/obtain/new)
        
        status 含义: 0=未完成, 10=可领取, 20=可领取(日常类), 100=已完成
        """
        # 验证是否是创作者
        access = self.weapi_post("/weapi/creator/user/access")
        if access.get("code") != 200 or access.get("data") is not True:
            return None, "非音乐人账号，跳过"

        results = []
        total_beans = 0

        # 获取周期任务列表
        cycle = self.weapi_post("/weapi/nmusician/workbench/mission/cycle/list")
        time.sleep(random.uniform(0.5, 1))

        # 获取阶段任务列表
        stage = self.weapi_post("/weapi/nmusician/workbench/mission/stage/list")
        time.sleep(random.uniform(0.5, 1))

        # 合并任务
        missions = []
        if cycle.get("code") == 200:
            missions.extend(cycle.get("data", {}).get("list", []))
        if stage.get("code") == 200:
            for m in stage.get("data", {}).get("list", []):
                for target in m.get("userStageTargetList", []):
                    mission = m.copy()
                    mission["status"] = target.get("status", 0)
                    mission["rewardWorth"] = target.get("worth", 0)
                    if "userMissionId" in target:
                        mission["userMissionId"] = target["userMissionId"]
                    missions.append(mission)

        # 领取可领取的云豆（status=10 或 status=20 都是可领取）
        for mission in missions:
            status = mission.get("status", 0)
            description = mission.get("description", mission.get("displayDescription", "未知任务"))
            worth = mission.get("rewardWorth", 0)
            user_mission_id = mission.get("userMissionId", 0)
            period = mission.get("period", "")

            if status in (10, 20) and user_mission_id:
                r = self.weapi_post("/weapi/nmusician/workbench/mission/reward/obtain/new",
                                    {"userMissionId": user_mission_id, "period": str(period)})
                if r.get("code") == 200:
                    try:
                        worth_int = int(worth)
                    except (ValueError, TypeError):
                        worth_int = 0
                    total_beans += worth_int
                    results.append(f"{description}: 云豆+{worth}")
                    logger.info(f"[{name}] 音乐人任务完成: {description} +{worth}云豆")
                else:
                    msg = r.get("msg", r.get("message", ""))
                    results.append(f"{description}: 领取失败({msg})")
                time.sleep(random.uniform(0.5, 1.5))

        # 查询云豆余额
        bean = self.weapi_post("/weapi/cloudbean/get")
        if bean.get("code") == 200:
            balance = bean.get("data", {}).get("cloudBean", 0)
            results.append(f"当前云豆余额: {balance}")

        # 查询创作者数据概览
        overview = self.weapi_post("/weapi/creator/musician/statistic/data/overview/get")
        if overview.get("code") == 200:
            data = overview.get("data", {})
            play_count = data.get("playCount", "--")
            follower_inc = data.get("followerCountIncrement", "--")
            results.append(f"昨日播放量: {play_count}, 昨日新增粉丝: {follower_inc}")

        if total_beans > 0:
            return True, f"音乐人签到完成: 共领{total_beans}云豆", results
        elif results:
            return True, "音乐人签到: 无可领取云豆", results
        else:
            return False, "音乐人签到失败", results


def main():
    cfg = None
    try:
        wait_seconds = random.randint(30, 300)
        logger.info(f"随机等待 {wait_seconds} 秒后开始签到...")
        time.sleep(wait_seconds)

        cfg = load_config("accounts.json")
        accounts = cfg.get("accounts", [])
        if not accounts:
            logger.warning("accounts.json 中没有配置任何账号")
            sys.exit(1)

        signin_accounts = [a for a in accounts if "signin" in a.get("roles", "")]
        if not signin_accounts:
            logger.info("没有配置 roles 包含 signin 的账号，跳过签到")
            print("没有 signin 账号，跳过")
            sys.exit(0)

        success_count = 0
        # run.py 已经直邮过的失效号名单（同 job 同目录），用于避免重复发信
        mailed = _already_mailed()
        fail_count = 0
        skipped_count = 0
        expired = []          # 明确失效的账号名，末尾汇总一行 warning（群主告警邮件 2026-10-23 已移除）
        all_results = []

        for acc in signin_accounts:
            aname = acc.get("name", "未知")
            cookie = acc.get("cookie", "")
            is_musician = acc.get("is_musician", False)
            results = [f"\n===== {aname} ====="]

            client = NeteaseClient(cookie)
            chk = client.login_check(aname)
            if chk is None:
                logger.warning(f"[{aname}] 网络异常，跳过本次签到（明天自动重试）")
                skipped_count += 1
                continue
            if chk is False:
                expired.append(aname)
                fail_count += 1
                # 2026-10-22：判失效的这一刻就直邮号主。失效清理会把这个号移出账号池，
                # signin 明天再也看不到它，不在这里发就永远没机会发了。
                # 2026-10-23：run.py 播放前验活更早、判定更严，已经发过的号记在 dead_sent.json，
                # 这里跳过，避免同一个号一天收到两封同样的邮件。
                if aname in mailed:
                    logger.info(f"[{aname}] 失效已由 run.py 直邮，跳过重复提醒")
                else:
                    try:
                        import notify
                        if notify.mail_ready() and (acc.get("email") or "").strip():
                            if notify.notify_relogin(acc.get("email", ""), getattr(client, "nickname", ""), aname):
                                logger.info(f"[{aname}] 已直邮号主：账号信息过期")
                    except Exception as e:
                        logger.warning(f"[{aname}] 直邮提醒失败（不影响签到）: {e}")
                continue

            time.sleep(random.uniform(1, 3))

            # 1. 每日日常
            ok, msg = client.daily_sign(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 2. 云贝中心签到
            ok, msg = client.yunbei_sign(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 3. 云贝到账确认（查账单）
            ok, msg, details = client.yunbei_sign_confirm(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            for d in details:
                results.append(f"    {d}")
            time.sleep(random.uniform(1, 2))

            # 4. 云贝任务奖励领取
            claimed = client.yunbei_task_claim(aname)
            if claimed:
                results.append(f"  云贝任务已领取: {', '.join(claimed)}")
            else:
                results.append("  云贝任务: 无可领取奖励")
            time.sleep(random.uniform(1, 2))

            # 5. 黑胶乐签（eapi，每天 +3 成长值）
            # 用 try 兜住：非黑胶会员账号在 eapi 上可能报错，不能让新功能炸掉整个账号的日常
            try:
                ok, msg = client.vip_sign(aname)
            except Exception as e:
                msg = f"黑胶乐签异常（已跳过）: {str(e)[:100]}"
                logger.warning(f"[{aname}] {msg}")
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 6. VIP 待领成长值
            try:
                ok, msg = client.vip_growth_claim(aname)
            except Exception as e:
                msg = f"VIP成长值异常（已跳过）: {str(e)[:100]}"
                logger.warning(f"[{aname}] {msg}")
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 7. 创作者日常（仅创作者账号）
            if is_musician:
                ok, msg, detail_list = client.musician_sign(aname)
                logger.info(f"[{aname}] {msg}")
                results.append(f"  {msg}")
                for d in detail_list:
                    results.append(f"    {d}")
            else:
                logger.info(f"[{aname}] 非音乐人账号，跳过音乐人签到")

            success_count += 1
            all_results.extend(results)
            time.sleep(random.uniform(2, 5))

        logger.info(f"签到完成: 成功 {success_count} 个, 失败 {fail_count} 个, 网络异常跳过 {skipped_count} 个")
        print("\n".join(all_results))

        if expired:
            logger.warning(f"{len(expired)} 个账号凭证失效：{'、'.join(expired)}")

        if fail_count > 0 and success_count == 0:
            sys.exit(1)

    except Exception as e:
        logger.error(f"程序异常: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()