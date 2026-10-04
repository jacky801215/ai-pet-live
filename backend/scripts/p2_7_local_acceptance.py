# -*- coding: utf-8 -*-
"""Phase 2 · 任务 2-7「性能测试」—— **本机一键验收脚本**。

位置
----
本文件位于 ``backend/scripts/``（**受版本控制**）；运行时会向 ``<repo>/tmp/``
写日志与临时校准库（``tmp/`` 已 gitignore），**不触碰任何受跟踪文件**。

用途
----
在**目标机器**上跑一次，直接得到 2-7 的 PASS/FAIL 结论。

**验收口径（CR-7 #4 修订）**
---------------------------
早期版本的 ``env_calibration`` 测的是「单连接 + 默认 ``delete``/``FULL``」的
**原始 fsync 能力** —— 那是 app 的历史访问形态，自 **CR-8（thread-local 连接复用）**
起已不再代表 app 的真实写入路径，导致 C5 在 app 已达标时仍被判 SKIP。

现在的模型与 app 真实路径**对齐**：

- ``app_write_path``（**必需**，C5 依据）：直接调用项目真实 ``Database.connect()``
  —— ``journal_mode=WAL`` + ``synchronous=NORMAL`` + **thread-local 持久连接复用**；
- ``raw_fs_sync``（**可选诊断**，保留历史口径）：单连接 + 默认 ``delete``/``FULL``，
  仅作环境参考，**不作为** C5 判据。

覆盖（后端 / 推送侧）
----
  C1 不崩溃            —— 压力后服务仍存活、/api/stats 仍 200
  C2 无内存泄漏        —— 压力前后进程工作集增量有界（默认 < 150MB）
  C3 到期正常回落      —— 单事件播完后自动推 idle 状态帧（L3）
  C4 不卡顿(响应恢复)  —— 排空后 /api/stats 延迟恢复到基线量级（默认 < 1000ms）
  C5 延迟 p95 < 500ms  —— **仅当 app 写入路径自校准达标时断言**，否则标 SKIP(环境)
  (参考) 事件帧计数 / 丢帧率 / 落库增量 / 队列容量(设计=3) / 延迟分布

⛔ 不覆盖：浏览器**画面渲染**侧（掉帧 / JS 堆 / 视觉卡顿）—— 需另用浏览器探针。

治理
----
* **只读仓库**：不改受跟踪文件、不提交。（``--json-out`` 默认写工作区，非仓库）
* **副作用**：向 demo DB 写入 N 条 gift 事件（默认 100）；owner 已有备份
  ``database/pet_live_backup_20260928.db``，如需还原请自行执行。
* F-A 登记：动作队列容量 = 3（``services/action_engine.py``），满则**丢弃最旧**。
  ⇒「连续触发 100 次」按设计**不会播 100 次**；本脚本据此**不以「全播」为判据**。

用法
----
  python backend/scripts/p2_7_local_acceptance.py            # 完整（100 条 @100ms）
  python backend/scripts/p2_7_local_acceptance.py --n 20     # 快速自检
  python backend/scripts/p2_7_local_acceptance.py --repo D:/AI-Pet-Live --json-out out.json

退出码：0 = 全部必需项 PASS；1 = 有 FAIL；2 = 环境不具备（延迟项 SKIP）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

DEFAULT_REPO = r"D:\AI-Pet-Live"
ENVELOPE_KEYS = {"event_type", "payload", "timestamp", "source"}
SNAPSHOT_KEYS = ["pet_id", "state", "action", "asset_url", "queue_size", "last_event", "loop"]
QUEUE_LIMIT_DESIGN = 3          # F-A：设计行为
LEAK_THRESHOLD_KB = 150 * 1024  # C2：150MB
RESP_THRESHOLD_MS = 1000.0      # C4：排空后 /api/stats 上限
LATENCY_THRESHOLD_MS = 500.0    # C5：p95 判据

#: 环境自校准门槛（CR-7 #4 修订）：作用于 **app 真实写入路径**（``Database.connect()``，
#: WAL/NORMAL + 持久连接复用）。历史口径（单连接 delete/FULL）仅作诊断保留，不参与判定。
ENV_CAPABLE_COMMIT_MS = 15.0


def _say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:  # 中文 Windows 控制台兜底
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", "replace"))
        sys.stdout.buffer.flush()


def _rm_single(path: str) -> None:
    """删除单个文件（含 SQLite 的 -wal / -shm 伴生文件）。

    逐个文件删除，**不**批量删除目录 —— 避免触发沙箱「单轮删除 > N」保护。
    """
    for p in (path, path + "-wal", path + "-shm"):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:  # noqa: BLE001
            pass


def _lat_stats(lat: list[float]) -> dict:
    s = sorted(lat)
    return {
        "n": len(s),
        "p50_ms": round(s[len(s) // 2], 1),
        "p95_ms": round(s[min(len(s) - 1, int(0.95 * (len(s) - 1)))], 1),
    }


def find_python(repo: str) -> str:
    """优先仓库 venv，其次本机已知解释器，最后当前解释器。"""
    cands = [
        os.path.join(repo, ".venv", "Scripts", "python.exe"),
        os.path.join(repo, "backend", ".venv", "Scripts", "python.exe"),
        os.path.join(repo, "venv", "Scripts", "python.exe"),
        r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
        sys.executable,
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return sys.executable


def _calib_tmpdir(repo: str) -> str:
    tmp = os.path.join(repo, "tmp")
    return tmp if os.path.isdir(tmp) else tempfile.gettempdir()


def calibrate_app_write(backend: str, tmpdir: str, n: int = 100) -> dict:
    """**必需** —— app 真实写入路径自校准（C5 依据）。

    直接调用项目真实 ``Database.connect()``（**CR-8**：thread-local 持久连接复用 +
    ``PRAGMA journal_mode=WAL`` / ``synchronous=NORMAL``），逐条 INSERT 计时取 p50。
    这才是 app「能不能及时落库」的真实能力。
    """
    path = os.path.join(tmpdir, f"p27_appcalib_{os.getpid()}.db")
    lat: list[float] = []
    try:
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from app.core import constants
        from app.repositories.db import Database

        _rm_single(path)
        db = Database(path, constants.SCHEMA_PATH)
        db.initialize()                       # 建表 + 建立（并缓存）线程连接
        with db.connect() as conn:
            jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
            sy = conn.execute("PRAGMA synchronous").fetchone()[0]
        for _ in range(n):
            t0 = time.perf_counter()
            with db.connect() as conn:        # 复用同一持久连接
                conn.execute(
                    "INSERT INTO events (event_type, payload, created_at) "
                    "VALUES ('like', '{}', CURRENT_TIMESTAMP)"
                )
            lat.append((time.perf_counter() - t0) * 1000)
        db.dispose()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "err": repr(exc)}
    finally:
        _rm_single(path)
    out = {"ok": True, "measure": "Database.connect() (WAL/NORMAL, thread-local reuse)",
           "journal_mode": jm, "synchronous": sy, "connection": "persistent(reused)",
           **_lat_stats(lat)}
    out["env_capable"] = out["p50_ms"] < ENV_CAPABLE_COMMIT_MS
    return out


def calibrate_raw_fs(tmpdir: str, n: int = 100) -> dict:
    """**可选诊断** —— 原始 fsync 能力（历史口径，保留不删）。

    单连接持久 + 默认 ``delete``/``FULL``（即 CR-8 前 app 的形态）。
    仅用于环境画像对照，**不作为** C5 判据。
    """
    path = os.path.join(tmpdir, f"p27_calib_{os.getpid()}.db")
    lat: list[float] = []
    try:
        _rm_single(path)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con.commit()
        for i in range(n):
            t0 = time.perf_counter()
            con.execute("INSERT INTO t (v) VALUES (?)", (f"v{i}",))
            con.commit()
            lat.append((time.perf_counter() - t0) * 1000)
        con.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "err": repr(exc)}
    finally:
        _rm_single(path)
    return {"ok": True, "measure": "sqlite3.connect() persistent, delete/FULL (legacy)",
            "journal_mode": "delete", "synchronous": "full", **_lat_stats(lat)}


def calibrate(repo: str, backend: str, n: int = 100) -> dict:
    """环境自校准：app 写入路径（必需）+ raw fsync（可选诊断）。

    Returns:
        dict，同时提供**新模型**（``app_write_path`` / ``raw_fs_sync`` / ``env_capable``）
        与**历史字段**（``ok`` / ``n`` / ``p50_ms`` / ``p95_ms``，取自 app 路径）以向后兼容。
    """
    tmpdir = _calib_tmpdir(repo)
    app = calibrate_app_write(backend, tmpdir, n)
    raw = calibrate_raw_fs(tmpdir, n)
    return {
        # -- 新模型 ---------------------------------------------------------
        "app_write_path": app,          # required（C5 依据）
        "raw_fs_sync": raw,             # optional diagnostic（历史口径，保留）
        "env_capable": bool(app.get("env_capable")),
        "gate_ms": ENV_CAPABLE_COMMIT_MS,
        # -- 兼容旧字段（p50/p95 取自 app 路径）-----------------------------
        "ok": app.get("ok"),
        "n": n,
        "p50_ms": app.get("p50_ms"),
        "p95_ms": app.get("p95_ms"),
    }


def start_server(py: str, backend: str, port: int, log: str):
    fh = open(log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        cwd=backend, stdout=fh, stderr=subprocess.STDOUT,
    )
    return proc, fh


def wait_ready(http: str, timeout: float = 60.0) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{http}/api/stats", timeout=2) as resp:
                if resp.status == 200:
                    return {"ready": True, "secs": round(time.time() - t0, 2),
                            "body": json.loads(resp.read().decode("utf-8"))}
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(0.4)
    return {"ready": False, "secs": round(time.time() - t0, 2), "err": last}


def rss_kb(pid: int):
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, encoding="utf-8", errors="replace")
        line = r.stdout.strip().splitlines()[0]
        parts = [p.strip('"') for p in line.split('","')]
        return int(parts[-1].replace(" K", "").replace(",", "").replace('"', "").strip())
    except Exception:  # noqa: BLE001
        return None


def http_get(http: str, path: str, timeout: float = 5.0):
    t0 = time.time()
    try:
        with urllib.request.urlopen(f"{http}{path}", timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), (time.time() - t0) * 1000
    except Exception:  # noqa: BLE001
        return -1, None, (time.time() - t0) * 1000


def gift(ts: str) -> dict:
    return {"event_type": "gift",
            "payload": {"gift_name": "小心心", "gift_count": 1},
            "timestamp": ts, "source": "ws"}


async def probe(ws_url: str, http: str, pid: int, n: int, cadence: float, drain: float) -> dict:
    import websockets

    recv: list = []
    sends: list = []

    async with websockets.connect(ws_url) as ws:
        async def reader() -> None:
            # ⛔ U-6a：禁在收帧上用 wait_for / 超时取消（会吞帧 ⇒ 假丢帧）。
            try:
                while True:
                    frame = json.loads(await ws.recv())
                    recv.append((time.time(), frame))
            except Exception:  # noqa: BLE001
                return

        rt = asyncio.ensure_future(reader())
        await asyncio.sleep(1.5)                       # 连接首帧不推（initial_state_frame=deferred）

        # ---- Phase Y：单事件 → 到期回落（先测，避免被后段队列污染）----
        sends.append(time.time())
        await ws.send(json.dumps(gift("2026-10-03T14:00:00Z")))
        t_y = time.time()
        playing_at = idle_at = None
        while time.time() - t_y < 12.0 and idle_at is None:
            await asyncio.sleep(0.05)
            for at, f in recv:
                if f.get("type") == "playback_state":
                    st = f.get("snapshot", {}).get("state")
                    if st == "playing" and playing_at is None:
                        playing_at = at
                    if st == "idle" and playing_at is not None:
                        idle_at = at
                        break
        y_playing_ms = round((playing_at - t_y) * 1000, 1) if playing_at else None
        y_idle_ms = round((idle_at - t_y) * 1000, 1) if idle_at else None

        # ---- Phase X：N 连发 ----
        recv.clear(); sends.clear()
        rss_before = rss_kb(pid)
        base_ms = http_get(http, "/api/stats")[2]
        _, stats_before_stress, _ = http_get(http, "/api/stats")
        t0 = time.time()
        for i in range(n):
            sends.append(time.time())
            await ws.send(json.dumps(gift(f"2026-10-03T14:10:{i % 60:02d}Z")))
            await asyncio.sleep(cadence)
        send_span_s = time.time() - t0
        await asyncio.sleep(drain)                     # 排空窗
        post_ms = http_get(http, "/api/stats")[2]
        rss_after = rss_kb(pid)
        try:
            rt.cancel()
        except Exception:  # noqa: BLE001
            pass

    def kind(f: dict) -> str:
        if f.get("type") == "playback_state":
            return "state"
        return "event" if set(f.keys()) == ENVELOPE_KEYS else "other"

    events = [(at, f) for at, f in recv if kind(f) == "event"]
    states = [(at, f) for at, f in recv if kind(f) == "state"]
    lat = sorted(round((at - sends[k]) * 1000, 1) for k, (at, _) in enumerate(events) if k < len(sends))

    def pct(p: float):
        if not lat:
            return None
        return lat[min(len(lat) - 1, int(round(p / 100 * (len(lat) - 1))))]

    qs = [f["snapshot"]["queue_size"] for _, f in states]
    return {
        "stats_before_stress": stats_before_stress,
        "phase_y": {"playing_frame_ms": y_playing_ms, "idle_after_expiry_ms": y_idle_ms,
                    "idle_seen": y_idle_ms is not None},
        "phase_x": {
            "sent": len(sends), "send_span_s": round(send_span_s, 2),
            "event_frames": len(events), "state_frames": len(states),
            "event_frame_loss": len(sends) - len(events),
            "drain_ratio": round(len(events) / max(1, len(sends)), 3),
            "latency_ms": {"p50": pct(50), "p95": pct(95), "min": lat[0] if lat else None,
                           "max": lat[-1] if lat else None},
            "queue_size": {"max": max(qs) if qs else None, "last": qs[-1] if qs else None},
            "rss_kb_before": rss_before, "rss_kb_after": rss_after,
            "rss_delta_kb": (rss_after - rss_before) if (rss_before is not None and rss_after is not None) else None,
            "stats_latency_ms": {"baseline": round(base_ms, 1), "post_drain": round(post_ms, 1)},
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--python", default=None, dest="py")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--cadence", type=float, default=0.10)
    ap.add_argument("--drain", type=float, default=45.0)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    repo = args.repo.replace("\\", "/")
    backend = os.path.join(repo, "backend")
    py = args.py or find_python(repo)
    http = f"http://127.0.0.1:{args.port}"
    ws_url = f"ws://127.0.0.1:{args.port}/api/ws"
    log = os.path.join(repo, "tmp", "p2_7_local_server.log") if os.path.isdir(os.path.join(repo, "tmp")) \
        else os.path.join(tempfile.gettempdir(), "p2_7_local_server.log")

    _say("=" * 72)
    _say("Phase 2 · 2-7 本机验收（后端/推送侧）")
    _say(f"  repo   = {repo}")
    _say(f"  python = {py}")
    _say(f"  参数   = n={args.n} cadence={args.cadence}s drain={args.drain}s")
    _say("  口径   = C5 依据 app 真实写入路径（Database.connect: WAL/NORMAL + 连接复用）")
    _say("  F-A 登记：队列容量=3（满则丢弃最旧）⇒ 不以「100 次全播」为判据")
    _say("=" * 72)

    result: dict = {"repo": repo, "python": py, "params": {"n": args.n, "cadence": args.cadence, "drain": args.drain}}

    # 0) 环境自校准
    _say("[1/3] 环境自校准中（app 写入路径 100 次 commit + raw fsync 诊断，约数秒～数十秒）...")
    t_cal = time.time()
    calib = calibrate(repo, backend)
    result["env_calibration"] = calib
    app = calib.get("app_write_path", {})
    raw = calib.get("raw_fs_sync", {})
    _say(f"[1/3] 校准完成（{round(time.time() - t_cal, 1)}s）")
    _say(f"      app 写入路径 (必需)  p50={app.get('p50_ms')}ms p95={app.get('p95_ms')}ms "
         f"[{app.get('journal_mode')}/{app.get('synchronous')} · {app.get('connection')}] "
         f"=> env_capable={calib.get('env_capable')}")
    _say(f"      raw fsync   (仅诊断) p50={raw.get('p50_ms')}ms p95={raw.get('p95_ms')}ms "
         f"[{raw.get('journal_mode')}/{raw.get('synchronous')}]")
    if not app.get("ok"):
        _say(f"[警告] app 写入路径校准失败：{app.get('err')}（仍继续，C5 将标 SKIP）")

    _say(f"[2/3] 启动后端 uvicorn（127.0.0.1:{args.port}）并等待就绪 ...")
    proc, fh = start_server(py, backend, args.port, log)
    rc = 1
    try:
        ready = wait_ready(http)
        result["server"] = {"ready": ready.get("ready"), "secs": ready.get("secs")}
        if not ready.get("ready"):
            result["server"]["tail"] = open(log, encoding="utf-8", errors="replace").read()[-1500:]
            _say("[FAIL] 服务未就绪 —— 见 traceback 尾部")
            rc = 1
        else:
            _say(f"[2/3] 就绪（{ready.get('secs')}s）")
            _say(f"[3/3] 压测中：{args.n} 条 @{args.cadence}s + 排空 {args.drain}s（预计 "
                 f"{round(1.5 + 12 + args.n * args.cadence + args.drain)}s 左右，请勿关窗）...")
            perf = asyncio.run(probe(ws_url, http, proc.pid, args.n, args.cadence, args.drain))
            result["perf"] = perf
            status, body, _ = http_get(http, "/api/stats")
            result["stats_after"] = {"status": status, "body": body}
            sb = perf.get("stats_before_stress")
            if sb and body:
                result["stats_delta"] = {k: body["events"][k] - sb["events"][k] for k in body["events"]}
                result["stats_delta"]["total"] = body["total"] - sb["total"]

            # ---- 判据（F-A 修正版）----
            py_ = perf["phase_y"]; px = perf["phase_x"]
            rss_d = px["rss_delta_kb"]
            post = px["stats_latency_ms"]["post_drain"]
            base = px["stats_latency_ms"]["baseline"]
            env_cap = bool(calib.get("env_capable"))
            p95 = px["latency_ms"]["p95"]

            crit = {
                "C1_不崩溃": (status == 200 and proc.poll() is None),
                "C2_无内存泄漏": (rss_d is not None and rss_d < LEAK_THRESHOLD_KB),
                "C3_到期正常回落": py_["idle_seen"],
                "C4_不卡顿_排空后响应恢复": (post < max(RESP_THRESHOLD_MS, 3 * base)),
                "C5_延迟p95_<500ms": (p95 is not None and p95 < LATENCY_THRESHOLD_MS) if env_cap else None,
            }
            required_ok = all(crit[k] is True for k in ("C1_不崩溃", "C2_无内存泄漏", "C3_到期正常回落", "C4_不卡顿_排空后响应恢复"))
            latency_state = "PASS" if crit["C5_延迟p95_<500ms"] is True else ("FAIL" if crit["C5_延迟p95_<500ms"] is False else "SKIP(环境不达标)")
            if required_ok and latency_state == "PASS":
                overall = "PASS"                      # 全部判据成立
            elif required_ok and latency_state.startswith("SKIP"):
                overall = "PASS_未含延迟"               # 必需项全过，延迟因环境无法断言
            else:
                overall = "FAIL"
            result["criteria"] = crit
            result["verdict"] = {"required_ok": required_ok, "latency": latency_state, "overall": overall}

            _say("")
            _say("-" * 72)
            _say(f"事件帧  {px['event_frames']}/{px['sent']}  (丢帧 {px['event_frame_loss']}, drain_ratio {px['drain_ratio']})")
            _say(f"落库增量 {result.get('stats_delta', {}).get('total')} / {px['sent']}")
            _say(f"延迟    p50={px['latency_ms']['p50']}ms  p95={p95}ms  max={px['latency_ms']['max']}ms")
            _say(f"队列    max={px['queue_size']['max']} (设计上限 {QUEUE_LIMIT_DESIGN})")
            _say(f"RSS     {px['rss_kb_before']} -> {px['rss_kb_after']} KB  (delta {rss_d} KB)")
            _say(f"响应    baseline={base}ms  post_drain={post}ms")
            _say(f"到期→idle  {py_['idle_after_expiry_ms']}ms  (seen={py_['idle_seen']})")
            _say("-" * 72)
            for k, v in crit.items():
                tag = "PASS" if v is True else ("FAIL" if v is False else "SKIP")
                _say(f"  [{tag}] {k}")
            _say("-" * 72)
            _say(f"结论：overall={overall}  (必需项 {'OK' if required_ok else 'NG'} / 延迟项 {latency_state})")
            if not env_cap:
                _say(f"⚠️ app 写入路径 commit 偏慢（p50={app.get('p50_ms')}ms ≥ {ENV_CAPABLE_COMMIT_MS}ms）"
                     f" ⇒ 延迟项已 SKIP；如需断言请换更快的磁盘环境。")
            _say("=" * 72)
            rc = 0 if overall == "PASS" else (2 if overall == "PASS_未含延迟" else 1)
    finally:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        fh.close()

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        _say(f"[json] {args.json_out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
