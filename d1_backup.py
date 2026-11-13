# -*- coding: utf-8 -*-
"""D1 账号池自动备份（2026-10-22 新增）。

背景：2026-10-22 起账号池的权威数据（accounts / snapshots / kv_misc）只在 Cloudflare D1 里，
KV 只是双写备份，GitHub Secrets 分片已降级为只读回退。D1 是单点，必须有独立备份。

做四件事：
  1) 导出 schema（sqlite_master 里的建表/建索引 DDL）—— 灾难恢复时「先建表」的唯一依据；
  2) 通过 Cloudflare D1 HTTP API 导出 accounts / snapshots / kv_misc / dead_log 四张表为 JSON；
  3) gzip 后用 openssl aes-256-cbc 加密（备份里有明文 CK，绝不能以明文落在 public 仓库）；
  4) 输出到指定目录，由工作流提交进仓库 backup/ 并上传 artifact。

2026-10-29 新增「空库护栏」：
  账号池现有 480+ 个号，若某次导出只有个位数甚至 0 行，说明 CF_TOKEN/D1_UUID 指错了库、
  或 D1 真的被清空了。以前这种情况会「成功」生成一份空备份并提交进 backup/，
  于是最新那份备份就是空气 —— 真要回滚时取「本轮那份」会拿到空库。现在直接失败、不落盘。

环境变量：
  CF_TOKEN        Cloudflare API 令牌（需 D1 读权限）
  CF_ACCOUNT_ID   账户 ID
  D1_UUID         D1 数据库 uuid（不填用默认 netpool）
  BACKUP_PASS     加密口令（GitHub Secret；丢了就解不开，务必与本地保管的一致）
  BACKUP_DIR      输出目录，默认 backup
  BACKUP_MIN_ACCOUNTS  空库判定阈值，默认 50（号池正常 480+，留足余量）

用法：
  python d1_backup.py                # 备份到今天
  python d1_backup.py --no-encrypt   # 本地排查用，输出明文 json.gz（慎用）
"""
import datetime
import gzip
import json
import os
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

ACC = os.environ.get("CF_ACCOUNT_ID", "").strip() or "c60450bfb7f2c2becfd744ba2508a4f2"
D1_UUID = (os.environ.get("D1_UUID", "").strip()
           or "54f742fc-5f56-4723-a7a0-a832953d38c7")
TOK = (os.environ.get("CF_TOKEN", "") or "").strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
OUT_DIR = os.environ.get("BACKUP_DIR", "backup").strip() or "backup"
# 空库护栏阈值（2026-10-29 新增）。号池正常 480+，50 已留足余量；
# 真要备份一个刚建的空库做测试，用 BACKUP_MIN_ACCOUNTS=0 显式放开。
try:
    MIN_ACCOUNTS = int((os.environ.get("BACKUP_MIN_ACCOUNTS") or "50").strip())
except ValueError:
    MIN_ACCOUNTS = 50

# 账号池全字段（含 ck，恢复时必需）
# 2026-10-27：加 agent / plan（客服 + 套餐）。少备这两列的话，恢复一次客服归属就全没了。
# 2026-11-04：补齐 suspect_at / pub / relogin_at。
# 漏 pub 的后果最严重：恢复后公益号（pub=1）会变回正常号，去签到、发笔记、进互听环；
# 漏 suspect_at 会让「判死加固」的存疑标记全丢；漏 relogin_at 会让复登闭环的名单归零。
# 2026-11-05：加 rb / rb_from / rb_start（补号标记 + 关联原单 + 原单登记日）。
# 漏了会把「哪些是免费补号、不参与提成」的标记全丢 → 补号当月被按正常单多结一次提成。
COLS = ["pool", "uid", "name", "song", "ck", "added", "exp", "no_listen",
        "email", "updated_at", "note", "suspect_at", "agent", "plan",
        "pub", "relogin_at", "rb", "rb_from", "rb_start"]
PAGE = 200          # 单次查询行数，避免 D1 HTTP 响应过大被截断
SNAP_DAYS = 60      # 快照只备最近 60 天（控制台最多回看 90 天，够用）
RETRY = 4           # 单条查询最多尝试次数（含首次）
RETRY_WAIT = [3, 8, 20]   # 每次重试前等几秒


