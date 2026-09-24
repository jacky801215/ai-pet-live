"""WebSocket outbound dispatcher 测试（Phase 2.2-7B-2）——验证 commit → dispatch 出站链路。

契约来源（均 v1.0 FROZEN）：``phase2_websocket_push_boundary_decision.md``（WP-1 ~ WP-6）、
``phase2_websocket_commit_point_decision.md``（WC-1 ~ WC-6）。

覆盖（指令 D1 ~ D6 + 契约不变量 + 静态守卫）：

1. **D1 正常事件发送**：合法帧经 commit 后回推 **WM-1 envelope**（恰 4 字段，``source="ws"``，
   ISO-8601 UTC ``timestamp``）；
2. **D2 commit 顺序**：出站推送**严格位于** ``apply_event()`` 返回**之后**
   （有序日志 ``["commit", "send"]``，WC-1 / WC-4）；
3. **D3 reject 不发送**：非法帧（JSON / envelope / event_type / payload）**零 commit 零推送**；
4. **D4 disconnect 不发送**：断线动作本身不产生任何出站帧；
5. **D5 Failure Policy**：发送失败**只 log**、不上抛（unit）+ 失败**不影响**已提交的 runtime
   mutation、连接继续（endpoint，WC-5）；
6. **D6 HTTP 回归**：``POST /api/events/simulate`` 行为与写库口径（``platform="simulator"``）
   均不变，且**不经过** ws dispatcher（零推送）。

隔离（与 ``test_websocket_endpoint.py`` 同口径）：临时 ``project_root`` + 临时 SQLite +
真实 DDL，绝不触碰真实 ``database/pet_live.db``；``TestClient`` 同步驱动。
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.api.ws import get_ws_adapter, get_ws_dispatcher
from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.models.event import Event
from app.platform.websocket_adapter import WebSocketAdapter
from app.platform.websocket_dispatcher import (
    ENVELOPE_FIELDS,
    PUSH_SOURCE,
    WebSocketDispatcher,
)
from app.services.event_gateway import EventGateway
from app.services.pipeline import (
    PLATFORM_SIMULATOR,
    SimulationPipeline,
    get_pipeline,
)

#: 合法 envelope（WM-1 恰 4 字段；comment 无需素材即可 normalize）
COMMENT_ENVELOPE: dict = {
    "event_type": "comment",
    "payload": {"content": "你好"},
    "timestamp": "2026-09-21T04:00:00Z",
    "source": "ws",
}
#: HTTP simulate 请求体（API-1 契约）
COMMENT_RAW: dict = {"event_type": "comment", "payload": {"content": "你好"}}

#: ISO-8601 UTC（``...Z``）——WM-1 ``timestamp`` 口径
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: PlaybackState（API-2）字段：**禁止**出现在出站帧顶层（WS-4 / WP-3）
PLAYBACK_STATE_FIELDS = {
    "pet_id", "state", "action", "asset_url", "queue_size", "last_event", "loop",
    "duration", "progress", "current_time", "video_state", "queue",
}


# ---------------------------------------------------------------------------
# 替身（spy / 记录器）：全测试零真实 sleep、零真实网络
# ---------------------------------------------------------------------------

class SpyGateway:
    """包装真实 EventGateway：记录交付参数、复用真实 normalize。"""

    def __init__(self) -> None:
        self._real = EventGateway()
        self.calls: list[dict] = []

    def normalize(self, raw_event: dict):
        self.calls.append(raw_event)
        return self._real.normalize(raw_event)


class CommitRecordingPipeline(SimulationPipeline):
    """在 ``apply_event()`` **返回后**记 ``"commit"``（commit point = 返回前，WC-1）。"""

    def __init__(self, *args: Any, order: list[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._order = order

    def apply_event(self, event: Event, *, platform: str = PLATFORM_SIMULATOR):
        snapshot = super().apply_event(event, platform=platform)
        self._order.append("commit")  # 提交完成（apply_event 已返回）
        return snapshot


class SendRecordingDispatcher(WebSocketDispatcher):
    """记录发送调用（D2 有序日志 / D3-D4 零发送断言）。"""

    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    async def send_event(self, event: Event, websocket: Any) -> bool:
        self._order.append("send")
        return await super().send_event(event, websocket)


class _ExplodingSocket:
    """必炸 socket：``send_json`` 抛异常（D5 失败策略）。"""

    async def send_json(self, data: Any) -> None:  # pragma: no cover - 永远抛
        raise RuntimeError("socket boom")


class FailingDispatcher(WebSocketDispatcher):
    """把真实 socket 换成必炸 socket——模拟「发送失败」（D5 失败隔离，endpoint 级）。"""

    async def send_event(self, event: Event, websocket: Any) -> bool:
        return await super().send_event(event, _ExplodingSocket())


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

def _build_env(
    tmp_path: Path,
    dispatcher_factory: Callable[[list[str]], WebSocketDispatcher],
) -> SimpleNamespace:
    """隔离环境：临时库 pipeline + spy adapter + 可注入 dispatcher + TestClient。"""
    order: list[str] = []
    logs: list[str] = []
    spy = SpyGateway()
    adapter = WebSocketAdapter(spy, logs.append)

    settings = Settings(
        project_root=tmp_path,
        assets_root=tmp_path / "assets" / "pets",
        database_path=tmp_path / "dispatcher_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    pipeline = CommitRecordingPipeline(settings=settings, order=order)

    app = create_app(static_dir=tmp_path / "assets" / "pets")
    app.dependency_overrides[get_ws_adapter] = lambda: adapter
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_ws_dispatcher] = lambda: dispatcher_factory(order)

    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        spy=spy,
        logs=logs,
        adapter=adapter,
        pipeline=pipeline,
        order=order,
    )


@pytest.fixture()
def env(tmp_path: Path) -> SimpleNamespace:
    """成功路径环境（真实发送 + 顺序记录）。"""
    return _build_env(tmp_path, lambda order: SendRecordingDispatcher(order))


@pytest.fixture()
def failing_env(tmp_path: Path) -> SimpleNamespace:
    """失败路径环境（socket 必炸）。"""
    return _build_env(tmp_path, lambda order: FailingDispatcher())


# ---------------------------------------------------------------------------
# D1 正常事件发送（WM-1 envelope 逐字段）
# ---------------------------------------------------------------------------

def test_d1_valid_event_pushes_wm1_envelope(env: SimpleNamespace) -> None:
    """D1：合法帧 commit 后回推 WM-1 envelope——恰 4 字段、source="ws"、ISO-8601 UTC。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        frame = ws.receive_json()

    assert set(frame) == set(ENVELOPE_FIELDS)  # 恰 4 字段（WM-1 / WP-3）
    assert len(frame) == 4
    assert frame["event_type"] == "comment"
    assert frame["payload"] == {"content": "你好"}
    assert frame["source"] == PUSH_SOURCE == "ws"  # source 固定 "ws"
    assert ISO_UTC_RE.match(frame["timestamp"])  # transport 生成 ISO-8601 UTC
    assert PLAYBACK_STATE_FIELDS.isdisjoint(frame)  # 零 PlaybackState 字段（WS-4 / WP-3）


