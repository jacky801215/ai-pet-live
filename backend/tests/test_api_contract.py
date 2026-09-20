"""Backend API 契约测试（Step 4.3-B-1）。

契约来源：

    - ``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）API-1 / API-2 / API-3 / API-4
    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）DA-1 / DA-3 / DA-5 / DA-7
    - ``docs/development/step4_api_runtime_decision.md``（v1.0 FROZEN）DB-4 / DB-5 / DB-6

覆盖范围（DB-5 冻结）：

    ① ``POST /api/events/simulate``（含 API-1 反例：发 ``action`` / ``action_type`` /
       ``asset_url`` / 白名单外 ``event_type`` ⇒ 400）
    ② ``GET /api/playback/state``（六字段快照 + 到期回落）
    ③ ``GET /api/stats``
    ④ ``GET /api/events/recent``（含 ``limit`` 边界）
    ⑤ 错误契约（``{code,message}`` 三码 + 未知顶层字段 400）
    ⑥ 结构守卫（``api/**`` 不 import 引擎、无 SQL；``main.py`` 零路由零引擎）
    ⑦ 静态挂载与 CORS（DA-5 / DB-6）

隔离（DB-5 硬要求）：**临时** ``project_root`` + 临时 SQLite + 真实 DDL
（``constants.SCHEMA_PATH``），**绝不触碰**真实 ``database/pet_live.db``；
``TestClient`` 同步驱动，**不**真起端口。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.core import constants
from app.core.exceptions import AssetNotFoundError
from app.main import create_app
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.services.asset_manager import AssetManager
from app.services.pipeline import SimulationPipeline, get_pipeline
from tests.conftest import FAKE_MP4_BYTES, make_action_file, register_asset

# ---------------------------------------------------------------------------
# 常量 / 夹具
# ---------------------------------------------------------------------------

#: 测试宠物已登记的动作（时长 1s，便于验证播放窗口）
ACTIONS: tuple[str, ...] = ("idle", "heart", "happy")
ASSET_DURATION_MS: int = 1000

#: 命中规则的事件：``gift`` + ``小心心`` → ``heart``
GIFT_HEART: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
}
#: 命中规则的事件：``like`` + ``like_count >= 3`` → ``happy``
LIKE_HAPPY: dict = {"event_type": "like", "payload": {"like_count": 3}}

PLAYBACK_FIELDS: frozenset[str] = frozenset(
    {"pet_id", "state", "action", "asset_url", "queue_size", "last_event"}
)
EVENT_ITEM_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "event_type",
        "user_id",
        "user_name",
        "pet_id",
        "action_name",
        "platform",
        "payload",
        "created_at",
    }
)


class FakeClock:
    """可控单调时钟（秒）—— 让「轮询驱动到期」可被确定性地验证。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def api(tmp_path: Path) -> SimpleNamespace:
    """隔离的 API 测试环境（临时库 + 临时素材 + 假时钟 + 假依赖覆盖）。"""
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
        database_path=tmp_path / "api_test.db",
        # 复用真实建表脚本，确保测试覆盖实际 DDL（DB-5）
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

    # 静态目录用临时素材根，导入/挂载不依赖真实仓库目录（DB-R1 落地口径）
    app = create_app(static_dir=assets_root)
    app.dependency_overrides[get_pipeline] = lambda: pipeline

    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        pipeline=pipeline,
        clock=clock,
        settings=settings,
        project_root=tmp_path,
        assets_root=assets_root,
    )


def _simulate(client: TestClient, **body: object):
    """POST /api/events/simulate 的简写。"""
    return client.post("/api/events/simulate", json=body)


# ---------------------------------------------------------------------------
# ① Event API（API-1）
# ---------------------------------------------------------------------------


def test_simulate_gift_triggers_heart_playing(api: SimpleNamespace) -> None:
    """``gift`` + ``小心心`` → ``heart``，响应是**裸快照**（无 ``accepted`` 包裹）。"""
    resp = _simulate(api.client, **GIFT_HEART)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "playing"
    assert body["action"] == "heart"
    assert body["asset_url"] == "/assets/pets/cat/actions/heart/heart.mp4"
    assert body["pet_id"] == "cat_001"
    assert body["last_event"] == "gift"
    assert body["queue_size"] == 0


