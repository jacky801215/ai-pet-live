"""``DataManager`` 测试（Step 4.2-B §七 / §八）。

覆盖：schema 创建、``write_event`` 的 payload JSON 与 ``action_name`` 可空、
身份字段（``user_id`` / ``user_name`` / ``pet_id`` / ``platform``）的落库与向后兼容、
``record_action``、``aggregate_counter`` 的首次创建与累加、连接级 PRAGMA（CR-7）、以及结构守卫。

测试自身**不 import** ``Event`` / ``ActionEngine`` / ``PlaybackManager``
（守卫见文件末尾 ``test_test_module_has_no_upstream_imports``）。
"""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import constants
from app.repositories.db import Database
from app.services.data_manager import DataManager

SERVICE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "data_manager.py"
TEST_PATH = Path(__file__).resolve()

#: §八：DataManager 禁止 import 的上游模块
FORBIDDEN_IMPORTS = ("event", "action_engine", "interaction_engine", "playback_manager")
#: §五：禁止作为公开方法名出现
FORBIDDEN_METHODS = ("evaluate", "execute", "play", "subscribe", "trigger", "process", "handle")
#: §八：禁止作为调用出现（``conn.execute`` 属第三方 DB API，不在其列）
FORBIDDEN_CALLS = ("evaluate", "execute", "play", "subscribe")


@pytest.fixture()
def ctx(tmp_path: Path) -> SimpleNamespace:
    """隔离环境：临时 SQLite + 真实建表脚本（覆盖实际 DDL）。"""
    database = Database(tmp_path / "test_data.db", constants.SCHEMA_PATH)
    database.initialize()
    return SimpleNamespace(db=database, dm=DataManager(database))


