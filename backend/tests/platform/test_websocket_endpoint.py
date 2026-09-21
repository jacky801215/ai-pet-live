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
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.ws import get_ws_adapter, get_ws_dispatcher
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


# ---------------------------------------------------------------------------
# 5) HR-1：unexpected runtime exception containment（9-4A）
# ---------------------------------------------------------------------------


class BoomPipeline:
    """真实 pipeline 包装：仅 apply_event 抛非预期异常，其余委托真实实现（保持其他端点可用）。"""

    def __init__(self, real: SimulationPipeline) -> None:
        self._real = real

    def apply_event(self, event, *, platform: str = "ws"):
        raise RuntimeError("unexpected boom inside pipeline.apply_event")

    def __getattr__(self, name):
        return getattr(self._real, name)


class BoomAdapter(WebSocketAdapter):
    """Fake adapter：handle 抛出非 WebSocketAdapterRejectError 的异常（异常路径）。"""

    def handle(self, raw: str):
        raise RuntimeError("unexpected boom inside adapter.handle")


class SpyDispatcher:
    """记录出站调用次数的 dispatcher 替身（验证异常时不发帧）。"""

    def __init__(self) -> None:
        self.calls: int = 0

    async def send_event(self, event, websocket) -> bool:
        self.calls += 1
        return False


@pytest.fixture()
def boom_pipeline_env(tmp_path: Path) -> SimpleNamespace:
    """apply_event 抛异常的环境：adapter 真实、pipeline 替身、dispatcher 替身。"""
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
    app = create_app(static_dir=tmp_path / "assets" / "pets")
    real_pipeline = SimulationPipeline(settings=settings)
    app.dependency_overrides[get_ws_adapter] = lambda: adapter
    app.dependency_overrides[get_pipeline] = lambda: BoomPipeline(real_pipeline)
    dispatcher = SpyDispatcher()
    app.dependency_overrides[get_ws_dispatcher] = lambda: dispatcher
    return SimpleNamespace(client=TestClient(app), spy=spy, logs=logs, dispatcher=dispatcher)


