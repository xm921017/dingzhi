# -*- coding: utf-8 -*-
"""
目标任务快照上午 10 点补采（2026-10-23 新增）。

背景：凌晨 02:35-05:38 的播放轮顺带采的创作者后台数据，落在目标「结算前」，
控制台日环比会出现「明明涨了却显示 0」的假象（2026-10-23 实锤：9 个对照号里 8 个
其实涨了，只是凌晨采集太早）。本脚本由 GitHub Actions 在北京时间 10:00 触发，
全池重查一次工作台，POST /api/snap（slice=am）补采。

覆盖逻辑：控制台读侧「同号同天 rpc30 更大者胜」（worker.js readSnapDay），
rpc30 是累计值只增不减 → 10 点这份自然覆盖凌晨各片的同号数据；
凌晨之后失效的号仍保留凌晨那份数据，不会丢。

分批上报（2026-10-26 改）：全池一次性上报时，291 个号要串行查 15~25 分钟，
中途任何一段出错这一整批数据全丢，控制台也要等最后一批写完才跳变。
现在每采满 SNAP_BATCH（默认 50）个号就 POST 一次，单批失败只影响那 50 个号；
由于读侧「同号同天 rpc30 大者胜」，分批写与一次性写在结果上完全等价。

并行采集（2026-10-26 改）：原来全池串行，292 个号要 19 分钟；每个号只是发一次只读 GET
（跟播放轮一片 6 个号同时播比，这点压力可以忽略），改成 SNAP_WORKERS（默认 6）个线程同时查，
全池压到 5 分钟左右。攒满一批仍然立刻上报，写侧锁保护，读侧 rpc30 大者胜保证幂等。

数据流：GET /api/assign?job=0&jobs=1（当天的 D1 轮转计划，含 ck/email）
       → 逐号 Client(ck).workbench_info() → 攒满 SNAP_BATCH 个就 POST 一批
       → POST /api/snap {pool, slice:'am', date:北京今天, accs}。

分片采集（2026-10-27 改）：号码池涨到 400+ 之后，单个 runner 用 6 线程连查全池
既要 5 分钟、又是「一个出口 IP 打全部号」，是全项目最集中的查询动作。现在改为由 workflow
按号池人数算出片数 SNAP_JOBS，每个 job 只采第 SNAP_JOB 片（每片约 12 个号、各自独立 runner、
各自独立出口 IP），全池 1 分钟内采完。取号仍走 /api/assign?job=N&jobs=M，worker 侧无需改动。

去重（2026-10-27 改）：采集有两条触发路径——relay 播放轮跑完由 workflow_run 自动触发（主路径），
以及 CF cron 北京 10:00 派发的兜底。兜底那条跑之前先问 GitHub「今天主路径采过没有」，
采过就直接退出（already_collected_today），避免每天白采一次、也避免单 IP 再打一遍全池。

口令：/api/assign 用 ASSIGN_PASS（回明文 CK 的接口不能用群口令）；
     /api/snap 用 NB_PASS（本群群口令；dz 仓库的这份发到主群 worker 时，
     对端 PEER_PASS 存的就是 dz 群口令，鉴权口径与 run.py 完全一致）。
失败不影响任何主任务，本脚本独立运行、不碰播放。
"""
import json
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from run import Client, BROWSER_UA

# 本群 worker（取 D1 分配）；dz 仓库这份默认 https://dingzhi.xx1031.xyz
WORKER_URL = os.environ.get("WORKER_URL", "https://xx1031.xyz").strip()
# 快照归口 worker：两群都发主群（与 run.py 的 SNAP_URL 口径一致）
SNAP_URL = os.environ.get("SNAP_URL", "https://xx1031.xyz").strip()
POOL = os.environ.get("POOL_TAG", "hz").strip() or "hz"
SLICE_TAG = "am"   # 控制台分片维度；固定 am = 上午补采
# 每批上报多少个号（2026-10-26）：50 个号约 3~4 分钟，控制台能较早看到首屏
# 2026-10-26 修复：env 填了非数字（如 "50 " 里的全角空格、写错成 "abc"）原来会直接
# ValueError 让整个快照任务起不来。统一走 _env_int 兜底。
def _env_int(name, default, lo=1, hi=None):
    try:
        v = int(str(os.environ.get(name, "") or default).strip())
    except Exception:
        v = default
    v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


