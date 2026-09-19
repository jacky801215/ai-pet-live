"""AssetManager 单元测试。

覆盖 Step 1 验收标准：
    A1  正常查询 heart → heart.mp4
    A2  不存在动作 → ASSET_NOT_FOUND（且不得自动拼路径）
    A3  新增动作无需修改查询代码
    +   多角色隔离（cat/heart 与 dog/heart 路径不得混淆）
    +   文件缺失、参数非法等异常路径
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.constants import SCHEMA_PATH
from app.core.exceptions import (
    AssetFileMissingError,
    AssetNotFoundError,
    InvalidRequestError,
)
from tests.conftest import register_asset

# ---------------------------------------------------------------------------
# A1 正常查询
# ---------------------------------------------------------------------------


def test_default_query_returns_action_asset(env: SimpleNamespace) -> None:
    """A1: cat/heart 应返回 heart.mp4 的元数据。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "heart")
    register_asset(env.manager, "cat", "heart")

    meta = env.manager.get_asset("cat", "heart")

    assert meta.asset_path.endswith("actions/heart/heart.mp4")
    assert meta.pet_type == "cat"
    assert meta.action == "heart"


def test_asset_id_follows_convention(env: SimpleNamespace) -> None:
    """asset_id 必须为 {pet_type}_action_{action} 格式。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "happy")
    register_asset(env.manager, "cat", "happy")

    meta = env.manager.get_asset("cat", "happy")

    assert meta.asset_id == "cat_action_happy"


def test_to_dict_matches_contract(env: SimpleNamespace) -> None:
    """对外契约只输出 3 个约定字段。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "sad")
    register_asset(env.manager, "cat", "sad", duration=1000)

    payload = env.manager.get_asset("cat", "sad").to_dict()

    assert set(payload) == {"asset_id", "asset_path", "duration"}
    assert payload["asset_id"] == "cat_action_sad"
    assert payload["duration"] == 1000


def test_duration_is_preserved(env: SimpleNamespace) -> None:
    """duration 应原样返回，不被改写。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "surprise")
    register_asset(env.manager, "cat", "surprise", duration=1234)

    assert env.manager.get_asset("cat", "surprise").duration == 1234


def test_all_five_actions_queryable(env: SimpleNamespace) -> None:
    """五个约定动作全部可查询。"""
    from tests.conftest import make_action_file

    actions = ["idle", "heart", "happy", "sad", "surprise"]
    for action in actions:
        make_action_file(env.project_root, "cat", action)
        register_asset(env.manager, "cat", action)

    for action in actions:
        meta = env.manager.get_asset("cat", action)
        assert meta.action == action
        assert meta.asset_path.endswith(f"{action}.mp4")


# ---------------------------------------------------------------------------
# A2 不存在的动作
# ---------------------------------------------------------------------------


def test_unknown_action_raises_asset_not_found(env: SimpleNamespace) -> None:
    """A2: 未登记动作必须抛 AssetNotFoundError。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "heart")
    register_asset(env.manager, "cat", "heart")

    with pytest.raises(AssetNotFoundError) as exc:
        env.manager.get_asset("cat", "unknown")

    assert exc.value.code == "ASSET_NOT_FOUND"


def test_unknown_action_does_not_fallback_to_path_guessing(
    env: SimpleNamespace,
) -> None:
    """A2 强化：即使磁盘上文件存在，未登记也不得返回。

    这是"禁止自动拼路径"的核心验证 —— 素材文件躺在对应位置，
    但元数据未登记时，系统必须显式失败。
    """
    from tests.conftest import make_action_file

    # 磁盘上确实存在该文件
    ghost = make_action_file(env.project_root, "cat", "ghost")
    assert ghost.is_file()

    # 但元数据未登记 → 必须报错，不得凭路径猜测返回
    with pytest.raises(AssetNotFoundError):
        env.manager.get_asset("cat", "ghost")


def test_error_never_returns_empty_string(env: SimpleNamespace) -> None:
    """失败路径不得返回空字符串（Step 1 明确禁止）。"""
    with pytest.raises(AssetNotFoundError):
        env.manager.get_asset("cat", "nope")


def test_find_asset_returns_none_when_missing(env: SimpleNamespace) -> None:
    """宽容版查询：未登记返回 None，而非抛异常。"""
    assert env.manager.find_asset("cat", "missing") is None


def test_exists_false_for_unregistered(env: SimpleNamespace) -> None:
    """exists 对未登记动作返回 False。"""
    assert env.manager.exists("cat", "missing") is False


# ---------------------------------------------------------------------------
# 多角色隔离
# ---------------------------------------------------------------------------


def test_multi_pet_paths_are_isolated(env: SimpleNamespace) -> None:
    """cat/heart 与 dog/heart 路径不得混淆。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "heart")
    make_action_file(env.project_root, "dog", "heart")
    register_asset(env.manager, "cat", "heart")
    register_asset(env.manager, "dog", "heart")

    cat_meta = env.manager.get_asset("cat", "heart")
    dog_meta = env.manager.get_asset("dog", "heart")

    assert "pets/cat/" in cat_meta.asset_path
    assert "pets/dog/" in dog_meta.asset_path
    assert cat_meta.asset_path != dog_meta.asset_path
    assert cat_meta.asset_id == "cat_action_heart"
    assert dog_meta.asset_id == "dog_action_heart"


def test_one_pet_registered_does_not_leak_to_other(
    env: SimpleNamespace,
) -> None:
    """只登记 cat 时，dog 的同名动作必须查不到。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "heart")
    register_asset(env.manager, "cat", "heart")

    with pytest.raises(AssetNotFoundError):
        env.manager.get_asset("dog", "heart")


