"""EventGateway 单元测试。

覆盖 Step 2.3 要求：
    1. 正常 comment → 返回 Event
    2. gift 的 gift_count 保留
    3. follow 拒绝 → EVENT_TYPE_INVALID
    4. payload null 拒绝 → EVENT_PAYLOAD_INVALID
    5. 错误透传 —— Gateway 不改变 exception.code

另补充结构性守卫测试（无状态、不重复实现校验、不依赖其他层）。
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    EventPayloadInvalidError,
    PetLiveError,
    EventSchemaInvalidError,
    EventTypeInvalidError,
)
from app.models.event import Event
from app.services.event_gateway import EventGateway

# ---------------------------------------------------------------------------
# 1. 正常 comment
# ---------------------------------------------------------------------------


def test_process_comment_returns_event() -> None:
    """契约 §2.2 示例：comment 输入 → 返回 Event。"""
    raw = {
        "event_type": "comment",
        "user_id": "1",
        "user_name": "jack",
        "payload": {"content": "hello"},
    }

    result = EventGateway().process(raw)

    assert isinstance(result, Event)
    assert result.event_type == "comment"
    assert result.user_id == "1"
    assert result.user_name == "jack"
    assert result.payload == {"content": "hello"}


def test_process_returns_equivalent_event_to_model() -> None:
    """返回值必须与直接调用 Event Model 完全等价。"""
    raw = {
        "event_type": "comment",
        "user_id": "1",
        "user_name": "jack",
        "payload": {"content": "hello"},
    }

    assert EventGateway().process(raw) == Event.from_dict(raw)


# ---------------------------------------------------------------------------
# 2. gift 的 gift_count 保留
# ---------------------------------------------------------------------------


def test_process_gift_preserves_gift_count() -> None:
    """gift 的 gift_count 必须原样保留（不得改名、不得丢失）。"""
    raw = {
        "event_type": "gift",
        "user_id": "2",
        "user_name": "rose",
        "payload": {"gift_name": "rose", "gift_count": 3},
    }

    result = EventGateway().process(raw)

    assert isinstance(result, Event)
    assert result.event_type == "gift"
    assert result.payload["gift_count"] == 3
    assert result.payload["gift_name"] == "rose"


def test_process_gift_keeps_platform_extension_fields() -> None:
    """payload 内的平台扩展字段必须完整透传，不得被网关裁剪。"""
    raw = {
        "event_type": "gift",
        "payload": {"gift_name": "rose", "gift_count": 1, "platform": "simulator"},
    }

    assert EventGateway().process(raw).payload["platform"] == "simulator"


# ---------------------------------------------------------------------------
# 3. follow 拒绝
# ---------------------------------------------------------------------------


def test_process_rejects_follow() -> None:
    """follow 不在 Phase 1 白名单 → EVENT_TYPE_INVALID。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        EventGateway().process({"event_type": "follow"})

    assert exc.value.code == "EVENT_TYPE_INVALID"


