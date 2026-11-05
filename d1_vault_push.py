# -*- coding: utf-8 -*-
"""D1 备份多账号分发（2026-11-04 新增）。

背景 / 为什么要有这个脚本
--------------------------
2026-11-04 之前每日备份只有一份，落在 xm921016/cron-relay 的 Actions artifact 里。
artifact 依附账号，账号一封（xm921018 就是这样没的）备份跟着一起消失 ——
备份和被测系统放在同一个篮子里，等于没备份。

现在改成：每天导出一次 D1，加密后推到 **5 个不同 GitHub 账号各自的私库 vault**，
每个私库滚动保留最近 30 天。任一个账号存活即可取回全量数据。

设计要点
--------
· 不 clone：走 GitHub Contents API 直接 PUT/DELETE，单次运行 5 个仓也就十几个请求。
· 幂等：同一天重复跑会覆盖同名文件（先 GET 取 sha 再 PUT），不会撞冲突。
· 隔离：每个账号独立 try，一个账号 token 失效/仓库被删只影响它自己，其余照常推。
· 滚动保留：按文件名（d1-YYYY-MM-DD）排序删到 KEEP 份，不能用创建时间
  （Contents API 不返回 mtime 的稳定可比语义，文件名排序才是确定的）。
· 只写不读：本脚本绝不删除 D1、绝不动账号池，唯一的写目标是各 vault 仓的 backup/ 目录。

环境变量
--------
  BACKUP_DIR    本地 .enc 所在目录，默认 backup_daily
  VAULT_TOKENS  多行文本，每行 `<owner> <token>`（token 就是该账号的 PAT，需 repo 权限）
  VAULT_REPO    vault 仓名，默认 vault
  VAULT_BRANCH  分支，默认 main
  VAULT_KEEP    保留份数，默认 30
  VAULT_DRY     设 1 则只打印计划不真写（排查用）

单独使用
--------
  python d1_vault_push.py                       # 把 BACKUP_DIR 里的 .enc 分发出去
  python d1_vault_push.py --ensure-repos        # 只补齐缺失的私库，不推文件
"""
import base64
import glob
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
UA = "d1-vault-push/1.0"
OUT_DIR = (os.environ.get("BACKUP_DIR") or "backup_daily").strip()
REPO = (os.environ.get("VAULT_REPO") or "vault").strip()
BRANCH = (os.environ.get("VAULT_BRANCH") or "main").strip()
KEEP = int((os.environ.get("VAULT_KEEP") or "30").strip() or "30")
DRY = (os.environ.get("VAULT_DRY") or "").strip() in ("1", "true", "yes")
SUBDIR = "backup"


def gh(tok, url, method="GET", data=None, raw=False):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + tok, "User-Agent": UA,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
            return r.status, (body if raw else (json.loads(body.decode()) if body else {}))
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        return e.code, {"error": detail}


def parse_targets():
    """解析 VAULT_TOKENS：每行 `<owner> <token>`，忽略空行与 # 注释。"""
    raw = os.environ.get("VAULT_TOKENS") or ""
    out = []
    for line in raw.replace("\r", "").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            print(f"  ! 跳过无法解析的行：{line[:20]}…")
            continue
        out.append((parts[0], parts[1]))
    return out


def ensure_repo(owner, tok):
    """私库不存在就建（private 必须写死 True：备份里有 CK，绝不能落 public）。"""
    s, d = gh(tok, f"{API}/repos/{owner}/{REPO}")
    if s == 200:
        if not d.get("private"):
            print(f"  ! {owner}/{REPO} 是 public，拒绝写入（备份含 CK）")
            return False
        return True
    if s != 404:
        print(f"  ! {owner}/{REPO} 检查失败 HTTP {s}: {d.get('error','')}")
        return False
    if DRY:
        print(f"  [dry] 将新建私库 {owner}/{REPO}")
        return True
    s2, d2 = gh(tok, f"{API}/user/repos", "POST",
                {"name": REPO, "private": True, "auto_init": True,
                 "description": "D1 号池加密备份（每日滚动 30 份）"})
    if s2 in (200, 201):
        print(f"  + 已新建私库 {owner}/{REPO}")
        return True
    print(f"  ! 建库失败 {owner}/{REPO} HTTP {s2}: {d2.get('error','')}")
    return False