SNAP_BATCH = _env_int("SNAP_BATCH", 50, 1, 500)
# 并发线程数（2026-10-26）：4 个线程查工作台，全池约 5 分钟（串行要 19 分钟）。
# 不建议超过 6：同一出口 IP 并发太高容易触发接口限流，收益也不大（瓶颈是单次请求耗时）。
SNAP_WORKERS = _env_int("SNAP_WORKERS", 6, 1, 16)

# 分片参数（2026-10-27）：全池切成 SNAP_JOBS 片，本进程只采第 SNAP_JOB 片。
# 不设时是 0/1 = 退化成「一个 job 采全池」的老行为，方便回滚。
SNAP_JOB = _env_int("SNAP_JOB", 0, 0, 999)
SNAP_JOBS = _env_int("SNAP_JOBS", 1, 1, 999)
# 去重所需（2026-10-27）：TRIGGER_EVENT 由 workflow 传 github.event_name；
# GH_REPO_SLUG / GH_API_TOKEN 用来查本仓库今天的采集 run（只需 actions:read）。
TRIGGER_EVENT = os.environ.get("TRIGGER_EVENT", "").strip()
GH_REPO_SLUG = os.environ.get("GH_REPO_SLUG", "").strip()
GH_API_TOKEN = os.environ.get("GH_API_TOKEN", "").strip()

ASSIGN_PASS = os.environ.get("ASSIGN_PASS", "").strip() or os.environ.get("NB_PASS", "").strip()
# 2026-10-29：NB_PASS 没配就回退 ASSIGN_PASS（worker 的 /api/snap 两者都认）。
SNAP_PASS = os.environ.get("NB_PASS", "").strip() or ASSIGN_PASS

UA = {"User-Agent": BROWSER_UA, "Accept": "application/json"}


def bj_today():
    return (datetime.utcnow() + timedelta(hours=8)).date().isoformat()


def load_pool():
    """问 worker 要本片要采的号（jobs=SNAP_JOBS → 全池切成 SNAP_JOBS 片，只取第 SNAP_JOB 片）。

    默认 0/1 时等价于老行为「全部号一整片」。worker 侧 /api/assign 用 i % jobs 轮转分配，
    「只收不听」的 idle 号走同一套规则，所以任意片数都不会漏采、也不会重复。
    """
    params = {"job": SNAP_JOB, "jobs": SNAP_JOBS, "pass": ASSIGN_PASS, "day": bj_today()}
    r = requests.get(WORKER_URL.rstrip("/") + "/api/assign", params=params,
                     timeout=90, headers=UA)
    d = r.json()
    if not d.get("ok"):
        print(f"[assign] 服务端返回失败：{d.get('message')}")
        return None
    accs = []
    # 2026-10-26：/api/assign 把「只收不听」的号单独放在 idle 数组里（accounts 只有参与播放轮转的）。
    # 原来只读 accounts → 这些号永远拿不到 10:00 补采，控制台一直显示它们凌晨那份旧快照。
    for a in (d.get("accounts") or []) + (d.get("idle") or []):
        if a.get("ck"):
            accs.append({
                "name": a.get("name") or str(a.get("uid")),
                "uid": a.get("uid"),
                "ck": a.get("ck"),
                "song": str(a.get("song") or ""),
            })
    return accs


def run_snap_stats(run_id):
    """数一次 snapshot run 里「成功的 / 失败的」snap 分片作业，返回 (ok_n, bad_n)。

    作业名形如 "snap (0)"…"snap (34)"，plan 作业不计。被 `if:` 跳过没创建的作业不会出现在
    列表里 —— 正是靠这一点区分「真的采过」和「relay 忙碌导致的空跑」。
    查不到 / 没 token 时返回 (0, 0)，调用方按「没采过」处理（宁可多采一次也不能漏采）。
    """
    if not (run_id and GH_REPO_SLUG and GH_API_TOKEN):
        return 0, 0
    try:
        r = requests.get(
            "https://api.github.com/repos/" + GH_REPO_SLUG + "/actions/runs/" + str(run_id) + "/jobs",
            params={"per_page": 100},
            headers={"Authorization": "Bearer " + GH_API_TOKEN,
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "snapshot-dedupe"},
            timeout=30)
        jobs = (r.json() or {}).get("jobs") or []
    except Exception as e:
        print(f"[650补采] 查 #{run_id} 的分片作业失败（按未采过处理）：{e}")
        return 0, 0
    ok_n = bad_n = 0
    for j in jobs:
        if not str(j.get("name") or "").startswith("snap"):
            continue
        st, cc = j.get("status"), j.get("conclusion")
        if st != "completed":
            continue
        if cc == "success":
            ok_n += 1
        elif cc not in (None, "skipped", "neutral"):
            bad_n += 1
    return ok_n, bad_n


