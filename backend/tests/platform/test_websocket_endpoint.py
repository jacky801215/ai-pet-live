"""WebSocket endpoint transport 测试（Phase 2.2-3B-2）——验证 :mod:`app.api.ws` 接线。

覆盖（指令四条验证 + 静态守卫）：

1. **可连接**：``/api/ws`` accept 成功、合法消息处理后正常断开；
2. **合法消息进入 adapter**：经 platform adapter 转交 ``EventGateway.normalize()``
   恰一次，交付恰为契约字段 ``{event_type, payload}``（timestamp/source 已丢弃，WM-1）；
3. **非法消息 reject**：JSON/envelope/event_type/payload 四类非法帧被消息级拒收
   （WA-4 reject + log），**连接继续**服务后续合法消息；
4. **disconnect 不产生额外业务事件**：断线动作本身零事件（合法消息经 pipeline 落库
   ``platform="ws"`` —— Phase 2.2-5 runtime integration 后的口径；spy 计数证明断线零额外事件）。

隔离（与 ``test_api_contract.py`` 同口径）：临时 ``project_root`` + 临时 SQLite +
真实 DDL，绝不触碰真实 ``database/pet_live.db``；``TestClient`` 同步驱动。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.ws import get_ws_adapter
from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.platform.websocket_adapter import WebSocketAdapter
from app.services.event_gateway import EventGateway
from app.services.pipeline import SimulationPipeline, get_pipeline

#: 合法 envelope（WM-1 恰 4 字段；comment 无需素材即可 normalize）
VALID_ENVELOPE: dict = {
    "event_type": "comment",
    "payload": {"content": "你好"},
    "timestamp": "2026-09-21T04:00:00Z",
    "source": "ws",
}


class SpyGateway:
    """包装真实 EventGateway：记录交付参数、复用真实 normalize（与 impl 测试同型）。"""

    def __init__(self) -> None:
        self._real = EventGateway()
        self.calls: list[dict] = []

    def normalize(self, raw_event: dict):
        self.calls.append(raw_event)
        return self._real.normalize(raw_event)


@pytest.fixture()
def ws_env(tmp_path: Path) -> SimpleNamespace:
    """隔离环境：临时库 pipeline + spy adapter 双依赖覆盖 + TestClient。"""
    spy = SpyGateway()
    logs: list[str] = []
    adapter = WebSocketAdapter(spy, logs.append)

    settings = Settings(
        project_root=tmp_path,
        assets_root=tmp_path / "assets" / "pets",
        database_path=tmp_path / "ws_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    pipeline = SimulationPipeline(settings=settings)

    app = create_app(static_dir=tmp_path / "assets" / "pets")
    app.dependency_overrides[get_ws_adapter] = lambda: adapter
    app.dependency_overrides[get_pipeline] = lambda: pipeline

    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        spy=spy,
        logs=logs,
        adapter=adapter,
        pipeline=pipeline,
    )


# ---------------------------------------------------------------------------
# 1) 可连接 + 2) 合法消息进入 adapter
# ---------------------------------------------------------------------------

def test_ws_connects_and_valid_message_reaches_adapter(ws_env: SimpleNamespace) -> None:
    """验证 1 + 2：可连接；合法 envelope 经 adapter 进入 normalize 恰一次。"""
    with ws_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(VALID_ENVELOPE))

    # 恰一次、恰契约字段（timestamp / source 已在 adapter 丢弃，WM-1 映射口径）
    assert len(ws_env.spy.calls) == 1
    assert ws_env.spy.calls[0] == {
        "event_type": "comment",
        "payload": {"content": "你好"},
    }
    assert ws_env.logs == []  # 合法消息零日志


def test_ws_normalization_returns_real_event(ws_env: SimpleNamespace) -> None:
    """端点转交后产出真实内部事件（Event），但端点不消费它（transport 边界）。"""
    event = ws_env.adapter.handle(json.dumps(VALID_ENVELOPE))
    assert event.event_type == "comment"
    assert event.payload == {"content": "你好"}


# ---------------------------------------------------------------------------
# 3) 非法消息 reject（连接继续）
# ---------------------------------------------------------------------------

def test_ws_invalid_json_rejected_connection_survives(ws_env: SimpleNamespace) -> None:
    """非法 JSON → 消息级拒收（reject + log），后续合法消息照常受理。"""
    with ws_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text("{not-json")
        ws.send_text(json.dumps(VALID_ENVELOPE))

    assert len(ws_env.spy.calls) == 1  # 非法帧零交付
    assert len(ws_env.logs) == 1
    assert "invalid json" in ws_env.logs[0]


def test_ws_envelope_and_event_type_rejected(ws_env: SimpleNamespace) -> None:
    """缺字段 envelope / 未知 event_type / 非对象 payload → 全部拒收且连接继续。"""
    missing_field = {k: v for k, v in VALID_ENVELOPE.items() if k != "event_type"}
    unknown_type = dict(VALID_ENVELOPE, event_type="follow")
    null_payload = dict(VALID_ENVELOPE, payload=None)

    with ws_env.client.websocket_connect("/api/ws") as ws:
        for broken in (missing_field, unknown_type, null_payload):
            ws.send_text(json.dumps(broken))
        ws.send_text(json.dumps(VALID_ENVELOPE))  # 连接仍存活

    assert len(ws_env.spy.calls) == 1  # 只有最后的合法消息被交付
    assert len(ws_env.logs) == 3
    assert any("follow" in m for m in ws_env.logs)  # 未知类型 log 含原因（WA-4）


# ---------------------------------------------------------------------------
# 4) disconnect 不产生业务事件
# ---------------------------------------------------------------------------

def test_ws_disconnect_produces_no_extra_business_event(ws_env: SimpleNamespace) -> None:
    """断线本身零**额外**业务事件（WS-5）：只有发送的那条经 pipeline 落库（platform="ws"）。

    Phase 2.2-5 行为升级：合法 WS 事件**进入** pipeline（runtime integration），
    因此「零业务事件」收窄为「零**额外**事件」——断线动作本身不产生任何事件。
    """
    before = ws_env.client.get("/api/events/recent?limit=200").json()

    with ws_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(VALID_ENVELOPE))  # 这条经 pipeline 落库
    # with 退出 = 客户端主动 disconnect（WS-5：只记日志）

    after = ws_env.client.get("/api/events/recent?limit=200").json()
    assert after["count"] - before["count"] == 1  # 恰为发送的那条
    assert after["items"][0]["platform"] == "ws"  # WS 写库口径（2.2-5 裁决）
    assert len(ws_env.spy.calls) == 1  # 断线本身零事件（只有发送的那条）


# ---------------------------------------------------------------------------
# 静态守卫（transport 边界：api 层零业务触达）
# ---------------------------------------------------------------------------

def test_ws_endpoint_source_static_guard() -> None:
    """ws.py 源码（剥注释/docstring）零业务引用：引擎 / 仓储 / simulate / 写库。"""
    source = Path(__file__).resolve().parents[2] / "app" / "api" / "ws.py"
    code = source.read_text(encoding="utf-8")
    stripped = re.sub(r'"""[\s\S]*?"""', "", code)
    stripped = re.sub(r"^\s*#.*$", "", stripped, flags=re.M)

    for banned in (
        "ActionEngine",
        "PlaybackManager",
        "InteractionEngine",
        "DataManager",
        "repositories",
        "simulate",
        "write_event",
    ):
        assert banned not in stripped, banned