def test_d1_push_reflects_event_not_playback_state(env: SimpleNamespace) -> None:
    """D1 补：出站帧是**事件形态**（payload 为事件 payload），不是状态快照。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        frame = ws.receive_json()

    assert frame["payload"] == COMMENT_ENVELOPE["payload"]  # 原样透传事件 payload
    assert "state" not in frame and "queue_size" not in frame


# ---------------------------------------------------------------------------
# D2 commit 顺序（push 严格位于 apply_event 返回之后）
# ---------------------------------------------------------------------------

def test_d2_push_happens_after_commit(env: SimpleNamespace) -> None:
    """D2：有序日志必须恰为 ``["commit", "send"]``——推送在 commit point 之后（WC-1/WC-4）。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        ws.receive_json()

    assert env.order == ["commit", "send"]


def test_d2_order_holds_for_multiple_events(env: SimpleNamespace) -> None:
    """D2 补：多消息时顺序仍逐条 ``commit → send``（per-message 生命周期，WC-4）。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        ws.receive_json()
        ws.send_text(json.dumps(dict(COMMENT_ENVELOPE, payload={"content": "第二条"})))
        ws.receive_json()

    assert env.order == ["commit", "send", "commit", "send"]


# ---------------------------------------------------------------------------
# D3 reject 不发送
# ---------------------------------------------------------------------------

def test_d3_rejected_frames_are_never_committed_or_pushed(env: SimpleNamespace) -> None:
    """D3：非法帧消息级拒收——零 commit、零 push、零落库（WA-4 / Step 2 硬约束）。"""
    missing_field = {k: v for k, v in COMMENT_ENVELOPE.items() if k != "event_type"}
    unknown_type = dict(COMMENT_ENVELOPE, event_type="follow")
    null_payload = dict(COMMENT_ENVELOPE, payload=None)

    with env.client.websocket_connect("/api/ws") as ws:
        for broken in ("{not-json", json.dumps(missing_field),
                       json.dumps(unknown_type), json.dumps(null_payload)):
            ws.send_text(broken)

    assert env.order == []  # 零 commit、零 send
    assert env.client.get("/api/events/recent?limit=200").json()["count"] == 0


def test_d3_reject_does_not_block_following_valid_push(env: SimpleNamespace) -> None:
    """D3 补：非法帧后连接继续，合法帧仍恰发一帧（消息级拒收不污染推送通道）。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text("{not-json")
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        frame = ws.receive_json()

    assert frame["event_type"] == "comment"
    assert env.order == ["commit", "send"]  # 只有合法帧留下痕迹


