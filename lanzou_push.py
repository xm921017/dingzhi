#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1 加密备份 → 蓝奏云「D1备份」文件夹（每日一份，滚动保留 N 份）。

===============================================================================
2026-11-04 重写：上传就是一步，别再绕
===============================================================================
上一版绕了远路（先传根目录 → task=20 移动 → 回读），原因是我漏了 multipart
里的 **folder_id_bb_n** 字段。实测（tmp/lanzou_probe.py，2026-11-04 22:48）：
    带上 folder_id_bb_n=<folder_id> 后，html5up.php 直接把文件落进目标文件夹，
    根目录不留残留、不需要移动、不需要事后修。
这个写法与 DDT挂机脚本/工具/lanzou_update.py 完全一致（那边日常用了很久）。
⇒ 本脚本现在：探活 → (同名先删) → 直传进夹 → 回读校验 → 滚动保留。

同理，列目录也不必再抓 vei 一次性签名：只要请求头同时带
    Referer: https://pc.woozooo.com/mydisk.php?item=files&action=index
    X-Requested-With: XMLHttpRequest
task=5 + folder_id + pg 就正常返回 zt=1 + text[]（实测同一时刻带 vei 与不带
vei 结果一致）。抓 vei 的路径保留为兜底，仅在首次列目录失败时再试。

仍成立的两条老经验（保留防坑）：
  · 上传端点必须是 pc.woozooo.com/html5up.php，字段 task=1 + vie=2 + ve=2；
    老域名 up.woozooo.com 一律 {"zt":0} 静默失败。
  · 删除必须 task=6 + file_id **单值**；写成 file_id[] 会回「已删除」但文件还在。

取回（下载）走 developer*.lanrar.com，前置阿里云 ESA WAF + 人机验证，脚本取
不回来 ⇒ 本脚本只负责「存」，取回由人工在网页点（文件夹密码 6wvi）。

===============================================================================
Cookie 失效告警（2026-11-04 新增）
===============================================================================
Cookie 过期是这套备份唯一会「无声失败」的点：步骤本身 continue-on-error，
Actions 红了也不会有人看。所以脚本自己发邮件：
    EMAIL_FROM / EMAIL_AUTH_CODE   发件 QQ 邮箱 + SMTP 授权码
    ALERT_TO                       收件人（缺省 = EMAIL_FROM 自己）
判定依据是接口而不是页面文案：task=5 返回 zt=9 / info 含 login → 判失效。

环境变量：
    LANZOU_COOKIE   必填。整串 cookie（ylogin=...; phpdisk_info=...）
    LANZOU_FOLDER   目标文件夹 id，默认 14198686（「D1备份」）
    LANZOU_UID      默认 1537461
    BACKUP_DIR      本地待上传目录，默认 backup_daily
    LANZOU_KEEP     保留份数，默认 30
    LANZOU_DRY=1    预演，不实际写入
