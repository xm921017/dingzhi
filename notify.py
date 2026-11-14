# -*- coding: utf-8 -*-
"""
号主直邮模块（2026-10-17 新增）。

账号出问题时，给成员本人发一封说人话的邮件（不是给群主、也不是 GitHub 那种
开发者日志），只讲三件事：发生了什么、不影响什么、要做哪一步。
语气保持平和，不使用"风控/拦截/异常"等刺激性措辞。

通道：QQ 邮箱 SMTP，凭据从环境变量读取（GitHub Secrets 注入）：
  EMAIL_FROM      发件 QQ 邮箱地址
  EMAIL_AUTH_CODE 该邮箱的 SMTP 授权码（16 位）
未配置或发送失败都只记日志，绝不影响批量执行/日常主流程。

触发分工（避免同一个号一天收到多封重复提醒）：
  - 登录凭证失效 → run.py 在播放前验活时先发（它的判定最严、覆盖最广，包含「code 200
                   但已掉线、每日推荐 0 首」这类号）；signin.py 只对 run.py 本片没报过的
                   号补发。两者同 job 同目录，靠 dead_sent.json 去重 → 一个号一天最多一封。
  - 发动态需安全验证 → notes.py 负责（每 6 天最多轮到一次）
"""
import os
import json
import smtplib
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr

DISPLAY_NAME = "网易音乐人650任务"
# 2026-11-14：调 worker 必须带浏览器 UA，否则被 Cloudflare 1010 挡回
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# 2026-10-23：落款统一（此前 verify 用「小助手」、relogin 用「目标任务」，同一个人收到两封
# 会出现两个身份）。全部改用品牌名，两群模板完全一致，只有 JOIN_PAGE 按群不同。
SIGN = "网易音乐人650任务"
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
# 成员接入登记页（邮件里给号主重新登录用）
JOIN_PAGE = "https://dingzhi.xx1031.xyz"


def _cred():
    return (
        (os.environ.get("EMAIL_FROM", "") or "").strip(),
        (os.environ.get("EMAIL_AUTH_CODE", "") or "").strip(),
    )


def mail_ready():
    f, a = _cred()
    return bool(f and a)


def send_user_email(to_email, subject, body):
    """给成员本人发一封纯文本邮件。任何异常只记日志，不抛出、不影响主流程。"""
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return False
    f, a = _cred()
    if not f or not a:
        print("[notify] 未配置 EMAIL_FROM/EMAIL_AUTH_CODE，跳过直邮")
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((DISPLAY_NAME, f))
        msg["To"] = to_email
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(f, a)
            server.sendmail(f, [to_email], msg.as_string())
        print(f"[notify] 已直邮号主 {to_email}：{subject}")
        return True
    except Exception as e:
        print(f"[notify] 直邮失败 {to_email}：{e}")
        return False


def _who(nickname, name):
    who = (nickname or "").strip()
    if name:
        who = f"{who}（{name}）" if who else str(name)
    return who or "网易音乐人650任务成员"


VERIFY_COOL_DAYS = 3          # 同一个号多少天内最多收一封 250 提醒（可用 VERIFY_COOL_DAYS 覆盖）
VERIFY_GATE_PATH = "/api/verify_gate"


