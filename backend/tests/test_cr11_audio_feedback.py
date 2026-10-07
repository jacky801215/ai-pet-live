"""CR-11 音效契约：数据层 / DB 迁移 / 素材解析单元测试。

契约来源：``docs/change_request/cr-11_audio_feedback_design.md``。

覆盖：

    ① **DDL 增量**：``assets.audio_path`` 存在，且**新建库**与**迁移库**列序**逐列相同**；
    ② **幂等迁移**：既有库（无该列）执行 ``initialize()`` 补列成功、**可重复调用**、
       既有数据零丢失、``UNIQUE(pet_type, action)`` 语义不变；
    ③ **仓储往返**：``audio_path`` 写入 / 读回；``upsert`` 采用**全量覆盖**
       （未提供 ⇒ 写 ``NULL``，**不**保留旧值）；
    ④ **模型契约**：``AssetRecord`` 默认值兼容既有构造点；
       ``AssetMetadata.to_dict()`` **仍恰 3 字段**（冻结契约，**不含** ``audio_path``）；
    ⑤ **解析入口**：``AssetManager.resolve_audio_asset`` 宽容语义（未登记 / 无音效 ⇒ ``None``）；
    ⑥ **seed 显式映射**：``AUDIO_ACTIONS`` 命中且文件存在才登记；**禁止**存在性推断。

隔离：临时库 + 真实 DDL（``constants.SCHEMA_PATH``），**绝不触碰**真实 ``database/pet_live.db``。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import constants
from app.core.exceptions import InvalidRequestError
from app.models.asset import AssetMetadata, AssetRecord
from app.repositories.db import Database
from scripts import init_assets
from tests.conftest import (
    asset_rel_path,
    audio_rel_path,
    make_action_file,
    register_asset,
)

HEART = "heart"
HAPPY = "happy"
IDLE = "idle"

#: ``assets`` 表的**期望列序**（含 CR-11 增量）。顺序有意义 —— ``ALTER TABLE`` 只能追加。
EXPECTED_ASSET_COLUMNS: list[str] = [
    "id", "pet_type", "action", "path", "duration", "audio_path",
]


def _columns(database: Database, table: str) -> list[str]:
    """``PRAGMA table_info`` 的**列序**（顺序有意义：迁移只能追加到末尾）。"""
    with database.connect() as conn:
        return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _write_legacy_assets_db(db_path: Path) -> None:
    """复现 **CR-11 之前** 的 ``assets`` 表（5 列，无 ``audio_path``）并留一行数据。"""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE assets ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "pet_type TEXT NOT NULL, action TEXT NOT NULL, path TEXT NOT NULL, "
            "duration INTEGER NOT NULL DEFAULT 0, UNIQUE (pet_type, action))"
        )
        conn.execute(
            "INSERT INTO assets (pet_type, action, path, duration) VALUES (?, ?, ?, ?)",
            ("cat", HEART, asset_rel_path("cat", HEART), 4459),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ① DDL 增量 + 列序一致
# ---------------------------------------------------------------------------


def test_fresh_and_migrated_databases_have_identical_asset_columns(
    tmp_path: Path,
) -> None:
    """**不变量**：``schema.sql`` 新建库 与 既有库 ``ALTER TABLE`` 迁移后，列序**逐列相同**。

    若两者不一致（例如把 ``audio_path`` 声明在 ``duration`` 之前），
    「业务 schema 逐列 == ``schema.sql``」这条审计不变量就会**随建库路径漂移**。
    """
    fresh = Database(tmp_path / "fresh.db", constants.SCHEMA_PATH)
    fresh.initialize()
    legacy_path = tmp_path / "legacy.db"
    _write_legacy_assets_db(legacy_path)
    migrated = Database(legacy_path, constants.SCHEMA_PATH)
    migrated.initialize()

    assert _columns(fresh, "assets") == EXPECTED_ASSET_COLUMNS
    assert _columns(migrated, "assets") == EXPECTED_ASSET_COLUMNS
    fresh.dispose()
    migrated.dispose()


# ---------------------------------------------------------------------------
# ② 幂等迁移（既有库）
# ---------------------------------------------------------------------------


def test_initialize_migrates_existing_db_and_preserves_rows(tmp_path: Path) -> None:
    """既有库补列：既有行**零丢失**、``audio_path`` 为 ``NULL``、唯一定位仍生效。"""
    db_path = tmp_path / "legacy.db"
    _write_legacy_assets_db(db_path)
    database = Database(db_path, constants.SCHEMA_PATH)
    database.initialize()

    with database.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM assets")]
        indexes = [dict(r) for r in conn.execute("PRAGMA index_list(assets)")]

    assert len(rows) == 1
    assert rows[0]["action"] == HEART
    assert rows[0]["duration"] == 4459
    assert rows[0]["audio_path"] is None
    # UNIQUE(pet_type, action) 仍在（自动索引，origin="u"）
    assert any(i["unique"] and i["origin"] == "u" for i in indexes)
    database.dispose()


def test_initialize_is_idempotent_for_added_columns(tmp_path: Path) -> None:
    """迁移**幂等**：连续 ``initialize()`` 三次不报错、不重复加列。"""
    db_path = tmp_path / "legacy.db"
    _write_legacy_assets_db(db_path)
    database = Database(db_path, constants.SCHEMA_PATH)

    for _ in range(3):
        database.initialize()

    columns = _columns(database, "assets")
    assert columns == EXPECTED_ASSET_COLUMNS
    assert columns.count("audio_path") == 1
    database.dispose()


# ---------------------------------------------------------------------------
# ③ 仓储往返 + upsert 全量覆盖
# ---------------------------------------------------------------------------


def test_audio_path_round_trip(env: SimpleNamespace) -> None:
    """``register(audio_path=...)`` ⇒ ``find`` 读回同一相对路径；``resolve_audio_asset`` 一致。"""
    make_action_file(env.project_root, "cat", HEART)
    register_asset(env.manager, "cat", HEART, audio_path=audio_rel_path("cat", HEART))

    record = env.repository.find("cat", HEART)
    assert record is not None
    assert record.audio_path == audio_rel_path("cat", HEART)
    assert env.manager.resolve_audio_asset("cat", HEART) == audio_rel_path("cat", HEART)


def test_upsert_overwrites_audio_path_with_null_when_absent(
    env: SimpleNamespace,
) -> None:
    """**全量覆盖**：第二次登记未提供 ``audio_path`` ⇒ 写 ``NULL``（**不** COALESCE 保留旧值）。"""
    make_action_file(env.project_root, "cat", HEART)
    register_asset(env.manager, "cat", HEART, audio_path=audio_rel_path("cat", HEART))
    assert env.manager.resolve_audio_asset("cat", HEART) is not None

    # 再次登记（未提供音频）—— 模拟「音频文件被移走后的重跑 seed」
    register_asset(env.manager, "cat", HEART)

    record = env.repository.find("cat", HEART)
    assert record is not None
    assert record.audio_path is None
    assert env.manager.resolve_audio_asset("cat", HEART) is None


def test_upsert_can_set_audio_path_after_null(env: SimpleNamespace) -> None:
    """反向：先无音效、后补音效 ⇒ 覆盖为音频路径（两个方向都必须是覆盖语义）。"""
    make_action_file(env.project_root, "cat", HAPPY)
    register_asset(env.manager, "cat", HAPPY)
    assert env.manager.resolve_audio_asset("cat", HAPPY) is None

    register_asset(env.manager, "cat", HAPPY, audio_path=audio_rel_path("cat", HAPPY))
    assert env.manager.resolve_audio_asset("cat", HAPPY) == audio_rel_path("cat", HAPPY)


# ---------------------------------------------------------------------------
# ④ 模型契约
# ---------------------------------------------------------------------------


def test_asset_record_audio_path_defaults_to_none() -> None:
    """``AssetRecord`` 新字段**必须有默认值** ⇒ 既有构造点（至多 5 个位置参数）不受影响。"""
    legacy = AssetRecord("cat", HEART, asset_rel_path("cat", HEART), 1000)
    assert legacy.audio_path is None
    positional = AssetRecord("cat", HEART, asset_rel_path("cat", HEART), 1000, 7)
    assert (positional.id, positional.audio_path) == (7, None)


def test_asset_metadata_to_dict_stays_three_fields(env: SimpleNamespace) -> None:
    """**冻结契约**：``to_dict()`` 仍恰 3 字段，**不含** ``audio_path``。"""
    make_action_file(env.project_root, "cat", HEART)
    register_asset(env.manager, "cat", HEART, audio_path=audio_rel_path("cat", HEART))

    metadata = env.manager.get_asset("cat", HEART)
    assert isinstance(metadata, AssetMetadata)
    assert set(metadata.to_dict()) == {"asset_id", "asset_path", "duration"}
    assert "audio_path" not in metadata.to_dict()
    # to_detail_dict 是**非契约**调试投影，含音频
    assert metadata.to_detail_dict()["audio_path"] == audio_rel_path("cat", HEART)


# ---------------------------------------------------------------------------
# ⑤ 解析入口（宽容语义）
# ---------------------------------------------------------------------------


def test_resolve_audio_asset_is_lenient(env: SimpleNamespace) -> None:
    """未登记 / 无音效 / 待机 的边界语义与 ``resolve_playback_asset`` 保持一致。"""
    make_action_file(env.project_root, "cat", IDLE)
    register_asset(env.manager, "cat", IDLE)  # 无音效

    assert env.manager.resolve_audio_asset("cat", IDLE) is None  # 已登记但无音效
    assert env.manager.resolve_audio_asset("cat", HEART) is None  # 未登记
    assert env.manager.resolve_audio_asset("cat", None) is None  # 待机回落 idle


def test_register_rejects_blank_audio_path(env: SimpleNamespace) -> None:
    """``audio_path`` 必须是非空字符串或 ``None`` —— 空白属参数错误（与 ``path`` 同口径）。"""
    make_action_file(env.project_root, "cat", HEART)
    with pytest.raises(InvalidRequestError):
        register_asset(env.manager, "cat", HEART, audio_path="   ")


# ---------------------------------------------------------------------------
# ⑥ seed 显式映射（禁止存在性推断）
# ---------------------------------------------------------------------------


def test_audio_actions_table_is_explicit_and_scoped() -> None:
    """映射表**只**含 cat 的 heart / happy（第一阶段范围冻结：``idle`` 静音）。"""
    assert set(init_assets.AUDIO_ACTIONS) == {"cat"}
    assert set(init_assets.AUDIO_ACTIONS["cat"]) == {HEART, HAPPY}
    assert set(init_assets.AUDIO_ACTIONS["cat"].values()) == {
        f"{HEART}.ogg",
        f"{HAPPY}.ogg",
    }
    assert IDLE not in init_assets.AUDIO_ACTIONS["cat"]


def _touch(path: Path) -> None:
    """创建占位文件（内容无关：选择逻辑只看文件名与存在性）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00audio")