def list_backups(owner, tok):
    """返回 backup/ 下已有的 .enc 文件名列表（目录不存在返回空）。"""
    s, d = gh(tok, f"{API}/repos/{owner}/{REPO}/contents/{SUBDIR}?ref={BRANCH}")
    if s == 404:
        return []
    if s != 200 or not isinstance(d, list):
        raise RuntimeError(f"列目录失败 HTTP {s}: {d.get('error', d) if isinstance(d, dict) else d}")
    return sorted(x["name"] for x in d
                  if x.get("type") == "file" and x["name"].endswith(".enc"))


def put_file(owner, tok, name, blob):
    path = f"{SUBDIR}/{name}"
    url = f"{API}/repos/{owner}/{REPO}/contents/{path}"
    # 同名已存在必须带上 sha，否则 GitHub 返回 422
    sha = None
    s, d = gh(tok, f"{url}?ref={BRANCH}")
    if s == 200 and isinstance(d, dict):
        sha = d.get("sha")
    body = {"message": f"backup: {name}", "content": base64.b64encode(blob).decode(),
            "branch": BRANCH}
    if sha:
        body["sha"] = sha
    s2, d2 = gh(tok, url, "PUT", body)
    if s2 in (200, 201):
        return True, "覆盖" if sha else "新增"
    return False, f"HTTP {s2}: {d2.get('error', '')}"


def delete_file(owner, tok, name):
    url = f"{API}/repos/{owner}/{REPO}/contents/{SUBDIR}/{name}"
    s, d = gh(tok, f"{url}?ref={BRANCH}")
    if s != 200 or not isinstance(d, dict):
        return False
    s2, d2 = gh(tok, url, "DELETE",
                {"message": f"prune: 超过 {KEEP} 份，删除 {name}",
                 "sha": d["sha"], "branch": BRANCH})
    return s2 in (200, 204)


def main():
    only_repos = "--ensure-repos" in sys.argv
    files = sorted(glob.glob(os.path.join(OUT_DIR, "*.enc")))
    if not only_repos and not files:
        raise SystemExit(f"{OUT_DIR} 下没有 .enc，先跑 d1_backup.py")
    targets = parse_targets()
    if not targets:
        raise SystemExit("缺 VAULT_TOKENS（每行 `<owner> <token>`）")

    print(f"[vault] 目标 {len(targets)} 个账号，仓库 {REPO}，保留 {KEEP} 份"
          f"{'（dry-run）' if DRY else ''}")
    ok, fail = [], []
    for owner, tok in targets:
        print(f"\n== {owner}/{REPO} ==")
        try:
            if not ensure_repo(owner, tok):
                fail.append(owner)
                continue
            if only_repos:
                print("  （只补仓库，不推文件）")
                ok.append(owner)
                continue
            existing = list_backups(owner, tok)
            for p in files:
                name = os.path.basename(p)
                blob = open(p, "rb").read()
                if DRY:
                    print(f"  [dry] 将上传 {name}（{len(blob)/1024:.0f}KB）")
                    continue
                good, how = put_file(owner, tok, name, blob)
                print(f"  {'+' if good else '!'} {name} {how}"
                      f"{'' if good else ''}")
                if not good:
                    raise RuntimeError(f"{name} 上传失败")
            # 滚动保留：按文件名排序，删掉最老的直到剩 KEEP 份
            merged = sorted(set(existing) | {os.path.basename(p) for p in files})
            drop = merged[:-KEEP] if len(merged) > KEEP else []
            for name in drop:
                if DRY:
                    print(f"  [dry] 将删除 {name}")
                    continue
                print(f"  - 删除 {name}：{'ok' if delete_file(owner, tok, name) else '失败'}")
            print(f"  = 现有 {min(len(merged), KEEP)} 份")
            ok.append(owner)
        except Exception as e:
            print(f"  ! {owner} 失败：{e}")
            fail.append(owner)

    print(f"\n[vault] 成功 {len(ok)}/{len(targets)}：{', '.join(ok) or '-'}")
    if fail:
        print(f"[vault] 失败：{', '.join(fail)}")
        # 只有全军覆没才算致命；单点失败不拦工作流（备份宁可 4/5 也不要 0/5）
        if len(ok) == 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
