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
from types import MappingProxyType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.ws import get_ws_settings
from app.config.settings import Settings
from app.core import constants
from app.core.exceptions import AssetNotFoundError
from app.main import create_app
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.services.asset_manager import AssetManager
from app.services.pet_context import ALIAS_TO_CANONICAL, normalize_pet_key
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


# ---------------------------------------------------------------------------
# ⑧ Phase 3.2-B：pet 作用域**读**接口（CR-1 / QP-6 · ``MB-2`` / ``MB-3``）
# ---------------------------------------------------------------------------
# 契约来源：``docs/development/phase3_pet_scoped_http_api_decision.md``（v1.0 FROZEN）
# ``MB-1``~``MB-4``；``step4_api_query_boundary_decision.md`` 的 **CR-1**（新铸 **QP-6**）。
# 授权：A1=B（alias + resolver，**仅 HTTP 读侧**）· A2=W（默认作用域 = ``NULL``）·
# A3=S-1（无参 = ``NULL`` 桶）· P-1=①（仅 canonical，不聚合 alias）· P-4（非法折 ``400``）。


@pytest.fixture()
def pet_api(api: SimpleNamespace) -> SimpleNamespace:
    """在 ``api`` 之上**再**隔离 ``settings`` 来源（P-3）。

    **为何必须覆盖**：``known_pet_keys()`` 缺省回落到 ``Settings.default()``（真实仓库），
    会 ``initialize()`` 真实 ``database/pet_live.db`` —— 与本文件「绝不触碰真实库」的
    隔离口径冲突。覆盖后合法键由**隔离**素材根 + 隔离库派生：

        ``{"cat_001"}``（``assets/pets/cat/config.json`` 的 ``pet_id``）
        ∪ ``{"cat"}``（隔离 ``assets`` 表登记出的 ``pet_type``）

    ⚠️ 只服务本小节用例；既有 ``api`` 夹具与全部既有断言**零改动**。
    """
    api.app.dependency_overrides[get_ws_settings] = lambda: api.settings
    return api


# -- 默认（无参）读路径回归：A2=W / A3=S-1 的核心不变量 ----------------------


def test_pet_scope_stats_without_pet_id_reads_null_bucket(
    pet_api: SimpleNamespace,
) -> None:
    """**T-2**：无参 ``/api/stats`` 仍读 ``pet_id IS NULL`` 桶 —— 行为与改动前逐字一致。"""
    _simulate(pet_api.client, **GIFT_HEART)

    assert pet_api.client.get("/api/stats").json() == {
        "events": {"gift": 1},
        "actions": {"heart": 1},
        "total": 1,
    }


def test_pet_scope_recent_events_without_pet_id_reads_whole_table(
    pet_api: SimpleNamespace,
) -> None:
    """**T-4**：无参 ``/api/events/recent`` 仍读**全表**（SQL 无 ``WHERE``）。"""
    _simulate(pet_api.client, event_type="comment", payload={"content": "a"})
    _simulate(pet_api.client, **LIKE_HAPPY)

    body = pet_api.client.get("/api/events/recent").json()
    assert body["count"] == 2
    assert {item["event_type"] for item in body["items"]} == {"comment", "like"}


# -- 显式 pet 作用域（T-1 / T-3）-----------------------------------------


def test_pet_scope_stats_with_canonical_pet_id_reads_that_bucket(
    pet_api: SimpleNamespace,
) -> None:
    """**T-1**：``?pet_id=cat_001`` 读该 canonical 桶 —— 与无参结果**可不同**。

    本步只上 **B-read**：默认 pipeline 的聚合写入仍是 ``pet_id IS NULL``（MP-3 / MP-4），
    故 pet 桶此刻为空。这恰好把 MP-4 的**双源不对称**变成可观测断言 ——
    ``events`` 表已有 ``cat_001`` 行，而 ``interactions`` 表只有 ``NULL`` 行。
    （R-10 已登记该语义不对称；本步不处理，未实现 B-live 前 UI 不消费 pet 计数。）
    """
    _simulate(pet_api.client, **GIFT_HEART)

    default_body = pet_api.client.get("/api/stats").json()
    pet_body = pet_api.client.get("/api/stats", params={"pet_id": "cat_001"}).json()

    assert default_body == {"events": {"gift": 1}, "actions": {"heart": 1}, "total": 1}
    assert pet_body == {"events": {}, "actions": {}, "total": 0}
    assert pet_body != default_body


def test_pet_scope_recent_events_filters_by_canonical_bucket(
    pet_api: SimpleNamespace,
) -> None:
    """**T-3**：``?pet_id=`` 只返回该 canonical 桶的行（写入侧派生键即 ``cat_001``）。"""
    _simulate(pet_api.client, **GIFT_HEART)

    canonical = pet_api.client.get(
        "/api/events/recent", params={"pet_id": "cat_001"}
    ).json()
    alias = pet_api.client.get("/api/events/recent", params={"pet_id": "cat"}).json()

    assert canonical["count"] == 1
    assert canonical["items"][0]["pet_id"] == "cat_001"
    # A1=B / P-1=①：别名与 canonical 归一到**同一**桶 ⇒ 对外只有一套读口径
    assert alias == canonical


