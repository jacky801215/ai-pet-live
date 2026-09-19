"""PlaybackManager 单元测试（Step 4.1-A）。

契约：``step4_playback_data_decision.md`` D1–D6 / ``step3_playback_decision.md`` P1–P6。
覆盖：入口形状 / 成功与失败路径 / 永不抛异常 / 回调通知 / pet_id 端到端映射 / AST 守卫。
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.playback_manager as playback_manager_module
from app.models.playback_command import PlaybackCommand
from app.services.playback_manager import PlaybackManager
from tests.conftest import make_action_file, register_asset

CAT_PET_ID = "cat_001"
CAT_TYPE = "cat"
CAT_ACTIONS = ("idle", "heart", "happy")


class FakeAssetManager:
    """``pet_id`` 主键的资料替身：内部完成 pet_id → pet_type 后再查动作域。"""

    def __init__(self, mapping=None, actions=None) -> None:
        self.mapping = dict(mapping or {CAT_PET_ID: CAT_TYPE})
        self.actions = set(actions) if actions is not None else {(CAT_TYPE, a) for a in CAT_ACTIONS}
        self.calls: list[tuple[str, str]] = []

    def find_asset(self, pet_id, action):
        self.calls.append((pet_id, action))
        pet_type = self.mapping.get(pet_id)
        if pet_type is None or (pet_type, action) not in self.actions:
            return None
        path = f"assets/pets/{pet_type}/actions/{action}/{action}.mp4"
        return SimpleNamespace(asset_path=path, duration=1000)


class RecordingPort:
    """记录被交给播放端口的路径。"""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def play(self, path: str) -> None:
        self.paths.append(path)


class FinishedRecorder:
    """记录 on_finished 回调收到的 pet_id。"""

    def __init__(self) -> None:
        self.pet_ids: list[str] = []

    def __call__(self, pet_id: str) -> None:
        self.pet_ids.append(pet_id)


def make_manager(asset_manager=None, port=None, finished=None) -> PlaybackManager:
    return PlaybackManager(
        asset_manager or FakeAssetManager(), on_finished=finished, playback_port=port
    )


# --- 1. 成功路径 ---------------------------------------------------------

def test_play_valid_command_returns_true() -> None:
    assert make_manager().play(PlaybackCommand(CAT_PET_ID, "heart")) is True


def test_play_reads_path_from_asset_manager_without_splicing() -> None:
    """P3：路径只由 AssetManager 给出，PlaybackManager 不得自行拼接。"""
    port = RecordingPort()
    fake = FakeAssetManager()
    assert make_manager(fake, port=port).play(PlaybackCommand(CAT_PET_ID, "heart")) is True
    assert port.paths == ["assets/pets/cat/actions/heart/heart.mp4"]
    assert fake.calls == [(CAT_PET_ID, "heart")]


def test_play_without_port_is_ok() -> None:
    assert make_manager(port=None).play(PlaybackCommand(CAT_PET_ID, "happy")) is True


def test_play_accepts_duck_typed_command() -> None:
    assert make_manager().play(SimpleNamespace(pet_id=CAT_PET_ID, action_type="heart")) is True


# --- 2. 失败路径（永不抛异常）-------------------------------------------

def test_play_unknown_action_returns_false() -> None:
    assert make_manager().play(PlaybackCommand(CAT_PET_ID, "unknown")) is False


def test_play_unknown_pet_id_returns_false() -> None:
    assert make_manager().play(PlaybackCommand("ghost_999", "heart")) is False


def test_play_unknown_action_does_not_reach_port() -> None:
    port = RecordingPort()
    assert make_manager(port=port).play(PlaybackCommand(CAT_PET_ID, "unknown")) is False
    assert port.paths == []


@pytest.mark.parametrize("bad_pet", ["", None, 123])
def test_play_rejects_bad_pet_id(bad_pet: object) -> None:
    assert make_manager().play(SimpleNamespace(pet_id=bad_pet, action_type="heart")) is False


@pytest.mark.parametrize("bad", [None, object(), SimpleNamespace(), SimpleNamespace(action_type="")])
def test_play_rejects_bad_command(bad: object) -> None:
    assert make_manager().play(bad) is False


def test_play_never_raises_on_invalid_input() -> None:
    manager = make_manager()
    for bad in (None, object(), SimpleNamespace(pet_id="", action_type="heart"), 42):
        manager.play(bad)  # 不抛异常即通过


def test_asset_manager_exception_is_treated_as_missing() -> None:
    class Boom:
        def find_asset(self, pet_id, action):
            raise RuntimeError("boom")

    assert make_manager(Boom()).play(PlaybackCommand(CAT_PET_ID, "heart")) is False


def test_port_exception_returns_false() -> None:
    class BoomPort:
        def play(self, path):
            raise RuntimeError("decode failed")

    assert make_manager(port=BoomPort()).play(PlaybackCommand(CAT_PET_ID, "heart")) is False


# --- 3. 完成 / 失败回调（D3 + D4）---------------------------------------

def test_notifies_finished_on_success() -> None:
    finished = FinishedRecorder()
    assert make_manager(finished=finished).play(PlaybackCommand(CAT_PET_ID, "heart")) is True
    assert finished.pet_ids == [CAT_PET_ID]


def test_notifies_finished_on_failure() -> None:
    """失败也必须通知 —— 否则 ActionEngine 会永久停在 playing（D4）。"""
    finished = FinishedRecorder()
    assert make_manager(finished=finished).play(PlaybackCommand(CAT_PET_ID, "unknown")) is False
    assert finished.pet_ids == [CAT_PET_ID]


def test_finished_callback_exception_does_not_propagate() -> None:
    def boom(pet_id: str) -> None:
        raise RuntimeError("restore failed")

    assert make_manager(finished=boom).play(PlaybackCommand(CAT_PET_ID, "heart")) is True


def test_invalid_command_does_not_notify() -> None:
    """没有可用 pet_id 时无从通知。"""
    finished = FinishedRecorder()
    assert make_manager(finished=finished).play(SimpleNamespace(action_type="heart")) is False
    assert finished.pet_ids == []


# --- 4. pet_id → pet_type 端到端（真实 AssetManager + config.json）------

def _write_pet_config(env: SimpleNamespace, pet_id: str = CAT_PET_ID) -> None:
    """在临时素材根目录写入宠物配置（映射来源）。"""
    config_dir = env.settings.assets_root / CAT_TYPE
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pet_id": pet_id, "pet_type": CAT_TYPE})
    (config_dir / "config.json").write_text(payload, encoding="utf-8")


def test_real_asset_manager_maps_pet_id_to_pet_type(env: SimpleNamespace) -> None:
    """D2：PlaybackManager 只给 pet_id，映射由 AssetManager 内部完成。"""
    make_action_file(env.project_root, CAT_TYPE, "heart")
    register_asset(env.manager, CAT_TYPE, "heart")
    _write_pet_config(env)

    port = RecordingPort()
    manager = PlaybackManager(env.manager, playback_port=port)

    assert manager.play(PlaybackCommand(pet_id=CAT_PET_ID, action_type="heart")) is True
    assert port.paths == ["assets/pets/cat/actions/heart/heart.mp4"]


def test_real_asset_manager_rejects_unmapped_pet_id(env: SimpleNamespace) -> None:
    make_action_file(env.project_root, CAT_TYPE, "heart")
    register_asset(env.manager, CAT_TYPE, "heart")
    _write_pet_config(env)

    assert PlaybackManager(env.manager).play(PlaybackCommand("ghost_999", "heart")) is False


# --- 5. AST 边界守卫 -----------------------------------------------------

def _module_source() -> str:
    return Path(playback_manager_module.__file__).read_text(encoding="utf-8")


def _imported_modules(src: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _code_string_literals(src: str) -> list[str]:
    """字符串字面量（**排除**文档字符串）。

    文档字符串里写「不读 rules.json」这类**禁止说明**是合法的，
    守卫只约束真正参与执行的代码字面量。
    """
    tree = ast.parse(src)
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def test_module_has_no_forbidden_imports() -> None:
    """P4：不得 import ActionEngine / DataManager / 事件与指令模型 / 规则层。"""
    forbidden = (
        "app.services.action_engine",
        "app.services.data_manager",
        "app.services.rule_loader",
        "app.services.interaction_engine",
        "app.models.event",
        "app.models.action_command",
    )
    for name in _imported_modules(_module_source()):
        assert name not in forbidden, f"禁止导入 {name}"


def test_module_has_no_file_or_json_io() -> None:
    """无 IO：不导入 json / pathlib，不出现 open() 与 json.load()。"""
    assert "json" not in _imported_modules(_module_source())
    calls = [n for n in ast.walk(ast.parse(_module_source())) if isinstance(n, ast.Call)]
    for func in (call.func for call in calls):
        assert not (isinstance(func, ast.Name) and func.id == "open"), "禁止 open()"
        if isinstance(func, ast.Attribute):
            assert not (isinstance(func.value, ast.Name) and func.value.id == "json")


def test_code_has_no_forbidden_literals() -> None:
    """P3 / D2：代码中不得出现规则文件、宠物配置或素材路径拼接字面量。"""
    for literal in _code_string_literals(_module_source()):
        for token in ("rules.json", "RuleLoader", "config.json", "assets/pets"):
            assert token not in literal, f"代码不得出现 {token!r}"


def test_public_api_is_only_play() -> None:
    assert [m for m in dir(PlaybackManager) if not m.startswith("_")] == ["play"]


def test_play_signature_and_constructor() -> None:
    assert list(inspect.signature(PlaybackManager.play).parameters) == ["self", "command"]
    ctor = list(inspect.signature(PlaybackManager.__init__).parameters)
    assert ctor == ["self", "asset_manager", "on_finished", "playback_port"]


def test_manager_does_not_own_business_state() -> None:
    """P6：状态机不属本模块。"""
    manager = make_manager()
    assert not hasattr(manager, "_state")
    assert not hasattr(manager, "restore_idle")