def api(sql, params=None, label="query"):
    """查一次 D1，带重试。

    2026-11-05 教训：D1 的 `internal error / code 7500 / e_vBhBOP_*` 不是「数据坏了」也不是
    「分页写错了」—— 它会**随机**打在某一次查询上（改游标后照样本月 05 号凌晨又挂一次），
    同一条 SQL 隔几秒重发就成功。以前一次失败就直接 SystemExit，整条备份链当天归零。
    所以这里的策略是：**只对 5xx / 7500 / 网络异常重试**，4xx 参数类错误立刻抛。
    报错信息带上 label（schema / accounts 第N页 / snapshots 第N页…），
    下次再挂日志里就能一眼看出是哪张表哪一页 —— 之前因为没 label，只能靠猜。
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/d1/database/{D1_UUID}/query"
    body = {"sql": sql}
    if params:
        body["params"] = params
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": "Bearer " + TOK, "User-Agent": UA,
                 "Content-Type": "application/json"})
    last_err, transient = "", True
    for attempt in range(RETRY):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last_err, transient = f"HTTP {e.code}: {e.read().decode()[:500]}", e.code >= 500
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err, transient = f"网络异常: {e}", True
        else:
            if d.get("success"):
                res = d.get("result") or []
                return (res[0].get("results") or []) if res else []
            last_err = json.dumps(d.get("errors"), ensure_ascii=False)[:500]
            transient = "7500" in last_err or "internal error" in last_err
        if not transient or attempt == RETRY - 1:
            break
        wait = RETRY_WAIT[min(attempt, len(RETRY_WAIT) - 1)]
        print(f"::warning::D1 查询失败（{label}，第 {attempt + 1} 次）：{last_err[:200]}"
              f" —— {wait}s 后重试")
        time.sleep(wait)
    raise SystemExit(f"D1 查询失败（{label}）: {last_err}")


def dump_schema():
    """建表 / 建索引 DDL（2026-10-29 新增）。

    为什么必须备：schema 原本只活在 Cloudflare 那一个活着的库里，仓库和文档里一句
    CREATE TABLE 都没有。D1 一旦被删或重建，光有数据备份也灌不回去 —— 表都不存在。
    现在每次备份都捎带一份，恢复时 --tables schema 先建表再灌数据。
    """
    try:
        return api("SELECT type,name,tbl_name,sql FROM sqlite_master "
                   "WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%' "
                   "AND sql IS NOT NULL "
                   "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name",
                   label="schema")
    except SystemExit as e:
        # schema 拿不到不该阻断数据备份（数据更要紧），但要吼一声
        print(f"::warning::schema 导出失败，本次备份不含建表语句：{e}")
        return []


def dump_accounts():
    # OFFSET 分页在这里仍然安全：号池 660~1200 行，最大 OFFSET 不过 1000，
    # 远离 D1 那条 5800 的暗线（见 dump_snapshots 的注释）。号池若涨到 5000+
    # 必须一并改成游标分页。
    rows = []
    off = 0
    while True:
        page = off // PAGE + 1
        part = api(f"SELECT {','.join(COLS)} FROM accounts ORDER BY pool, uid LIMIT ? OFFSET ?",
                   [PAGE, off], label=f"accounts 第{page}页")
        rows.extend(part)
        if len(part) < PAGE:
            break
        off += PAGE
    print(f"[backup] accounts 取完 {len(rows)} 行（{off // PAGE + 1} 次查询）")
    return rows


def dump_snapshots():
    """按 (day,pool,uid) 游标翻页 —— 不要用 OFFSET。

    2026-11-04 踩的坑：D1 的 HTTP 接口在 **OFFSET ≥ 5800** 时直接返回
    HTTP 500 {"code":7500,"internal error"}（reference e_vBhBOP_*），
    同样的 SQL 换个 OFFSET 就正常 —— 既不是网络问题，也不是库坏了。
    当天 relay 跑完快照 6119 行，翻页到 OFFSET 5800 正好踩雷，导出连续
    两次全挂（先误判成 Cloudflare 故障，本地复现才定位）。
    游标翻页没有这个上限，且不用让数据库扫过前面所有行。

    2026-11-05 补记：改成游标后 05 号凌晨 02:51 那次又挂了同样的 7500，
    说明 7500 不只由 OFFSET 触发（同一条 SQL 隔几秒重发就成功）。
    所以「页级重试」才是真正的兜底，本函数顺便逐页打点，
    再挂时日志能直接指出是第几页。
    """
    since = (datetime.date.today() - datetime.timedelta(days=SNAP_DAYS)).isoformat()
    cols = "day,pool,uid,name,rate,rpc30,missions,dur,at,cnt"
    rows = []
    last = None
    page = 0
    while True:
        page += 1
        if last is None:
            part = api(f"SELECT {cols} FROM snapshots WHERE day >= ? "
                       "ORDER BY day, pool, uid LIMIT ?", [since, PAGE],
                       label=f"snapshots 第{page}页")
        else:
            part = api(f"SELECT {cols} FROM snapshots WHERE day >= ? "
                       "AND (day, pool, uid) > (?, ?, ?) "
                       "ORDER BY day, pool, uid LIMIT ?",
                       [since, last[0], last[1], last[2], PAGE],
                       label=f"snapshots 第{page}页(游标 {last})")
        rows.extend(part)
        print(f"[backup] snapshots 第{page}页 {len(part)} 行，累计 {len(rows)}")
        if len(part) < PAGE:
            break
        nxt = (part[-1]["day"], part[-1]["pool"], part[-1]["uid"])
        if nxt == last:          # 理论上不会发生；真卡住就退出，别死循环
            print("::warning::快照游标没有前进（%s），提前结束翻页" % (nxt,))
            break
        last = nxt
    return rows


def dump_misc():
    try:
        return api("SELECT k,v,updated_at FROM kv_misc", label="kv_misc")
    except SystemExit:
        return []


def dump_dead():
    """失效账号流水（含清理原因/时间）——恢复时能看出哪些号是确认死号、不要往回捞。"""
    try:
        return api("SELECT id,pool,uid,name,reason,at FROM dead_log ORDER BY id DESC LIMIT 2000",
                   label="dead_log")
    except SystemExit:
        return []


def dump_ledger():
    """记账流水（2026-11-05 新增表）。

    这张表是「成交台账」：登记那一刻写一笔，删号/改套餐/改客服都不动它。
    控制台月度结算全靠它，丢了就没法回溯历史月份的账 → 跟 accounts 同级别必须备。
    表可能还不存在（老库），失败只警告不阻断。
    """
    rows = []
    off = 0
    try:
        while True:
            page = off // PAGE + 1
            part = api(f"SELECT id,pool,uid,name,agent,plan,price,days,day,start,exp,"
                       "rb,rb_from,remark,src,at FROM ledger ORDER BY id LIMIT ? OFFSET ?",
                       [PAGE, off], label=f"ledger 第{page}页")
            rows.extend(part)
            if len(part) < PAGE:
                break
            off += PAGE
    except SystemExit as e:
        print(f"::warning::ledger 导出失败（记账流水未备份）：{e}")
        return []
    print(f"[backup] ledger 取完 {len(rows)} 行")
    return rows


# ---------------------------------------------------------------------------
# 2026-11-09：主路径改成 /export（整库 SQL dump），彻底绕开 rows_read 配额
#
# 起因：11-08 当天 D1 日读额度被打满（244%），d1-daily-vault 在「导出 D1 并加密」
# 这一步直接失败（errors code 7500），一天的备份链归零。根因是这里全走分页 SELECT，
# 而 D1 的 rows_read 是「扫描行数」—— OFFSET 分页 + 大表游标翻页都会把整表反复扫。
# 实测 11-09 00:20 那一个 5 分钟桶就烧了 35.7 万行 / 99 次查询（约 3600 行/次）。
#
# Cloudflare 的 D1 /export 接口返回 R2 签名地址上的整库 SQL dump，**不计 rows_read**。
# 拿回来往内存 sqlite 里 executescript（实测全库 6.3MB / 0.2 秒），
# 之后所有表的 SELECT 全在本地做，D1 一次都不读。
# 保留原分页函数作为兜底：/export 挂掉时自动回退，行为与改前一致。
# ---------------------------------------------------------------------------

SNAP_COLS = "day,pool,uid,name,rate,rpc30,missions,dur,at,cnt"
LEDGER_COLS = ("id,pool,uid,name,agent,plan,price,days,day,start,exp,"
               "rb,rb_from,remark,src,at")


def export_sql():
    """调 /export 拿整库 SQL 文本。不吃 rows_read 配额。

    R2 签名地址在本机会被 schannel 的「吊销列表离线」卡住，所以用跳过校验的
    context；这段与 tmp/d1_mirror.py 里验证过的实现保持一致。
    """
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/d1/database/{D1_UUID}"
    req = urllib.request.Request(
        base + "/export",
        data=json.dumps({"output_format": "file"}).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + TOK, "User-Agent": UA,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    if not d.get("success"):
        raise RuntimeError("导出失败：%s" % json.dumps(d.get("errors"), ensure_ascii=False)[:300])
    url = d["result"]["signed_url"]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}),
            timeout=240, context=ctx) as r:
        buf, total = [], 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            buf.append(chunk)
            total += len(chunk)
    return b"".join(buf).decode("utf-8", "replace"), total


def load_mem_db(sql_text):
    """把整库 dump 装进内存 sqlite。返回 connection。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.executescript(sql_text)
    return conn


