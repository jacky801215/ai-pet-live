"""Phase 3.2-C：多宠物上下文**端到端**验证（test-only，零生产代码改动）。

与 :mod:`tests.platform.test_websocket_endpoint` 的「8) Phase 3.2-A」小节是**两层不同的
验证**，刻意并存而非重复：

- **3.2-A 小节 = 对象层**：``monkeypatch`` 拦截 ``build_pipeline_for_pet`` 抓取并断言
  per-connection pipeline **对象**（``pet_id`` / ``snapshot()``）；且 ``get_ws_dispatcher``
  被替身覆盖 —— 出站推送**没走**真实 dispatcher。
- **本文件 = 端到端黑盒层**：**不 stub pet 路径上的任何实现** —— 真实
  ``known_pet_keys`` → ``build_pipeline_for_pet`` → ``build_runtime`` →
  ``SimulationPipeline.apply_event`` → ``InteractionEngine`` / ``ActionEngine`` →
  ``DataManager`` → SQLite → **真实** ``WebSocketDispatcher`` → 客户端**实际收到** WM-1 帧。
  断言只依赖**可观测产物**：WS 出站帧、``events`` / ``interactions`` 表行、HTTP 读接口。

覆盖（Phase 3.2-C 指令 Step 1 六项）：

1. ``cat_001`` WS 上下文 → cat runtime 变更路径（端到端）；
2. ``dog_001`` WS 上下文 → dog runtime 变更路径（端到端）；
3. cat / dog 隔离验证（**不同动作**交叉，严于同动作对比）；
4. 非法 pet_id 拒收验证（含变体矩阵）；
5. **无跨宠物变更泄漏**（出站帧 / events / counters / 全局读路径 / 默认 runtime 五路）；
6. **WM-1 / Event schema 零变更**守卫（出站帧恰 4 字段、入站恰 4 字段、事件类型白名单、
   ``Event`` 冻结字段、冻结 DDL 列集、``interactions`` 唯一约束）。
7. **Phase 3.2-A1**（构造清理）追加：显式 ``pet_id`` **构造期定值**、cat/dog 作用域正确、
   **无跨 pet 泄漏**、默认路径 **NULL 计数作用域保持**，以及 ``build_pipeline_for_pet``
   与显式构造的**等价性**（不再经 ``__new__``）。
8. **Phase 3.2-B**（pet 作用域 **HTTP 读**接口）追加：``?pet_id=`` 端到端往返
   （``/api/stats`` + ``/api/events/recent`` 读回**同一** pet 作用域）、别名归一化、
   无参路径仍为 ``NULL`` 桶 / 全表、非法键折 ``400 INVALID_REQUEST``（不新增错误码）、
   以及 **A1-resolver-scope = 仅读侧** 的边界（WS 写侧 ``pet_id`` 零归一化）。

约束遵守（指令 Step 2）：本文件**只新增测试**；未修改 ``api/ws.py`` / ``pipeline.py`` /
``dispatcher.py`` / ``DataManager`` / frontend 生产代码 / ``PROJECT_RULES.md`` /
PH·HR·WM·WC·WL 冻结文档；未引入 reconnect / retry / heartbeat / 协议变更；
未做 pipeline 构造清理。

前端（指令 Scope 条件项）：``frontend`` **确有**可用测试基础设施（vitest 2.1.9 +
``frontend/tests/**`` 共 11 个文件，``npm test`` = ``vitest run``），但**前端尚无 pet
上下文能力** —— 那属 Phase 3.2-B（本次未授权）。故本步**不新增前端测试**：没有可供端到端
验证的前端多宠物行为，提前编写会越过 3.2-B 的授权边界。
（3.2-C Step 0 用户裁决：采纳本文件为交付物；前端确认**本次不加**测试。）

隔离口径：临时 ``project_root`` + 临时 SQLite + 真实 DDL，绝不触碰真实
``database/pet_live.db``；``TestClient`` 同步驱动真实 ASGI 应用。
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.ws import get_ws_settings
from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.models.event import ALLOWED_EVENT_TYPES, TOP_LEVEL_FIELDS, Event
from app.platform.websocket_adapter import ENVELOPE_KEYS
from app.platform.websocket_dispatcher import ENVELOPE_FIELDS, PUSH_SOURCE
from app.repositories.db import Database
from app.services.asset_manager import build_default_manager
from app.services.pipeline import SimulationPipeline, get_pipeline
from app.services.runtime_factory import build_pipeline_for_pet

# ---------------------------------------------------------------------------
# 契约夹具（全部为 WM-1 恰 4 字段 envelope）
# ---------------------------------------------------------------------------

#: rules.json: gift + payload.gift_name == "小心心" → action ``heart``
GIFT_HEART: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
    "timestamp": "2026-09-22T08:00:00Z",
    "source": "ws",
}

#: rules.json: like + payload.like_count >= 3 → action ``happy``
LIKE_HAPPY: dict = {
    "event_type": "like",
    "payload": {"like_count": 3},
    "timestamp": "2026-09-22T08:00:01Z",
    "source": "ws",
}

#: ``comment`` 无匹配规则 → 只落事件行、**不**产生动作（``action_name`` 为 NULL）
COMMENT_NO_ACTION: dict = {
    "event_type": "comment",
    "payload": {"content": "你好"},
    "timestamp": "2026-09-22T08:00:02Z",
    "source": "ws",
}

#: 每宠物登记的动作全集（与 ``assets/pets/*/config.json`` 一致）
PET_ACTIONS: tuple[str, ...] = ("idle", "heart", "happy", "sad", "surprise")

#: 素材时长（毫秒）：取足够大，避免测试期间播放窗口到期（不依赖假时钟）
PET_ASSET_DURATION_MS: int = 3_600_000

#: 冻结 DDL 列集（``database/schema.sql``；3.2-C 断言其零变更）
FROZEN_EVENTS_COLUMNS: tuple[str, ...] = (
    "id", "event_type", "user_id", "user_name", "pet_id",
    "action_name", "platform", "payload", "created_at",
)
FROZEN_INTERACTIONS_COLUMNS: tuple[str, ...] = (
    "id", "stat_type", "stat_key", "pet_id", "value", "created_at", "last_time",
)
FROZEN_ASSETS_COLUMNS: tuple[str, ...] = (
    "id", "pet_type", "action", "path", "duration",
)


# ---------------------------------------------------------------------------
# 环境装配：**最小依赖覆盖**（只隔离默认容器，pet 路径全真实）
# ---------------------------------------------------------------------------


def _seed_pets(settings: Settings, *pet_types: str) -> None:
    """在隔离素材根写入 pet config 并登记资产（同时产出 pet_id 与 pet_type 两类合法键）。"""
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
def e2e_env(tmp_path) -> SimpleNamespace:
    """多宠物端到端环境。

    依赖覆盖**只有两个**（其余全部真实）：

    - ``get_pipeline`` → 隔离 ``Settings`` 的默认 pipeline（防止默认/旧路径落真实库；
      同时因 ``get_ws_adapter`` 依赖它，真实 adapter 也自动指向隔离 gateway）；
    - ``get_ws_settings`` → 隔离 ``Settings``（pet 路径的合法键判定与 runtime 装配用）。

    **刻意不覆盖** ``get_ws_dispatcher``（用真实 dispatcher → 客户端真收 WM-1 帧）、
    **不 monkeypatch** ``build_pipeline_for_pet``（真实装配）——这是与 3.2-A 小节的关键差异。
    """
    settings = Settings(
        project_root=tmp_path,
        assets_root=tmp_path / "assets" / "pets",
        database_path=tmp_path / "multi_pet_e2e.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=False,
    )
    settings.ensure_directories()
    _seed_pets(settings, "cat", "dog")

    default_pipeline = SimulationPipeline(settings=settings)

    app = create_app(static_dir=settings.assets_root)
    app.dependency_overrides[get_pipeline] = lambda: default_pipeline
    app.dependency_overrides[get_ws_settings] = lambda: settings

    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        settings=settings,
        default_pipeline=default_pipeline,
        #: 默认（派生）宠物主键 —— 旧路径 events 行使用它（AS-2：由组合根派生）
        default_pet_id=build_default_manager(settings).pet_ids()[0],
    )


# ---------------------------------------------------------------------------
# 只读观测助手（全部走真实 SQLite，不 import 生产实现内部）
# ---------------------------------------------------------------------------


def _fetch(env: SimpleNamespace, sql: str, params: tuple = ()) -> list[dict]:
    """只读查询隔离库。"""
    db = Database(env.settings.database_path, constants.SCHEMA_PATH)
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _events(env: SimpleNamespace, pet_id: str) -> list[dict]:
    """某 pet 作用域的 ``events`` 行（按 id 升序 = 写入顺序）。"""
    return _fetch(
        env,
        "SELECT event_type, action_name, platform FROM events WHERE pet_id = ? ORDER BY id",
        (pet_id,),
    )


def _counter_rows(env: SimpleNamespace, pet_id: str) -> set[tuple]:
    """某 pet 作用域的聚合计数集 ``(stat_type, stat_key, value)``。"""
    rows = _fetch(
        env,
        "SELECT stat_type, stat_key, value FROM interactions WHERE pet_id = ?",
        (pet_id,),
    )
    return {(r["stat_type"], r["stat_key"], r["value"]) for r in rows}


def _event_pet_scopes(env: SimpleNamespace) -> set:
    """``events`` 表出现过的全部 ``pet_id`` 值（含 NULL → ``None``）。"""
    return {r["pet_id"] for r in _fetch(env, "SELECT DISTINCT pet_id FROM events")}


def _counter_pet_scopes(env: SimpleNamespace) -> set:
    """``interactions`` 表出现过的全部 ``pet_id`` 值（含 NULL → ``None``）。"""
    return {r["pet_id"] for r in _fetch(env, "SELECT DISTINCT pet_id FROM interactions")}


def _push(
    env: SimpleNamespace, path: str, *envelopes: dict, expect: int | None = None
) -> list[dict]:
    """在一个连接内依次发送 envelope，返回服务端**实际推送**的帧（按序）。

    Args:
        env: 端到端环境。
        path: 连接路径（可含 ``?pet_id=``）。
        *envelopes: 依次发送的 envelope。
        expect: 期望收到的帧数；``None`` = 等于发送条数（全部合法帧的场景）。
            ⚠️ 必须显式给出，否则当存在**被拒收**的帧时，多余的 ``receive_json()``
            会永久阻塞（``TestClient`` 的接收无超时）——这正是本文件初版挂起的成因。
    """
    wanted = len(envelopes) if expect is None else expect
    frames: list[dict] = []
    with env.client.websocket_connect(path) as ws:
        for envelope in envelopes:
            ws.send_text(json.dumps(envelope))
        for _ in range(wanted):
            frames.append(ws.receive_json())
    return frames


# ---------------------------------------------------------------------------
# 1 + 2) cat_001 / dog_001 上下文 → 运行时变更路径（端到端）
# ---------------------------------------------------------------------------


def test_e2e_cat_001_context_drives_cat_runtime_mutation_path(e2e_env: SimpleNamespace) -> None:
    """``?pet_id=cat_001`` 端到端：帧 → cat runtime 变更 → 落库 → WM-1 回推。

    运行时**真正被变更**的证据链（全部可观测）：

    1. 收到出站帧 ⇒ ``apply_event()`` 成功返回（commit point，WC-1）；
    2. ``events.action_name == "heart"`` ⇒ ``ActionEngine`` 在 cat runtime 上**执行了动作**
       （D5：``action_name`` 非空 = 动作已执行）；
    3. ``interactions`` 出现 ``("action", "heart", 1)``（pet 作用域）⇒ 动作经
       ``DataManager`` 落库，且作用域是 cat_001。
    """
    frames = _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)

    assert len(frames) == 1
    assert frames[0]["event_type"] == "gift"
    assert frames[0]["payload"] == {"gift_name": "小心心", "gift_count": 1}

    assert _events(e2e_env, "cat_001") == [
        {"event_type": "gift", "action_name": "heart", "platform": "ws"}
    ]
    assert _counter_rows(e2e_env, "cat_001") == {("event", "gift", 1), ("action", "heart", 1)}


def test_e2e_dog_001_context_drives_dog_runtime_mutation_path(e2e_env: SimpleNamespace) -> None:
    """``?pet_id=dog_001`` 端到端：**不同事件/动作**（like → happy）在 dog runtime 上生效。"""
    frames = _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    assert len(frames) == 1
    assert frames[0]["event_type"] == "like"

    assert _events(e2e_env, "dog_001") == [
        {"event_type": "like", "action_name": "happy", "platform": "ws"}
    ]
    assert _counter_rows(e2e_env, "dog_001") == {("event", "like", 1), ("action", "happy", 1)}


# ---------------------------------------------------------------------------
# 3 + 5) 隔离验证 + 无跨宠物泄漏
# ---------------------------------------------------------------------------


def test_e2e_cat_and_dog_are_fully_isolated_no_cross_pet_leakage(
    e2e_env: SimpleNamespace,
) -> None:
    """cat / dog 用**不同动作**交叉验证：任一宠物的活动都不得出现在对方命名空间。

    比 3.2-A 的「同动作对比」更强：若存在串扰（如共享 runtime / 写错作用域），
    交叉断言会同时命中事件、动作与计数三个面。
    """
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    cat_counters = _counter_rows(e2e_env, "cat_001")
    dog_counters = _counter_rows(e2e_env, "dog_001")

    # 正向：各自的写入完整且正确
    assert cat_counters == {("event", "gift", 1), ("action", "heart", 1)}
    assert dog_counters == {("event", "like", 1), ("action", "happy", 1)}
    assert _events(e2e_env, "cat_001") == [
        {"event_type": "gift", "action_name": "heart", "platform": "ws"}
    ]
    assert _events(e2e_env, "dog_001") == [
        {"event_type": "like", "action_name": "happy", "platform": "ws"}
    ]

    # 反向：**跨宠物零泄漏**（事件维度）
    assert ("event", "like", 1) not in cat_counters
    assert ("action", "happy", 1) not in cat_counters
    assert ("event", "gift", 1) not in dog_counters
    assert ("action", "heart", 1) not in dog_counters

    # 反向：**跨宠物零泄漏**（计数作用域维度）
    assert _counter_pet_scopes(e2e_env) == {"cat_001", "dog_001"}
    assert _event_pet_scopes(e2e_env) == {"cat_001", "dog_001"}
    # 每宠物恰 1 条事件行（2 次发送 → 2 行，未互相叠加）
    assert _fetch(e2e_env, "SELECT COUNT(*) AS n FROM events")[0]["n"] == 2


def test_e2e_interleaved_sessions_accumulate_per_pet_without_leakage(
    e2e_env: SimpleNamespace,
) -> None:
    """多次、交替的连接会话：同宠物累加、异宠物完全隔离（MP-2 per-connection 独立物件图）。

    会话顺序 cat → cat → dog。若 per-connection runtime 被错误共享/串用，
    cat 的第二次会话会污染 dog 或反之，本用例的计数与帧序列会立刻失败。
    """
    cat_frame_1 = _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    cat_frame_2 = _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    dog_frame = _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    # 每次会话各自收到属于自己的帧（3 次会话 → 3 帧，事件类型与连接一致）
    assert [f[0]["event_type"] for f in (cat_frame_1, cat_frame_2, dog_frame)] == [
        "gift", "gift", "like",
    ]

    # cat 两次累加到 2；dog 独立为 1
    assert _counter_rows(e2e_env, "cat_001") == {("event", "gift", 2), ("action", "heart", 2)}
    assert _counter_rows(e2e_env, "dog_001") == {("event", "like", 1), ("action", "happy", 1)}
    assert len(_events(e2e_env, "cat_001")) == 2
    assert len(_events(e2e_env, "dog_001")) == 1
    # 无第三个作用域被凭空创建
    assert _counter_pet_scopes(e2e_env) == {"cat_001", "dog_001"}


def test_e2e_pet_activity_never_leaks_into_null_scope_global_reads_or_default_runtime(
    e2e_env: SimpleNamespace,
) -> None:
    """pet 活动**不得**泄漏到：NULL 作用域 / ``/api/stats`` / ``/api/playback/state``。

    末项锁定 MP-2 的边界：pet runtime 是 per-connection 的，**不**存在服务端
    「当前宠物」——故默认 runtime（HTTP 读路径所读）必须保持未受扰动。
    """
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    # NULL 作用域零写入（MP-3：仅显式 pet 连接按 pet 写）
    assert _fetch(
        e2e_env, "SELECT id FROM interactions WHERE pet_id IS NULL"
    ) == []
    # 全局统计读路径（``pet_id IS NULL``）读不到 pet 作用域数据
    assert e2e_env.client.get("/api/stats").json()["events"] == {}
    # 默认 runtime 未被任何 pet 连接扰动（MP-2：无全局 current_pet / 无共享 active runtime）
    state = e2e_env.client.get("/api/playback/state").json()
    assert state["state"] == "idle"
    assert state["last_event"] is None
    # 默认 pipeline 自身快照亦未受扰动（同进程内直接只读校验）
    assert e2e_env.default_pipeline.snapshot().last_event is None


def test_e2e_comment_event_records_row_without_action_per_pet(
    e2e_env: SimpleNamespace,
) -> None:
    """无匹配规则的事件（``comment``）仍按宠物作用域落行，但**不产生动作**。

    用于确认「事件写入」与「动作执行」两条链路在 pet 作用域下都正确（不因多宠物而耦合）。
    """
    _push(e2e_env, "/api/ws?pet_id=cat_001", COMMENT_NO_ACTION)

    assert _events(e2e_env, "cat_001") == [
        {"event_type": "comment", "action_name": None, "platform": "ws"}
    ]
    assert _counter_rows(e2e_env, "cat_001") == {("event", "comment", 1)}


# ---------------------------------------------------------------------------
# 4) 非法 pet_id 拒收
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    ["unknown", "cat_00", "dog_002", "", " ", "CAT", "cat_001x", "熊猫"],
)
def test_e2e_invalid_pet_context_rejected_without_runtime_or_writes(
    e2e_env: SimpleNamespace, variant: str
) -> None:
    """非法 / 空 / 大小写不符 / 近似值 pet 上下文 → 连接被拒，且**不装配 runtime、不落库**。

    变体覆盖：完全不存在的键、近似键、空串、纯空白、大小写不符、非 ASCII。
    """
    before_events = _fetch(e2e_env, "SELECT COUNT(*) AS n FROM events")[0]["n"]
    before_counters = _fetch(e2e_env, "SELECT COUNT(*) AS n FROM interactions")[0]["n"]

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with e2e_env.client.websocket_connect(f"/api/ws?pet_id={quote(variant)}") as ws:
            ws.send_text(json.dumps(GIFT_HEART))

    # MP-1：拒收码 = 1008（policy violation），与「不建 fallback pet」口径一致
    assert excinfo.value.code == 1008

    # 零副作用：无事件行、无计数行、无 NULL 作用域写入
    assert _fetch(e2e_env, "SELECT COUNT(*) AS n FROM events")[0]["n"] == before_events
    assert _fetch(e2e_env, "SELECT COUNT(*) AS n FROM interactions")[0]["n"] == before_counters
    assert _fetch(e2e_env, "SELECT id FROM interactions WHERE pet_id IS NULL") == []


def test_e2e_invalid_context_after_valid_activity_leaves_existing_data_intact(
    e2e_env: SimpleNamespace,
) -> None:
    """**先合法后非法**：非法连接的拒收不得影响（也不得伪造）已有宠物的数据。"""
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    cat_before = _counter_rows(e2e_env, "cat_001")
    events_before = _fetch(e2e_env, "SELECT COUNT(*) AS n FROM events")[0]["n"]

    with pytest.raises(WebSocketDisconnect):
        with e2e_env.client.websocket_connect("/api/ws?pet_id=nope") as ws:
            ws.send_text(json.dumps(GIFT_HEART))

    assert _counter_rows(e2e_env, "cat_001") == cat_before
    assert _fetch(e2e_env, "SELECT COUNT(*) AS n FROM events")[0]["n"] == events_before
    assert _counter_pet_scopes(e2e_env) == {"cat_001"}


# ---------------------------------------------------------------------------
# 6) WM-1 / Event schema 零变更守卫
# ---------------------------------------------------------------------------


def test_e2e_outbound_frames_are_wm1_four_fields_for_every_pet(
    e2e_env: SimpleNamespace,
) -> None:
    """出站帧（真实 dispatcher，经网络抵达客户端）恒为 WM-1 **恰 4 字段**，逐宠物一致。"""
    cat_frames = _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    dog_frames = _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    for frame in (*cat_frames, *dog_frames):
        assert set(frame) == set(ENVELOPE_FIELDS) == set(ENVELOPE_KEYS)
        assert list(frame) == list(ENVELOPE_FIELDS)  # WM-1 字段顺序即输出顺序
        assert frame["source"] == PUSH_SOURCE == "ws"
        assert isinstance(frame["timestamp"], str) and frame["timestamp"].endswith("Z")

    assert cat_frames[0]["payload"] == {"gift_name": "小心心", "gift_count": 1}
    assert dog_frames[0]["payload"] == {"like_count": 3}


def test_e2e_inbound_envelope_still_must_be_exactly_four_fields(
    e2e_env: SimpleNamespace,
) -> None:
    """入站仍强制 WM-1 恰 4 字段：多字段 / 少字段一律消息级拒收，且连接存活。"""
    extra_field = dict(GIFT_HEART, room_id="r-1")           # 5 字段
    missing_field = {k: v for k, v in GIFT_HEART.items() if k != "source"}  # 3 字段

    # 只有末尾那条合法帧会产出出站帧（前两条消息级拒收 → 零推送）
    frames = _push(
        e2e_env, "/api/ws?pet_id=cat_001", extra_field, missing_field, GIFT_HEART, expect=1
    )

    # 收到的**首帧**即合法帧的内容 ⇒ 被拒的两条**没有**产出任何出站帧
    assert len(frames) == 1
    assert frames[0]["event_type"] == "gift"
    assert set(frames[0]) == set(ENVELOPE_FIELDS)
    # 被拒的两条零落库（恰 1 条事件行）
    assert len(_events(e2e_env, "cat_001")) == 1
    assert _counter_rows(e2e_env, "cat_001") == {("event", "gift", 1), ("action", "heart", 1)}


def test_e2e_event_model_and_frozen_ddl_schema_unchanged(e2e_env: SimpleNamespace) -> None:
    """Event 模型冻结面 + 冻结 DDL 列集**零变更**（3.2-C 未引入任何 schema 漂移）。

    同时验证一个关键设计事实：``interactions`` 的 ``pet_id`` 列与
    ``UNIQUE(stat_type, stat_key, pet_id)`` **在 Phase 1 冻结 DDL 中就已存在** ——
    多宠物作用域复用既有列，**不需要** schema 变更或 DB migration。
    """
    # -- Event 模型冻结面 ------------------------------------------------
    assert TOP_LEVEL_FIELDS == ("event_type", "user_id", "user_name", "payload")
    assert ALLOWED_EVENT_TYPES == ("comment", "gift", "like", "system")
    assert [f.name for f in dataclasses.fields(Event)] == list(TOP_LEVEL_FIELDS)
    assert list(ENVELOPE_FIELDS) == ["event_type", "payload", "timestamp", "source"]

    # -- 冻结 DDL 列集 ---------------------------------------------------
    db = Database(e2e_env.settings.database_path, constants.SCHEMA_PATH)
    with db.connect() as conn:
        def columns(table: str) -> list[str]:
            return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]

        assert tuple(columns("events")) == FROZEN_EVENTS_COLUMNS
        assert tuple(columns("interactions")) == FROZEN_INTERACTIONS_COLUMNS
        assert tuple(columns("assets")) == FROZEN_ASSETS_COLUMNS

        # ``interactions`` 仍以 (stat_type, stat_key, pet_id) 为唯一键
        unique_indexes = [
            r["name"] for r in conn.execute("PRAGMA index_list(interactions)")
            if r["unique"]
        ]
        assert unique_indexes, "interactions 缺少唯一索引"
        unique_columns = {
            tuple(
                r["name"] for r in conn.execute(f"PRAGMA index_info({name})")
            )
            for name in unique_indexes
        }
        assert ("stat_type", "stat_key", "pet_id") in unique_columns


# ---------------------------------------------------------------------------
# 基线行为：默认（无 pet_id）路径不受 3.2-A/3.2-C 影响
# ---------------------------------------------------------------------------


def test_e2e_default_path_unchanged_and_isolated_from_pet_scope(
    e2e_env: SimpleNamespace,
) -> None:
    """无 ``pet_id`` 的旧路径：行为逐字不变（``platform="ws"``、计数写 NULL、``/api/stats`` 可读），
    且与显式 pet 作用域**互不污染**。

    before / after 行为记录：本用例先走旧路径、再走 pet 路径，断言旧路径的
    NULL 作用域与 ``/api/stats`` 在 pet 写入前后**数值不变**。
    """
    # --- before：默认路径 ---
    default_frames = _push(e2e_env, "/api/ws", GIFT_HEART)
    assert len(default_frames) == 1

    default_rows = _fetch(
        e2e_env,
        "SELECT pet_id, action_name, platform FROM events ORDER BY id",
    )
    assert len(default_rows) == 1
    assert default_rows[0]["platform"] == "ws"
    assert default_rows[0]["action_name"] == "heart"
    # AS-2：旧路径的 events.pet_id 取组合根**派生**值（非 NULL），计数器才为 NULL
    assert default_rows[0]["pet_id"] == e2e_env.default_pet_id

    null_scope = {
        (r["stat_type"], r["stat_key"], r["value"])
        for r in _fetch(
            e2e_env,
            "SELECT stat_type, stat_key, value FROM interactions WHERE pet_id IS NULL",
        )
    }
    assert null_scope == {("event", "gift", 1), ("action", "heart", 1)}
    stats_before = e2e_env.client.get("/api/stats").json()
    assert stats_before["events"] == {"gift": 1}

    # --- after：显式 pet 上下文写入 ---
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)

    # 旧路径的 NULL 作用域与全局统计**完全不变**（pet 写入不污染全局读路径）
    null_scope_after = {
        (r["stat_type"], r["stat_key"], r["value"])
        for r in _fetch(
            e2e_env,
            "SELECT stat_type, stat_key, value FROM interactions WHERE pet_id IS NULL",
        )
    }
    assert null_scope_after == null_scope
    assert e2e_env.client.get("/api/stats").json() == stats_before

    # pet 作用域独立成立
    assert _counter_rows(e2e_env, "cat_001") == {("event", "gift", 1), ("action", "heart", 1)}
    # 两个作用域并存且互不干扰
    assert _counter_pet_scopes(e2e_env) == {None, "cat_001"}


# ---------------------------------------------------------------------------
# 7) Phase 3.2-A1：显式 pet_id 构造（构造期定值 / 作用域正确 / 无跨 pet 泄漏）
# ---------------------------------------------------------------------------

#: HTTP 门面（``simulate``）输入 —— API-1 顶层**恰 4 字段**；上面那些常量是 **WS envelope**
#: （含 ``timestamp`` / ``source``），只有经 adapter 才合法，**不可**直接喂给 ``simulate``。
GIFT_HEART_HTTP: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
}
LIKE_HAPPY_HTTP: dict = {
    "event_type": "like",
    "payload": {"like_count": 3},
}


def test_a1_explicit_pet_id_construction_scopes_writes_without_cross_leak(
    e2e_env: SimpleNamespace,
) -> None:
    """两个显式 pet 管道（``cat_001`` / ``dog_001``）—— **构造期定值**且互不干扰。

    与 WS 路径的差异：本测**不经连接**，直接以构造参数建立上下文，证明「pet 上下文」
    不再依赖 transport，也不再依赖 ``__new__`` 手工补写。
    """
    cat = SimulationPipeline(settings=e2e_env.settings, pet_id="cat_001")
    dog = SimulationPipeline(settings=e2e_env.settings, pet_id="dog_001")

    assert (cat.pet_id, dog.pet_id) == ("cat_001", "dog_001")

    cat.simulate(GIFT_HEART_HTTP)

    # 快照：cat 播放中；dog 的独立状态机未被影响
    assert cat.snapshot().action == "heart"
    assert cat.snapshot().pet_id == "cat_001"
    assert dog.snapshot().state == "idle"
    assert dog.snapshot().action is None

    # 落库作用域：只有 cat_001
    assert _events(e2e_env, "cat_001") == [
        {"event_type": "gift", "action_name": "heart", "platform": "simulator"}
    ]
    assert _events(e2e_env, "dog_001") == []
    assert _counter_rows(e2e_env, "cat_001") == {("event", "gift", 1), ("action", "heart", 1)}
    assert _counter_rows(e2e_env, "dog_001") == set()

    # **无跨 pet 泄漏**：显式管道绝不写 NULL 作用域，也不写对方的 key
    assert _event_pet_scopes(e2e_env) == {"cat_001"}
    assert _counter_pet_scopes(e2e_env) == {"cat_001"}


def test_a1_default_construction_keeps_legacy_null_counter_scope(
    e2e_env: SimpleNamespace,
) -> None:
    """默认构造（``pet_id=None``）**保持** Phase 1 兼容语义：counters 仍落 NULL 作用域。

    ⚠️ 这正是 MP-3 裁决「**仅显式 pet 按 pet 写**」的可观测后果，也是本步**刻意不变更**的
    既有行为：``events.pet_id`` 取组合根派生值（非 NULL），而 ``interactions.pet_id``
    为 NULL —— 二者**不同源**（MP-4 已登记的不对称，本步不解决）。
    """
    pipeline = SimulationPipeline(settings=e2e_env.settings)

    assert pipeline.pet_id == e2e_env.default_pet_id  # 派生，非硬编码

    pipeline.simulate(GIFT_HEART_HTTP)

    assert _events(e2e_env, e2e_env.default_pet_id) == [
        {"event_type": "gift", "action_name": "heart", "platform": "simulator"}
    ]
    assert _counter_pet_scopes(e2e_env) == {None}
    assert {
        (r["stat_type"], r["stat_key"], r["value"])
        for r in _fetch(
            e2e_env,
            "SELECT stat_type, stat_key, value FROM interactions WHERE pet_id IS NULL",
        )
    } == {("event", "gift", 1), ("action", "heart", 1)}


def test_a1_build_pipeline_for_pet_equals_explicit_constructor(
    e2e_env: SimpleNamespace,
) -> None:
    """``build_pipeline_for_pet`` 与显式构造**等价**（同一构造路径，非 ``__new__`` 产物）。

    ``__init__`` 的构造期初始化在此必须齐备 —— 这三项正是 3.2-A 时期需要手工补写、
    如今已删除的内容（``_last_event`` / ``_playback_clock`` / ``_runtime``）。
    """
    pipeline = build_pipeline_for_pet("dog_001", e2e_env.settings)

    assert type(pipeline) is SimulationPipeline
    assert pipeline.pet_id == "dog_001"
    assert pipeline._last_event is None
    assert pipeline._playback_clock.deadline() is None
    assert pipeline.event_repository is not None

    pipeline.simulate(LIKE_HAPPY_HTTP)

    assert _events(e2e_env, "dog_001") == [
        {"event_type": "like", "action_name": "happy", "platform": "simulator"}
    ]
    assert _counter_rows(e2e_env, "dog_001") == {("event", "like", 1), ("action", "happy", 1)}


# ---------------------------------------------------------------------------
# 8) Phase 3.2-B：pet 作用域 HTTP **读**接口（``?pet_id=``）端到端往返
# ---------------------------------------------------------------------------
# 本节断言只依赖**可观测产物**：真实 HTTP 读接口的响应体 + 库表行。
# 与上面各节的差异：那些看「出站帧 / 表行」，本节看**读接口能否读回同一作用域**。
# 契约：``phase3_pet_scoped_http_api_decision.md``（MB-1~MB-4）+ ``step4_api_query_boundary``
# 的 CR-1（QP-6）；授权 P-1=①（仅 canonical，不聚合 alias）· P-4（非法折 400，不新增码）。


def test_e2e_pet_scoped_stats_read_returns_that_pet_bucket(
    e2e_env: SimpleNamespace,
) -> None:
    """WS 按 pet 写入 → ``GET /api/stats?pet_id=`` **读回同一作用域**（B-read 核心往返）。

    同时锁定 A2=W：无参读路径仍只反映 ``NULL`` 桶，**读不到**任何 pet 作用域数据。
    """
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    cat = e2e_env.client.get("/api/stats", params={"pet_id": "cat_001"}).json()
    dog = e2e_env.client.get("/api/stats", params={"pet_id": "dog_001"}).json()
    default = e2e_env.client.get("/api/stats").json()

    assert cat == {"events": {"gift": 1}, "actions": {"heart": 1}, "total": 1}
    assert dog == {"events": {"like": 1}, "actions": {"happy": 1}, "total": 1}
    # 无参 = NULL 桶：pet 作用域的写入**不**泄漏进来（MP-3 + A2=W）
    assert default == {"events": {}, "actions": {}, "total": 0}
    # 别名与 canonical 归一到同一桶（A1=B / P-1=①）
    assert e2e_env.client.get("/api/stats", params={"pet_id": "cat"}).json() == cat


def test_e2e_pet_scoped_events_read_returns_only_that_pet(
    e2e_env: SimpleNamespace,
) -> None:
    """``GET /api/events/recent?pet_id=`` 只返回该宠物行；无参仍为**全表**（SQL 无 ``WHERE``）。"""
    _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)
    _push(e2e_env, "/api/ws?pet_id=dog_001", LIKE_HAPPY)

    cat = e2e_env.client.get("/api/events/recent", params={"pet_id": "cat_001"}).json()
    dog = e2e_env.client.get("/api/events/recent", params={"pet_id": "dog_001"}).json()
    all_rows = e2e_env.client.get("/api/events/recent").json()

    assert [i["event_type"] for i in cat["items"]] == ["gift"]
    assert [i["event_type"] for i in dog["items"]] == ["like"]
    # 行内 ``pet_id`` 与查询作用域一致（无跨界行）
    assert {i["pet_id"] for i in cat["items"]} == {"cat_001"}
    assert {i["pet_id"] for i in dog["items"]} == {"dog_001"}
    # 别名同样命中（读侧归一化）
    assert e2e_env.client.get("/api/events/recent", params={"pet_id": "dog"}).json() == dog
    # 无参 = 全表：两条都在，且 = 两个作用域过滤结果之和
    assert all_rows["count"] == cat["count"] + dog["count"] == 2


def test_e2e_pet_scoped_read_combines_with_limit(e2e_env: SimpleNamespace) -> None:
    """``limit`` 与 ``pet_id`` 可组合（``/events/recent`` 白名单恰 ``{limit, pet_id}``）。"""
    for _ in range(3):
        _push(e2e_env, "/api/ws?pet_id=cat_001", GIFT_HEART)

    one = e2e_env.client.get(
        "/api/events/recent", params={"limit": 1, "pet_id": "cat_001"}
    ).json()
    assert one["count"] == 1
    assert {i["pet_id"] for i in one["items"]} == {"cat_001"}

    full = e2e_env.client.get(
        "/api/events/recent", params={"limit": 200, "pet_id": "cat_001"}
    ).json()
    assert full["count"] == 3


@pytest.mark.parametrize("bad", ["nope", "cat_002", "", " ", "CAT", "熊猫"])
def test_e2e_invalid_pet_query_rejected_with_400_existing_code(
    e2e_env: SimpleNamespace, bad: str
) -> None:
    """非法 / 空 ``pet_id`` ⇒ ``400 INVALID_REQUEST``（P-4：复用既有码，AS-1 恰 3 码）。

    ⚠️ 与 WS 侧拒收（``close(1008)``，见上节）是**不同层**的等价处理：HTTP 无连接语义，
    故折为请求级 ``400``；两者互不替代、也不构成契约冲突。
    """
    stats = e2e_env.client.get("/api/stats", params={"pet_id": bad})
    assert stats.status_code == 400, bad
    assert stats.json()["code"] == "INVALID_REQUEST"

    recent = e2e_env.client.get("/api/events/recent", params={"pet_id": bad})
    assert recent.status_code == 400, bad
    assert recent.json()["code"] == "INVALID_REQUEST"


def test_e2e_unknown_query_param_still_rejected_with_pet_id_present(
    e2e_env: SimpleNamespace,
) -> None:
    """QP-2 不破：``pet_id`` 进白名单后，未知参数仍被拒（白名单语义，**非**忽略未知项）。"""
    resp = e2e_env.client.get(
        "/api/events/recent", params={"pet_id": "cat_001", "x": "1"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_e2e_write_side_pet_key_not_normalized_read_side_only(
    e2e_env: SimpleNamespace,
) -> None:
    """A1-resolver-scope = **仅 HTTP 读侧**：WS 写侧 ``pet_id`` 原样落库，**不**被归一化。

    可观测后果（MP-4 / R-10 已登记的**边界**，本步只上 B-read，**不处理**）：
    WS ``?pet_id=cat`` 写入键 ``cat``，而 HTTP ``?pet_id=cat`` 读的是 canonical ``cat_001``
    ⇒ 同一别名在读写两侧**不同源**。本用例锁定「**写侧零变更**」这一授权约束本身，
    并与上一条（读侧归一化）形成对照 —— 若 resolver 被误接进写侧，此用例立刻失败。
    """
    _push(e2e_env, "/api/ws?pet_id=cat", GIFT_HEART)

    # 写侧：原样写 ``cat``（未被 resolver 改写），且只出现这一个作用域
    assert _counter_rows(e2e_env, "cat") == {("event", "gift", 1), ("action", "heart", 1)}
    assert _events(e2e_env, "cat") == [
        {"event_type": "gift", "action_name": "heart", "platform": "ws"}
    ]
    assert _counter_pet_scopes(e2e_env) == {"cat"}
    assert _event_pet_scopes(e2e_env) == {"cat"}
    # 不存在被读侧归一化「顺手补齐」出的 cat_001 行
    assert _counter_rows(e2e_env, "cat_001") == set()
    assert _events(e2e_env, "cat_001") == []

    # 读侧：``?pet_id=cat`` 归一到 canonical ``cat_001`` ⇒ 读不到 ``cat`` 桶（边界，非缺陷修复）
    for key in ("cat", "cat_001"):
        assert e2e_env.client.get("/api/stats", params={"pet_id": key}).json() == {
            "events": {},
            "actions": {},
            "total": 0,
        }
