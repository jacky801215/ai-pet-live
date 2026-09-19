"""Event Model 单元测试。

覆盖 Step 2.1-B 要求：
    创建         comment / gift / like / system 四类事件均可创建
    默认行为     payload 缺失 → {}；user_name 缺失 → ""；system 无用户 → 通过
    失败行为     follow 拒绝；payload null 拒绝；text / count / action 错字段拒绝
    序列化       dict → Event → dict 数据一致，且保留 None / {} / "" 三态区别

另补充契约不变量测试（顶层字段冻结、平台字段上浮拦截、白名单一致性）。
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    EventPayloadInvalidError,
    EventSchemaInvalidError,
    EventTypeInvalidError,
)
from app.models.event import (
    ALLOWED_EVENT_TYPES,
    DEFAULT_USER_NAME,
    SYSTEM_EVENT_TYPE,
    TOP_LEVEL_FIELDS,
    Event,
)

# ---------------------------------------------------------------------------
# 契约常量不变量
# ---------------------------------------------------------------------------


def test_top_level_fields_are_frozen() -> None:
    """顶层字段必须是冻结的 4 个，不得增删改名（契约 §2.1）。"""
    assert TOP_LEVEL_FIELDS == ("event_type", "user_id", "user_name", "payload")
    assert len(TOP_LEVEL_FIELDS) == 4


def test_event_has_exactly_four_business_fields() -> None:
    """Event 对象不得出现第 5 个业务字段。"""
    event = Event(event_type="like")
    assert set(event.to_dict()) == set(TOP_LEVEL_FIELDS)


def test_allowed_event_types_is_minimal_closed_set() -> None:
    """白名单必须是最小闭环集合，且不含 follow（契约 v1.1 §六 C6）。"""
    assert set(ALLOWED_EVENT_TYPES) == {"comment", "gift", "like", "system"}
    assert "follow" not in ALLOWED_EVENT_TYPES


def test_payload_rules_cover_all_allowed_types() -> None:
    """事件级 payload 规则表必须与白名单一一对应，不得出现规则缺口。"""
    from app.models.event import _PAYLOAD_RULES

    assert set(_PAYLOAD_RULES) == set(ALLOWED_EVENT_TYPES)


# ---------------------------------------------------------------------------
# 创建测试（四类事件）
# ---------------------------------------------------------------------------


def test_create_comment_event() -> None:
    """comment 事件创建成功。"""
    event = Event.from_dict(
        {
            "event_type": "comment",
            "user_id": "u2001",
            "user_name": "Amy",
            "payload": {"content": "hello"},
        }
    )

    assert event.event_type == "comment"
    assert event.user_id == "u2001"
    assert event.user_name == "Amy"
    assert event.payload["content"] == "hello"
    assert event.has_user is True
    assert event.is_system_event is False


def test_create_gift_event() -> None:
    """gift 事件创建成功。"""
    event = Event.from_dict(
        {
            "event_type": "gift",
            "user_id": "u1001",
            "user_name": "Jack",
            "payload": {"gift_name": "flower", "gift_count": 1},
        }
    )

    assert event.event_type == "gift"
    assert event.payload["gift_name"] == "flower"
    assert event.payload["gift_count"] == 1


def test_create_like_event() -> None:
    """like 事件创建成功（payload 允许为空 dict）。"""
    event = Event.from_dict(
        {
            "event_type": "like",
            "user_id": "u3001",
            "user_name": "小明",
            "payload": {"like_count": 5},
        }
    )

    assert event.event_type == "like"
    assert event.payload["like_count"] == 5


def test_create_like_event_with_empty_payload() -> None:
    """like 事件 payload 允许为 {}（本 Step 不处理阈值）。"""
    event = Event.from_dict({"event_type": "like", "user_id": "u1", "user_name": "A"})
    assert event.payload == {}


def test_create_system_event() -> None:
    """system 事件创建成功（user_id / user_name 均为 null）。"""
    event = Event.from_dict(
        {
            "event_type": "system",
            "user_id": None,
            "user_name": None,
            "payload": {"command": "startup"},
        }
    )

    assert event.event_type == SYSTEM_EVENT_TYPE
    assert event.user_id is None
    assert event.user_name is None
    assert event.payload["command"] == "startup"
    assert event.is_system_event is True
    assert event.has_user is False


# ---------------------------------------------------------------------------
# 默认行为测试
# ---------------------------------------------------------------------------


def test_missing_payload_defaults_to_empty_dict() -> None:
    """payload 缺失 → 补 {}。"""
    event = Event.from_dict({"event_type": "like"})
    assert event.payload == {}


def test_missing_user_name_defaults_to_empty_string() -> None:
    """user_name 缺失 → 补 ""（字段存在性保证）。"""
    event = Event.from_dict({"event_type": "like", "user_id": "u1"})
    assert event.user_name == DEFAULT_USER_NAME
    assert event.user_name == ""


def test_missing_user_id_defaults_to_none() -> None:
    """user_id 缺失 → 补 None，且**不得**自动转成 anonymous / guest / unknown。"""
    event = Event.from_dict({"event_type": "like"})

    assert event.user_id is None
    assert event.user_id != "anonymous"
    assert event.user_id != "guest"
    assert event.user_id != "unknown"


def test_system_event_with_null_user_passes() -> None:
    """system 无用户：显式 null 必须通过（不得被改写为 "" 或常量）。"""
    event = Event.from_dict(
        {
            "event_type": "system",
            "user_id": None,
            "user_name": None,
            "payload": {"command": "startup"},
        }
    )

    assert event.user_id is None
    assert event.user_name is None


def test_explicit_null_user_name_is_not_replaced_by_empty_string() -> None:
    """显式 user_name: null 必须保留 None，不得替换为 ""（契约 §2.3）。"""
    event = Event.from_dict(
        {
            "event_type": "system",
            "user_id": None,
            "user_name": None,
            "payload": {"command": "startup"},
        }
    )

    assert event.user_name is None
    assert event.user_name != ""


def test_direct_construction_also_validates() -> None:
    """直接构造 Event(...) 同样走校验，不能绕过不变量。"""
    event = Event(event_type="like", user_id="u1", user_name="A")
    assert event.payload == {}

    with pytest.raises(EventTypeInvalidError):
        Event(event_type="follow")

    with pytest.raises(EventPayloadInvalidError):
        Event(event_type="comment", payload={"text": "hi"})


# ---------------------------------------------------------------------------
# 失败测试（事件类型）
# ---------------------------------------------------------------------------


def test_follow_event_type_is_rejected() -> None:
    """follow 不在 Phase 1 白名单 → EVENT_TYPE_INVALID。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        Event.from_dict(
            {
                "event_type": "follow",
                "user_id": "u4001",
                "user_name": "路人甲",
                "payload": {"platform": "simulator"},
            }
        )

    assert exc.value.code == "EVENT_TYPE_INVALID"