def q(db: Database, sql: str, params: tuple = ()) -> list[dict]:
    """执行只读查询，返回 dict 行列表。"""
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def count(db: Database, table: str) -> int:
    """统计表行数。"""
    return q(db, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


def columns(db: Database, table: str) -> set[str]:
    """读取表字段名集合。"""
    return {r["name"] for r in q(db, f"PRAGMA table_info({table})")}


def imported_names(path: Path) -> set[str]:
    """AST 解析：收集模块 import 的顶层名字。"""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.update(node.module.split("."))
    return imported


# ---------------------------------------------------------------------------
# §四 schema
# ---------------------------------------------------------------------------
def test_schema_creates_events_and_interactions(ctx: SimpleNamespace) -> None:
    assert columns(ctx.db, "events") == {
        "id", "event_type", "user_id", "user_name", "pet_id",
        "action_name", "platform", "payload", "created_at",
    }
    assert columns(ctx.db, "interactions") == {
        "id", "stat_type", "stat_key", "pet_id",
        "value", "created_at", "last_time",
    }


def test_schema_does_not_create_pets_users_sessions(ctx: SimpleNamespace) -> None:
    names = {r["name"] for r in q(ctx.db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not ({"pets", "users", "sessions"} & names)
    assert {"assets", "events", "interactions"} <= names


def test_schema_indexes_are_present(ctx: SimpleNamespace) -> None:
    idx = {r["name"] for r in q(ctx.db, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_events_type", "idx_events_time", "idx_interactions_stat"} <= idx


# ---------------------------------------------------------------------------
# CR-7 连接级 PRAGMA
# ---------------------------------------------------------------------------
def test_connect_uses_wal_journal_and_normal_sync(ctx: SimpleNamespace) -> None:
    """CR-7：``Database.connect()`` 应为 **WAL** 且 ``synchronous=NORMAL``。

    - ``journal_mode`` 为库级持久属性 ⇒ 断言为 ``"wal"``；
    - ``synchronous`` 为连接级属性 ⇒ ``1`` = ``NORMAL``（修复前默认 ``2`` = ``FULL``）。
    """
    with ctx.db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1


def test_schema_is_idempotent(ctx: SimpleNamespace) -> None:
    ctx.db.initialize()  # 重复建表不得报错
    assert count(ctx.db, "events") == 0


# ---------------------------------------------------------------------------
# §六 write_event
# ---------------------------------------------------------------------------
def test_write_event_inserts_row_with_type_action_and_time(ctx: SimpleNamespace) -> None:
    ctx.dm.write_event("gift", {"gift": "heart"}, "heart")
    assert count(ctx.db, "events") == 1
    row = q(ctx.db, "SELECT * FROM events")[0]
    assert (row["event_type"], row["action_name"]) == ("gift", "heart")
    assert row["created_at"]


def test_write_event_action_name_is_nullable(ctx: SimpleNamespace) -> None:
    ctx.dm.write_event("comment", {"text": "hi"})
    assert q(ctx.db, "SELECT action_name FROM events")[0]["action_name"] is None


def test_write_event_payload_is_json_string(ctx: SimpleNamespace) -> None:
    payload = {"gift": "小红花", "nested": {"a": [1, 2]}}
    ctx.dm.write_event("gift", payload, "heart")
    stored = q(ctx.db, "SELECT payload FROM events")[0]["payload"]
    assert isinstance(stored, str)
    assert json.loads(stored) == payload
    assert "小红花" in stored  # ensure_ascii=False，中文不转义


@pytest.mark.parametrize("bad", ["", None])
def test_write_event_rejects_invalid_event_type(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.write_event(bad, {"a": 1})  # type: ignore[arg-type]
    assert count(ctx.db, "events") == 0


@pytest.mark.parametrize("bad", [[], None])
def test_write_event_rejects_non_mapping_payload(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.write_event("gift", bad)  # type: ignore[arg-type]
    assert count(ctx.db, "events") == 0


@pytest.mark.parametrize("bad", ["", 7])
def test_write_event_rejects_invalid_action_name(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.write_event("gift", {"a": 1}, bad)  # type: ignore[arg-type]
    assert count(ctx.db, "events") == 0


def test_write_event_rejects_unserializable_payload(ctx: SimpleNamespace) -> None:
    ctx.dm.write_event("gift", {"bad": {1, 2}})  # set 不可 JSON 序列化
    assert count(ctx.db, "events") == 0


def test_write_event_identity_columns_default_to_null(ctx: SimpleNamespace) -> None:
    """向后兼容（Step 4.3-B-2-L2）：旧式 2 参数调用 ⇒ 身份四列仍落 ``NULL``。

    省略 keyword-only 身份参数**不得**改变既有行为：行照写（不丢写），四列为 ``NULL``。
    """
    ctx.dm.write_event("test", {})
    assert count(ctx.db, "events") == 1
    row = q(ctx.db, "SELECT * FROM events")[0]
    assert row["user_id"] is None
    assert row["user_name"] is None
    assert row["pet_id"] is None
    assert row["platform"] is None


def test_write_event_identity_columns_are_persisted(ctx: SimpleNamespace) -> None:
    """新 keyword-only 参数 ⇒ 身份四列落真实值（``events`` 九字段完整落库）。"""
    ctx.dm.write_event(
        "gift",
        {"gift": "heart"},
        "heart",
        user_id="u_1",
        user_name="Tom",
        pet_id="cat_001",
        platform="simulator",
    )
    assert count(ctx.db, "events") == 1
    row = q(ctx.db, "SELECT * FROM events")[0]
    assert row["user_id"] == "u_1"
    assert row["user_name"] == "Tom"
    assert row["pet_id"] == "cat_001"
    assert row["platform"] == "simulator"
    assert row["action_name"] == "heart"  # 既有位置参数行为不变
    assert row["event_type"] == "gift"


def test_write_event_empty_user_name_is_preserved(ctx: SimpleNamespace) -> None:
    """``user_name=""`` 是**合法值**（事件契约：``user_name`` 缺失补 ``""``）。

    空串与 ``None``（显式 ``null``）语义不同，**不得**把 ``""`` 折叠为 ``NULL``。
    """
    ctx.dm.write_event("like", {}, user_name="")
    assert q(ctx.db, "SELECT user_name FROM events")[0]["user_name"] == ""


def test_write_event_non_str_identity_falls_back_to_null(ctx: SimpleNamespace) -> None:
    """身份字段非 ``str``/``None`` ⇒ 降级为 ``NULL`` 且**不丢行**。

    身份字段是附加元数据：非法值不应导致整行明细丢写（丢行会让事件计数与明细不一致）。
    """
    ctx.dm.write_event("like", {}, user_id={"bad": 1})  # type: ignore[arg-type]
    assert count(ctx.db, "events") == 1
    assert q(ctx.db, "SELECT user_id FROM events")[0]["user_id"] is None


# ---------------------------------------------------------------------------
# §六 record_action
# ---------------------------------------------------------------------------
def test_record_action_creates_then_accumulates(ctx: SimpleNamespace) -> None:
    ctx.dm.record_action("heart")
    row = q(ctx.db, "SELECT * FROM interactions")[0]
    assert (row["stat_type"], row["stat_key"], row["value"]) == ("action", "heart", 1)

    ctx.dm.record_action("heart")
    assert count(ctx.db, "interactions") == 1
    assert q(ctx.db, "SELECT value FROM interactions")[0]["value"] == 2


def test_record_action_uses_separate_rows_per_action(ctx: SimpleNamespace) -> None:
    ctx.dm.record_action("heart")
    ctx.dm.record_action("happy")
    rows = q(ctx.db, "SELECT stat_key FROM interactions ORDER BY stat_key")
    assert [r["stat_key"] for r in rows] == ["happy", "heart"]


def test_record_action_writes_no_event_rows(ctx: SimpleNamespace) -> None:
    ctx.dm.record_action("heart")
    assert count(ctx.db, "events") == 0


@pytest.mark.parametrize("bad", ["", None])
def test_record_action_rejects_invalid_action(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.record_action(bad)  # type: ignore[arg-type]
    assert count(ctx.db, "interactions") == 0


# ---------------------------------------------------------------------------
# §六 aggregate_counter
# ---------------------------------------------------------------------------
def test_aggregate_creates_then_accumulates(ctx: SimpleNamespace) -> None:
    ctx.dm.aggregate_counter("event", "like", 1)
    row = q(ctx.db, "SELECT * FROM interactions")[0]
    assert (row["stat_type"], row["stat_key"], row["value"]) == ("event", "like", 1)

    ctx.dm.aggregate_counter("event", "like", 1)
    assert count(ctx.db, "interactions") == 1
    assert q(ctx.db, "SELECT value FROM interactions")[0]["value"] == 2


def test_aggregate_keeps_created_at_and_refreshes_last_time(ctx: SimpleNamespace) -> None:
    ctx.dm.aggregate_counter("event", "gift", 1)
    created_before = q(ctx.db, "SELECT created_at FROM interactions")[0]["created_at"]
    with ctx.db.connect() as conn:
        conn.execute("UPDATE interactions SET last_time = '2000-01-01 00:00:00'")

    ctx.dm.aggregate_counter("event", "gift", 1)

    row = q(ctx.db, "SELECT created_at, last_time FROM interactions")[0]
    assert row["created_at"] == created_before
    assert row["last_time"] != "2000-01-01 00:00:00"


def test_aggregate_event_and_action_coexist(ctx: SimpleNamespace) -> None:
    ctx.dm.aggregate_counter("event", "gift", 1)
    ctx.dm.aggregate_counter("action", "heart", 1)
    rows = q(ctx.db, "SELECT stat_type FROM interactions ORDER BY stat_type")
    assert [r["stat_type"] for r in rows] == ["action", "event"]


@pytest.mark.parametrize("bad", ["total", "ACTION"])
def test_aggregate_rejects_invalid_stat_type(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.aggregate_counter(bad, "like", 1)  # type: ignore[arg-type]
    assert count(ctx.db, "interactions") == 0


@pytest.mark.parametrize("bad", ["", None])
def test_aggregate_rejects_invalid_stat_key(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.aggregate_counter("event", bad, 1)  # type: ignore[arg-type]
    assert count(ctx.db, "interactions") == 0


@pytest.mark.parametrize("bad", ["1", True])
def test_aggregate_rejects_non_int_value(ctx: SimpleNamespace, bad: object) -> None:
    ctx.dm.aggregate_counter("event", "like", bad)  # type: ignore[arg-type]
    assert count(ctx.db, "interactions") == 0


# ---------------------------------------------------------------------------
# §八 结构守卫
# ---------------------------------------------------------------------------
class _BrokenDatabase:
    """模拟连接失败的数据库（验证写库失败被吞掉）。"""

    def connect(self):  # pragma: no cover - 仅用于触发异常
        raise sqlite3.OperationalError("boom")


def test_write_failure_is_swallowed() -> None:
    dm = DataManager(_BrokenDatabase())  # type: ignore[arg-type]
    dm.write_event("gift", {"a": 1}, "heart")  # 不抛异常
    dm.record_action("heart")
    dm.aggregate_counter("event", "gift", 1)


def test_public_api_is_exactly_three_methods() -> None:
    public = {m for m in dir(DataManager) if not m.startswith("_")}
    assert public == {"write_event", "record_action", "aggregate_counter"}


def test_module_imports_are_allowed_only() -> None:
    imported = imported_names(SERVICE_PATH)
    assert not (set(FORBIDDEN_IMPORTS) & imported)
    assert "models" not in imported  # 不得依赖任何上游模型


def test_module_has_no_forbidden_definitions_or_calls() -> None:
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in FORBIDDEN_METHODS and not node.name.startswith("_"):
                hits.append(f"def {node.name}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                hits.append(f"call {node.func.id}")
    assert hits == []


def test_test_module_has_no_upstream_imports() -> None:
    imported = imported_names(TEST_PATH)
    assert not (set(FORBIDDEN_IMPORTS) & imported)
    assert "models" not in imported