# ---------------------------------------------------------------------------
# D4 disconnect 不发送
# ---------------------------------------------------------------------------

def test_d4_disconnect_without_message_pushes_nothing(env: SimpleNamespace) -> None:
    """D4：直接断线（未发消息）→ 零 commit、零 push（WS-5）。"""
    with env.client.websocket_connect("/api/ws"):
        pass

    assert env.order == []
    assert env.client.get("/api/events/recent?limit=200").json()["count"] == 0


def test_d4_disconnect_itself_adds_no_extra_push(env: SimpleNamespace) -> None:
    """D4 补：一条合法帧后断线 → 出站帧**恰 1 条**（断线动作本身零额外推送）。"""
    with env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        ws.receive_json()
    # with 退出 = 客户端 disconnect

    assert env.order == ["commit", "send"]
    assert env.order.count("send") == 1


# ---------------------------------------------------------------------------
# D5 Failure Policy（失败只 log、不上抛、不影响 mutation）
# ---------------------------------------------------------------------------

def test_d5_send_failure_is_logged_not_raised() -> None:
    """D5（unit）：``send_json`` 抛异常 → ``send_event`` 返回 False + log，**不上抛**（WP-5）。"""
    logs: list[str] = []
    dispatcher = WebSocketDispatcher(
        logger=lambda msg, *args: logs.append(msg % args if args else msg)
    )
    event = EventGateway().normalize(COMMENT_RAW)

    result = asyncio.run(dispatcher.send_event(event, _ExplodingSocket()))

    assert result is False  # 失败 = False，不抛（WC-5）
    assert len(logs) == 1
    assert "push failed" in logs[0]
    assert "comment" in logs[0]  # log 含 event_type（可诊断）


def test_d5_push_failure_does_not_block_commit_or_connection(
    failing_env: SimpleNamespace,
) -> None:
    """D5（endpoint）：推送失败**不影响** runtime mutation，连接继续（WC-5）。"""
    with failing_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(COMMENT_ENVELOPE))
        ws.send_text(json.dumps(dict(COMMENT_ENVELOPE, payload={"content": "第二条"})))

    # 两次都 commit（推送失败不回滚、不中断 inbound 循环）
    assert failing_env.order == ["commit", "commit"]
    body = failing_env.client.get("/api/events/recent?limit=200").json()
    assert body["count"] == 2
    assert all(row["platform"] == "ws" for row in body["items"])


