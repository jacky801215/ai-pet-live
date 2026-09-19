"""InteractionEngine 单元测试。

覆盖 Step 3.1 §九 要求：
    1. gift「小心心」命中 -> ``ActionCommand(action_type="heart")``
    2. like 阈值 ``>= 3`` 命中
    3. like ``< 3`` -> ``None``
    4. comment / system 按契约预留（无规则）-> ``None``
    5. priority 冲突 -> 高 priority 胜出

另补充：声明顺序仲裁、disabled 过滤、操作符语义、**纯函数/无 IO 结构性守卫**、
公开 API 只保留 ``evaluate``。
"""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.action_command import ActionCommand
from app.models.event import Event
from app.services import interaction_engine
from app.services.interaction_engine import SUPPORTED_OPERATORS, InteractionEngine
from app.services.rule_loader import RuleLoader

# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------


def rule(
    rule_id: str,
    event_type: str,
    field: str,
    op: str,
    value: Any,
    action: str,
    priority: int = 50,
    enabled: bool = True,
) -> SimpleNamespace:
    """构造一个**结构化规则对象**（不依赖 RuleLoader 的具体类型）。

    刻意用 :class:`SimpleNamespace` 而非 ``Rule`` —— 以此证明引擎只依赖
    结构化接口（duck typing），**不需要**导入 RuleLoader（契约 §六）。
    """
    return SimpleNamespace(
        id=rule_id,
        event_type=event_type,
        match={"field": field, "op": op, "value": value},
        action=action,
        priority=priority,
        enabled=enabled,
    )


def gift(name: str = "小心心", count: int = 1) -> Event:
    return Event.from_dict(
        {"event_type": "gift", "payload": {"gift_name": name, "gift_count": count}}
    )


def like(count: int | None = 3) -> Event:
    payload: dict[str, Any] = {} if count is None else {"like_count": count}
    return Event.from_dict({"event_type": "like", "payload": payload})


def comment(text: str = "你好") -> Event:
    return Event.from_dict({"event_type": "comment", "payload": {"content": text}})


def system(command: str = "startup") -> Event:
    return Event.from_dict({"event_type": "system", "payload": {"command": command}})


# ---------------------------------------------------------------------------
# 1. 端到端：真实 rules.json -> Engine
# ---------------------------------------------------------------------------


def test_end_to_end_with_real_rules_file() -> None:
    """RuleLoader 产物直接注入引擎即可工作（两个模块的接口契约一致）。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(gift("小心心")).action_type == "heart"
    assert engine.evaluate(like(3)).action_type == "happy"


def test_gift_heart_hit_returns_action_command() -> None:
    """gift + gift_name=小心心 -> ActionCommand(action_type='heart')。"""
    engine = InteractionEngine(RuleLoader.load())

    result = engine.evaluate(
        Event.from_dict(
            {"event_type": "gift", "payload": {"gift_name": "小心心", "gift_count": 1}}
        )
    )

    assert isinstance(result, ActionCommand)
    assert result.action_type == "heart"
    assert result.payload == {}


def test_gift_other_name_falls_back_to_defaults() -> None:
    """其他礼物 -> defaults['gift'] = heart（兜底不走第二条执行路径）。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(gift("火箭")).action_type == "heart"


# ---------------------------------------------------------------------------
# 2/3. like 阈值
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [3, 4, 10, 999])
def test_like_at_or_above_threshold_hits(count: int) -> None:
    """like_count >= 3 -> 命中。"""
    engine = InteractionEngine(RuleLoader.load())

    result = engine.evaluate(like(count))

    assert isinstance(result, ActionCommand)
    assert result.action_type == "happy"


@pytest.mark.parametrize("count", [0, 1, 2])
def test_like_below_threshold_returns_none(count: int) -> None:
    """like_count < 3 -> None（like 未配置 defaults）。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(like(count)) is None


def test_like_without_count_returns_none() -> None:
    """字段缺失 -> 不匹配（不报错）—— like 的 payload 允许为空。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(like(None)) is None


# ---------------------------------------------------------------------------
# 4. comment / system 预留
# ---------------------------------------------------------------------------


def test_comment_without_rule_returns_none() -> None:
    """comment 规则按契约预留 -> 无规则 -> None。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(comment("跳舞")) is None


def test_system_without_rule_returns_none() -> None:
    """system 规则按契约预留 -> 无规则 -> None。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(system()) is None


