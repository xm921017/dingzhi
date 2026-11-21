# -*- coding: utf-8 -*-
"""定制群统一群发邮件（2026-11-21 一次性任务，workflow_dispatch 手动触发）。

用户口径：给 dz 池所有留了邮箱的号主统一发一封邮件，让大家加预留的定制群
（QQ 群 1064412365）。文案沿用主群「登记成功」邮件格式（cron-relay notify.py
notify_reg_ok，2026-11-06 定稿，逐字使用），群号一行换成定制群预留群号
（与 mail_remind.py GROUP_LINE_DZ 同款，2026-11-20 用户已确认的写法）。

发件邮箱 = dingzhi 仓 GitHub Secrets 的 EMAIL_FROM / EMAIL_AUTH_CODE
（定制群自己的 QQ 邮箱，与主群发件号完全独立）。

名单来源：现查 D1 netpool.accounts WHERE pool='dz'（CF_TOKEN / CF_ACCOUNT_ID，
与 d1_backup.py 同一套凭据），只取 uid/name/email 三列。主键 (pool,uid) 游标
分页，251 行左右，rows_read 微量。邮箱只在内存使用，日志一律打码 ——
**本仓是 public 仓，Actions 日志任何人可见，绝不打印完整邮箱/手机号。**

发信节奏：每封间隔 MAIL_INTERVAL 秒（默认 8，QQ SMTP 高频连发断连，
mail_remind 实测口径）。250 封 ≈ 35~40 分钟，workflow timeout 留 90 分钟。

⚠ 本脚本不记水位、不写 mail_queue：重跑会把名单**再发一遍**。误发/中断后
  不要盲目重跑，先确认要不要补发差额。

环境变量（workflow 注入）：
  CF_TOKEN / CF_ACCOUNT_ID     D1 只读（与 d1-daily.yml 同源）
  EMAIL_FROM / EMAIL_AUTH_CODE 发件 QQ 邮箱 + SMTP 授权码（定制群的）
  TEST_TO                      非空 = 只发一封样件（'self' = 发给发件箱自己）
  MAIL_INTERVAL                每封间隔秒数，默认 8
  MAIL_LIMIT                   本班最多发多少封，默认 0=全部

用法：
  python mail_broadcast.py --dry    # 只查名单打印统计，不登录 SMTP 不发送
  python mail_broadcast.py          # 正式群发（或样件，看 TEST_TO）
"""
import json
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr

ACC = (os.environ.get("CF_ACCOUNT_ID", "") or "c60450bfb7f2c2becfd744ba2508a4f2").strip()
DB_UUID = "54f742fc-5f56-4723-a7a0-a832953d38c7"   # netpool，与 d1_backup.py 同源
TOK = (os.environ.get("CF_TOKEN", "") or "").strip()
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

EMAIL_FROM = (os.environ.get("EMAIL_FROM", "") or "").strip()
EMAIL_AUTH = (os.environ.get("EMAIL_AUTH_CODE", "") or "").strip()
TEST_TO = (os.environ.get("TEST_TO", "") or "").strip()
try:
    INTERVAL = float(os.environ.get("MAIL_INTERVAL", "8") or 8)
except ValueError:
    INTERVAL = 8.0
try:
    LIMIT = int(os.environ.get("MAIL_LIMIT", "0") or 0)
except ValueError:
    LIMIT = 0
DRY = "--dry" in sys.argv

SIGN = "网易音乐人650任务"
DISPLAY_NAME = "网易音乐人650任务"
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465

# 2026-11-21 用户口径：预留的定制群号 1064412365，写法沿用 mail_remind.GROUP_LINE_DZ
GROUP_LINE = "售后群：QQ 群 1064412365（续费/咨询请在群里联系客服）"
SUBJECT = "【" + SIGN + "】登记成功，麻烦加一下售后群"

# 邮箱粗校验（与 mail_remind.py 同口径）：只挡「明显不可能存在」的地址
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


def mask_addr(addr):
    """日志打码：本仓 public，Actions 日志任何人可见。"""
    s = (addr or "").strip()
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    return (local[:2] if local else "") + "***@" + domain


def mask_name(name):
    s = (name or "").strip()
    return (s[:3] + "***") if len(s) > 3 else (s[:1] + "***" if s else "***")


def _who(name, uid):
    who = (name or "").strip()
    if who.startswith(("qr:", "manual:", "name:")):
        who = ""
    return who or (str(uid) if uid else "定制群成员")


def build_body(who):
    """文案 = 主群 notify_reg_ok（2026-11-06 定稿）逐字，仅群号一行换成定制群预留号。"""
    return (
        "你好，" + who + "：\n"
        "你的账号已经登记成功，明天起会开始听歌任务，你可按照以前习惯一切正常使用APP。\n"
        + GROUP_LINE + "\n"
        "以后账号要是需要重新登录、或者有什么变化，我们会在群里通知。\n"
        "比等邮件快得多，邮件偶尔会掉进垃圾箱，容易耽误事。\n"
        "（备注一下登记用的手机号）\n\n"
        "——" + SIGN
    )