def already_collected_today():
    """兜底路径专用去重（2026-10-27）：今天若已由 relay 跑完自动触发的那一班采过，本次直接跳过。

    只在这两种触发下生效：CF cron 派发的 workflow_dispatch、以及 GitHub 原生 schedule。
    workflow_run（relay 刚跑完）这条主路径永远不跳过，否则会自己把自己判成"已采过"。

    判定只认 event == 'workflow_run' 的 run，且必须是"成功"或"还在跑/排队"：
    - success        → 已经采过了，跳过
    - in_progress    → 主路径正在进行，别重复劳动，跳过
    - failure/cancel → 主路径没成，兜底必须采，不跳过
    查不到（没给 token、API 出错）一律按"没采过"处理，宁可多采一次也不能漏采。
    """
    if TRIGGER_EVENT not in ("schedule", "workflow_dispatch"):
        return False
    if not (GH_REPO_SLUG and GH_API_TOKEN):
        return False
    try:
        r = requests.get(
            "https://api.github.com/repos/" + GH_REPO_SLUG + "/actions/workflows/snapshot.yml/runs",
            params={"per_page": 20},
            headers={"Authorization": "Bearer " + GH_API_TOKEN,
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "snapshot-dedupe"},
            timeout=30)
        runs = (r.json() or {}).get("workflow_runs") or []
    except Exception as e:
        print(f"[650补采] 去重检查失败（按未采过处理）：{e}")
        return False
    today = bj_today()
    for x in runs:
        if x.get("event") != "workflow_run":
            continue
        try:
            bjc = (datetime.fromisoformat(str(x.get("created_at")).replace("Z", "+00:00"))
                   + timedelta(hours=8)).date().isoformat()
        except Exception:
            continue
        if bjc != today:
            continue
        st, cc = x.get("status"), x.get("conclusion")
        if st != "completed":
            print(f"[650补采] 今天由 relay 触发的那一班正在排队/进行中"
                  f"（#{x.get('id')} {st}），本次跳过，不重复采集。")
            return True
        if cc != "success":
            continue                      # 主路径失败/被取消 → 兜底必须采
        # 2026-10-29 修复：conclusion=success 并不代表真采过。relay 还在跑时 snap 各片被 `if:`
        # 整片跳过（job 根本不创建），plan 成功 → run 结论仍是 success；旧逻辑只看 conclusion
        # 就 return True，于是两条兜底全被这次「空跑」挡掉，当天零快照。
        ok_n, bad_n = run_snap_stats(x.get("id"))
        if ok_n <= 0:
            print(f"[650补采] #{x.get('id')} 结论 success 但没有任何成功的 snap 片"
                  f"（成功 {ok_n} / 失败 {bad_n}），判定为 relay 忙碌导致的空跑，继续采集。")
            continue
        if bad_n > 0:
            print(f"[650补采] #{x.get('id')} 有 {bad_n} 片 snap 失败（成功 {ok_n}），"
                  f"判定本次采集不完整，继续采集补齐。")
            continue
        print(f"[650补采] 今天已由 relay 结束触发的那一班采集"
              f"（#{x.get('id')} {st}/{cc}，成功 {ok_n} 片），本次跳过，不重复采集。")
        return True
    return False