def test_none_is_returned_without_raising() -> None:
    """None 是正常业务结果 —— 不得以异常表达「无动作」。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(comment("普通评论")) is None
    assert engine.evaluate(system()) is None
    assert engine.evaluate(like(1)) is None


# ---------------------------------------------------------------------------
# 5. priority 冲突仲裁
# ---------------------------------------------------------------------------


def test_higher_priority_wins() -> None:
    """多条规则命中 -> priority 最大者胜出。"""
    engine = InteractionEngine(
        [
            rule("low", "gift", "payload.gift_name", "eq", "小心心", "heart", priority=10),
            rule("high", "gift", "payload.gift_name", "eq", "小心心", "special", priority=90),
            rule("mid", "gift", "payload.gift_name", "eq", "小心心", "dance", priority=50),
        ]
    )

    assert engine.evaluate(gift("小心心")).action_type == "special"


def test_higher_priority_wins_regardless_of_declaration_order() -> None:
    """高优先级声明在后也必须胜出（不得退化为「最后一条胜出」）。"""
    engine = InteractionEngine(
        [
            rule("high", "gift", "payload.gift_name", "eq", "小心心", "special", priority=90),
            rule("low", "gift", "payload.gift_name", "eq", "小心心", "heart", priority=10),
        ]
    )

    assert engine.evaluate(gift("小心心")).action_type == "special"


def test_equal_priority_first_declared_wins() -> None:
    """同优先级 -> 取声明顺序靠前者（确定性优先）。"""
    engine = InteractionEngine(
        [
            rule("first", "gift", "payload.gift_name", "eq", "小心心", "heart", priority=50),
            rule("second", "gift", "payload.gift_name", "eq", "小心心", "dance", priority=50),
        ]
    )

    assert engine.evaluate(gift("小心心")).action_type == "heart"


def test_equal_priority_order_is_not_alphabetical() -> None:
    """顺序仲裁取决于**声明顺序**，不是 id 字典序（反向声明应换结果）。"""
    engine = InteractionEngine(
        [
            rule("z_first", "gift", "payload.gift_name", "eq", "小心心", "dance", priority=50),
            rule("a_second", "gift", "payload.gift_name", "eq", "小心心", "heart", priority=50),
        ]
    )

    assert engine.evaluate(gift("小心心")).action_type == "dance"


# ---------------------------------------------------------------------------
# 过滤与匹配语义
# ---------------------------------------------------------------------------


def test_disabled_rule_is_skipped() -> None:
    """enabled=false 的规则不参与匹配。"""
    engine = InteractionEngine(
        [
            rule("off", "gift", "payload.gift_name", "eq", "小心心", "special",
                 priority=99, enabled=False),
            rule("on", "gift", "payload.gift_name", "eq", "小心心", "heart", priority=10),
        ]
    )

    assert engine.evaluate(gift("小心心")).action_type == "heart"


def test_event_type_must_match_exactly() -> None:
    """event_type 精确匹配 —— 其他类型的规则不参与本事件。"""
    engine = InteractionEngine(
        [rule("c", "comment", "payload.content", "contains", "跳舞", "dance")]
    )

    assert engine.evaluate(gift("小心心")) is None
    assert engine.evaluate(comment("跳舞")).action_type == "dance"


def test_contains_operator_on_string() -> None:
    """contains：子串匹配。"""
    engine = InteractionEngine(
        [rule("c", "comment", "payload.content", "contains", "跳舞", "dance")]
    )

    assert engine.evaluate(comment("给我跳舞吧")).action_type == "dance"
    assert engine.evaluate(comment("你好")) is None


def test_lte_operator() -> None:
    """lte：小于等于。"""
    engine = InteractionEngine(
        [rule("l", "like", "payload.like_count", "lte", 2, "angry")]
    )

    assert engine.evaluate(like(1)).action_type == "angry"
    assert engine.evaluate(like(3)) is None


def test_eq_on_missing_field_does_not_match() -> None:
    """规则字段在事件中不存在 -> 不匹配（不抛异常）。"""
    engine = InteractionEngine(
        [rule("g", "like", "payload.gift_name", "eq", "小心心", "heart")]
    )

    assert engine.evaluate(like(5)) is None


def test_type_mismatch_returns_false_without_raising() -> None:
    """类型不匹配（对 str 用 gte）-> 不匹配，不抛异常。"""
    engine = InteractionEngine(
        [rule("g", "comment", "payload.content", "gte", 3, "dance")]
    )

    assert engine.evaluate(comment("abc")) is None


def test_unknown_operator_returns_false_without_raising() -> None:
    """未知操作符（Loader 本应拒绝）-> 防御性不匹配，不抛异常。"""
    engine = InteractionEngine(
        [rule("x", "gift", "payload.gift_name", "==", "小心心", "heart")]
    )

    assert engine.evaluate(gift("小心心")) is None


def test_defaults_absent_for_event_type_returns_none() -> None:
    """无规则命中且 defaults 无该 event_type -> None。"""
    engine = InteractionEngine([], defaults={"gift": "heart"})

    assert engine.evaluate(gift("火箭")).action_type == "heart"
    assert engine.evaluate(like(9)) is None


def test_empty_engine_always_returns_none() -> None:
    """空规则集（配置降级形态）-> 对任何事件都返回 None。"""
    engine = InteractionEngine(RuleLoader.from_mapping(["broken"]))

    assert engine.evaluate(gift("小心心")) is None
    assert engine.evaluate(like(9)) is None


# ---------------------------------------------------------------------------
# 构造形态
# ---------------------------------------------------------------------------


def test_accepts_ruleset_object() -> None:
    """接受 RuleSet 对象（引擎按结构解包 ``rules`` / ``defaults``）。"""
    engine = InteractionEngine(RuleLoader.load())

    assert engine.evaluate(gift("小心心")).action_type == "heart"


def test_accepts_plain_rule_sequence_with_defaults() -> None:
    """接受规则序列 + 显式 defaults。"""
    engine = InteractionEngine(
        [rule("g", "gift", "payload.gift_name", "eq", "小心心", "heart")],
        defaults={"gift": "wave"},
    )

    assert engine.evaluate(gift("小心心")).action_type == "heart"
    assert engine.evaluate(gift("其他")).action_type == "wave"


def test_is_stateless_across_calls() -> None:
    """无状态：多次调用结果一致，且互不影响。"""
    engine = InteractionEngine(RuleLoader.load())

    first = engine.evaluate(like(3))
    engine.evaluate(gift("小心心"))
    second = engine.evaluate(like(3))

    assert first == second


def test_returns_action_command_instance() -> None:
    """返回值必须是 ActionCommand 实例（不是 dict）。"""
    engine = InteractionEngine(RuleLoader.load())

    assert isinstance(engine.evaluate(like(3)), ActionCommand)


# ---------------------------------------------------------------------------
# 结构性守卫（契约 §六）
# ---------------------------------------------------------------------------


def test_public_api_is_only_evaluate() -> None:
    """公开 API 只保留 evaluate()（契约 §八）。"""
    public = sorted(
        name
        for name, value in vars(InteractionEngine).items()
        if not name.startswith("_") and callable(value)
    )

    assert public == ["evaluate"]


def test_supported_operators_are_frozen() -> None:
    """操作符白名单固定为 4 个（契约 §五）。"""
    assert SUPPORTED_OPERATORS == ("eq", "contains", "gte", "lte")


def test_engine_module_has_no_io_and_does_not_import_rule_loader() -> None:
    """引擎模块不得有文件/JSON/网络/DB/线程依赖，也不得导入 RuleLoader。

    这是契约 §六 禁止项的**静态回归守卫** —— 用 AST 精确检查（避免误判
    文档字符串里出现的 ``open()`` 等字样）。
    """
    tree = ast.parse(inspect.getsource(interaction_engine))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    forbidden_roots = {
        "json", "sqlite3", "socket", "threading", "requests", "urllib", "http",
    }
    assert not {m.split(".")[0] for m in imported} & forbidden_roots
    assert not [m for m in imported if "rule_loader" in m]

    app_imports = sorted(m for m in imported if m.startswith("app."))
    assert app_imports == ["app.models.action_command", "app.models.event"]

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called_names


def test_engine_can_be_constructed_without_dependencies() -> None:
    """零外部依赖即可构造（构造函数不得做任何 IO）。"""
    engine = InteractionEngine([])

    assert isinstance(engine, InteractionEngine)