def test_resolve_action_audio_requires_explicit_mapping_and_existing_file(
    tmp_path: Path,
) -> None:
    """命中映射 **且** 文件存在 ⇒ 返回文件名；任一不满足 ⇒ ``None``。"""
    root = tmp_path / "assets" / "pets"

    # 映射命中但文件缺失 ⇒ None（不抛错、不寻找替代）
    assert init_assets.resolve_action_audio("cat", HEART, root) is None

    _touch(root / "cat" / "actions" / HEART / f"{HEART}.ogg")
    assert init_assets.resolve_action_audio("cat", HEART, root) == f"{HEART}.ogg"

    # 未映射的组合：即便磁盘上有 ogg，也必须是 None（**禁止存在性推断**）
    _touch(root / "cat" / "actions" / IDLE / f"{IDLE}.ogg")
    assert init_assets.resolve_action_audio("cat", IDLE, root) is None
    _touch(root / "dog" / "actions" / HEART / f"{HEART}.ogg")
    assert init_assets.resolve_action_audio("dog", HEART, root) is None

    # 不提供 root ⇒ 纯枚举、不触碰文件系统
    assert init_assets.resolve_action_audio("cat", HEART, None) is None


class _FakeManager:
    """记录 ``register()`` 调用与 ``audio_path`` 入参（不做任何文件 / ffprobe 校验）。"""

    instances: list["_FakeManager"] = []

    def __init__(self, repository: object, settings: object) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.audio_calls: list[str | None] = []
        _FakeManager.instances.append(self)

    def register(
        self,
        pet_type: str,
        action: str,
        path: str,
        duration: int | None = None,
        audio_path: str | None = None,
    ) -> SimpleNamespace:
        self.calls.append((pet_type, action, path))
        self.audio_calls.append(audio_path)
        return SimpleNamespace(duration=1000)