@pytest.fixture()
def boom_adapter_env(tmp_path: Path) -> SimpleNamespace:
    """adapter.handle 抛非预期异常的环境：adapter 替身、pipeline 真实。"""
    spy = SpyGateway()
    logs: list[str] = []
    settings = Settings(
        project_root=tmp_path,
        assets_root=tmp_path / "assets" / "pets",
        database_path=tmp_path / "ws_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    pipeline = SimulationPipeline(settings=settings)
    app = create_app(static_dir=tmp_path / "assets" / "pets")
    app.dependency_overrides[get_ws_adapter] = lambda: BoomAdapter(spy, logs.append)
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    return SimpleNamespace(client=TestClient(app), spy=spy, logs=logs)


def test_ws_unexpected_exception_in_apply_event_contained(boom_pipeline_env, caplog) -> None:
    """HR-1：apply_event 非预期异常在端点层收敛为干净关闭，不冒泡到框架。

    before：exception escapes endpoint → framework abrupt close
    after ：endpoint catches → warning logged + 干净关闭 + 无出站帧 + 无写库
    """
    with caplog.at_level(logging.WARNING, logger="app.api.ws"):
        with boom_pipeline_env.client.websocket_connect("/api/ws") as ws:
            ws.send_text(json.dumps(VALID_ENVELOPE))

    # HR-1 containment：端点捕获了非预期异常（记录 warning）
    assert any(
        "unexpected error" in r.message and "terminating connection" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]
    # 异常路径不发任何出站帧（WC-4 / WP-5：commit 未发生）
    assert boom_pipeline_env.dispatcher.calls == 0
    # 无部分写库（apply_event 在 _record 之前抛，HR-2 边界不被破坏）
    before = boom_pipeline_env.client.get("/api/events/recent?limit=200").json()["count"]
    after = boom_pipeline_env.client.get("/api/events/recent?limit=200").json()["count"]
    assert after == before


def test_ws_unexpected_exception_in_adapter_contained(boom_adapter_env, caplog) -> None:
    """HR-1：adapter.handle 非预期异常（非 reject）在端点层收敛，连接干净关闭。"""
    with caplog.at_level(logging.WARNING, logger="app.api.ws"):
        with boom_adapter_env.client.websocket_connect("/api/ws") as ws:
            ws.send_text(json.dumps(VALID_ENVELOPE))

    assert any("unexpected error" in r.message for r in caplog.records), [
        r.message for r in caplog.records
    ]
    # adapter 在 normalize 之前抛 → 事件未交付 gateway
    assert len(boom_adapter_env.spy.calls) == 0


# ---------------------------------------------------------------------------
# 6) HR-5：gap coverage T-G1 / T-G3（9-4B，仅测试）
# ---------------------------------------------------------------------------


@pytest.fixture()
def malformed_frame_env(tmp_path: Path) -> SimpleNamespace:
    """真实 pipeline + 真实 adapter + SpyDispatcher 替身：断言 reject 路径零出站帧。"""
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
    dispatcher = SpyDispatcher()
    app.dependency_overrides[get_ws_dispatcher] = lambda: dispatcher
    return SimpleNamespace(client=TestClient(app), spy=spy, logs=logs, dispatcher=dispatcher)


def test_tg1_network_interruption_keeps_committed_mutation_quiet_and_no_retry(
    ws_env: SimpleNamespace,
) -> None:
    """HR-5 T-G1：network interruption（客户端主动断开）行为覆盖。

    - 中断前已提交（落库）的 mutation 不因连接中断而回滚（HR-2 边界：无 atomic rollback）；
    - 中断本身不产生额外业务事件（WS-5：disconnect 零事件）；
    - 端点干净关闭、异常不冒泡框架（HR-1 containment：with 块退出无异常）；
    - 不引入 reconnect / retry / heartbeat（静态守卫：ws.py 不含这些 token）。
    """
    before = ws_env.client.get("/api/events/recent?limit=200").json()["count"]

    with ws_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(VALID_ENVELOPE))  # 提交一条合法消息；with 退出 = 客户端主动中断

    # with 块无异常退出 ⇒ 框架未崩溃、异常未冒泡（HR-1 containment 生效）
    after = ws_env.client.get("/api/events/recent?limit=200").json()
    assert after["count"] - before == 1  # 仅发送的那条被提交，未被中断回滚（HR-2）
    assert after["items"][0]["platform"] == "ws"  # 落库口径（2.2-5）

    # 静态守卫：endpoint 不引入 reconnect / retry / heartbeat（HR-5 / PH-6 禁止项）
    source = Path(__file__).resolve().parents[2] / "app" / "api" / "ws.py"
    code = source.read_text(encoding="utf-8")
    stripped = re.sub(r'"""[\s\S]*?"""', "", code)
    stripped = re.sub(r"^\s*#.*$", "", stripped, flags=re.M)
    for banned in ("reconnect", "retry", "heartbeat"):
        assert banned not in stripped.lower(), f"forbidden token present in ws.py: {banned}"


def test_tg3_malformed_frame_rejected_no_outbound_push_connection_survives(
    malformed_frame_env: SimpleNamespace,
) -> None:
    """HR-5 T-G3：malformed transport frame → adapter reject + 零出站帧 + 连接存活。

    - 经 /api/ws 发非法帧（非法 JSON）→ adapter 消息级拒收（WA-4 reject + log）；
    - 连接仍在既有 lifecycle 契约内（连续拒收两帧、干净关闭，无重连 / 无心跳）；
    - 无非法事件进入 runtime（gateway 零交付）；
    - 无出站 push 生成（dispatcher.calls == 0，WC-4 per-message / WP-5 fail-only）。
    """
    with malformed_frame_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text("{not-json")  # 第一帧 malformed
        ws.send_text("{also-not-json}")  # 第二帧 malformed（验证连接存活、连续拒收）

    # 两帧均被拒收、零交付、零出站帧
    assert len(malformed_frame_env.spy.calls) == 0  # 无非法事件进入 runtime
    assert len(malformed_frame_env.logs) == 2  # 两次 reject 各一条 log
    assert malformed_frame_env.dispatcher.calls == 0  # reject 路径零 push（WC-4 / WP-5）
