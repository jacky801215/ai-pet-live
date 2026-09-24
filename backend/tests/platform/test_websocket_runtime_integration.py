"""WebSocket runtime integration 测试（Phase 2.2-5）——WS → adapter → EventGateway →
SimulationPipeline → ActionEngine → Playback 的 backend 闭环守卫。

覆盖（指令六条验证 + WG-2 gateway ownership）：

1. **合法 WS event 进入 pipeline**：消息经真实 adapter（消费组合根共享 gateway）驱动编排；
2. **ActionEngine 被调用**：``gift``+``小心心`` 命中规则 → ``playing``/``heart``；
3. **Playback 更新**：``GET /api/playback/state`` 反映 WS 驱动的状态；
4. **runtime state 改变**：事件落库（``platform="ws"``）+ 统计计数变化；
5. **HTTP simulate 回归不受影响**：行为与写库口径（``platform="simulator"``）不变；
   且 WS 与 HTTP 驱动**同一个** ActionEngine（黑盒共享证明：队列承接）；
6. **非法事件 reject 不进入 pipeline**：库与状态零变化。

WG-2 gateway ownership（白盒）：``pipeline.gateway`` 存在、稳定、与 HTTP simulate
内部使用的 ``_runtime.gateway`` 是**同一实例**（方案 A 落地证据）。

隔离（与 ``test_api_contract.py`` 同口径）：临时 ``project_root`` + 临时 SQLite +
真实 DDL + 临时素材，绝不触碰真实 ``database/pet_live.db``。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.services.asset_manager import AssetManager
from app.services.event_gateway import EventGateway
from app.services.pipeline import SimulationPipeline, get_pipeline
from tests.conftest import make_action_file, register_asset

#: 测试宠物已登记的动作（时长 1s，FakeClock 冻结 → 播放窗口不过期）
ACTIONS: tuple[str, ...] = ("idle", "heart", "happy")
ASSET_DURATION_MS: int = 1000

#: WS envelope（WM-1 恰 4 字段）：``gift`` + ``小心心`` → ``heart``
GIFT_HEART_ENVELOPE: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
    "timestamp": "2026-09-21T05:00:00Z",
    "source": "ws",
}
#: HTTP simulate 请求体（API-1 契约 4 键）
GIFT_HEART_RAW: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
}
COMMENT_ENVELOPE: dict = {
    "event_type": "comment",
    "payload": {"content": "你好"},
    "timestamp": "2026-09-21T05:00:01Z",
    "source": "ws",
}


class FakeClock:
    """可控单调时钟（秒）—— 冻结时间让播放窗口永不过期，状态确定。"""

    def __init__(self, start: float = 2000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def wsrt(tmp_path: Path) -> SimpleNamespace:
    """隔离集成环境：临时库 + 临时素材 + 真实 adapter 接线（只覆盖 get_pipeline）。"""
    assets_root = tmp_path / "assets" / "pets"
    cat_dir = assets_root / "cat"
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "config.json").write_text(
        json.dumps(
            {
                "pet_id": "cat_001",
                "pet_type": "cat",
                "name": "小橘",
                "actions": list(ACTIONS),
                "default_action": "idle",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    settings = Settings(
        project_root=tmp_path,
        assets_root=assets_root,
        database_path=tmp_path / "ws_integration_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    database = Database(settings.database_path, settings.schema_path)
    database.initialize()

    manager = AssetManager(AssetRepository(database), settings)
    for action in ACTIONS:
        make_action_file(tmp_path, "cat", action)
        register_asset(manager, "cat", action, duration=ASSET_DURATION_MS)

    clock = FakeClock()
    pipeline = SimulationPipeline(settings=settings, clock=clock)

    app = create_app(static_dir=assets_root)
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    return SimpleNamespace(client=TestClient(app), pipeline=pipeline, clock=clock)


# ---------------------------------------------------------------------------
# WG-2 gateway ownership（白盒证据）
# ---------------------------------------------------------------------------

def test_gateway_accessor_is_stable_shared_instance(wsrt: SimpleNamespace) -> None:
    """``pipeline.gateway`` 存在、幂等稳定，且与 HTTP simulate 内部同一实例（方案 A）。"""
    pipeline = wsrt.pipeline
    assert isinstance(pipeline.gateway, EventGateway)
    assert pipeline.gateway is pipeline.gateway  # 幂等（无重建）
    assert pipeline.gateway is pipeline._runtime.gateway  # 与 HTTP simulate 同一实例


def test_apply_event_is_the_shared_orchestration_kernel(wsrt: SimpleNamespace) -> None:
    """WS 门面（apply_event）与 HTTP 门面（simulate）驱动同一 runtime 状态机。"""
    pipeline = wsrt.pipeline

    snap_ws = pipeline.apply_event(
        pipeline.gateway.normalize(GIFT_HEART_RAW), platform="ws"
    )
    assert snap_ws.state == "playing"
    assert snap_ws.action == "heart"

    snap_http = pipeline.simulate(GIFT_HEART_RAW)  # 同一 FakeClock → 窗口不过期 → 入队
    assert snap_http.state == "playing"
    assert snap_http.queue_size == 1  # 第二条指令进入**同一个** ActionEngine 队列


# ---------------------------------------------------------------------------
# 1-4) 合法 WS 事件：进入 pipeline → ActionEngine → Playback → runtime state
# ---------------------------------------------------------------------------

def test_ws_valid_event_drives_full_runtime(wsrt: SimpleNamespace) -> None:
    """验证 1/2/3：合法 WS gift → 编排内核 → ActionEngine 执行 → playing/heart。"""
    with wsrt.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    body = wsrt.client.get("/api/playback/state").json()
    assert body["state"] == "playing"  # ActionEngine 被调用（验证 2）
    assert body["action"] == "heart"  # 规则命中 + 动作执行
    assert body["asset_url"] == "/assets/pets/cat/actions/heart/heart.mp4"
    assert body["pet_id"] == "cat_001"
    assert body["last_event"] == "gift"  # Playback 更新（验证 3）
    assert set(body) == {
        "pet_id", "state", "action", "asset_url", "queue_size", "last_event", "loop",
    }  # PlaybackState 7 字段（CR-1）冻结不破（WS-4 / WG-4）


def test_ws_event_recorded_with_ws_platform(wsrt: SimpleNamespace) -> None:
    """验证 4：runtime state 改变——事件落库且 ``platform="ws"``（2.2-5 写库口径）。"""
    with wsrt.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    body = wsrt.client.get("/api/events/recent?limit=200").json()
    assert body["count"] == 1
    row = body["items"][0]
    assert row["event_type"] == "gift"
    assert row["platform"] == "ws"  # WS 口径（HTTP 为 simulator，见回归用例）
    assert row["action_name"] == "heart"
    assert row["pet_id"] == "cat_001"

    stats = wsrt.client.get("/api/stats").json()
    assert stats["events"].get("gift") == 1  # 统计计数随 WS 事件变化
    assert stats["actions"].get("heart") == 1


def test_ws_and_http_share_one_runtime_engine(wsrt: SimpleNamespace) -> None:
    """黑盒共享证明：WS 事件与 HTTP simulate 驱动**同一个** ActionEngine 队列。"""
    with wsrt.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))
    assert wsrt.client.get("/api/playback/state").json()["state"] == "playing"

    # 同一 FakeClock 下窗口不过期 → 第二条指令只能进入同一个引擎队列
    resp = wsrt.client.post("/api/events/simulate", json=GIFT_HEART_RAW)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "playing"
    assert body["queue_size"] == 1  # 队列承接 = 同一 runtime（WG-2 方案 A 运行时证据）


# ---------------------------------------------------------------------------
# 5) HTTP simulate 回归不受影响
# ---------------------------------------------------------------------------

def test_http_simulate_regression_unchanged(wsrt: SimpleNamespace) -> None:
    """HTTP simulate：行为（快照/落库）与写库口径（``platform="simulator"``）均不变。"""
    resp = wsrt.client.post("/api/events/simulate", json=GIFT_HEART_RAW)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "playing"
    assert body["action"] == "heart"
    assert body["asset_url"] == "/assets/pets/cat/actions/heart/heart.mp4"
    assert body["last_event"] == "gift"
    assert body["queue_size"] == 0

    row = wsrt.client.get("/api/events/recent?limit=200").json()["items"][0]
    assert row["platform"] == "simulator"  # HTTP 口径不变（Step 1 硬要求）


def test_http_simulate_no_rule_stays_idle_regression(wsrt: SimpleNamespace) -> None:
    """无规则命中仍属正常业务结果：200 受理 + 落库 + 保持 idle（既有契约不变）。"""
    resp = wsrt.client.post(
        "/api/events/simulate", json={"event_type": "comment", "payload": {"content": "hi"}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "idle"
    assert body["last_event"] == "comment"


# ---------------------------------------------------------------------------
# 6) 非法事件：reject，不进入 pipeline
# ---------------------------------------------------------------------------

def test_ws_invalid_event_never_enters_pipeline(wsrt: SimpleNamespace) -> None:
    """非法帧（JSON/类型/payload）→ 消息级拒收：库与播放态**零变化**。

    基线先用一条合法 comment 建立（消化 last_event 初始差异），随后非法帧必须
    让快照与库**完全不动**（reject 不进入 pipeline 的黑盒证据）。
    """
    with wsrt.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))

    baseline_state = wsrt.client.get("/api/playback/state").json()
    baseline = wsrt.client.get("/api/events/recent?limit=200").json()

    broken_frames = (
        "{not-json",
        json.dumps({k: v for k, v in GIFT_HEART_ENVELOPE.items() if k != "event_type"}),
        json.dumps(dict(GIFT_HEART_ENVELOPE, event_type="follow")),
        json.dumps(dict(GIFT_HEART_ENVELOPE, payload=None)),
    )
    with wsrt.client.websocket_connect("/api/ws") as ws:
        for frame in broken_frames:
            ws.send_text(frame)
        ws.send_text("{also-bad")  # 连接继续（WA-4 消息级拒收）

    after_state = wsrt.client.get("/api/playback/state").json()
    after = wsrt.client.get("/api/events/recent?limit=200").json()
    assert after_state == baseline_state  # 播放态零变化
    assert after["count"] == baseline["count"]  # 库零新增（验证 6）