def _sel(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [x[0] for x in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def dump_all_via_export():
    """一次 /export 拿全部五张表 + schema。失败抛异常，由 main 决定是否回退。"""
    t0 = time.time()
    sql_text, nbytes = export_sql()
    conn = load_mem_db(sql_text)
    try:
        schema = _sel(conn, "SELECT type,name,tbl_name,sql FROM sqlite_master "
                            "WHERE sql IS NOT NULL")
        since = (datetime.date.today() - datetime.timedelta(days=SNAP_DAYS)).isoformat()
        accounts = _sel(conn, "SELECT %s FROM accounts ORDER BY pool, uid"
                        % ",".join('"%s"' % c for c in COLS))
        snapshots = _sel(conn, "SELECT %s FROM snapshots WHERE day >= ? "
                               "ORDER BY day, pool, uid" % SNAP_COLS, (since,))
        misc = _sel(conn, "SELECT k,v,updated_at FROM kv_misc")
        dead = _sel(conn, "SELECT id,pool,uid,name,reason,at FROM dead_log "
                          "ORDER BY id DESC LIMIT 2000")
        ledger = _sel(conn, "SELECT %s FROM ledger ORDER BY id" % LEDGER_COLS)
    finally:
        conn.close()
    print(f"[backup] /export 完成：{nbytes/1024:.0f}KB SQL、耗时 {time.time()-t0:.1f}s，"
          f"本地解析出 accounts {len(accounts)} / snapshots {len(snapshots)} / "
          f"misc {len(misc)} / dead {len(dead)} / ledger {len(ledger)} / schema {len(schema)}"
          f"（D1 rows_read 消耗 0）")
    return schema, accounts, snapshots, misc, dead, ledger


def main():
    if not TOK:
        raise SystemExit("缺 CF_TOKEN")
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).date().isoformat()
    # 主路径：/export 整库 dump，零 rows_read。失败才回退到原来的分页 SELECT。
    # 回退路径在额度打满当天一定还会失败（那也是它存在的意义：报错要具体到哪张表哪一页），
    # 但至少不会因为 /export 单独出问题就没备份。
    try:
        schema, accounts, snapshots, misc, dead, ledger = dump_all_via_export()
    except Exception as e:  # noqa: BLE001
        print(f"::warning::/export 路径失败（{str(e)[:200]}）→ 回退分页 SELECT（会消耗 rows_read）")
        schema = dump_schema()
        accounts, snapshots, misc, dead, ledger = (dump_accounts(), dump_snapshots(),
                                                   dump_misc(), dump_dead(), dump_ledger())

    # 空库护栏（2026-10-29）：宁可这次备份失败变红，也不能让一份空备份顶掉历史备份。
    if not accounts or len(accounts) < MIN_ACCOUNTS:
        raise SystemExit(
            f"备份异常：accounts 只导出 {len(accounts)} 行（阈值 {MIN_ACCOUNTS}），拒绝生成备份。\n"
            f"  多半是 CF_TOKEN / D1_UUID 指错了库，或 D1 真被清空了。\n"
            f"  确认无误（例如确实要备一个空库）请设 BACKUP_MIN_ACCOUNTS=0 重跑。")
    if not snapshots:
        # 快照为 0 不影响账号池恢复，只警告：数据备份优先级高于报表数据
        print("::warning::本次 snapshots 导出 0 行（快照任务可能没跑），账号池备份照常生成")

    by_pool = {}
    for r in accounts:
        by_pool[r.get("pool")] = by_pool.get(r.get("pool"), 0) + 1
    payload = {
        "meta": {"date": today, "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
                 "d1_uuid": D1_UUID, "accounts": len(accounts),
                 "by_pool": by_pool, "snapshots": len(snapshots), "misc": len(misc),
                 "dead_log": len(dead), "schema": len(schema),
                 "ledger": len(ledger),
                 "snap_days": SNAP_DAYS},
        "schema": schema,
        "accounts": accounts,
        "snapshots": snapshots,
        "kv_misc": misc,
        "dead_log": dead,
        "ledger": ledger,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz_path = os.path.join(OUT_DIR, f"d1-{today}.json.gz")
    with gzip.open(gz_path, "wb", compresslevel=9) as f:
        f.write(raw)
    print(f"[backup] 导出 {len(accounts)} 个号（{by_pool}）、{len(snapshots)} 条快照、"
          f"{len(misc)} 条 misc、{len(dead)} 条死号流水、{len(ledger)} 条记账流水、"
          f"{len(schema)} 条 schema → {os.path.getsize(gz_path)/1024:.0f}KB")

    if "--no-encrypt" in sys.argv:
        print("[backup] 明文模式（仅排查用）：", gz_path)
        return

    pwd = (os.environ.get("BACKUP_PASS") or "").strip()
    if not pwd:
        # 没有口令就不落地明文：直接失败，让工作流报警，避免 CK 明文进仓库
        os.remove(gz_path)
        raise SystemExit("缺 BACKUP_PASS：拒绝以明文形式保存含 CK 的备份")
    enc_path = gz_path + ".enc"
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
         "-in", gz_path, "-out", enc_path, "-pass", "env:BACKUP_PASS"],
        check=True, env={**os.environ, "BACKUP_PASS": pwd})
    os.remove(gz_path)
    print(f"[backup] 已加密 → {enc_path}（{os.path.getsize(enc_path)/1024:.0f}KB）")


if __name__ == "__main__":
    main()
