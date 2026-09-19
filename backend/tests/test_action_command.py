"""ActionCommand 单元测试。

覆盖 Step 3.1 §九 要求：
    1. 正常创建
    2. 空 action_type 拒绝
    3. 非 dict payload 拒绝

另补充：字段集冻结守卫（不得出现 event_id / user_id / priority）、
序列化、不可变性、异常类型与 code。
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.core.exceptions import InvalidRequestError, PetLiveError
from app.models.action_command import ACTION_COMMAND_FIELDS, ActionCommand

# ---------------------------------------------------------------------------
# 1. 正常创建
# ---------------------------------------------------------------------------


def test_create_with_payload() -> None:
    """正常创建：action_type + payload。"""
    command = ActionCommand(action_type="heart", payload={"volume": 1})

    assert command.action_type == "heart"
    assert command.payload == {"volume": 1}


def test_create_without_payload_defaults_to_empty_dict() -> None:
    """省略 payload 时为独立空 dict（不得共享同一个可变默认值）。"""
    first = ActionCommand(action_type="heart")
    second = ActionCommand(action_type="heart")

    assert first.payload == {}
    assert first.payload is not second.payload


def test_is_usable_as_dict_key_via_equality() -> None:
    """相等性按字段值比较（值语义）。"""
    assert ActionCommand("heart", {"a": 1}) == ActionCommand("heart", {"a": 1})
    assert ActionCommand("heart") != ActionCommand("dance")


# ---------------------------------------------------------------------------
# 2. 空 action_type 拒绝
# ---------------------------------------------------------------------------


def test_rejects_empty_action_type() -> None:
    """空字符串 action_type -> InvalidRequestError。"""
    with pytest.raises(InvalidRequestError) as exc:
        ActionCommand(action_type="", payload={})

    assert exc.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize("bad", [None, 123, 1.5, [], {}, b"heart"])
def test_rejects_non_str_action_type(bad: object) -> None:
    """非字符串 action_type -> InvalidRequestError。"""
    with pytest.raises(InvalidRequestError) as exc:
        ActionCommand(action_type=bad)  # type: ignore[arg-type]

    assert exc.value.code == "INVALID_REQUEST"


def test_action_type_is_not_silently_normalized() -> None:
    """不得静默 strip / 转小写 —— 动作名漂移必须显式暴露。"""
    command = ActionCommand(action_type=" Heart ")

    assert command.action_type == " Heart "


# ---------------------------------------------------------------------------
# 3. 非 dict payload 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, [], "x", 1, 1.5, (), set()])
def test_rejects_non_dict_payload(bad: object) -> None:
    """非 dict payload -> InvalidRequestError（显式 null 同样拒绝）。"""
    with pytest.raises(InvalidRequestError) as exc:
        ActionCommand(action_type="heart", payload=bad)  # type: ignore[arg-type]

    assert exc.value.code == "INVALID_REQUEST"


def test_payload_error_context_mentions_field() -> None:
    """异常 context 必须指出出错字段（下游排障依赖它）。"""
    with pytest.raises(InvalidRequestError) as exc:
        ActionCommand(action_type="heart", payload=None)  # type: ignore[arg-type]

    assert exc.value.context.get("field") == "payload"
    assert exc.value.to_dict()["code"] == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# 字段集冻结守卫
# ---------------------------------------------------------------------------


def test_field_set_is_frozen_to_two() -> None:
    """顶层字段固定为 action_type / payload（契约 §7.1）。"""
    assert tuple(f.name for f in fields(ActionCommand)) == ("action_type", "payload")
    assert ACTION_COMMAND_FIELDS == ("action_type", "payload")


@pytest.mark.parametrize("forbidden", ["event_id", "user_id", "priority"])
def test_forbidden_fields_are_absent(forbidden: str) -> None:
    """event_id / user_id / priority 不得出现（Step 3.0-A 裁决）。

    这是「ActionCommand 不是 Event 副本」这一不变量的**结构性回归守卫**：
    一旦有人「顺手」加回这些字段，本测试立即失败。
    """
    assert forbidden not in ACTION_COMMAND_FIELDS
    assert forbidden not in {f.name for f in fields(ActionCommand)}
    with pytest.raises(TypeError):
        ActionCommand(action_type="heart", **{forbidden: "x"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 序列化与不可变性
# ---------------------------------------------------------------------------


def test_to_dict_outputs_both_fields() -> None:
    """to_dict 始终输出全部 2 个字段。"""
    assert ActionCommand("heart").to_dict() == {"action_type": "heart", "payload": {}}


def test_to_dict_payload_is_shallow_copy() -> None:
    """to_dict 返回 payload 浅拷贝 —— 修改返回值不得影响原对象。"""
    command = ActionCommand("heart", {"a": 1})

    dumped = command.to_dict()
    dumped["payload"]["a"] = 999

    assert command.payload == {"a": 1}


def test_is_frozen() -> None:
    """字段不可重新绑定。"""
    command = ActionCommand("heart")

    with pytest.raises(Exception):
        command.action_type = "dance"  # type: ignore[misc]


def test_error_is_pet_live_error() -> None:
    """校验失败必须是项目统一异常体系内的异常。"""
    with pytest.raises(PetLiveError):
        ActionCommand(action_type="")