def test_pet_scope_pet_id_is_stripped_like_ws_transport(
    pet_api: SimpleNamespace,
) -> None:
    """首尾空白按 transport 惯例 ``strip()``（与 ``api/ws.py`` 同口径，**非**本步新规则）。"""
    _simulate(pet_api.client, **GIFT_HEART)

    padded = pet_api.client.get(
        "/api/events/recent", params={"pet_id": "  cat_001  "}
    ).json()
    exact = pet_api.client.get(
        "/api/events/recent", params={"pet_id": "cat_001"}
    ).json()
    assert padded == exact


# -- 非法输入与白名单（T-5 / T-6）---------------------------------------


@pytest.mark.parametrize("bad", ["nope", "cat_002", "", " ", "CAT", "cat_001x", "熊猫"])
def test_pet_scope_invalid_pet_id_rejected_with_existing_code(
    pet_api: SimpleNamespace, bad: str
) -> None:
    """**T-5**（P-4）：非法 / 空 ``pet_id`` ⇒ ``400 INVALID_REQUEST``（**不新增错误码**，AS-1）。

    变体覆盖：不存在键、近似键、空串、纯空白、大小写不符、超集键、非 ASCII。
    ⚠️ 与 WS 侧的 ``close(1008)`` 属**不同层**的等价处理，不构成契约冲突。
    失败语义是 **fail-closed**：绝不静默降级到默认作用域。
    """
    stats = pet_api.client.get("/api/stats", params={"pet_id": bad})
    assert stats.status_code == 400
    assert stats.json()["code"] == "INVALID_REQUEST"

    recent = pet_api.client.get("/api/events/recent", params={"pet_id": bad})
    assert recent.status_code == 400
    assert recent.json()["code"] == "INVALID_REQUEST"


def test_pet_scope_unknown_param_still_rejected_alongside_pet_id(
    pet_api: SimpleNamespace,
) -> None:
    """**T-6**（QP-2 不破）：``pet_id`` 进白名单后未知参数仍被拒（白名单语义，非忽略未知项）。

    同时验证**逐端点**白名单：``limit`` 只属 ``/events/recent``，出现在 ``/stats`` 上仍被拒。
    """
    resp = pet_api.client.get(
        "/api/events/recent", params={"pet_id": "cat_001", "x": "1"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"

    resp = pet_api.client.get("/api/stats", params={"pet_id": "cat_001", "limit": "5"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


# -- T-7：resolver 单元口径（纯映射 · 无副作用）---------------------------


def test_normalize_pet_key_maps_alias_to_canonical() -> None:
    """别名 → canonical；canonical → 自身（A1 = Option B）。"""
    assert normalize_pet_key("cat") == "cat_001"
    assert normalize_pet_key("cat_001") == "cat_001"
    assert normalize_pet_key("dog") == "dog_001"
    assert normalize_pet_key("panda_001") == "panda_001"


def test_normalize_pet_key_returns_none_for_absent_or_unmapped() -> None:
    """``None`` 透传（= 无作用域）；表外键 / 大小写不符 ⇒ ``None``（由调用方折 ``400``）。

    ⚠️ resolver **不做** ``strip()``：首尾空白由调用方按 transport 惯例处理（见上一条用例）。
    """
    assert normalize_pet_key(None) is None
    assert normalize_pet_key("CAT") is None
    assert normalize_pet_key("cat_002") is None
    assert normalize_pet_key(" cat_001") is None
    assert normalize_pet_key("") is None


def test_normalize_pet_key_table_is_read_only_and_complete() -> None:
    """别名表为**只读**映射，且每个 canonical 键与其别名成对登记（无单向残留）。"""
    assert isinstance(ALIAS_TO_CANONICAL, MappingProxyType)

    with pytest.raises(TypeError):
        ALIAS_TO_CANONICAL["cow"] = "cow_001"  # type: ignore[index]

    canonicals = set(ALIAS_TO_CANONICAL.values())
    assert canonicals == {"cat_001", "dog_001", "panda_001"}
    assert set(ALIAS_TO_CANONICAL) == canonicals | {"cat", "dog", "panda"}


# -- T-8：结构守卫（resolver 的作用域硬约束）------------------------------

SERVICES_DIR = APP_DIR / "services"
PET_CONTEXT_PATH = SERVICES_DIR / "pet_context.py"


def test_pet_context_resolver_respects_layer_boundaries() -> None:
    """**T-8**（``MB-2`` 作用域硬约束）：resolver 不越层 —— 无引擎 / 无仓储 / 无 ``sqlite3`` / 无 SQL。

    ``pet_context.py`` **不在** ``COMPOSITION_ROOT_MODULES`` 内 ⇒ 不受 300 行守卫；
    但它落在 ``services/`` ⇒ 仍受「引擎 import 只许落组合根两模块」守卫，本用例据实锁定。
    """
    assert PET_CONTEXT_PATH.is_file(), "services/pet_context.py 应存在"

    imported = _imported_names(PET_CONTEXT_PATH)
    assert not (imported & set(ENGINE_NAMES)), "resolver 不得 import 引擎类"
    for module in imported:
        assert not module.endswith(ENGINE_MODULES), f"resolver 不得 import {module}"
        assert module != "sqlite3", "resolver 不得 import sqlite3"
        assert module != "app.services.pipeline", "resolver 不得触达组合根"
        assert not module.startswith("app.repositories"), "resolver 不得 import 仓储层"
        assert not module.startswith("app.api"), "resolver 不得 import API 层"

    for text in _string_literals(PET_CONTEXT_PATH):
        upper = text.upper()
        for keyword in SQL_KEYWORDS:
            assert keyword not in upper, f"resolver 出现 SQL 字面量: {keyword}"