# ---------------------------------------------------------------------------
# D6 HTTP 回归（simulate 不变、不经过 ws dispatcher）
# ---------------------------------------------------------------------------

def test_d6_http_simulate_unchanged_and_never_pushes(env: SimpleNamespace) -> None:
    """D6：HTTP simulate 行为/写库口径不变；**零**出站推送（HTTP 不走 ws 通道）。"""
    resp = env.client.post("/api/events/simulate", json=COMMENT_RAW)
    assert resp.status_code == 200
    assert resp.json()["last_event"] == "comment"

    row = env.client.get("/api/events/recent?limit=200").json()["items"][0]
    assert row["platform"] == "simulator"  # HTTP 口径不变（Step 2 硬要求）
    # 共享编排内核照常 commit（WG-2 两门面同内核），但 HTTP 门面**不经过** ws dispatcher
    assert env.order == ["commit"]
    assert "send" not in env.order  # 零出站推送（HTTP 不走 ws 通道）


# ---------------------------------------------------------------------------
# 契约不变量（envelope 形状 / 可注入时钟 / payload 拷贝 / 无连接状态）
# ---------------------------------------------------------------------------

def test_envelope_has_exactly_four_fields_and_fixed_source() -> None:
    """WM-1 / WP-3：envelope 恰 4 字段、source 恒 "ws"、timestamp 为 ISO-8601 UTC。"""
    dispatcher = WebSocketDispatcher(
        now=lambda: datetime(2026, 9, 21, 5, 0, 0, tzinfo=timezone.utc)
    )
    envelope = dispatcher.build_envelope(EventGateway().normalize(COMMENT_RAW))

    assert set(envelope) == set(ENVELOPE_FIELDS)
    assert envelope["timestamp"] == "2026-09-21T05:00:00Z"  # 注入时钟 → 确定性输出
    assert envelope["source"] == "ws"


def test_envelope_timestamp_normalises_naive_datetime_to_utc() -> None:
    """防御：朴素 datetime 按 UTC 解释——本地时区不泄漏进线上帧。"""
    dispatcher = WebSocketDispatcher(now=lambda: datetime(2026, 9, 21, 5, 0, 0))
    envelope = dispatcher.build_envelope(EventGateway().normalize(COMMENT_RAW))
    assert envelope["timestamp"] == "2026-09-21T05:00:00Z"


def test_envelope_payload_is_shallow_copy() -> None:
    """envelope.payload 为浅拷贝：不与被受理事件共享可变引用。"""
    event = EventGateway().normalize(COMMENT_RAW)
    envelope = WebSocketDispatcher().build_envelope(event)

    event.payload["content"] = "被改动"
    assert envelope["payload"] == {"content": "你好"}


def test_dispatcher_holds_no_connection_state() -> None:
    """WP-4：dispatcher 不持有 socket / registry——仅时钟 + logger 两个属性。"""
    dispatcher = WebSocketDispatcher()
    assert set(dispatcher.__dict__) == {"_now", "_logger"}


# ---------------------------------------------------------------------------
# 静态守卫（WP-1 / WP-2 / WC-6：dispatcher 源码零 runtime / 零机制）
# ---------------------------------------------------------------------------

def test_dispatcher_source_static_guard() -> None:
    """dispatcher 源码（剥注释/docstring）零 runtime 引用、零连接/重试机制。"""
    source = (
        Path(__file__).resolve().parents[2]
        / "app" / "platform" / "websocket_dispatcher.py"
    )
    code = source.read_text(encoding="utf-8")
    stripped = re.sub(r'"""[\s\S]*?"""', "", code)
    stripped = re.sub(r"^\s*#.*$", "", stripped, flags=re.M)

    for banned in (
        "ActionEngine", "PlaybackManager", "InteractionEngine", "DataManager",
        "repositories", "simulate", "write_event", "EventGateway",
        "app.services", "asyncio", "sleep", "retry", "reconnect", "send_text",
    ):
        assert banned not in stripped, banned
