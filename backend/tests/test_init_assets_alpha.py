"""``init_assets`` 素材选择：alpha 显式映射（**CR-9**）单元测试。

被锁定的行为：

    - ``ALPHA_ACTIONS`` **显式映射**命中且文件存在 ⇒ 该组合选 webm
    - 映射命中但文件缺失 ⇒ 回退 mp4
    - 未映射的组合（``sad`` / ``surprise`` / ``dog`` / ``panda`` / 新角色）⇒ **恒为** mp4
    - **禁止存在性推断**：未映射的组合即使磁盘上躺着 webm，也必须是 mp4
      （防「扫目录 / glob / 后缀猜测」回归 —— 那是本 CR 的明确红线）
    - ``seed()`` 交给 ``AssetManager.register()`` 的路径 = 上述选择结果

隔离：本模块**不触碰真实仓库、不调用 ffprobe** ——
``seed()`` 依赖的 ``Database`` / ``AssetRepository`` / ``AssetManager``
一律替换为替身（替身只记录调用）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config.settings import Settings
from app.core import constants
from scripts import init_assets

ALPHA_ACTIONS = ("idle", "heart", "happy")
OTHER_ACTIONS = ("sad", "surprise")


def _touch(path: Path, content: bytes = b"\x00placeholder") -> None:
    """创建占位文件（内容无关：选择逻辑只看文件名与存在性）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _pets_root(tmp_path: Path) -> Path:
    root = tmp_path / "assets" / "pets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_map(
    root: Path,
    pet_types: tuple[str, ...] = ("cat",),
    actions: tuple[str, ...] = init_assets.ALLOWED_ACTIONS,
) -> dict[tuple[str, str], tuple[str, bool]]:
    """``(pet_type, action) -> (relative_path, is_alpha)``。"""
    return {
        (pet_type, action): (relative, is_alpha)
        for pet_type, action, relative, is_alpha in init_assets.iter_seed_targets(
            pet_types, actions, root
        )
    }


# ---------------------------------------------------------------------------
# 映射表本身
# ---------------------------------------------------------------------------


def test_alpha_actions_table_is_explicit_and_minimal() -> None:
    """映射表**只**含 cat 的 idle/heart/happy（Phase 2-1J 素材范围冻结）。"""
    assert set(init_assets.ALPHA_ACTIONS) == {"cat"}
    assert set(init_assets.ALPHA_ACTIONS["cat"]) == set(ALPHA_ACTIONS)
    assert set(init_assets.ALPHA_ACTIONS["cat"].values()) == {
        f"{action}{constants.ALPHA_ASSET_SUFFIX}" for action in ALPHA_ACTIONS
    }


# ---------------------------------------------------------------------------
# 选择：命中 / 回退 / 未映射
# ---------------------------------------------------------------------------


def test_mapped_actions_select_webm_when_file_exists(tmp_path: Path) -> None:
    """映射命中且文件存在 ⇒ 选 webm，且 ``is_alpha`` 为真。"""
    root = _pets_root(tmp_path)
    for action in ALPHA_ACTIONS:
        _touch(root / "cat" / "actions" / action / f"{action}.webm")

    resolved = _resolve_map(root)

    for action in ALPHA_ACTIONS:
        relative, is_alpha = resolved[("cat", action)]
        assert relative == f"assets/pets/cat/actions/{action}/{action}.webm"
        assert is_alpha is True


def test_mapped_action_falls_back_to_mp4_when_webm_missing(tmp_path: Path) -> None:
    """映射命中但 webm 缺失 ⇒ 回退 mp4（不再抛错、不再寻找替代）。"""
    root = _pets_root(tmp_path)
    (root / "cat" / "actions" / "idle").mkdir(parents=True, exist_ok=True)

    resolved = _resolve_map(root, actions=("idle",))

    assert resolved[("cat", "idle")] == ("assets/pets/cat/actions/idle/idle.mp4", False)


def test_unmapped_actions_stay_mp4_even_if_webm_exists(tmp_path: Path) -> None:
    """**红线**：未映射动作即便磁盘上有 webm，也必须选 mp4（禁止存在性推断）。"""
    root = _pets_root(tmp_path)
    for action in OTHER_ACTIONS:
        _touch(root / "cat" / "actions" / action / f"{action}.webm")

    resolved = _resolve_map(root, actions=OTHER_ACTIONS)

    for action in OTHER_ACTIONS:
        relative, is_alpha = resolved[("cat", action)]
        assert relative == f"assets/pets/cat/actions/{action}/{action}.mp4"
        assert is_alpha is False


