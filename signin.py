# -*- coding: utf-8 -*-
"""
账号任务执行工具（多账号，通过 accounts.json 的 roles 控制）
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

# ---------- crypto A ----------
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
    text = json.dumps(data).encode("utf-8")
    secret = _create_key(16)
    params = base64.b64encode(_aes_cbc(base64.b64encode(_aes_cbc(text, _NONCE)), secret))
    encseckey = _rsa_encrypt(secret, _PUBKEY, _MODULUS)
    return {"params": params.decode("utf-8"), "encSecKey": encseckey}


# ---------- crypto B ----------
_EAPI_KEY = b"e82ckenh8dichen8"
_EAPI_SEP = "-36cd479b6b5-"
_EAPI_SALT = "nobody%suse%smd5forencrypt"
_ANDROID_UA = ("NeteaseMusic/9.2.85.250418145357(9002085);"
               "Dalvik/2.1.0 (Linux; U; Android 9; SM-S9180 Build/PQ3B.190801.10101846)")


def eapi_encrypt(path, data):
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
        self._eapi_s = None
        self.eapi_device_id = hashlib.sha256(cookie.encode("utf-8")).hexdigest().upper()[:52]

        if not device_id:
            device_id = "YD-" + hashlib.md5(cookie.encode("utf-8")).hexdigest()[:32]

        # 解析原始 cookie 并注入到 session cookies 中
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.s.cookies.set(k.strip(), v.strip(), domain="music.163.com", path="/")

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
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        try:
            r = self.s.post(url, data=enc, timeout=30)
            return r.json()
        except Exception as e:
            logger.warning(f"请求失败 {path}: {str(e)[:120]}")
            return {"code": -1, "message": f"请求失败: {str(e)[:120]}"}

    def _eapi_session(self):
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
        """返回 True=有效 / False=失效 / None=网络异常。"""
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
            logger.info(f"[{name}] Cookie 有效（备用校验通过）")
            return True
        # 两次请求都 code=-1 = 请求层失败（网络/HTTP 错误），不是 cookie 本身的问题，
        # 返回 None 让主程序跳过本次而非误判过期（2026-10-13 修复）
        if code == -1 and body2.get("code", -1) == -1:
            logger.warning(f"[{name}] 网络异常，无法判定 cookie 状态（明天重试）")
            return None
        logger.error(f"[{name}] Cookie 无效或已过期: code={code}")
        return False

    def p1_do(self, name):
        body = self.weapi_post("/weapi/point/dailyTask", {"type": 1})
        code = body.get("code", -1)
        msg = body.get("msg", body.get("message", ""))

        if code == 200:
            point = body.get("point", "")
            return True, f"P1 完成 (+{point})" if point else "P1 完成"
        elif code == -2:
            return True, "P1 已完成"
        else:
            return False, f"P1 失败: code={code} msg={msg}"

    def p2_do(self, name):
        body = self.weapi_post("/weapi/pointmall/user/sign", {}, with_csrf=False)
        code = body.get("code", -1)
        msg = body.get("msg", body.get("message", ""))
        if code != 200:
            return False, f"P2 失败: code={code} msg={msg}"

        data = body.get("data") or {}
        if data.get("sign"):
            num = data.get("yunbeiNum", 0)
            return True, f"P2 完成 (+{num})" if num else "P2 完成"
        return True, "P2 已完成"

    def p3_audit(self, name):
        body = self.weapi_post("/store/api/point/receipt", {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return False, f"P3 查询失败: code={code}", []

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
            details.append(f"{fixed} +{amount}")

        if total > 0:
            return True, f"P3 核对: 今日 +{total}", details
        return False, "P3 核对: 今日无记录", details

    def p4_claim(self, name):
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
                        claimed.append(f"{task_name}(+{point})")
                        logger.info(f"[{name}] P4 已领取: {task_name} +{point}")
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
                            logger.info(f"[{name}] P4 已领取: {task_name}")
                        time.sleep(random.uniform(0.5, 1.5))

        return claimed

    def p5_state(self, name):
        body = self.weapi_post(
            "https://interface3.music.163.com/weapi/vipnewcenter/app/user/sign/info",
            {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return None, 0, f"P5 查询失败: code={code} msg={body.get('message', '')}"
        for row in body.get("data") or []:
            if row.get("today"):
                return True, row.get("score", 0), "已完成"
        return False, 0, "未完成"

    def p5_do(self, name):
        signed, score, msg = self.p5_state(name)
        if signed is None:
            return False, msg
        if signed:
            return True, f"P5 已完成 (+{score})"

        body = self.eapi_post("https://interface.music.163.com/eapi/vip-center-bff/task/sign")
        code = body.get("code", -1)
        if code != 200:
            return False, f"P5 失败: code={code} msg={body.get('message', '')}"

        time.sleep(1.5)
        after_signed, after_score, _ = self.p5_state(name)
        if after_signed:
            return True, f"P5 完成 (+{after_score})"
        return False, "P5: 接口成功但状态未变更，需核实"

    def p6_point(self):
        body = self.eapi_post(
            "https://interface3.music.163.com/eapi/vipnewcenter/app/level/growhpoint/basic")
        if body.get("code") != 200:
            return None
        return (body.get("data") or {}).get("userLevel", {}).get("growthPoint")

    def p6_claim(self, name):
        before = self.p6_point()
        body = self.weapi_post(
            "/weapi/vipnewcenter/app/level/task/reward/getall", {}, with_csrf=False)
        code = body.get("code", -1)
        if code != 200:
            return False, f"P6 失败: code={code} msg={body.get('message', '')}"
        if not (body.get("data") or {}).get("result"):
            return False, "P6: 未生效"

        time.sleep(2)
        after = self.p6_point()
        if before is not None and after is not None and after > before:
            return True, f"P6 完成 (+{after - before}，当前 {after})"
        current = after if after is not None else "未知"
        return True, f"P6 已完成（当前 {current}，到账可能延迟）"

    def p7_do(self, name):
        access = self.weapi_post("/weapi/creator/user/access")
        if access.get("code") != 200 or access.get("data") is not True:
            return None, "P7: 条件不满足，跳过", []

        results = []
        total_beans = 0

        cycle = self.weapi_post("/weapi/nmusician/workbench/mission/cycle/list")
        time.sleep(random.uniform(0.5, 1))

        stage = self.weapi_post("/weapi/nmusician/workbench/mission/stage/list")
        time.sleep(random.uniform(0.5, 1))

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

        # status 10/20 = 可领取
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
                    results.append(f"{description}: +{worth}")
                    logger.info(f"[{name}] P7 完成: {description} +{worth}")
                else:
                    msg = r.get("msg", r.get("message", ""))
                    results.append(f"{description}: 失败({msg})")
                time.sleep(random.uniform(0.5, 1.5))

        bean = self.weapi_post("/weapi/cloudbean/get")
        if bean.get("code") == 200:
            balance = bean.get("data", {}).get("cloudBean", 0)
            results.append(f"当前余额: {balance}")

        overview = self.weapi_post("/weapi/creator/musician/statistic/data/overview/get")
        if overview.get("code") == 200:
            data = overview.get("data", {})
            play_count = data.get("playCount", "--")
            follower_inc = data.get("followerCountIncrement", "--")
            results.append(f"播放量: {play_count}, 新增关注: {follower_inc}")

        if total_beans > 0:
            return True, f"P7 完成: 共 +{total_beans}", results
        elif results:
            return True, "P7: 无可领取", results
        else:
            return False, "P7 失败", results


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
        # 已直邮过的失效号名单（同 job 同目录）
        mailed = _already_mailed()
        fail_count = 0
        skipped_count = 0
        expired = []          # 明确失效的账号名
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
                # 判失效时立即直邮号主；run.py 已发过的跳过，避免重复提醒
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

            # 1
            ok, msg = client.p1_do(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 2
            ok, msg = client.p2_do(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 3
            ok, msg, details = client.p3_audit(aname)
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            for d in details:
                results.append(f"    {d}")
            time.sleep(random.uniform(1, 2))

            # 4
            claimed = client.p4_claim(aname)
            if claimed:
                results.append(f"  P4 已领取: {', '.join(claimed)}")
            else:
                results.append("  P4: 无可领取")
            time.sleep(random.uniform(1, 2))

            # 5（新步骤：异常不影响原有流程）
            try:
                ok, msg = client.p5_do(aname)
            except Exception as e:
                msg = f"P5 异常（已跳过）: {str(e)[:100]}"
                logger.warning(f"[{aname}] {msg}")
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 6（新步骤）
            try:
                ok, msg = client.p6_claim(aname)
            except Exception as e:
                msg = f"P6 异常（已跳过）: {str(e)[:100]}"
                logger.warning(f"[{aname}] {msg}")
            logger.info(f"[{aname}] {msg}")
            results.append(f"  {msg}")
            time.sleep(random.uniform(1, 2))

            # 7（条件项）
            if is_musician:
                ok, msg, detail_list = client.p7_do(aname)
                logger.info(f"[{aname}] {msg}")
                results.append(f"  {msg}")
                for d in detail_list:
                    results.append(f"    {d}")
            else:
                logger.info(f"[{aname}] P7 跳过（条件不满足）")

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