def test_list_actions_scoped_by_pet(env: SimpleNamespace) -> None:
    """动作列表按角色隔离。"""
    from tests.conftest import make_action_file

    for pet, actions in (("cat", ["idle", "heart"]), ("dog", ["idle"])):
        for action in actions:
            make_action_file(env.project_root, pet, action)
            register_asset(env.manager, pet, action)

    assert env.manager.list_actions("cat") == ["heart", "idle"]
    assert env.manager.list_actions("dog") == ["idle"]


# ---------------------------------------------------------------------------
# 文件缺失
# ---------------------------------------------------------------------------


def test_registered_but_file_missing(env: SimpleNamespace) -> None:
    """已登记但物理文件缺失 → AssetFileMissingError（不崩溃）。"""
    register_asset(env.manager, "cat", "heart")  # 不创建文件

    with pytest.raises(AssetFileMissingError) as exc:
        env.manager.get_asset("cat", "heart")

    assert exc.value.code == "ASSET_FILE_MISSING"


def test_register_allows_pending_file(env: SimpleNamespace) -> None:
    """登记是"声明"行为，允许素材后补；查询才强制校验。

    这条边界固定了 register / get_asset 的职责分工：
        - register：只写元数据（文件缺失仅警告）
        - get_asset：强制校验文件（缺失即报错）
    """
    meta = env.manager.register(
        pet_type="cat",
        action="later",
        path="assets/pets/cat/actions/later/later.mp4",
        duration=1000,
    )
    assert meta.asset_id == "cat_action_later"

    # 但查询必须失败 —— 声明过不等于可用
    with pytest.raises(AssetFileMissingError):
        env.manager.get_asset("cat", "later")


def test_list_assets_skips_missing_files(env: SimpleNamespace) -> None:
    """列表场景下跳过文件缺失项，不中断整体。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "idle")
    register_asset(env.manager, "cat", "idle")
    register_asset(env.manager, "cat", "heart")  # 文件缺失

    assets = env.manager.list_assets("cat")

    assert len(assets) == 1
    assert assets[0].action == "idle"


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pet_type", "action"),
    [
        ("", "heart"),
        ("cat", ""),
        ("   ", "heart"),
        ("cat", "   "),
        ("cat/../dog", "heart"),
        ("cat", "../../etc/passwd"),
        ("cat", "he/art"),
        ("ca\\t", "heart"),
    ],
)
def test_invalid_identifier_rejected(
    env: SimpleNamespace, pet_type: str, action: str
) -> None:
    """非法标识符（空值、路径穿越、分隔符）必须被拒绝。"""
    with pytest.raises(InvalidRequestError):
        env.manager.get_asset(pet_type, action)


def test_invalid_identifier_not_swallowed_by_find(env: SimpleNamespace) -> None:
    """find_asset 的宽容仅针对"查不到"，不针对"参数错"。"""
    with pytest.raises(InvalidRequestError):
        env.manager.find_asset("cat", "")


def test_register_rejects_negative_duration(env: SimpleNamespace) -> None:
    """登记时 duration 必须为非负整数。"""
    with pytest.raises(InvalidRequestError):
        env.manager.register("cat", "heart", "assets/x.mp4", duration=-1)


def test_register_rejects_empty_path(env: SimpleNamespace) -> None:
    """登记时 path 不能为空。"""
    with pytest.raises(InvalidRequestError):
        env.manager.register("cat", "heart", "", duration=1000)


# ---------------------------------------------------------------------------
# A3 新增动作无需改代码
# ---------------------------------------------------------------------------


def test_new_action_requires_no_code_change(env: SimpleNamespace) -> None:
    """A3: 新增 cat/test 只需写入元数据即可访问。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "cat", "test")
    env.manager.register(
        pet_type="cat",
        action="test",
        path="assets/pets/cat/actions/test/test.mp4",
        duration=2000,
    )

    meta = env.manager.get_asset("cat", "test")

    assert meta.asset_id == "cat_action_test"
    assert meta.duration == 2000
    assert meta.asset_path.endswith("actions/test/test.mp4")


def test_new_pet_requires_no_code_change(env: SimpleNamespace) -> None:
    """新增角色 hamster 同理，无需修改任何查询代码。"""
    from tests.conftest import make_action_file

    make_action_file(env.project_root, "hamster", "idle")
    register_asset(env.manager, "hamster", "idle")

    meta = env.manager.get_asset("hamster", "idle")

    assert meta.pet_type == "hamster"
    assert "pets/hamster/" in meta.asset_path


def test_upsert_updates_existing_record(env: SimpleNamespace) -> None:
    """重复登记应更新而非新增（幂等）。"""
    env.manager.register("cat", "heart", "assets/old.mp4", duration=1000)
    env.manager.register("cat", "heart", "assets/new.mp4", duration=3000)

    assert env.repository.count("cat") == 1
    record = env.repository.find("cat", "heart")
    assert record is not None
    assert record.duration == 3000
    assert record.path == "assets/new.mp4"


# ---------------------------------------------------------------------------
# 空库边界
# ---------------------------------------------------------------------------


def test_empty_database_raises_not_found(env: SimpleNamespace) -> None:
    """空库查询必须报 ASSET_NOT_FOUND，不得崩溃。"""
    assert env.repository.count() == 0

    with pytest.raises(AssetNotFoundError):
        env.manager.get_asset("cat", "heart")


def test_list_actions_returns_empty_for_unknown_pet(
    env: SimpleNamespace,
) -> None:
    """未知角色返回空列表，不报错。"""
    assert env.manager.list_actions("unknown_pet") == []


def test_schema_file_exists() -> None:
    """建表脚本必须存在（装配依赖）。"""
    assert SCHEMA_PATH.is_file()