def test_unmapped_pet_types_stay_mp4_even_if_webm_exists(tmp_path: Path) -> None:
    """**红线**：dog / panda（及其它新角色）一律 mp4，不做全量迁移。"""
    root = _pets_root(tmp_path)
    for pet_type in ("dog", "panda", "hamster"):
        for action in ALPHA_ACTIONS:
            _touch(root / pet_type / "actions" / action / f"{action}.webm")

    resolved = _resolve_map(root, pet_types=("dog", "panda", "hamster"),
                            actions=ALPHA_ACTIONS)

    for pet_type in ("dog", "panda", "hamster"):
        for action in ALPHA_ACTIONS:
            relative, is_alpha = resolved[(pet_type, action)]
            assert relative.endswith(f"{action}.mp4")
            assert is_alpha is False


def test_without_assets_root_enumeration_is_mp4_only() -> None:
    """不提供 ``assets_root`` ⇒ 纯枚举、不触碰文件系统，一律 mp4。"""
    for pet_type, action, relative, is_alpha in init_assets.iter_seed_targets(
        ("cat",), ALPHA_ACTIONS, None
    ):
        assert relative == f"assets/pets/{pet_type}/actions/{action}/{action}.mp4"
        assert is_alpha is False


def test_resolve_action_asset_signature_defaults_to_mp4(tmp_path: Path) -> None:
    """``resolve_action_asset`` 缺省（无 root）必须是 mp4 兼容行为。"""
    assert init_assets.resolve_action_asset("cat", "idle") == "idle.mp4"
    assert init_assets.resolve_action_asset("cat", "sad", tmp_path) == "sad.mp4"


# ---------------------------------------------------------------------------
# seed() 接线（替身隔离，不调用 ffprobe）
# ---------------------------------------------------------------------------


class _FakeManager:
    """记录 ``register()`` 调用，不做任何文件/ffprobe 校验。"""

    instances: list["_FakeManager"] = []

    def __init__(self, repository: object, settings: object) -> None:
        self.calls: list[tuple[str, str, str]] = []
        _FakeManager.instances.append(self)

    def register(
        self, pet_type: str, action: str, path: str, duration: int | None = None
    ) -> SimpleNamespace:
        self.calls.append((pet_type, action, path))
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


@pytest.fixture()
def fake_seed_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """把 ``seed()`` 的三件依赖替换为替身，返回隔离的 Settings。"""
    _FakeManager.instances.clear()
    monkeypatch.setattr(init_assets, "Database", _FakeDatabase)
    monkeypatch.setattr(init_assets, "AssetRepository", _FakeRepository)
    monkeypatch.setattr(init_assets, "AssetManager", _FakeManager)

    root = _pets_root(tmp_path)
    for action in ALPHA_ACTIONS:
        _touch(root / "cat" / "actions" / action / f"{action}.webm")

    return Settings(
        project_root=tmp_path,
        assets_root=root,
        database_path=tmp_path / "seed_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=False,
    )


def test_seed_registers_alpha_paths_and_reports_them(fake_seed_env: Settings) -> None:
    """``seed()`` 登记的是 webm 路径（不再被 ``.mp4`` 覆盖），并回填到报告。"""
    report = init_assets.seed(pet_types=("cat",), settings=fake_seed_env)

    manager = _FakeManager.instances[-1]
    paths = {f"{pet}/{action}": path for pet, action, path in manager.calls}

    for action in ALPHA_ACTIONS:
        assert paths[f"cat/{action}"] == (
            f"assets/pets/cat/actions/{action}/{action}.webm"
        )
    for action in OTHER_ACTIONS:
        assert paths[f"cat/{action}"] == (
            f"assets/pets/cat/actions/{action}/{action}.mp4"
        )

    assert report.written == len(init_assets.ALLOWED_ACTIONS)
    assert [(pet, action) for pet, action, _ in report.alpha] == [
        ("cat", action) for action in ALPHA_ACTIONS
    ]


def test_seed_falls_back_to_mp4_when_alpha_file_absent(tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """webm 缺失时 ``seed()`` 必须回退 mp4，且报告 alpha 为空。"""
    _FakeManager.instances.clear()
    monkeypatch.setattr(init_assets, "Database", _FakeDatabase)
    monkeypatch.setattr(init_assets, "AssetRepository", _FakeRepository)
    monkeypatch.setattr(init_assets, "AssetManager", _FakeManager)

    root = _pets_root(tmp_path)  # 刻意不创建任何 webm
    settings = Settings(
        project_root=tmp_path,
        assets_root=root,
        database_path=tmp_path / "seed_test.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=False,
    )

    report = init_assets.seed(pet_types=("cat",), settings=settings)

    manager = _FakeManager.instances[-1]
    for _pet, action, path in manager.calls:
        assert path.endswith(f"{action}.mp4")
    assert report.alpha == []
