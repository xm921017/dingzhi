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
（跟播放轮一片 6 个号同时播比，这点压力可以忽略），改成 SNAP_WORKERS（默认 4）个线程同时查，
全池压到 5 分钟左右。攒满一批仍然立刻上报，写侧锁保护，读侧 rpc30 大者胜保证幂等。

数据流：GET /api/assign?job=0&jobs=1（当天的 D1 轮转计划，含 ck/email）
       → 逐号 Client(ck).workbench_info() → 攒满 SNAP_BATCH 个就 POST 一批
       → POST /api/snap {pool, slice:'am', date:北京今天, accs}。

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
SNAP_BATCH = max(1, int(os.environ.get("SNAP_BATCH", "50") or 50))
# 并发线程数（2026-10-26）：4 个线程查工作台，全池约 5 分钟（串行要 19 分钟）。
# 不建议超过 6：同一出口 IP 并发太高容易触发接口限流，收益也不大（瓶颈是单次请求耗时）。
SNAP_WORKERS = max(1, int(os.environ.get("SNAP_WORKERS", "4") or 4))

ASSIGN_PASS = os.environ.get("ASSIGN_PASS", "").strip() or os.environ.get("NB_PASS", "").strip()
SNAP_PASS = os.environ.get("NB_PASS", "").strip()

UA = {"User-Agent": BROWSER_UA, "Accept": "application/json"}


def bj_today():
    return (datetime.utcnow() + timedelta(hours=8)).date().isoformat()


def load_pool():
    """问 worker 要全池（jobs=1 → 全部号一整片，含 ck/email/uid）。失败返回 None。"""
    params = {"job": 0, "jobs": 1, "pass": ASSIGN_PASS, "day": bj_today()}
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

    accs = load_pool()
    if accs is None:
        raise SystemExit(1)
    total = len(accs)
    nb = max(1, (total + SNAP_BATCH - 1) // SNAP_BATCH)
    print(f"[650补采] 全池 {total} 个号，{SNAP_WORKERS} 线程并行查工作台，"
          f"每 {SNAP_BATCH} 个上报一次（共 {nb} 批）…")

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
