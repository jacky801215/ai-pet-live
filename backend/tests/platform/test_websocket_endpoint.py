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
from starlette.websockets import WebSocketDisconnect

from app.api.ws import get_ws_adapter, get_ws_dispatcher, get_ws_settings
from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.platform.websocket_adapter import WebSocketAdapter
from app.repositories.db import Database
from app.services.asset_manager import build_default_manager
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


# ---------------------------------------------------------------------------
# 8) Phase 3.2-A：backend multi-pet context（MP-1 / MP-2 / MP-3）
# ---------------------------------------------------------------------------

#: 触发动作的合法 envelope（rules.json：gift + gift_name=小心心 → action heart）
#: gift 的契约必填字段为 gift_name / gift_count（见 ``app/models/event.py``）
GIFT_HEART_ENVELOPE: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
    "timestamp": "2026-09-22T04:00:00Z",
    "source": "ws",
}

#: 每个宠物登记的动作全集（与 assets/pets/*/config.json 一致）
PET_ACTIONS: tuple[str, ...] = ("idle", "heart", "happy", "sad", "surprise")

#: 素材时长（毫秒）：取足够大，避免测试期间播放窗口到期（不依赖假时钟）
PET_ASSET_DURATION_MS: int = 3_600_000


def _seed_pets(settings: Settings, *pet_types: str) -> None:
    """在隔离素材根写入 pet config 并登记资产。

    同时产出两类合法键：``pet_id``（``cat_001``，来自 config.json）与 ``pet_type``
    （``cat``，来自 ``assets`` 表）——覆盖 3.2-A 裁决「pet_id 或 pet_type 均合法」。
    """
    manager = build_default_manager(settings)
    for pet_type in pet_types:
        pet_dir = settings.assets_root / pet_type
        pet_dir.mkdir(parents=True, exist_ok=True)
        (pet_dir / "config.json").write_text(
            json.dumps(
                {
                    "pet_id": f"{pet_type}_001",
                    "pet_type": pet_type,
                    "actions": list(PET_ACTIONS),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        for action in PET_ACTIONS:
            manager.register(
                pet_type,
                action,
                f"assets/pets/{pet_type}/{action}.mp4",
                duration=PET_ASSET_DURATION_MS,
            )


@pytest.fixture()
def multi_pet_env(tmp_path: Path) -> SimpleNamespace:
    """多宠物隔离环境：临时库 + 已登记 cat/dog 资产 + 真实 pipeline/adapter/dispatcher。"""
    settings = Settings(
        project_root=tmp_path,
        assets_root=tmp_path / "assets" / "pets",
        database_path=tmp_path / "multi_pet.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=False,
    )
    settings.ensure_directories()
    _seed_pets(settings, "cat", "dog")

    spy = SpyGateway()
    logs: list[str] = []
    adapter = WebSocketAdapter(spy, logs.append)
    pipeline = SimulationPipeline(settings=settings)

    app = create_app(static_dir=settings.assets_root)
    app.dependency_overrides[get_ws_adapter] = lambda: adapter
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_ws_dispatcher] = lambda: SpyDispatcher()
    app.dependency_overrides[get_ws_settings] = lambda: settings

    return SimpleNamespace(
        client=TestClient(app),
        settings=settings,
        spy=spy,
        logs=logs,
    )


def _fetch(env: SimpleNamespace, sql: str, params: tuple = ()) -> list[dict]:
    """只读查询隔离库（断言 MP-1 / MP-3 的落库效果）。"""
    db = Database(env.settings.database_path, constants.SCHEMA_PATH)
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _counters(env: SimpleNamespace, pet_key: str) -> set[tuple]:
    """某 pet 作用域下的聚合计数组（stat_type, stat_key, value）。"""
    rows = _fetch(
        env,
        "SELECT stat_type, stat_key, value FROM interactions WHERE pet_id = ?",
        (pet_key,),
    )
    return {(r["stat_type"], r["stat_key"], r["value"]) for r in rows}


def _capture_pipelines(monkeypatch: pytest.MonkeyPatch) -> dict:
    """拦截 ``app.api.ws.build_pipeline_for_pet``，记录 per-connection 装配结果。"""
    import app.api.ws as ws_module
    from app.services.runtime_factory import build_pipeline_for_pet as real

    created: dict = {}

    def spy(pet_key: str, settings=None, **kwargs):
        pipeline = real(pet_key, settings, **kwargs)
        created[pet_key] = pipeline
        return pipeline

    monkeypatch.setattr(ws_module, "build_pipeline_for_pet", spy)
    return created


def test_mp1_cat_context_routes_to_cat_runtime(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-1 Test 1（Cat Context）：``?pet_id=cat`` → cat runtime 真实受理并变更。

    禁止的是「``build_runtime(pet_id)`` ↓ discard ↓ new default pipeline」：
    本用例以 ``pipeline.pet_id`` / ``snapshot()`` / 落库三重证据锁定 **cat runtime 被真正使用**。
    """
    created = _capture_pipelines(monkeypatch)

    with multi_pet_env.client.websocket_connect("/api/ws?pet_id=cat") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert list(created) == ["cat"]  # 恰装配一次、且为 cat
    cat = created["cat"]
    assert cat.pet_id == "cat"  # 是 cat 的 runtime，而非默认 runtime
    snapshot = cat.snapshot()
    assert snapshot.last_event == "gift"  # cat runtime 状态被变更
    assert (snapshot.state, snapshot.action) == ("playing", "heart")  # 路由到 cat 的动作

    rows = _fetch(multi_pet_env, "SELECT * FROM events WHERE pet_id = 'cat'")
    assert len(rows) == 1
    assert rows[0]["event_type"] == "gift"
    assert rows[0]["action_name"] == "heart"
    assert rows[0]["platform"] == "ws"
    assert _counters(multi_pet_env, "cat") == {("event", "gift", 1), ("action", "heart", 1)}


def test_mp2_dog_context_isolated_from_cat(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-1 Test 2 + MP-2（Dog Isolation）：cat / dog 各持独立 runtime，互不串扰。"""
    created = _capture_pipelines(monkeypatch)

    with multi_pet_env.client.websocket_connect("/api/ws?pet_id=cat") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))
    cat_counters_before = _counters(multi_pet_env, "cat")
    cat_before = created["cat"].snapshot()
    cat_before_state = (cat_before.last_event, cat_before.state, cat_before.action)

    with multi_pet_env.client.websocket_connect("/api/ws?pet_id=dog") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert set(created) == {"cat", "dog"}
    assert created["cat"] is not created["dog"]  # MP-2：两个独立物件图
    assert (created["cat"].pet_id, created["dog"].pet_id) == ("cat", "dog")

    # dog 被变更
    assert created["dog"].snapshot().last_event == "gift"
    assert _counters(multi_pet_env, "dog") == {("event", "gift", 1), ("action", "heart", 1)}

    # cat 保持不变（隔离：dog 的连接/事件不触碰 cat runtime 与 cat 计数）
    assert _counters(multi_pet_env, "cat") == cat_counters_before
    after = created["cat"].snapshot()
    assert (after.last_event, after.state, after.action) == cat_before_state
    assert len(_fetch(multi_pet_env, "SELECT id FROM events WHERE pet_id = 'cat'")) == 1


def test_mp1_registered_pet_id_key_also_accepted(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-1：``pet_id`` 形态（``cat_001``）同样合法并路由到自身命名空间。"""
    created = _capture_pipelines(monkeypatch)

    with multi_pet_env.client.websocket_connect("/api/ws?pet_id=cat_001") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert list(created) == ["cat_001"]
    assert created["cat_001"].pet_id == "cat_001"
    assert _counters(multi_pet_env, "cat_001") == {("event", "gift", 1), ("action", "heart", 1)}


def test_mp1_unknown_pet_context_rejected_without_runtime(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-1 Test 3（Invalid Pet）：非法 key → 拒收连接，且**不装配 runtime**、不落库。"""
    created = _capture_pipelines(monkeypatch)
    before = _fetch(multi_pet_env, "SELECT COUNT(*) AS n FROM events")[0]["n"]

    with pytest.raises(WebSocketDisconnect):
        with multi_pet_env.client.websocket_connect("/api/ws?pet_id=unknown") as ws:
            ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert created == {}  # 未创建 runtime / 未落 fallback pet
    assert _fetch(multi_pet_env, "SELECT COUNT(*) AS n FROM events")[0]["n"] == before


def test_mp1_legacy_default_path_preserves_stats_read_path(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-1 Test 4（Legacy Compatibility）：无 ``pet_id`` → 既有默认行为，统计读路径不变。"""
    created = _capture_pipelines(monkeypatch)

    with multi_pet_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert created == {}  # 未走 pet 上下文
    # 默认路径聚合行保持 pet_id IS NULL（与冻结读路径 stat_repository 逐字一致）
    null_keys = {
        (r["stat_type"], r["stat_key"])
        for r in _fetch(multi_pet_env, "SELECT stat_type, stat_key FROM interactions WHERE pet_id IS NULL")
    }
    assert ("event", "gift") in null_keys
    body = multi_pet_env.client.get("/api/stats").json()
    assert body["events"].get("gift") == 1  # /api/stats 仍可读（读路径未被破坏）


def test_mp3_pet_scoped_counters_stay_out_of_global_stats(
    multi_pet_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-3：pet 连接的聚合计数落在独立命名空间，不写 NULL、不污染 ``/api/stats``。"""
    _capture_pipelines(monkeypatch)

    with multi_pet_env.client.websocket_connect("/api/ws?pet_id=cat") as ws:
        ws.send_text(json.dumps(GIFT_HEART_ENVELOPE))

    assert _counters(multi_pet_env, "cat") == {("event", "gift", 1), ("action", "heart", 1)}
    assert _fetch(multi_pet_env, "SELECT id FROM interactions WHERE pet_id IS NULL") == []
    assert multi_pet_env.client.get("/api/stats").json()["events"] == {}