@pytest.mark.parametrize("bad_type", ["share", "unknown", "enter", "GIFT", "Comment"])
def test_unknown_event_type_is_rejected(bad_type: str) -> None:
    """任何非白名单取值（含大小写不一致）都必须拒绝。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        Event.from_dict({"event_type": bad_type})

    assert exc.value.code == "EVENT_TYPE_INVALID"


def test_missing_event_type_is_rejected() -> None:
    """event_type 缺失 → EVENT_TYPE_INVALID。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        Event.from_dict({"user_id": "u1"})

    assert exc.value.code == "EVENT_TYPE_INVALID"


@pytest.mark.parametrize("bad_type", ["", None, 123, [], {}])
def test_invalid_event_type_shape_is_rejected(bad_type: object) -> None:
    """空串 / 非字符串类型 → EVENT_TYPE_INVALID。"""
    with pytest.raises(EventTypeInvalidError) as exc:
        Event.from_dict({"event_type": bad_type})

    assert exc.value.code == "EVENT_TYPE_INVALID"


# ---------------------------------------------------------------------------
# 失败测试（payload）
# ---------------------------------------------------------------------------


def test_explicit_null_payload_is_rejected() -> None:
    """payload 显式 null → EVENT_PAYLOAD_INVALID（不得静默修正为 {}）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict({"event_type": "like", "payload": None})

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


@pytest.mark.parametrize("bad_payload", ["str", 123, [], ["a"]])
def test_non_dict_payload_is_rejected(bad_payload: object) -> None:
    """payload 非 object → EVENT_PAYLOAD_INVALID。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict({"event_type": "like", "payload": bad_payload})

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_comment_using_text_is_rejected() -> None:
    """comment 使用 text → 失败（必须用 content）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict(
            {
                "event_type": "comment",
                "user_id": "u1",
                "user_name": "A",
                "payload": {"text": "hello"},
            }
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"
    assert "text" in str(exc.value.context)


def test_comment_missing_content_is_rejected() -> None:
    """comment 缺少 content → 失败。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict(
            {"event_type": "comment", "user_id": "u1", "user_name": "A", "payload": {}}
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"


def test_comment_using_message_is_rejected() -> None:
    """comment 使用 message → 失败（同为禁用别名）。"""
    with pytest.raises(EventPayloadInvalidError):
        Event.from_dict(
            {
                "event_type": "comment",
                "user_id": "u1",
                "user_name": "A",
                "payload": {"message": "hi"},
            }
        )


def test_gift_using_count_is_rejected() -> None:
    """gift 使用 count → 失败（必须用 gift_count）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict(
            {
                "event_type": "gift",
                "user_id": "u1",
                "user_name": "A",
                "payload": {"gift_name": "rose", "count": 1},
            }
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"
    assert "count" in str(exc.value.context)


def test_gift_missing_gift_count_is_rejected() -> None:
    """gift 缺少 gift_count → 失败。"""
    with pytest.raises(EventPayloadInvalidError):
        Event.from_dict(
            {
                "event_type": "gift",
                "user_id": "u1",
                "user_name": "A",
                "payload": {"gift_name": "rose"},
            }
        )


def test_system_using_action_is_rejected() -> None:
    """system 使用 action → 失败（必须用 command；action 属宠物动作领域）。"""
    with pytest.raises(EventPayloadInvalidError) as exc:
        Event.from_dict(
            {
                "event_type": "system",
                "user_id": None,
                "user_name": None,
                "payload": {"action": "startup"},
            }
        )

    assert exc.value.code == "EVENT_PAYLOAD_INVALID"
    assert "action" in str(exc.value.context)


def test_system_missing_command_is_rejected() -> None:
    """system 缺少 command → 失败。"""
    with pytest.raises(EventPayloadInvalidError):
        Event.from_dict(
            {
                "event_type": "system",
                "user_id": None,
                "user_name": None,
                "payload": {},
            }
        )


def test_combined_invalid_example_is_rejected() -> None:
    """契约 §5.4 非法样例：event_type 空串 + payload null → 必须拒绝。"""
    with pytest.raises(EventTypeInvalidError):
        Event.from_dict({"event_type": "", "payload": None})


# ---------------------------------------------------------------------------
# 失败测试（顶层结构 —— 平台字段上浮兜底）
# ---------------------------------------------------------------------------


def test_extra_top_level_field_is_rejected() -> None:
    """顶层出现第 5 个字段 → EVENT_SCHEMA_INVALID。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        Event.from_dict(
            {
                "event_type": "like",
                "user_id": "u1",
                "user_name": "A",
                "payload": {},
                "douyin_user_level": 5,
            }
        )

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "extra_field", ["timestamp", "id", "source", "platform", "device", "room_id"]
)
def test_forbidden_extra_top_level_fields_are_rejected(extra_field: str) -> None:
    """契约 §2.1 明确禁止的顶层字段一律拒绝。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        Event.from_dict({"event_type": "like", extra_field: "x"})

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


def test_non_mapping_input_is_rejected() -> None:
    """入参不是 mapping → EVENT_SCHEMA_INVALID。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        Event.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