def test_simulate_like_threshold_triggers_happy(api: SimpleNamespace) -> None:
    """``like`` + ``like_count >= 3`` → ``happy``（规则由后端判定，UI 不知道阈值）。"""
    resp = _simulate(api.client, **LIKE_HAPPY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "playing"
    assert body["action"] == "happy"
    assert body["asset_url"] == "/assets/pets/cat/actions/happy/happy.mp4"
    assert body["last_event"] == "like"


def test_simulate_without_matching_rule_stays_idle(api: SimpleNamespace) -> None:
    """无规则命中是**正常业务结果**（不是错误）：事件仍 200 受理并落库。"""
    resp = _simulate(api.client, event_type="comment", payload={"content": "你好"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "idle"
    assert body["action"] is None
    assert body["asset_url"] is None
    assert body["last_event"] == "comment"


def test_playback_state_has_exactly_six_contract_fields(api: SimpleNamespace) -> None:
    """快照**恰好**六字段；内部命名与物理路径一律不得外泄（API-2）。"""
    body = _simulate(api.client, **GIFT_HEART).json()
    assert set(body) == PLAYBACK_FIELDS
    for forbidden in (
        "action_type",
        "path",
        "asset_path",
        "pet_type",
        "command",
        "metadata",
        "thinking",
        "mood",
        "counts",
    ):
        assert forbidden not in body


def test_simulate_missing_payload_defaults_to_empty_object(
    api: SimpleNamespace,
) -> None:
    """``payload`` 省略 ⇒ 补 ``{}``（缺失与显式 ``null`` 语义不同）。"""
    resp = _simulate(api.client, event_type="like")
    assert resp.status_code == 200
    assert resp.json()["last_event"] == "like"
    # like_count 缺失 → 阈值规则不命中 → 无动作
    assert resp.json()["action"] is None

    items = api.client.get("/api/events/recent").json()["items"]
    assert items[0]["payload"] == {}


def test_simulate_explicit_null_payload_rejected(api: SimpleNamespace) -> None:
    """``payload: null`` 属**非法类型**，必须拒绝（不得静默修正为 ``{}``）。"""
    resp = _simulate(api.client, event_type="like", payload=None)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_simulate_unknown_event_type_rejected(api: SimpleNamespace) -> None:
    """白名单外 ``event_type`` ⇒ 400；错误体只含 ``code`` / ``message``。"""
    resp = _simulate(api.client, event_type="follow")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "follow" in body["message"]
    assert set(body) <= {"code", "message"}

    joined = json.dumps(body, ensure_ascii=False).lower()
    for leaked in ("traceback", 'file "', "sqlite", "select "):
        assert leaked not in joined


def test_simulate_missing_event_type_rejected(api: SimpleNamespace) -> None:
    """缺 ``event_type`` ⇒ 400（契约要求的必填字段）。"""
    resp = _simulate(api.client, payload={"content": "x"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "extra",
    [{"action": "happy"}, {"action_type": "happy"}, {"asset_url": "/x.mp4"}],
)
def test_simulate_rejects_contract_forbidden_keys(
    api: SimpleNamespace, extra: dict
) -> None:
    """API-1 反例（DA-7 = A）：UI 不得发送规则输出或素材信息，未知顶层字段**拒绝**。"""
    resp = _simulate(api.client, **{**GIFT_HEART, **extra})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"
    assert "Extra inputs are not permitted" in resp.json()["message"]


def test_simulate_rejects_forbidden_payload_field(api: SimpleNamespace) -> None:
    """事件级 payload 禁止字段（``gift`` 用 ``count``）⇒ 400。"""
    resp = _simulate(
        api.client,
        event_type="gift",
        payload={"gift_name": "小心心", "gift_count": 1, "count": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_simulate_rejects_missing_payload_required_field(
    api: SimpleNamespace,
) -> None:
    """事件级 payload 必填字段缺失（``comment`` 缺 ``content``）⇒ 400。"""
    resp = _simulate(api.client, event_type="comment", payload={})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# ② Playback State API（API-2）
# ---------------------------------------------------------------------------


def test_playback_state_initially_idle(api: SimpleNamespace) -> None:
    """未受理任何事件时返回 ``idle`` 快照（``last_event`` 为 ``null``）。"""
    resp = api.client.get("/api/playback/state")
    assert resp.status_code == 200
    assert resp.json() == {
        "pet_id": "cat_001",
        "state": "idle",
        "action": None,
        "asset_url": None,
        "queue_size": 0,
        "last_event": None,
    }


def test_playback_state_playing_then_falls_back_to_idle(
    api: SimpleNamespace,
) -> None:
    """POST 后 ``playing``；播放窗口过后查询即回落 ``idle``（轮询驱动到期）。"""
    _simulate(api.client, **GIFT_HEART)

    playing = api.client.get("/api/playback/state").json()
    assert playing["state"] == "playing"
    assert playing["action"] == "heart"
    assert playing["asset_url"] == "/assets/pets/cat/actions/heart/heart.mp4"

    api.clock.advance(ASSET_DURATION_MS / 1000 + 1)

    idle = api.client.get("/api/playback/state").json()
    assert idle["state"] == "idle"
    assert idle["action"] is None
    assert idle["asset_url"] is None
    assert idle["queue_size"] == 0
    # 最近事件是纯投影，播放结束后仍保留
    assert idle["last_event"] == "gift"


# ---------------------------------------------------------------------------
# ③ Data Query API（API-3）
# ---------------------------------------------------------------------------


def test_stats_initially_empty(api: SimpleNamespace) -> None:
    """无数据时三个键都存在且为空（结构稳定先于取值）。"""
    assert api.client.get("/api/stats").json() == {
        "events": {},
        "actions": {},
        "total": 0,
    }


def test_stats_counts_events_and_actions_from_writes(api: SimpleNamespace) -> None:
    """``events`` / ``actions`` 由 ``interactions`` 两个维度派生；``total`` 只计事件。"""
    _simulate(api.client, **GIFT_HEART)
    api.clock.advance(ASSET_DURATION_MS / 1000 + 1)
    _simulate(api.client, **LIKE_HAPPY)
    api.clock.advance(ASSET_DURATION_MS / 1000 + 1)
    _simulate(api.client, event_type="comment", payload={"content": "你好"})

    body = api.client.get("/api/stats").json()
    assert body["events"] == {"comment": 1, "gift": 1, "like": 1}
    assert body["actions"] == {"happy": 1, "heart": 1}
    # total = 事件计数之和（动作是事件的派生结果，不重复计入）
    assert body["total"] == 3


def test_stats_rejects_unknown_query_params(api: SimpleNamespace) -> None:
    """未知查询参数拒绝（与 DA-7 同口径；``4.3-B-0/DB-5`` 残留项落地）。"""
    resp = api.client.get("/api/stats", params={"x": "1"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"
    assert "x" in resp.json()["message"]


def test_playback_state_rejects_unknown_query_params(api: SimpleNamespace) -> None:
    """QP-2 / L-QP-1：``GET /api/playback/state`` 未知 query 同样拒绝（原缺口）。"""
    resp = api.client.get("/api/playback/state", params={"x": "1"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_recent_events_rejects_unknown_query_params(api: SimpleNamespace) -> None:
    """QP-2：``GET /api/events/recent`` 未知 query 拒绝（与 stats 同口径）。"""
    resp = api.client.get("/api/events/recent", params={"x": "1"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_recent_events_rejects_mixed_query_params(api: SimpleNamespace) -> None:
    """QP-2：合法 ``limit`` 与未知参数**混用**同样拒绝（白名单语义，非忽略未知项）。"""
    resp = api.client.get("/api/events/recent", params={"limit": 20, "x": "1"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_recent_events_default_limit_and_count(api: SimpleNamespace) -> None:
    """默认 ``limit=20``；``count`` = ``items`` 实际条数。"""
    for _ in range(3):
        _simulate(api.client, event_type="comment", payload={"content": "hi"})

    body = api.client.get("/api/events/recent").json()
    assert body["count"] == 3
    assert len(body["items"]) == 3


def test_recent_event_item_shape_and_payload_decoding(api: SimpleNamespace) -> None:
    """``<EventItem>`` 恰好 9 字段；``payload`` 在响应中为**对象**（库内是字符串，D1）。"""
    _simulate(api.client, **GIFT_HEART)

    item = api.client.get("/api/events/recent").json()["items"][0]
    assert set(item) == EVENT_ITEM_FIELDS
    assert item["event_type"] == "gift"
    assert item["action_name"] == "heart"
    assert isinstance(item["payload"], dict)
    assert item["payload"] == {"gift_name": "小心心", "gift_count": 1}
    assert isinstance(item["created_at"], str) and item["created_at"]
    assert set(item["payload"]).isdisjoint({"action_name", "pet_id"})


def test_recent_events_identity_columns_are_persisted(api: SimpleNamespace) -> None:
    """Step 4.3-B-2-L2（AS-2 授权的 CR）：身份四列落**真实值**，不再是 ``NULL``。

    - ``user_id`` / ``user_name`` 取自 ``Event``（UI 发出的原始事件，API 层不补常量）；
    - ``pet_id`` 由组合根从 ``AssetManager`` 派生的对外主键（这里 = ``cat_001``）；
    - ``platform`` 固定 ``"simulator"``（Phase 1 无真实平台接入）。

    字段集**不变**（仍为 9 列），只取值从 ``null`` 变为真实值。
    """
    _simulate(
        api.client,
        event_type="gift",
        user_id="u_1",
        user_name="Tom",
        payload={"gift_name": "小心心", "gift_count": 1},
    )

    item = api.client.get("/api/events/recent").json()["items"][0]
    assert item["user_id"] == "u_1"
    assert item["user_name"] == "Tom"
    assert item["pet_id"] == "cat_001"
    assert item["platform"] == "simulator"


def test_recent_events_limit_one_returns_latest(api: SimpleNamespace) -> None:
    """排序 ``created_at DESC, id DESC`` ⇒ ``limit=1`` 取最新一条。"""
    _simulate(api.client, event_type="comment", payload={"content": "first"})
    _simulate(api.client, event_type="like")

    items = api.client.get("/api/events/recent", params={"limit": 1}).json()["items"]
    assert len(items) == 1
    assert items[0]["event_type"] == "like"


@pytest.mark.parametrize("bad_limit", [0, 201, "abc"])
def test_recent_events_limit_out_of_range_rejected(
    api: SimpleNamespace, bad_limit: object
) -> None:
    """``limit`` 越界（``<1`` / ``>200`` / 非整数）⇒ 400 ``INVALID_REQUEST``（非 422）。"""
    resp = api.client.get("/api/events/recent", params={"limit": bad_limit})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# ⑤ 错误契约（API-4 / DA-3）
# ---------------------------------------------------------------------------


def test_unhandled_exception_maps_to_500_internal_error(api: SimpleNamespace) -> None:
    """未捕获异常 ⇒ 500 ``INTERNAL_ERROR``；堆栈只进日志，响应体不含堆栈。"""
    app = create_app(static_dir=api.assets_root)

    @app.get("/_probe/unhandled")
    def _probe_unhandled() -> dict:  # pragma: no cover - 仅测试探针
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/_probe/unhandled")

    assert resp.status_code == 500
    assert resp.json() == {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}


def test_asset_not_found_maps_to_404(api: SimpleNamespace) -> None:
    """``AssetNotFoundError`` ⇒ 404 ``ASSET_NOT_FOUND``；``context`` 不下发（UI 不得依赖）。"""
    app = create_app(static_dir=api.assets_root)

    @app.get("/_probe/asset-missing")
    def _probe_asset_missing() -> dict:  # pragma: no cover - 仅测试探针
        raise AssetNotFoundError(
            "资产未登记: cat/unknown", pet_type="cat", action="unknown"
        )

    with TestClient(app) as client:
        resp = client.get("/_probe/asset-missing")

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "ASSET_NOT_FOUND"
    assert body["message"] == "资产未登记: cat/unknown"
    assert "context" not in body


# ---------------------------------------------------------------------------
# ⑦ 静态挂载（DA-5）与 CORS（DB-6）
# ---------------------------------------------------------------------------


def test_static_assets_served_and_project_root_not_mounted(
    api: SimpleNamespace,
) -> None:
    """素材经 ``/assets/pets`` 提供；**项目根不得挂载**（否则 DB / .env 会裸露）。"""
    assert constants.ASSET_URL_PREFIX == "/assets/pets"

    served = api.client.get("/assets/pets/cat/actions/heart/heart.mp4")
    assert served.status_code == 200
    assert served.content == FAKE_MP4_BYTES

    # 项目根未被挂载：任意仓库文件都不可经 HTTP 下载
    assert api.client.get("/database/schema.sql").status_code == 404


def test_cors_allows_localhost_dev_origin_only(api: SimpleNamespace) -> None:
    """CORS 白名单放行本机 dev 源；**禁止** ``allow_origins=["*"]``。"""
    allowed = api.client.get(
        "/api/stats", headers={"Origin": "http://localhost:5173"}
    )
    assert allowed.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )

    denied = api.client.get("/api/stats", headers={"Origin": "http://evil.example"})
    assert denied.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------------------
# ⑥ 结构守卫（§九）
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parents[1] / "app"
API_DIR = APP_DIR / "api"
MAIN_PATH = APP_DIR / "main.py"

ENGINE_NAMES: frozenset[str] = frozenset(
    {"ActionEngine", "InteractionEngine", "PlaybackManager"}
)
ENGINE_MODULES: tuple[str, ...] = (
    "action_engine",
    "interaction_engine",
    "playback_manager",
)
SQL_KEYWORDS: tuple[str, ...] = ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def _string_literals(path: Path) -> list[str]:
    return [
        node.value
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_api_layer_never_imports_engines() -> None:
    """§九 守卫：``api/**`` 只 import 组合根（``services/pipeline.py``），不 import 引擎。"""
    files = sorted(API_DIR.glob("*.py"))
    assert files, "app/api/ 下应存在路由模块"
    for path in files:
        imported = _imported_names(path)
        assert not (imported & set(ENGINE_NAMES)), f"{path.name} 不得 import 引擎类"
        for module in imported:
            assert not module.endswith(ENGINE_MODULES), f"{path.name} 不得 import {module}"


def test_api_layer_and_entry_contain_no_sql() -> None:
    """§九 守卫：API 层与入口均零 SQL、不 import ``sqlite3``（SQL 只属 repositories / DataManager）。"""
    for path in [*sorted(API_DIR.glob("*.py")), MAIN_PATH]:
        imported = _imported_names(path)
        assert "sqlite3" not in imported, f"{path.name} 不得 import sqlite3"
        for text in _string_literals(path):
            upper = text.upper()
            for keyword in SQL_KEYWORDS:
                assert keyword not in upper, f"{path.name} 出现 SQL 字面量: {keyword}"


def test_entry_defines_no_routes_and_no_engine_dependency() -> None:
    """§九 守卫：``main.py`` 零业务逻辑 —— 不定义路由、不碰引擎、不持 ``Database``。"""
    source = MAIN_PATH.read_text(encoding="utf-8")
    for marker in ("@app.get(", "@app.post(", "@app.put(", "@app.patch(", "@app.delete("):
        assert marker not in source, f"main.py 不得定义路由: {marker}"

    imported = _imported_names(MAIN_PATH)
    assert not (imported & set(ENGINE_NAMES))
    assert "Database" not in imported
    assert "sqlite3" not in imported


def test_asgi_entry_is_unique() -> None:
    """DB-3 / DB-4：ASGI 入口唯一 = ``app/main.py``；禁止第二入口与第二编排层。"""
    assert MAIN_PATH.is_file()
    assert not (API_DIR / "app.py").exists()
    assert not (APP_DIR / "routes").exists()
    assert not (APP_DIR / "services" / "api_service.py").exists()
