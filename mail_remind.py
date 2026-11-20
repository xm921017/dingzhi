# -*- coding: utf-8 -*-
"""定制群到期提醒派发（2026-11-20 新增）。

用户口径：客户有效期剩 30 天、15 天时各发一封提醒邮件。
发件邮箱 = dingzhi 仓 GitHub Secrets 的 EMAIL_FROM / EMAIL_AUTH_CODE
（定制群自己的 QQ 邮箱 SMTP，与主群的发件号完全独立，绝不动主群的号）。

链路（与主群 notify_mail.py 同构，按定制群规模精简）：
  worker /api/mail_scan   每天扫一遍 pool=dz 的到期档位并入队（KV 每日闸门，多跑只扫一次）
  worker /api/mail_pending 领取待发（state=pending → claimed，2 小时超时自动回退）
  本脚本 SMTP 发送 → worker /api/mail_sent 回写（失败退回 pending，3 次后 dropped 放弃）

去重与作废都在 worker 侧做（唯一键 (pool,uid,kind,ref)，ref=到期日）：
  续费（exp 变了）→ 旧 pending 被扫作废，新一轮重新计时；一个号一档只发一次。

环境变量（GitHub Secrets 注入）：
  WORKER_URL      默认 https://dingzhi.xx1031.xyz
  NB_PASS / ASSIGN_PASS  worker 口令（mail_* 三个接口都用它）
  EMAIL_FROM / EMAIL_AUTH_CODE  发件 QQ 邮箱 + SMTP 授权码（定制群的）

用法：
  python mail_remind.py           # 扫描 + 领取 + 发送 + 回写
  python mail_remind.py --dry     # 只查询不发送（不动状态）
  python mail_remind.py --noscan  # 跳过扫描（只想清积压时用）
"""
import json
import os
import re
import smtplib
import sys
import time
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr

WORKER = (os.environ.get("WORKER_URL", "") or "https://dingzhi.xx1031.xyz").strip().rstrip("/")
PASS = (os.environ.get("NB_PASS", "") or os.environ.get("ASSIGN_PASS", "")).strip()
DRY = "--dry" in sys.argv
NOSCAN = "--noscan" in sys.argv
LIMIT = int(os.environ.get("MAIL_LIMIT", "50") or 50)

SIGN = "网易音乐人650任务"
DISPLAY_NAME = "网易音乐人650任务"
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 邮箱粗校验（与主群 notify_mail.py 同口径）：只挡「明显不可能存在」的地址
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def email_ok(addr):
    s = (addr or "").strip()
    if not s or len(s) > 254 or not _EMAIL_RE.match(s):
        return False
    local, _, domain = s.partition("@")
    if local.startswith(".") or local.endswith(".") or ".." in s:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def call(path, payload, timeout=60):
    # 调 worker 必带浏览器 UA，否则 Cloudflare 1010（项目铁律 6）
    r = urllib.request.Request(WORKER + path,
                               data=json.dumps(payload).encode("utf-8"),
                               headers={"Content-Type": "application/json",
                                        "User-Agent": UA_BROWSER},
                               method="POST")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"message": str(e)}
    except Exception as e:
        return 0, {"message": str(e)}


def _cred():
    return ((os.environ.get("EMAIL_FROM", "") or "").strip(),
            (os.environ.get("EMAIL_AUTH_CODE", "") or "").strip())


def send_user_email(to_email, subject, body):
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return False
    f, a = _cred()
    if not f or not a:
        print("[mail-remind] 未配置 EMAIL_FROM/EMAIL_AUTH_CODE，跳过直邮")
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((DISPLAY_NAME, f))
        msg["To"] = to_email
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(f, a)
            server.sendmail(f, [to_email], msg.as_string())
        print(f"[mail-remind] 已直邮 {to_email}：{subject}")
        return True
    except Exception as e:
        print(f"[mail-remind] 直邮失败 {to_email}：{e}")
        return False


def _who(name, uid):
    who = (name or "").strip()
    if who.startswith(("qr:", "manual:", "name:")):
        who = ""
    return who or (str(uid) if uid else "定制群成员")