"""

import io
import json
import os
import random
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.utils import formataddr

HOST = "https://pc.woozooo.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
REFERER = HOST + "/mydisk.php?item=files&action=index"

COOKIE = (os.environ.get("LANZOU_COOKIE") or "").strip().strip("'").strip('"')
FOLDER = (os.environ.get("LANZOU_FOLDER") or "14198686").strip()
UID = (os.environ.get("LANZOU_UID") or "1537461").strip()
BACKUP_DIR = (os.environ.get("BACKUP_DIR") or "backup_daily").strip()
KEEP = int(os.environ.get("LANZOU_KEEP") or "30")
DRY = os.environ.get("LANZOU_DRY") == "1"


class AuthError(RuntimeError):
    """Cookie 失效 —— 唯一需要人工介入的故障类型。"""


# --------------------------------------------------------------------------- #
# HTTP 基础设施
# --------------------------------------------------------------------------- #
def _read(r, tries=40):
    buf = bytearray()
    for _ in range(tries):
        chunk = r.read(65536)
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def http(url, data=None, raw=None, ctype=None, retries=3):
    """GET / POST(表单) / POST(multipart 原始体)。断流自动重试。"""
    last = None
    for i in range(retries):
        headers = {"User-Agent": UA, "Cookie": COOKIE, "Referer": REFERER}
        if raw is not None:
            headers["Content-Type"] = ctype
            headers["Origin"] = HOST
            body = raw
        elif data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["X-Requested-With"] = "XMLHttpRequest"
            body = urllib.parse.urlencode(data, doseq=True).encode()
        else:
            body = None
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                return _read(r).decode("utf-8", "replace")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            last = "%s: %s" % (type(e).__name__, e)
            if i < retries - 1:
                print("  ! 第 %d 次请求失败（%s），重试" % (i + 1, last))
                time.sleep(3 * (i + 1))
    raise RuntimeError("请求失败 %s：%s" % (url, last))


def api(data, auth_strict=True):
    """doupload.php —— 蓝奏云的「后台」接口，全部 task 都走这里。"""
    txt = http(HOST + "/doupload.php?uid=" + UID, data=data)
    try:
        d = json.loads(txt)
    except ValueError:
        # 掉登录时整页跳转登录页，返回 HTML
        if auth_strict and ("login" in txt.lower() or "登录" in txt):
            raise AuthError("接口返回登录页（cookie 已失效）：" + txt[:120])
        raise RuntimeError("非 JSON 响应：" + txt[:200])
    if auth_strict:
        info = str(d.get("info") or "")
        if d.get("zt") == 9 or "login" in info.lower():
            raise AuthError("接口判定未登录：%s" % json.dumps(d, ensure_ascii=False)[:200])
    return d


# --------------------------------------------------------------------------- #
# 核心动作
# --------------------------------------------------------------------------- #
def check_login():
    """先探活再干活。cookie 过期是这套备份最可能的无声故障。"""
    if not COOKIE:
        raise AuthError("没配 LANZOU_COOKIE")
    if "ylogin" not in COOKIE or "phpdisk_info" not in COOKIE:
        raise AuthError("LANZOU_COOKIE 缺 ylogin/phpdisk_info，不是完整登录态")
    d = api({"task": "5", "folder_id": "-1", "pg": "1"})
    if d.get("zt") != 1:
        raise AuthError("探活失败：%s" % json.dumps(d, ensure_ascii=False)[:200])
    print("[lanzou] cookie 有效")
    return True


def _vei(folder):
    """兜底用：页面级一次性签名。正常路径不再需要。"""
    html = http("%s/mydisk.php?item=files&action=index&folder_id=%s" % (HOST, folder))
    m = re.search(r"'vei'\s*:\s*'([^']+)'", html)
    if not m:
        raise RuntimeError("抓不到 vei（页面结构变了？）")
    return m.group(1)


def list_files(folder=None):
    """返回 [{id, name, size}]。空文件夹是 zt:2 + text:[]（不是错误）。"""
    folder = folder or FOLDER
    d = api({"task": "5", "folder_id": folder, "pg": "1"})
    if d.get("zt") not in (1, 2):
        # 兜底：老路径（带 vei）
        d = api({"task": "5", "folder_id": folder, "pg": "1", "vei": _vei(folder)})
        if d.get("zt") not in (1, 2):
            raise RuntimeError("列目录失败：%s" % json.dumps(d, ensure_ascii=False)[:200])
    out = []
    for it in d.get("text") or []:
        if isinstance(it, dict) and it.get("id"):
            out.append({"id": str(it["id"]),
                        "name": it.get("name_all") or it.get("name") or "",
                        "size": it.get("size") or "",
                        "f_id": it.get("f_id") or ""})
    return out


def upload(name, blob, folder=None):
    """一步传进目标文件夹（folder_id_bb_n）。返回 (file_id, f_id)。"""
    folder = folder or FOLDER
    b = "----WebKitFormBoundary" + "".join(
        random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(16))
    o = io.BytesIO()
    for k, v in (("task", "1"), ("vie", "2"), ("ve", "2"),
                 ("folder_id_bb_n", folder), ("name", name)):
        o.write(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (b, k, v)).encode())
    o.write(("--%s\r\nContent-Disposition: form-data; name=\"upload_file\"; "
             "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
             % (b, name)).encode())
    o.write(blob)
    o.write(("\r\n--%s--\r\n" % b).encode())

    txt = http(HOST + "/html5up.php", raw=o.getvalue(),
               ctype="multipart/form-data; boundary=" + b)
    try:
        d = json.loads(txt)
    except ValueError:
        raise RuntimeError("上传返回非 JSON：" + txt[:200])
    if d.get("zt") != 1:
        info = str(d.get("info") or "")
        if d.get("zt") == 9 or "login" in info.lower():
            raise AuthError("上传被判定未登录：" + json.dumps(d, ensure_ascii=False)[:200])
        raise RuntimeError("上传失败：%s" % json.dumps(d, ensure_ascii=False)[:200])
    it = (d.get("text") or [{}])[0]
    return str(it.get("id") or ""), it.get("f_id") or ""


def delete(file_id):
    """task=6 + file_id 单值。不能用 file_id[]（会静默失败）。"""
    d = api({"task": "6", "file_id": file_id})
    if d.get("zt") != 1:
        raise RuntimeError("删除失败：%s" % json.dumps(d, ensure_ascii=False)[:200])


# --------------------------------------------------------------------------- #
# 邮件告警
# --------------------------------------------------------------------------- #
def send_alert(subject, body):
    frm = (os.environ.get("EMAIL_FROM") or "").strip()
    code = (os.environ.get("EMAIL_AUTH_CODE") or "").strip()
    to = (os.environ.get("ALERT_TO") or frm).strip()
    if not (frm and code and to):
        print("[alert] 未配置 EMAIL_FROM/EMAIL_AUTH_CODE/ALERT_TO，跳过邮件")
        print("[alert] 原定发送：%s" % subject)
        return False
    tag = (os.environ.get("ALERT_TAG") or "").strip()
    if tag:
        subject = "%s %s" % (tag, subject)   # 仅本地演练用，Actions 里不设
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("D1备份-蓝奏云", frm))
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as s:
            s.login(frm, code)
            s.sendmail(frm, [to], msg.as_string())
        print("[alert] 已发邮件 → %s：%s" % (to, subject))
        return True
    except Exception as e:
        print("[alert] 邮件发送失败：%s" % e)
        return False


def alert_body(headline, detail):
    run = (os.environ.get("GITHUB_SERVER_URL") or "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY") or "xm921016/cron-relay"
    rid = os.environ.get("GITHUB_RUN_ID") or ""
    link = "%s/%s/actions/runs/%s" % (run, repo, rid) if rid else "%s/%s/actions" % (run, repo)
    return "\n".join([
        headline,
        "",
        "时间：%s（北京时间）" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "",
        "详情：",
        detail,
        "",
        "影响范围：",
        "  · 号池数据仍在 5 个 GitHub 私库（vault）里，每天一份、各留 30 份 —— 备份没丢。",
        "  · 只是蓝奏云这第三条腿（异供应商）今天没存上。",
        "",
        "怎么修（蓝奏云 Cookie 过期时）：",
        "  1) 浏览器打开 https://pc.woozooo.com 确认已登录（账号 ylogin=1537461）",
        "  2) F12 → Console → 输入 document.cookie → 复制整串",
        "  3) 覆盖保存到 D:\\Installer\\DDT\\vibecoding\\网易云播放量\\蓝奏云cookie.txt",
        "  4) 跑：python tmp\\set_lanzou_secret.py   （把新 cookie 写进仓库 Secret）",
        "  5) 下次 d1-daily 自动恢复；也可手动 workflow_dispatch 立刻验一次",
        "",
        "运行记录：%s" % link,
    ])


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    print("[lanzou] 目标文件夹 id=%s，保留 %d 份，%s"
          % (FOLDER, KEEP, "预演模式" if DRY else "实际写入"))

    check_login()
    local = []
    if os.path.isdir(BACKUP_DIR):
        for fn in sorted(os.listdir(BACKUP_DIR)):
            if fn.endswith(".enc"):
                local.append(fn)
    if not local:
        print("[lanzou] %s 里没有 .enc，跳过" % BACKUP_DIR)
        return 0
    print("[lanzou] 本地待上传 %d 份：%s" % (len(local), ", ".join(local)))

    existing = list_files(FOLDER)
    print("[lanzou] 云端现有 %d 份" % len(existing))

    # ---- 上传（同名先删，保证每天只有一份、可重跑） ----
    for fn in local:
        path = os.path.join(BACKUP_DIR, fn)
        blob = open(path, "rb").read()
        same = [f for f in existing if f["name"] == fn]
        if same:
            if DRY:
                print("[lanzou] 预演：%s 已存在（id=%s），会先删再传" % (fn, same[0]["id"]))
                continue
            for f in same:
                delete(f["id"])
                print("[lanzou] 已删旧同名 %s (id=%s)" % (fn, f["id"]))
            existing = [f for f in existing if f["name"] != fn]
        if DRY:
            print("[lanzou] 预演：会上传 %s (%d B)" % (fn, len(blob)))
            continue

        fid, f_id = upload(fn, blob)
        if not fid:
            raise RuntimeError("上传 %s 没拿到文件 id" % fn)
        print("[lanzou] 已上传 %s → id=%s f_id=%s (%d B)" % (fn, fid, f_id, len(blob)))
        # 回读校验：确认它真的落在目标文件夹里（而不是根目录）
        now = list_files(FOLDER)
        got = [f for f in now if f["id"] == fid]
        if not got:
            raise RuntimeError("上传后回读不到 %s（id=%s），可能落在根目录了" % (fn, fid))
        print("[lanzou] 回读确认在「D1备份」：%s  %s  f_id=%s"
              % (fn, got[0]["size"], got[0].get("f_id") or f_id))
        existing = now

    # ---- 滚动保留 ----
    now = list_files(FOLDER)
    named = [f for f in now if re.match(r"^d1-\d{4}-\d{2}-\d{2}", f["name"])]
    named.sort(key=lambda x: x["name"], reverse=True)     # 文件名带日期，倒序即新旧
    other = [f for f in now if f not in named]
    if other:
        print("[lanzou] 文件夹里还有 %d 个非本体系文件，不动它们：%s"
              % (len(other), ", ".join(f["name"] for f in other[:5])))
    drop = named[KEEP:]
    print("[lanzou] 滚动：共 %d 份，保留 %d 份，待删 %d 份"
          % (len(named), min(len(named), KEEP), len(drop)))
    for f in drop:
        if DRY:
            print("[lanzou] 预演：会删 %s (id=%s)" % (f["name"], f["id"]))
            continue
        delete(f["id"])
        print("[lanzou] 已删过期 %s (id=%s)" % (f["name"], f["id"]))

    final = list_files(FOLDER)
    print("[lanzou] 完成。云端共 %d 份：" % len(final))
    for f in sorted(final, key=lambda x: x["name"], reverse=True):
        print("    %-34s %-8s id=%-12s f_id=%s"
              % (f["name"], f["size"], f["id"], f.get("f_id") or "-"))
    return 0


if __name__ == "__main__":
    # --test-alert：只验证「告警邮件能不能发出去」，不探活、不上传。
    # 邮件通道一年也用不到几次，没有这个开关的话，真到 Cookie 过期那天才发现
    # 发信凭据也一起废了。用法见 .github/workflows/d1-daily.yml 的 test_alert 输入。
    if "--test-alert" in sys.argv:
        os.environ.setdefault("ALERT_TAG", "【测试】")
        ok = send_alert(
            "[告警] 蓝奏云 Cookie 已失效 —— D1 备份今天没存进蓝奏云",
            alert_body(
                "这是一封演练邮件（--test-alert），不是真的出事。",
                "触发方式：workflow_dispatch 勾选 test_alert，或本地 "
                "python lanzou_push.py --test-alert\n"
                "它能送到，说明真出问题时你也会收到同样的一封。"))
        raise SystemExit(0 if ok else 1)
    if "--alert-failure" in sys.argv:
        # 由 d1-daily.yml 的 if: failure() 步骤调用：导出/推私库那几步挂了，
        # 蓝奏云这步根本没文件可传，但「今天没备份」比「蓝奏云没存上」更要紧。
        os.environ.setdefault("ALERT_TAG", "")
        step = (os.environ.get("FAILED_STEP") or "导出 D1 或分发私库").strip()
        ok = send_alert(
            "[告警] D1 每日备份整体失败 —— 今天没有新增备份",
            alert_body(
                "d1-daily 这个 job 红了，失败发生在：「%s」之前的步骤。" % step,
                "蓝奏云那一步因此没有文件可传（脚本会打印「没有 .enc，跳过」并算成功，"
                "别被绿色误导）。\n"
                "先看 Actions 日志定位是 Cloudflare 接口报错、还是 5 个私库的 token 失效。"))
        raise SystemExit(0 if ok else 1)
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except AuthError as e:
        print("FAIL(cookie): %s" % e)
        send_alert(
            "[告警] 蓝奏云 Cookie 已失效 —— D1 备份今天没存进蓝奏云",
            alert_body(
                "蓝奏云登录态失效，本次 D1 备份没能上传到「D1备份」文件夹。",
                "原因：%s\n判定：接口 task=5 返回未登录（不是网络抖动，重试也没用）" % e))
        raise SystemExit(2)
    except Exception as e:
        print("FAIL: %s: %s" % (type(e).__name__, e))
        send_alert(
            "[告警] 蓝奏云上传失败 —— D1 备份今天没存进蓝奏云",
            alert_body(
                "蓝奏云备份步骤失败（不一定是 Cookie 问题，可能是网络或接口变动）。",
                "原因：%s: %s" % (type(e).__name__, e)))
        raise SystemExit(1)