def post_batch(metrics, seq, nb):
    """POST 一批快照。成功返回 True。幂等：读侧同号同天 rpc30 大者胜。"""
    try:
        r = requests.post(SNAP_URL.rstrip("/") + "/api/snap", json={
            "pass": SNAP_PASS,
            "pool": POOL,
            "slice": SLICE_TAG,
            "date": bj_today(),
            "accs": metrics,
        }, timeout=60, headers=UA)
        print(f"[650补采] 第 {seq}/{nb} 批（{len(metrics)} 个号）上报: "
              f"HTTP {r.status_code} {r.text[:160]}")
        return r.status_code == 200
    except Exception as e:
        print(f"[650补采] 第 {seq}/{nb} 批（{len(metrics)} 个号）上报失败: {e}")
        return False


def main():
    if not ASSIGN_PASS:
        print("::error::缺 ASSIGN_PASS，无法取号池")
        raise SystemExit(1)
    if not SNAP_PASS:
        print("::error::缺 NB_PASS，无法上报快照")
        raise SystemExit(1)

    if already_collected_today():
        return

    accs = load_pool()
    if accs is None:
        raise SystemExit(1)
    total = len(accs)
    # 分片后的正常现象：号数少于片数时会有片分不到号。这种片必须正常退出（退出码 0），
    # 否则「号池小 + 片数多」会天天红一片。老行为（jobs=1）永远走不到这里。
    if total == 0:
        print(f"[650补采] 本片（{SNAP_JOB + 1}/{SNAP_JOBS}）没分到号，正常退出。")
        return
    nb = max(1, (total + SNAP_BATCH - 1) // SNAP_BATCH)
    print(f"[650补采] 本片（{SNAP_JOB + 1}/{SNAP_JOBS}）{total} 个号，"
          f"{SNAP_WORKERS} 线程并行查工作台，每 {SNAP_BATCH} 个上报一次（共 {nb} 批）…")

    lock = threading.Lock()
    batch = {}
    st = {"seq": 0, "ok": 0, "fail": 0, "picked": 0, "dead": 0, "done": 0}

    def take_batch():
        """把攒满的 batch 摘出来交给上报（必须在锁内调用）。"""
        nonlocal batch
        if not batch:
            return None
        b, batch = batch, {}
        st["seq"] += 1
        return st["seq"], b

    def send(job):
        seq, metrics = job
        ok = post_batch(metrics, seq, nb)
        with lock:
            st["ok" if ok else "fail"] += 1

    def one(e):
        name = e["name"]
        # 单号查询失败（接口超时 / 偶发 5xx）重试一次再判死，避免每天固定漏几个号。
        wb, err = None, None
        for attempt in (1, 2):
            try:
                wb = Client(e["ck"]).workbench_info()
                err = None
            except Exception as ex:
                wb, err = None, ex
            if wb:
                break
            if attempt == 1:
                time.sleep(1.5)
        job = None
        with lock:
            if wb:
                batch[str(e.get("uid") or name)] = dict(wb)
                st["picked"] += 1
            else:
                st["dead"] += 1
                print(f"  [{name}] 工作台无数据（已重试一次），跳过" + (f"：{err}" if err else ""))
            st["done"] += 1
            if len(batch) >= SNAP_BATCH:
                job = take_batch()      # 锁内只摘数据，POST 放到锁外，不阻塞其他线程
            n = st["done"]
        if job:
            send(job)
        if n % 50 == 0:
            print(f"[650补采] 进度 {n}/{total}（采到 {st['picked']} / 无数据 {st['dead']}）")
        # 单个号的节流：每个线程各自随机停 1~2 秒，4 线程合计约 2~3 个/秒
        time.sleep(random.uniform(1, 2))

    with ThreadPoolExecutor(max_workers=SNAP_WORKERS) as ex:
        list(ex.map(one, accs))

    job = None
    with lock:
        job = take_batch()
    if job:
        send(job)

    picked, dead = st["picked"], st["dead"]
    ok_batches, fail_batches = st["ok"], st["fail"]
    print(f"[650补采] 完成：采到 {picked} 个号 / 无数据 {dead} 个 / "
          f"成功 {ok_batches} 批 / 失败 {fail_batches} 批")
    if ok_batches == 0:
        print("::error::所有批次都上报失败")
        raise SystemExit(1)
    if fail_batches:
        print(f"::warning::有 {fail_batches} 批上报失败（其余批已写入，读侧 rpc30 大者胜，不影响已写入部分）")


if __name__ == "__main__":
    main()