def notify_expire(email, name, uid, exp, days):
    """有效期还剩 days 天的提醒。平和陈述，不催收、不吓人。"""
    if not (email or "").strip():
        return False
    who = _who(name, uid)
    exp_s = (exp or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", exp_s):
        exp_line = f"到期日：{exp_s}（还剩约 {days} 天）"
    else:
        exp_line = f"当前有效期还剩约 {days} 天"
    subject = f"【{SIGN}】你的账号有效期还剩 {days} 天，需要续期请联系客服"
    body = (
        f"你好，{who}：\n\n"
        "跟你说一声：你在互听群登记的账号有效期快到了，提醒你一下。\n\n"
        f"{exp_line}\n\n"
        "到期后账号会自动停止任务，之前登记的歌和设置不受影响；\n"
        "想继续使用的话，联系客服选一个套餐续期即可（续费在原到期日基础上累加，"
        "剩余天数不会清零）。\n\n"
        "如果不打算续了，不用做任何操作，到期后我们会自动处理，不会再来打扰你。\n\n"
        "——" + SIGN
    )
    return send_user_email(email, subject, body)


def main():
    if not PASS:
        print("[mail-remind] 缺 NB_PASS/ASSIGN_PASS，退出")
        return 1
    f, a = _cred()
    if not (f and a):
        print("[mail-remind] 缺 EMAIL_FROM/EMAIL_AUTH_CODE，退出")
        return 1

    # ① 到期扫描（worker 内置 KV 每日闸门，多跑也只扫一次）
    if not NOSCAN:
        code, d = call("/api/mail_scan", {"pass": PASS, "dry": DRY})
        if code != 200 or not d.get("ok"):
            print(f"[mail-remind] 到期扫描失败 HTTP {code}: {d.get('message')}")
            return 1
        if d.get("skipped"):
            print(f"[mail-remind] 到期扫描：{d.get('message')}")
        else:
            print(f"[mail-remind] 到期扫描：扫 {d.get('scanned')} 号，入队 {d.get('will_enqueue')} 条"
                  + (f"，作废旧提醒 {d.get('dropped_stale')} 条" if d.get("dropped_stale") is not None else ""))

    # ② 领取待发（循环清队列；每轮领 ≤50、每封间隔 8 秒，80 封 ≈ 13 分钟卡在超时内）
    all_sent, all_failed, all_bad = [], [], []
    while True:
        if len(all_sent) + len(all_failed) >= 80:
            print("[mail-remind] 已发满 80 封/班，剩余下一班继续")
            break
        code, data = call("/api/mail_pending", {"pass": PASS, "limit": LIMIT, "dry": DRY})
        if code != 200 or not data.get("ok"):
            msg = str(data.get("message") or "")
            if "row read limit" in msg or "exceeded D1" in msg:
                print("::warning::[mail-remind] D1 读额度已打满，本轮跳过；队列未动，额度重置后自动补发")
                return 0
            print(f"[mail-remind] 领取失败 HTTP {code}: {msg}")
            return 1
        todo = data.get("to_send") or []
        skipped = data.get("skipped") or []
        print(f"[mail-remind] 本轮待发 {len(todo)} 条，判定不发 {len(skipped)} 条")
        for s in skipped:
            print(f"   - 不发 {s.get('name') or s.get('uid')} [{s.get('kind')}]: {s.get('why')}")

        if not todo:
            break
        if DRY:
            for t in todo:
                print(f"   [dry] {t.get('kind')} → {t.get('email')}（{t.get('name') or t.get('uid')}）")
            return 0

        sent, failed, bad = [], [], []
        for idx, t in enumerate(todo):
            # QQ SMTP 对高频连发断连（主群实测），每封之间强制间隔 8 秒
            if idx or all_sent or all_failed:
                time.sleep(8)
            who = str(t.get("name") or t.get("uid") or "")
            kind = str(t.get("kind") or "")
            email = (t.get("email") or "").strip()
            if not email_ok(email):
                bad.append(t)
                all_bad.append(t)
                print(f"   [{who}] 邮箱格式非法，不发（{email or '空'}）")
                continue
            try:
                if kind.startswith("exp"):
                    days = int(kind[3:]) if kind[3:].isdigit() else 30
                    ok = notify_expire(email, t.get("name"), t.get("uid"),
                                       t.get("exp") or t.get("ref") or "", days)
                else:
                    print(f"   [{who}] 未知类型 {kind}，跳过")
                    ok = False
            except Exception as e:
                print(f"   [{who}] 发信异常：{e}")
                ok = False
            if ok:
                sent.append(t)
                all_sent.append(t)
                print(f"   [{who}] 已直邮 {email}（{kind}）")
            else:
                failed.append(t)
                all_failed.append(t)
                print(f"   [{who}] 发信失败（{kind}）")

        # ③ 回写：成功标 sent；失败退回 pending 下轮再试（3 次后 worker 标 dropped）
        if sent:
            code, d = call("/api/mail_sent", {"pass": PASS, "result": "sent", "items": [
                {"pool": x["pool"], "uid": x["uid"], "kind": x["kind"], "ref": x["ref"]} for x in sent]})
            print(f"[mail-remind] 已标记 sent {len(sent)} 条（HTTP {code} {d.get('updated')}）")
        if failed or bad:
            retry_items = failed + bad
            code, d = call("/api/mail_sent", {"pass": PASS, "result": "retry", "items": [
                {"pool": x["pool"], "uid": x["uid"], "kind": x["kind"], "ref": x["ref"]} for x in retry_items]})
            dp = d.get("dropped") or 0
            print(f"[mail-remind] 失败 {len(failed)} 条 + 非法邮箱 {len(bad)} 条已回写（HTTP {code}）"
                  + (f"，放弃 {dp} 条" if dp else ""))

    print(f"[mail-remind] 完成：成功 {len(all_sent)} / 失败 {len(all_failed)}"
          + (f" / 非法邮箱 {len(all_bad)}" if all_bad else ""))
    if all_failed and not all_sent:
        print("[mail-remind] 全部失败，判为真故障")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
