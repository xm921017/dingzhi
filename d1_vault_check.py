# -*- coding: utf-8 -*-
"""D1 备份幂等闸门（2026-11-05 新增）。

为什么要有它
------------
同一份每日备份现在有 4 个触发源，同一天完全可能全部命中：

  1) workflow_run：relay 跑完立刻备份（主力，拿到的是删号后的终态）
  2) schedule 11:40 UTC：relay 整轮被跳过时的兜底
  3) CF cron 发令：relay 没结束、前两个都没跑起来时补一刀
  4) workflow_dispatch：手动

没有闸门的话，每一次都会：重导出 D1（38 次查询 —— 正是 7500 随机报错的来源）
→ 重推 5 个私库（5 个 commit）→ 重传蓝奏云。同名覆盖不坏数据，但纯属浪费，
而且平白多一倍踩雷机会。

判据
----
看 5 个私库 vault 里有没有「北京今天」的 backup/d1-YYYY-MM-DD.json.gz.enc。
文件名日期由 d1_backup.py 用 UTC+8 生成（datetime.utcnow() + 8h），所以判据
和实际落盘的文件名严格一致，不会跨时区错位。

  · 任一存在          → skip=true，本次触发几秒内结束，不占并发、不动数据
  · 全都查不到/查失败 → skip=false，正常干活
  · FORCE=1           → 无条件 skip=false（手动想强制重跑时用）

语义提醒：判据是「今天有备份」，不是「今天 5/5 都齐」。只能写进 1 个库说明
另外 4 个账号的 token 挂了，重跑也补不上，要人修 —— 所以这里只打 warning，
不因此重跑，避免每天白白多跑一轮。

只读：本脚本只发 GET，没有任何写操作。

环境变量
--------
  VAULT_TOKENS  多行文本，每行 `<owner> <token>`（与 d1_vault_push.py 同一份 secret）
  VAULT_REPO    vault 仓名，默认 vault
  VAULT_BRANCH  分支，默认 main
  FORCE         1/true 则跳过闸门

输出（写入 $GITHUB_OUTPUT）
--------
  skip   true / false
  have   有今天备份的账号数
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UA = "d1-vault-check/1.0"
REPO = (os.environ.get("VAULT_REPO") or "vault").strip() or "vault"
BRANCH = (os.environ.get("VAULT_BRANCH") or "main").strip() or "main"
SUBDIR = "backup"
FORCE = (os.environ.get("FORCE") or "").strip().lower() in ("1", "true", "yes")


def gh(tok, url):
    """只读 GET，返回 (status, body)。网络异常折算成 status=0，不抛。"""
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok, "User-Agent": UA,
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read()
            return r.status, (json.loads(body.decode()) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}
    except Exception as e:                      # 超时/DNS/SSL 一律当「查不到」
        return 0, {"error": str(e)[:200]}


def parse_targets():
    """与 d1_vault_push.py 完全一致的解析规则：每行 `<owner> <token>`。"""
    raw = os.environ.get("VAULT_TOKENS") or ""
    out = []
    for line in raw.replace("\r", "").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
        else:
            print("  ! 跳过无法解析的行：%s…" % line[:20])
    return out


def today_cn():
    """与 d1_backup.py 同一口径：UTC+8 的自然日。"""
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=8)).date().isoformat()


def main():
    day = today_cn()
    fname = "d1-%s.json.gz.enc" % day
    print("[gate] 判据：%s/%s（北京 %s）" % (SUBDIR, fname, day))

    if FORCE:
        print("[gate] FORCE 已开启 → 无视已有备份，强制重跑")
        return report(False, 0)

    targets = parse_targets()
    if not targets:
        # 没有凭据就无法判断；宁可多跑一次备份，也不能因为闸门判定不了就跳过
        print("::warning::[gate] 缺 VAULT_TOKENS，无法判断今天是否已备份 → 按「未备份」继续")
        return report(False, 0)

    have, checked, broken, unknown = 0, 0, [], []
    for owner, tok in targets:
        s, d = gh(tok, "%s/repos/%s/%s/contents/%s?ref=%s"
                  % (API, owner, REPO, SUBDIR, BRANCH))
        if s == 200 and isinstance(d, list):
            checked += 1
            names = [x.get("name") for x in d if x.get("type") == "file"]
            if fname in names:
                have += 1
                print("  ✓ %s/vault 已有今天的备份（共 %d 份）" % (owner, len(names)))
            else:
                latest = max([n for n in names if n.endswith(".enc")] or ["—"])
                print("  · %s/vault 没有今天的备份（最新 %s）" % (owner, latest))
        elif s == 404:
            checked += 1
            print("  · %s/vault 还没建（或 backup/ 目录不存在）" % owner)
        elif s in (401, 403):
            broken.append("%s(HTTP %d)" % (owner, s))
            print("  ! %s token 失效 HTTP %d —— 这个账号的备份腿断了" % (owner, s))
        else:
            unknown.append("%s(HTTP %s)" % (owner, s))
            print("  ! %s 查询失败 HTTP %s: %s" % (owner, s, str(d.get("error", ""))[:80]))

    if broken:
        print("::warning::[gate] %d 个账号 token 失效：%s —— 备份只落在其余账号，建议尽快换 token"
              % (len(broken), ", ".join(broken)))
    if unknown:
        print("::warning::[gate] %d 个账号查询失败（网络/API 抖动）：%s"
              % (len(unknown), ", ".join(unknown)))

    skip = have > 0
    if skip:
        print("[gate] 今天已备份过（%d/%d 个账号有今天的文件）→ 本次触发直接跳过，"
              "不再导 D1、不再推库、不再传蓝奏云" % (have, len(targets)))
        if have < len(targets):
            print("::warning::[gate] 只有 %d/%d 个账号有今天的备份，其余缺失是 token 问题，"
                  "重跑补不上，请换 token 后手动 dispatch 并勾 force" % (have, len(targets)))
    else:
        print("[gate] %d 个账号都没有今天的备份 → 正常执行备份（已查 %d 个）"
              % (len(targets), checked))
    return report(skip, have)


def report(skip, have):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("skip=%s\n" % ("true" if skip else "false"))
            f.write("have=%d\n" % have)
    else:
        print("[gate] (本地运行，无 GITHUB_OUTPUT) skip=%s have=%d"
              % ("true" if skip else "false", have))


if __name__ == "__main__":
    sys.exit(main() or 0)