@pytest.mark.parametrize("bad_type", ["share", "unknown", "", None, 123])
def test_process_rejects_invalid_event_type(bad_type: object) -> None:
    """任何非白名单取值 → EVENT_TYPE_INVALID。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        EventGateway().process({"event_type": bad_type})

    assert exc.value.code == "EVENT_TYPE_INVALID"


# ---------------------------------------------------------------------------
# 4. payload null 拒绝
# ---------------------------------------------------------------------------


def test_process_rejects_null_payload() -> None:
    """payload 显式 null → EVENT_PAYLOAD_INVALID（不得静默补 {}）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        EventGateway().process({"event_type": "comment", "payload": None})

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_process_rejects_comment_using_text() -> None:
    """comment 使用 text → EVENT_PAYLOAD_INVALID（必须用 content）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        EventGateway().process(
            {"event_type": "comment", "payload": {"text": "hello"}}
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_process_rejects_gift_using_count() -> None:
    """gift 使用 count → EVENT_PAYLOAD_INVALID（必须用 gift_count）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        EventGateway().process(
            {"event_type": "gift", "payload": {"gift_name": "rose", "count": 1}}
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_process_rejects_system_using_action() -> None:
    """system 使用 action → EVENT_PAYLOAD_INVALID（必须用 command）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        EventGateway().process({"event_type": "system", "payload": {"action": "go"}})

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_process_rejects_extra_top_level_field() -> None:
    """顶层出现第 5 个字段 → EVENT_SCHEMA_INVALID（平台字段上浮兜底）。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        EventGateway().process({"event_type": "like", "douyin_user_level": 5})

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


def test_process_rejects_non_mapping() -> None:
    """非 dict 入参 → EVENT_SCHEMA_INVALID。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        EventGateway().process(["not", "a", "dict"])  # type: ignore[arg-type]

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# 5. 错误透传 —— Gateway 不改变 exception.code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_code",
    [
        ({"event_type": "follow"}, "EVENT_TYPE_INVALID"),
        ({"event_type": "comment", "payload": None}, "EVENT_PAYLOAD_INVALID"),
        ({"event_type": "comment", "payload": {"text": "x"}}, "EVENT_PAYLOAD_INVALID"),
        ({"event_type": "gift", "payload": {"gift_name": "r", "count": 1}},
         "EVENT_PAYLOAD_INVALID"),
        ({"event_type": "system", "payload": {"action": "go"}},
         "EVENT_PAYLOAD_INVALID"),
        ({"event_type": "like", "douyin_user_level": 5}, "EVENT_SCHEMA_INVALID"),
        ({"user_id": "1"}, "EVENT_TYPE_INVALID"),
    ],
)
def test_process_propagates_code_unchanged(raw: dict, expected_code: str) -> None:
    """Gateway 必须原样透传 Event Model 的 code，不得改写、包装或更换类型。"""
    with pytest.raises(PetLiveError) as exc:
        EventGateway().process(raw)

    assert exc.value.code == expected_code


def test_process_does_not_wrap_exception_type() -> None:
    """异常类型不得被包装 —— 必须就是 Event Model 抛出的那个类。"""
    with pytest.raises(EventTypeInvalidError) as gateway_exc:
        EventGateway().process({"event_type": "follow"})

    try:
        Event.from_dict({"event_type": "follow"})
    except PetLiveError as model_exc:
        assert type(gateway_exc.value) is type(model_exc)
        assert gateway_exc.value.code == model_exc.code
    else:  # pragma: no cover - 模型层不应放行 follow
        pytest.fail("Event.from_dict 未按预期拒绝 follow")


def test_process_preserves_exception_context() -> None:
    """异常 context 必须保留（下游排障依赖它）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        EventGateway().process({"event_type": "comment", "payload": None})

    assert exc.value.context.get("event_type") == "comment"
    assert exc.value.to_dict()["code"] == "EVENT_PAYLOAD_INVALID"


def test_process_does_not_swallow_exception() -> None:
    """不得吞掉异常 —— 失败必须以异常表达，不得返回 None。"""
    with pytest.raises(PetLiveError):
        EventGateway().process({"event_type": "follow"})


# ---------------------------------------------------------------------------
# 默认行为透传（补齐属 Event Model 职责）
# ---------------------------------------------------------------------------


def test_process_applies_model_defaults() -> None:
    """字段补齐必须由 Event Model 完成，网关只做透传。"""
    result = EventGateway().process({"event_type": "like"})

    assert result.user_id is None
    assert result.user_name == ""
    assert result.payload == {}


def test_process_system_event_with_null_user() -> None:
    """system 事件的显式 null 必须保留为 None，不得被改写为 ""。"""
    result = EventGateway().process(
        {
            "event_type": "system",
            "user_id": None,
            "user_name": None,
            "payload": {"command": "startup"},
        }
    )

    assert result.user_id is None
    assert result.user_name is None


# ---------------------------------------------------------------------------
# 结构性守卫
# ---------------------------------------------------------------------------

#: 与 Event Model 行为对照用的输入矩阵（含合法与非法）
_EQUIVALENCE_MATRIX: list[dict] = [
    {"event_type": "comment", "user_id": "1", "user_name": "jack",
     "payload": {"content": "hello"}},
    {"event_type": "gift", "payload": {"gift_name": "rose", "gift_count": 3}},
    {"event_type": "like"},
    {"event_type": "like", "user_id": None, "user_name": None, "payload": {}},
    {"event_type": "system", "user_id": None, "user_name": None,
     "payload": {"command": "startup"}},
    {"event_type": "follow"},
    {"event_type": "comment", "payload": None},
    {"event_type": "comment", "payload": {"text": "x"}},
    {"event_type": "like", "douyin_user_level": 1},
    {"user_id": "1"},
]


@pytest.mark.parametrize("raw", _EQUIVALENCE_MATRIX)
def test_process_behaviour_is_identical_to_model(raw: dict) -> None:
    """网关行为必须与 Event Model 逐例一致 —— 证明未重复实现校验/补齐逻辑。

    这是「禁止在 Gateway 重复实现字段补齐与校验」的**行为级回归守卫**：
    若有人在网关里另写一套 setdefault / 手动检查，本测试会在差异处失败。
    """
    try:
        expected = Event.from_dict(raw)
    except PetLiveError as model_exc:
        with pytest.raises(PetLiveError) as gateway_exc:
            EventGateway().process(raw)
        assert gateway_exc.value.code == model_exc.code
        return

    assert EventGateway().process(raw) == expected


def test_gateway_is_stateless_across_calls() -> None:
    """无状态：多次调用互不影响，且实例可复用。"""
    gateway = EventGateway()

    first = gateway.process({"event_type": "like", "user_id": "a"})
    second = gateway.process(
        {"event_type": "comment", "user_id": "b", "payload": {"content": "hi"}}
    )
    third = gateway.process({"event_type": "like", "user_id": "a"})

    assert first == third
    assert first.user_id == "a"
    assert second.user_id == "b"
    assert first is not second


def test_gateway_can_be_constructed_without_dependencies() -> None:
    """必须能零外部依赖构造 —— 构造函数不得做任何 IO。"""
    gateway = EventGateway()

    assert isinstance(gateway, EventGateway)
    assert not hasattr(gateway, "__dict__") or gateway.__dict__ == {}


def test_gateway_importable_from_services_package() -> None:
    """按 Step 2.3 §七 要求，可从 app.services 包级导入。"""
    from app.services import EventGateway as PackageLevelGateway

    assert PackageLevelGateway is EventGateway


def test_gateway_module_depends_only_on_event_model() -> None:
    """网关模块不得导入平台 / 规则 / 动作 / 数据层任何模块（禁止项回归守卫）。

    只允许依赖 ``app.models.event`` —— 这条不变量一旦破口，
    分层隔离就在源头失效。
    """
    import inspect

    from app.services import event_gateway

    source = inspect.getsource(event_gateway)
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    app_imports = [imp for imp in imports if imp.startswith(("import app.", "from app."))]
    assert app_imports == ["from app.models.event import Event"]

    forbidden = ("adapter", "simulator", "websocket", "engine", "playback",
                 "repository", "database", "requests", "socket", "threading")
    assert [imp for imp in imports if any(f in imp.lower() for f in forbidden)] == []