@pytest.mark.parametrize("bad_user_id", [123, 1.5, [], {}, True])
def test_invalid_user_id_type_is_rejected(bad_user_id: object) -> None:
    """user_id 类型非 str / None → EVENT_SCHEMA_INVALID。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        Event.from_dict({"event_type": "like", "user_id": bad_user_id})

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


@pytest.mark.parametrize("bad_user_name", [123, 1.5, [], {}])
def test_invalid_user_name_type_is_rejected(bad_user_name: object) -> None:
    """user_name 类型非 str / None → EVENT_SCHEMA_INVALID。"""
    with pytest.raises(EventSchemaInvalidError) as exc:
        Event.from_dict({"event_type": "like", "user_name": bad_user_name})

    assert exc.value.code == "EVENT_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# 序列化测试
# ---------------------------------------------------------------------------


def test_round_trip_preserves_data() -> None:
    """dict → Event → dict 数据完全一致。"""
    original = {
        "event_type": "comment",
        "user_id": "u2001",
        "user_name": "Amy",
        "payload": {"content": "hello", "platform": "simulator"},
    }

    assert Event.from_dict(original).to_dict() == original


def test_round_trip_preserves_none_empty_dict_and_empty_string() -> None:
    """必须保留 None / {} / "" 三种状态的**区别**（不得归一化）。"""
    system_event = Event.from_dict(
        {
            "event_type": "system",
            "user_id": None,
            "user_name": None,
            "payload": {"command": "startup"},
        }
    ).to_dict()

    anonymous_like = Event.from_dict(
        {
            "event_type": "like",
            "user_id": None,
            "user_name": "",
            "payload": {},
        }
    ).to_dict()

    # None 与 "" 是不同状态，不得互相替换
    assert system_event["user_name"] is None
    assert anonymous_like["user_name"] == ""
    assert system_event["user_name"] != anonymous_like["user_name"]
    assert system_event["user_id"] is None and anonymous_like["user_id"] is None

    # {} 必须保留为空 dict，不得变成 None
    assert anonymous_like["payload"] == {}
    assert anonymous_like["payload"] is not None
    assert isinstance(anonymous_like["payload"], dict)


def test_second_round_trip_is_stable() -> None:
    """二次往返结果必须与一次往返完全一致（序列化幂等）。"""
    source = {"event_type": "gift", "payload": {"gift_name": "rose", "gift_count": 3}}

    once = Event.from_dict(source).to_dict()
    twice = Event.from_dict(once).to_dict()

    assert once == twice


def test_to_dict_returns_payload_copy() -> None:
    """to_dict 输出的 payload 是浅拷贝，修改它不应影响原对象。"""
    event = Event.from_dict(
        {"event_type": "comment", "payload": {"content": "hi"}}
    )
    exported = event.to_dict()
    exported["payload"]["content"] = "mutated"

    assert event.payload["content"] == "hi"


def test_to_dict_always_emits_all_four_fields() -> None:
    """即使原始输入省略字段，序列化也必须输出完整 4 字段。"""
    exported = Event.from_dict({"event_type": "like"}).to_dict()

    assert set(exported) == set(TOP_LEVEL_FIELDS)
    assert exported == {
        "event_type": "like",
        "user_id": None,
        "user_name": "",
        "payload": {},
    }


def test_payload_platform_field_is_allowed() -> None:
    """payload 中的 platform 属契约约定字段，必须放行（且不视为顶层字段）。"""
    event = Event.from_dict(
        {
            "event_type": "gift",
            "payload": {"gift_name": "rose", "gift_count": 1, "platform": "x"},
        }
    )

    assert event.payload["platform"] == "x"
