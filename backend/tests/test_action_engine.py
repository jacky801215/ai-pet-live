"""ActionEngine / PlaybackCommand 单元测试（Step 3.2-D）。

契约：``docs/development/step3_action_engine_decision.md``（v1.0 FROZEN）
      ``docs/development/step3_action_command_decision.md``（v1.0 FROZEN）

覆盖：PlaybackCommand 冻结结构 / 成功与失败路径 / FIFO 队列 / 满丢最旧 /
边界输入 / 永不抛异常 / AST 边界守卫（无 IO、无跨层导入、唯一公开入口）。
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.action_engine as action_engine_module
from app.core.exceptions import InvalidRequestError
from app.models.action_command import ActionCommand
from app.models.event import Event
from app.models.playback_command import PLAYBACK_COMMAND_FIELDS, PlaybackCommand
from app.services.action_engine import DEFAULT_QUEUE_LIMIT, ActionEngine

CAT_PET_ID = "cat_001"
CAT_ACTIONS = ("idle", "heart", "happy", "sad", "surprise")


class FakeAssetManager:
    """只实现 ``exists(pet_id, action_type) -> bool`` 的最小替身。

    Step 4.1-A 接口对齐：AssetManager 对外主键为 ``pet_id``，方法名为 ``exists``。
    """

    def __init__(self, actions=None) -> None:
        self.actions = set(actions) if actions is not None else {(CAT_PET_ID, a) for a in CAT_ACTIONS}
        self.calls: list[tuple[str, str]] = []

    def exists(self, pet_id, action_type) -> bool:
        self.calls.append((pet_id, action_type))
        return (pet_id, action_type) in self.actions


class RecordingPort:
    """记录被下发的 PlaybackCommand。"""

    def __init__(self) -> None:
        self.commands: list[PlaybackCommand] = []

    def __call__(self, command) -> None:
        self.commands.append(command)


def make_engine(port=None, asset_manager=None, **kwargs) -> ActionEngine:
    if asset_manager is None:
        asset_manager = FakeAssetManager()
    return ActionEngine(asset_manager, playback_port=port, **kwargs)


# --- 1. PlaybackCommand 冻结结构 -------------------------------------------


def test_playback_command_fields_are_frozen() -> None:
    assert PLAYBACK_COMMAND_FIELDS == ("pet_id", "action_type")
    assert [f.name for f in dataclasses.fields(PlaybackCommand)] == ["pet_id", "action_type"]


def test_playback_command_to_dict() -> None:
    assert PlaybackCommand("cat_001", "heart").to_dict() == {"pet_id": "cat_001", "action_type": "heart"}


def test_playback_command_is_immutable() -> None:
    cmd = PlaybackCommand(pet_id="cat_001", action_type="heart")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmd.pet_id = "dog_001"  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", None])
def test_playback_command_rejects_bad_pet_id(bad: object) -> None:
    with pytest.raises(InvalidRequestError):
        PlaybackCommand(pet_id=bad, action_type="heart")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", None])
def test_playback_command_rejects_bad_action_type(bad: object) -> None:
    with pytest.raises(InvalidRequestError):
        PlaybackCommand(pet_id="cat_001", action_type=bad)  # type: ignore[arg-type]


# --- 2. 成功路径 -----------------------------------------------------------


def test_execute_heart_returns_true() -> None:
    assert make_engine().execute(ActionCommand("heart"), CAT_PET_ID) is True


def test_execute_dispatches_playback_command() -> None:
    """契约 §八：ActionCommand(heart) -> PlaybackCommand(cat_001, heart)。"""
    port = RecordingPort()
    engine = make_engine(port=port)
    assert engine.execute(ActionCommand("heart"), CAT_PET_ID) is True
    assert port.commands == [PlaybackCommand(pet_id="cat_001", action_type="heart")]


def test_execute_without_port_is_ok() -> None:
    assert make_engine(port=None).execute(ActionCommand("heart"), CAT_PET_ID) is True


def test_execute_accepts_duck_typed_command() -> None:
    assert make_engine().execute(SimpleNamespace(action_type="heart"), CAT_PET_ID) is True


# --- 3. 失败路径（动作越域 / 不存在）--------------------------------------


def test_execute_unknown_action_returns_false() -> None:
    assert make_engine().execute(ActionCommand("unknown"), CAT_PET_ID) is False


def test_execute_unknown_action_does_not_dispatch() -> None:
    port = RecordingPort()
    engine = make_engine(port=port)
    assert engine.execute(ActionCommand("unknown"), CAT_PET_ID) is False
    assert port.commands == []
    assert list(engine._pending) == []


def test_execute_action_valid_for_other_pet_is_rejected() -> None:
    """动作域是 per-pet 的：cat 的动作在 dog 上无效。"""
    assert make_engine().execute(ActionCommand("heart"), "dog_001") is False


# --- 4. 边界输入（永不抛异常）---------------------------------------------


@pytest.mark.parametrize("bad_pet", ["", None, 123])
def test_execute_rejects_bad_pet_id(bad_pet: object) -> None:
    assert make_engine().execute(ActionCommand("heart"), bad_pet) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, object(), SimpleNamespace(), SimpleNamespace(action_type="")])
def test_execute_rejects_bad_command(bad: object) -> None:
    assert make_engine().execute(bad, CAT_PET_ID) is False


def test_execute_never_raises_on_invalid_input() -> None:
    engine = make_engine()
    for bad in (None, object(), SimpleNamespace(action_type=""), 42):
        engine.execute(bad, CAT_PET_ID)  # 不抛异常即通过


def test_execute_rejects_event_object() -> None:
    """ActionEngine 不接收 Event（契约 §十一）。"""
    event = Event.from_dict({"event_type": "comment", "payload": {"content": "你好"}})
    assert make_engine().execute(event, CAT_PET_ID) is False


# --- 5. FIFO 队列 / 满丢最旧 ----------------------------------------------


def test_queue_fifo_abc() -> None:
    engine = make_engine()
    for action in ("heart", "happy", "sad"):
        assert engine.execute(ActionCommand(action), CAT_PET_ID) is True
    assert [c.action_type for c in engine._pending] == ["heart", "happy", "sad"]
    assert len(engine._pending) == DEFAULT_QUEUE_LIMIT


def test_queue_overflow_abcd_drops_oldest() -> None:
    engine = make_engine()
    for action in ("heart", "happy", "sad", "surprise"):
        engine.execute(ActionCommand(action), CAT_PET_ID)
    assert [c.action_type for c in engine._pending] == ["happy", "sad", "surprise"]


def test_queue_custom_limit_one() -> None:
    engine = make_engine(queue_limit=1)
    engine.execute(ActionCommand("heart"), CAT_PET_ID)
    engine.execute(ActionCommand("happy"), CAT_PET_ID)
    assert [c.action_type for c in engine._pending] == ["happy"]


def test_only_head_is_dispatched_to_port() -> None:
    """首条播放，其余入队 —— 端口只收到队首。"""
    port = RecordingPort()
    engine = make_engine(port=port)
    for action in ("heart", "happy", "sad"):
        engine.execute(ActionCommand(action), CAT_PET_ID)
    assert [c.action_type for c in port.commands] == ["heart"]
    assert [c.action_type for c in engine._pending] == ["heart", "happy", "sad"]


# --- 6. 依赖降级（异常不得上抛）-------------------------------------------


def test_asset_manager_exception_is_treated_as_missing() -> None:
    class Boom:
        def exists(self, pet_id, action_type) -> bool:
            raise RuntimeError("boom")

    assert ActionEngine(Boom()).execute(ActionCommand("heart"), CAT_PET_ID) is False


def test_playback_port_exception_does_not_propagate() -> None:
    def boom_port(command) -> None:
        raise RuntimeError("play failed")

    assert make_engine(port=boom_port).execute(ActionCommand("heart"), CAT_PET_ID) is True


# --- 7. AST 边界守卫 -------------------------------------------------------


def _module_source() -> str:
    return Path(action_engine_module.__file__).read_text(encoding="utf-8")


def _imported_modules(src: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _call_nodes(src: str) -> list[ast.Call]:
    return [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)]


def test_module_has_no_forbidden_imports() -> None:
    forbidden = (
        "app.services.rule_loader",
        "app.services.interaction_engine",
        "app.services.playback_manager",
        "app.services.data_manager",
        "app.models.event",
    )
    for name in _imported_modules(_module_source()):
        assert name not in forbidden, f"禁止导入 {name}"
        assert not name.endswith(".event") and name != "event", f"禁止导入 {name}"
        assert "rule_loader" not in name and "interaction_engine" not in name


def test_module_has_no_file_or_json_io() -> None:
    for call in _call_nodes(_module_source()):
        func = call.func
        if isinstance(func, ast.Name):
            assert func.id != "open", "禁止 open()"
        elif isinstance(func, ast.Attribute):
            is_json_load = isinstance(func.value, ast.Name) and func.value.id == "json"
            assert not (is_json_load and func.attr == "load"), "禁止 json.load()"


def test_module_source_has_no_forbidden_literals() -> None:
    src = _module_source()
    for token in ("RuleLoader", "rules.json", "open(", "json.load", "assets/"):
        assert token not in src, f"源码不得出现 {token!r}"


def test_public_api_is_execute_plus_restore_idle() -> None:
    """公开 API = 指令入口 ``execute`` + 状态恢复钩子 ``restore_idle``。

    Step 4.1-A：``restore_idle`` 是冻结的状态恢复接口（D3），不是第二执行入口。
    """
    assert [m for m in dir(ActionEngine) if not m.startswith("_")] == ["execute", "restore_idle"]


@pytest.mark.parametrize("alias", ["process", "trigger", "handle"])
def test_no_alias_entrypoints(alias: str) -> None:
    assert not hasattr(ActionEngine, alias)


def test_execute_signature_is_command_and_pet_id() -> None:
    assert list(inspect.signature(ActionEngine.execute).parameters) == ["self", "command", "pet_id"]


def test_engine_constructor_takes_asset_manager() -> None:
    assert list(inspect.signature(ActionEngine.__init__).parameters)[1] == "asset_manager"


# --- 8. restore_idle（状态恢复钩子，Step 4.1-A）----------------------------


def test_restore_idle_signature() -> None:
    assert list(inspect.signature(ActionEngine.restore_idle).parameters) == ["self", "pet_id"]


def test_restore_idle_resets_state_and_pops_finished() -> None:
    engine = make_engine()
    engine.execute(ActionCommand("heart"), CAT_PET_ID)
    assert engine._state == "playing"

    engine.restore_idle(CAT_PET_ID)

    assert engine._state == "idle"
    assert list(engine._pending) == []


def test_restore_idle_does_not_emit_idle_playback_request() -> None:
    """不再下发 idle 指令 —— 否则 play(idle) → on_finished → restore_idle 会无限递归。"""
    port = RecordingPort()
    engine = make_engine(port=port)
    engine.execute(ActionCommand("heart"), CAT_PET_ID)

    engine.restore_idle(CAT_PET_ID)

    assert [c.action_type for c in port.commands] == ["heart"]


def test_restore_idle_dispatches_next_queued_fifo() -> None:
    port = RecordingPort()
    engine = make_engine(port=port)
    engine.execute(ActionCommand("heart"), CAT_PET_ID)
    engine.execute(ActionCommand("happy"), CAT_PET_ID)

    engine.restore_idle(CAT_PET_ID)

    assert [c.action_type for c in port.commands] == ["heart", "happy"]
    assert [c.action_type for c in engine._pending] == ["happy"]
    assert engine._state == "playing"


def test_restore_idle_is_idempotent_and_never_raises() -> None:
    engine = make_engine()
    engine.restore_idle(CAT_PET_ID)
    for bad in ("", None, 123):
        engine.restore_idle(bad)  # type: ignore[arg-type]
    assert engine._state == "idle"