class _FakeRepository:
    def __init__(self, database: object) -> None:
        self.deleted = False

    def delete_all(self) -> None:
        self.deleted = True


class _FakeDatabase:
    def __init__(self, database_path: object, schema_path: object) -> None:
        self.initialized = False

    def initialize(self) -> None:
        self.initialized = True


def test_seed_registers_audio_only_when_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``seed()`` 透传音频路径（存在时）并在报告中回填；不存在 ⇒ ``None``（写 ``NULL``）。"""
    _FakeManager.instances.clear()
    monkeypatch.setattr(init_assets, "Database", _FakeDatabase)
    monkeypatch.setattr(init_assets, "AssetRepository", _FakeRepository)
    monkeypatch.setattr(init_assets, "AssetManager", _FakeManager)

    root = tmp_path / "assets" / "pets"
    for action in init_assets.ALLOWED_ACTIONS:
        _touch(root / "cat" / "actions" / action / f"{action}.mp4")
    _touch(root / "cat" / "actions" / HEART / f"{HEART}.ogg")  # 只备 heart 音效

    settings = SimpleNamespace(
        project_root=tmp_path,
        assets_root=root,
        database_path=tmp_path / "seed_test.db",
        schema_path=constants.SCHEMA_PATH,
        ensure_directories=lambda: None,
    )

    report = init_assets.seed(pet_types=("cat",), settings=settings)
    manager = _FakeManager.instances[-1]

    registered = {
        action: audio
        for (_pet, action, _path), audio in zip(manager.calls, manager.audio_calls)
    }
    assert registered[HEART] == audio_rel_path("cat", HEART)
    assert registered[IDLE] is None
    assert registered[HAPPY] is None
    assert report.audio == [("cat", HEART, audio_rel_path("cat", HEART))]
    assert report.written == len(init_assets.ALLOWED_ACTIONS)
