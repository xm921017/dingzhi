# -*- coding: utf-8 -*-
"""
目标任务快照上午 10 点补采（2026-10-23 新增，定制群版）。

背景：凌晨 02:35-05:38 的播放轮顺带采的创作者后台数据，落在目标「结算前」，
控制台日环比会出现「明明涨了却显示 0」的假象（2026-10-23 实锤：9 个对照号里 8 个
其实涨了，只是凌晨采集太早）。本脚本由 GitHub Actions 在北京时间 10:00 触发，
全池重查一次工作台，POST /api/snap（slice=am）补采。

覆盖逻辑：控制台读侧「同号同天 rpc30 更大者胜」（worker.js readSnapDay），
rpc30 是累计值只增不减 → 10 点这份自然覆盖凌晨各片的同号数据；
凌晨之后失效的号仍保留凌晨那份数据，不会丢。

数据流：GET /api/assign?job=0&jobs=1（当天的 D1 轮转计划，含 ck/email）
       → 逐号 Client(ck).workbench_info()
       → POST /api/snap {pool:'dz', slice:'am', date:北京今天, accs}
       → 归口发到主群 worker（与 run.py 的 SNAP_URL 口径一致，对端 PEER_PASS 存 dz 群口令）。

口令：/api/assign 用 ASSIGN_PASS（回明文 CK 的接口不能用群口令）；
     /api/snap 用 NB_PASS（本群群口令）。
失败不影响任何主任务，本脚本独立运行、不碰播放。
"""
import json
import os
import time
import random
from datetime import datetime, timedelta, timezone

import requests

from run import Client, BROWSER_UA

# 本群 worker（取 D1 分配）。2026-10-23：dz.xx1031.xyz 已泄露到用户手上，弃用。
WORKER_URL = os.environ.get("WORKER_URL", "https://dingzhi.xx1031.xyz").strip()
# 快照归口 worker：两群都发主群（与 run.py 的 SNAP_URL 口径一致）
SNAP_URL = os.environ.get("SNAP_URL", "https://xx1031.xyz").strip()
# 2026-10-23：固定 dz，不再从 URL 猜（dingzhi.xx1031.xyz 不含 "dz." 会误判）
POOL = os.environ.get("POOL_TAG", "dz").strip() or "dz"
SLICE_TAG = "am"   # 控制台分片维度；固定 am = 上午补采

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
    for a in d.get("accounts") or []:
        if a.get("ck"):
            accs.append({
                "name": a.get("name") or str(a.get("uid")),
                "uid": a.get("uid"),
                "ck": a.get("ck"),
                "song": str(a.get("song") or ""),
            })
    return accs


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
    print(f"[650补采] 全池 {len(accs)} 个号，逐号查工作台…")

    metrics = {}
    dead = 0
    for e in accs:
        name = e["name"]
        try:
            c = Client(e["ck"])
            wb = c.workbench_info()
            if wb:
                metrics[str(e.get("uid") or name)] = dict(wb)
            else:
                dead += 1
                print(f"  [{name}] 工作台无数据（可能失效），跳过")
        except Exception as ex:
            dead += 1
            print(f"  [{name}] 查询失败（跳过）: {ex}")
        time.sleep(random.uniform(1, 2))

    print(f"[650补采] 采到 {len(metrics)} 个号 / 无数据 {dead} 个，上报 /api/snap（slice={SLICE_TAG}）")
    try:
        r = requests.post(SNAP_URL.rstrip("/") + "/api/snap", json={
            "pass": SNAP_PASS,
            "pool": POOL,
            "slice": SLICE_TAG,
            "date": bj_today(),
            "accs": metrics,
        }, timeout=60, headers=UA)
        print(f"[650补采] 上报: HTTP {r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[650补采] 上报失败: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