def _verify_gate(uid, mark=False):
    """问 worker「这个号现在能不能再发一封 250 提醒」（与 hz 同一套闸门）。

    返回 dict（含 send=True/False）或 None（口令没配/网络不通 → 调用方按"能发"处理）。
    跨天状态只能放云端（KV vmail:<pool>:<uid>），GH runner 是一次性的。
    """
    uid = str(uid or "").strip()
    if not uid:
        return None
    pw = (os.environ.get("ASSIGN_PASS") or os.environ.get("NB_PASS") or "").strip()
    if not pw:
        return None
    base = (os.environ.get("WORKER_URL") or "https://dingzhi.xx1031.xyz").rstrip("/")
    try:
        days = max(1, int(os.environ.get("VERIFY_COOL_DAYS") or VERIFY_COOL_DAYS))
    except ValueError:
        days = VERIFY_COOL_DAYS
    payload = {"pass": pw, "uid": uid, "days": days, "mark": "1" if mark else "0"}
    try:
        req = urllib.request.Request(
            base + VERIFY_GATE_PATH,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": UA_BROWSER},
            method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d if isinstance(d, dict) else None
    except Exception as e:
        print(f"[notify] 提醒闸门不可用（按可发处理）：{e}")
        return None


def notify_verify(email, nickname, name, uid=""):
    """发动态时平台要求完成一次安全验证。平和陈述，不吓人。

    2026-10-23 改版：把「安全验证」从标题里拿掉（容易被读成"我账号出事了"），
    开场先说"跟你说一声"、把范围锁死在"一条动态"，动作改成可选项而不是义务。

    2026-11-11 改版（与 hz 同步，实测驱动，两处原话都已不成立）：
      · 删掉「你自己发一条动态就恢复了」—— 已证伪。我们发的是「分享到动态」eapi 接口，
        风控标记挂在我们库里那条 CK 会话上；号主在手机上发笔记走的是另一条会话，
        碰不到这条标记。实测：号主 11-07 亲手发过动态，之后我们每天仍 code=250。
      · 删掉「6 天后系统会自动再试一次」—— 旧口径。NOTES_EVERY_DAYS=1 起是每天都试，
        所以旧文案会让人以为"等着就行"，实际是天天失败、天天发信。
      · 动作改成「联系售后」：真正有效的是换一条新会话（重登后更新 CK），只能人工做。
      · 明确劝阻号主自己退出登录：他一退，我们那条 CK 会话大概率被踢，听歌任务直接中断，
        比现在更糟。必须先由售后准备好，再指导他重登，不能让他擅自操作。

    2026-11-14 改版（与 hz 同步，换绑实测复盘）：
      · 「换完就好」站不住：11-14 核过 4 个已换绑号，1 个当晚恢复、3 个换完首个发布日仍 250。
      · 号主自己发图文**能补任务进度**（我们一次没发成功，进度照样从 3/4 走满 4/4 被跳过），
        但不能解除我们这条 250 → 所以把「自己发够 4 条图文」提成主推路径。
      · 加 3 天冷却（VERIFY_COOL_DAYS）：同一号 3 天内最多一封，不再天天催。
    """
    if not (email or "").strip():
        return False
    gate = _verify_gate(uid)
    if gate is not None and gate.get("send") is False:
        print(f"[notify] {name} 的 250 提醒还在冷却期（上次 {gate.get('last') or '?'}，"
              f"还剩约 {gate.get('remainDays')} 天），本次不发")
        return False
    subject = "【网易音乐人650任务】一条动态暂时发不出去，今天先这样处理"
    body = (
        f"你好，{_who(nickname, name)}：\n\n"
        "跟你说一声：这个号在自动发动态时，被网易云要求做一次安全验证，这条动态暂时发不出去。\n"
        "其它都正常——听歌、签到、你的歌被别人播放，全都照旧。\n\n"
        "有两件事可以做，第二件更管用：\n\n"
        "【一·可选】联系客服拿一条「换绑登录」链接，用原来登记的那个网易云账号重新登录一次。\n"
        "这是把被标记的登录凭证换成一条全新的——免费，有效期、歌曲、邮箱都不变，听歌不受影响。\n"
        "实测有的号换完当晚就恢复；也有的号换完照旧发不出去（那是网易对这个账号本身的风控，"
        "不是凭证的问题），这种情况再换一次也没用，不要反复换。\n\n"
        "【二·更管用】打开网易云音乐 App → 底部「笔记」→ 自己发一条图文动态（一句话加一张图就行）。\n"
        "这个任务算的是「30 天内发够 4 条图文」，你自己发够 4 条，任务就算完成，"
        "我们这边也会自动跳过这个号——不再代发、也不再发这封提醒。\n\n"
        "提醒一句：请不要自己在 App 里退出登录 —— 换绑不需要先退出，照客服说的做就行；"
        "自己先退出的话听歌任务会中断，反而更麻烦。\n\n"
        "这条提醒我们最多 3 天发一次，不会天天打扰你；不影响听歌和播放，不用着急。\n\n"
        "——" + SIGN
    )
    ok = send_user_email(email, subject, body)
    if ok and uid:
        _verify_gate(uid, mark=True)   # 发成功才记冷却，发失败下一班还能补
    return ok


def notify_relogin(email, nickname, name):
    """登录凭证过期/掉线，需要重新登记一次。平和陈述，不吓人。

    2026-10-23 改版：
      · 触发面扩大 —— 以前只有日常程序（signin.py）会调用；现在听歌程序（run.py）在
        播放前验活时判定的失效号也会调用，两边靠 dead_sent.json 去重，一个号一天最多一封。
      · 措辞按需求改成「账号信息过期，重新登记」，并给出「找售后」这条兜底路径，
        避免不会操作的人卡在登记页上没人管。
      · 删掉「7 天后自动移除」——实际清理是「两次判死才删」，与 7 天无关，写进去会误导。
      · 正文里不再出现任何网址（用户要求）：号主不一定能分清哪个链接是真的，
        直接让他找售后最省事，也避免仿冒站搭便车。JOIN_PAGE 常量保留但已不写进邮件。
    """
    if not (email or "").strip():
        return False
    subject = "【网易音乐人650任务】账号信息过期了，麻烦重新登记一次"
    body = (
        f"你好，{_who(nickname, name)}：\n\n"
        "跟你说一声：这个号的登录信息过期了，直接联系售后帮你登记。\n\n"
        "重新登记完，下一次任务会自动恢复正常，不用再做别的。\n\n"
        "——" + SIGN
    )
    return send_user_email(email, subject, body)


if __name__ == "__main__":
    # 本地/CI 自测：python notify.py 收件邮箱 [relogin 账号名]
    # 模板：缺省=发件通道测试；relogin=账号过期重新登记提醒（test-email.yml 的 tpl=relogin 用）
    import sys
    if len(sys.argv) >= 2:
        to = sys.argv[1]
        tpl = sys.argv[2] if len(sys.argv) >= 3 else ""
        if tpl == "relogin":
            aname = sys.argv[3] if len(sys.argv) >= 4 else "你的账号"
            ok = notify_relogin(to, "", aname)
        else:
            ok = send_user_email(
                to,
                "【网易音乐人650任务】发件通道测试",
                "如果你收到这封邮件，说明直邮通道工作正常。\n\n——" + SIGN,
            )
        sys.exit(0 if ok else 1)
    print("usage: python notify.py <to_email> [relogin <account_name>]")
    sys.exit(2)