def d1_query(sql, params, label="query"):
    """查一次 D1，页级重试（5xx / 7500 / 网络异常 → 3/8/20s 退避；4xx 立刻抛）。"""
    url = ("https://api.cloudflare.com/client/v4/accounts/"
           + ACC + "/d1/database/" + DB_UUID + "/query")
    body = json.dumps({"sql": sql, "params": params}).encode("utf-8")
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Authorization": "Bearer " + TOK,
                "Content-Type": "application/json",
                "User-Agent": UA_BROWSER,
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            if not d.get("success"):
                raise RuntimeError("D1 success=false: " + json.dumps(d.get("errors") or [])[:200])
            return (d.get("result") or [{}])[0]
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:200]
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, detail)
            if 400 <= e.code < 500 and e.code not in (429,):
                raise SystemExit("[%s] D1 4xx 不重试：%s" % (label, last))
        except Exception as e:
            last = str(e)
        wait = (3, 8, 20)[min(attempt, 2)]
        print("[%s] 第 %d 次失败（%s），%ds 后重试" % (label, attempt + 1, last, wait))
        time.sleep(wait)
    raise SystemExit("[%s] 重试 4 次仍失败：%s" % (label, last))


def fetch_dz_rows():
    """游标分页拉 dz 池 uid/name/email（主键 (pool,uid)，走索引，无 TEMP B-TREE）。"""
    rows, last_uid, pages = [], "", 0
    while True:
        pages += 1
        r = d1_query(
            "SELECT uid, name, email FROM accounts "
            "WHERE pool = 'dz' AND uid > ? ORDER BY uid LIMIT 200",
            [last_uid], "accounts 第%d页" % pages)
        batch = r.get("results") or []
        rows.extend(batch)
        if len(batch) < 200:
            break
        last_uid = str(batch[-1].get("uid") or "")
        if not last_uid:
            break
    return rows, pages


def send_one(to_email, subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((DISPLAY_NAME, EMAIL_FROM))
    msg["To"] = to_email
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(EMAIL_FROM, EMAIL_AUTH)
        server.sendmail(EMAIL_FROM, [to_email], msg.as_string())


def summary(text):
    p = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if p:
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def main():
    if not TOK:
        print("缺 CF_TOKEN，退出")
        return 1

    rows, pages = fetch_dz_rows()
    todo, seen, bad = [], set(), 0
    for r in rows:
        addr = (r.get("email") or "").strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        if not email_ok(addr):
            bad += 1
            continue
        seen.add(key)
        todo.append({"uid": str(r.get("uid") or ""), "name": r.get("name") or "", "email": addr})

    print("[broadcast] dz 池 %d 行（%d 页）；有效邮箱 %d 个；无邮箱 %d 行；"
          "格式非法 %d 个（不发）"
          % (len(rows), pages, len(todo), len(rows) - len([r for r in rows if (r.get("email") or "").strip()]), bad))

    if DRY:
        for t in todo[:8]:
            print("   [dry] uid=%s name=%s mail=%s" % (t["uid"], mask_name(t["name"]), mask_addr(t["email"])))
        print("[broadcast] dry 模式，不登录 SMTP，不发送")
        return 0

    if not (EMAIL_FROM and EMAIL_AUTH):
        print("缺 EMAIL_FROM / EMAIL_AUTH_CODE，退出")
        return 1

    # 样件模式：只发一封给 TEST_TO（'self' = 发件箱自己），验证格式与通道
    if TEST_TO:
        target = EMAIL_FROM if TEST_TO.lower() == "self" else TEST_TO
        if not email_ok(target):
            print("TEST_TO 非法：%s" % mask_addr(target))
            return 1
        send_one(target, SUBJECT, build_body("样件收件人"))
        print("[broadcast] 样件已发 %s（正式群发请把 test_to 留空再 dispatch）" % mask_addr(target))
        return 0

    sent, failed = [], []
    for idx, t in enumerate(todo):
        if LIMIT and len(sent) + len(failed) >= LIMIT:
            print("[broadcast] 已达本班上限 MAIL_LIMIT=%d，剩余 %d 封不发" % (LIMIT, len(todo) - idx))
            break
        if idx:
            time.sleep(INTERVAL)
        who = _who(t["name"], t["uid"])
        try:
            send_one(t["email"], SUBJECT, build_body(who))
            sent.append(t)
            print("   [%s] %s 已发 %s" % (t["uid"], mask_name(who), mask_addr(t["email"])))
        except Exception as e:
            failed.append(t)
            print("   [%s] %s 发送失败 %s：%s" % (t["uid"], mask_name(who), mask_addr(t["email"]), str(e)[:120]))

    print("[broadcast] 完成：成功 %d / 失败 %d（发送人=%s，每封间隔 %gs）"
          % (len(sent), len(failed), mask_addr(EMAIL_FROM), INTERVAL))
    summary("**定制群群发完成**：成功 %d / 失败 %d（名单 %d，间隔 %gs）"
            % (len(sent), len(failed), len(todo), INTERVAL))
    if failed and not sent:
        print("[broadcast] 全部失败，判为真故障")
        return 1
    if failed:
        print("[broadcast] 失败名单 uid: %s" % ",".join(x["uid"] for x in failed))
        print("[broadcast] ⚠ 重跑会全量重发，补发差额请人工单独联系，勿盲目重跑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
