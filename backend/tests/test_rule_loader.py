"""RuleLoader 单元测试。

覆盖 Step 3.1 §九 要求：
    1. 正常加载
    2. 非法 op 拒绝
    3. 缺字段拒绝
    4. disabled rule 过滤

另补充：字段集冻结守卫、容错不崩溃（文件缺失 / 非法 JSON）、
「单条坏规则不阻断其余规则」、操作符白名单**单一事实来源**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.models.event import ALLOWED_EVENT_TYPES
from app.services import interaction_engine, rule_loader
from app.services.rule_loader import (
    DEFAULT_RULES_PATH,
    MATCH_FIELDS,
    RULE_FIELDS,
    RuleLoader,
    RuleSet,
)

# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------


def make_rule(**overrides: Any) -> dict[str, Any]:
    """构造一条合法规则，按需覆盖字段。"""
    rule: dict[str, Any] = {
        "id": "gift_heart",
        "event_type": "gift",
        "match": {"field": "payload.gift_name", "op": "eq", "value": "小心心"},
        "action": "heart",
        "priority": 50,
        "enabled": True,
    }
    rule.update(overrides)
    return rule


def from_rules(*rules: dict[str, Any], defaults: Any = None) -> RuleSet:
    """把若干规则包成文件级结构后交给 RuleLoader。"""
    data: dict[str, Any] = {"version": "1.0", "rules": list(rules)}
    if defaults is not None:
        data["defaults"] = defaults
    return RuleLoader.from_mapping(data, source="<test>")


# ---------------------------------------------------------------------------
# 1. 正常加载
# ---------------------------------------------------------------------------


def test_load_real_rules_file() -> None:
    """默认路径的 rules.json 必须可加载（同时验证随包配置文件本身合法）。"""
    ruleset = RuleLoader.load()

    assert isinstance(ruleset, RuleSet)
    assert ruleset.version == "1.0"
    assert [rule.id for rule in ruleset.rules] == ["gift_heart", "like_dance"]
    assert ruleset.defaults == {"gift": "heart"}
    assert ruleset.rejected == ()
    assert ruleset.disabled_ids == ()
    assert ruleset.is_empty is False


def test_load_accepts_explicit_path(tmp_path: Path) -> None:
    """允许显式传入路径（测试与多环境部署需要）。"""
    target = tmp_path / "custom_rules.json"
    target.write_text(
        json.dumps({"version": "1.0", "rules": [make_rule()]}, ensure_ascii=False),
        encoding="utf-8",
    )

    ruleset = RuleLoader.load(target)

    assert [rule.id for rule in ruleset.rules] == ["gift_heart"]
    assert ruleset.source == str(target)


def test_rule_carries_all_six_fields() -> None:
    """已校验的规则必须完整携带 6 个字段。"""
    rule = from_rules(make_rule()).rules[0]

    for name in RULE_FIELDS:
        assert hasattr(rule, name)
    assert rule.match == {"field": "payload.gift_name", "op": "eq", "value": "小心心"}


# ---------------------------------------------------------------------------
# 2. 非法 op 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_op", ["==", ">=", "<=", "!=", ">", "<", "regex", "in", ""])
def test_rejects_operator_outside_whitelist(bad_op: str) -> None:
    """符号形式与未知操作符一律拒绝（禁止双语法）。"""
    ruleset = from_rules(make_rule(match={"field": "payload.gift_count", "op": bad_op, "value": 1}))

    assert ruleset.rules == ()
    assert len(ruleset.rejected) == 1
    assert "op" in ruleset.rejected[0].reason


@pytest.mark.parametrize("good_op", ["eq", "contains", "gte", "lte"])
def test_accepts_every_whitelisted_operator(good_op: str) -> None:
    """白名单内 4 个操作符必须全部可用。"""
    ruleset = from_rules(make_rule(match={"field": "payload.x", "op": good_op, "value": 1}))

    assert len(ruleset.rules) == 1


def test_operator_whitelist_has_single_source() -> None:
    """操作符白名单必须只有一份（定义在引擎），Loader 直接引用。

    若两处各写一份，会出现「规则加载通过、引擎不认识该操作符」——规则永不命中
    且系统不报错。本断言保证不存在第二份白名单。
    """
    assert rule_loader.SUPPORTED_OPERATORS is interaction_engine.SUPPORTED_OPERATORS
    assert tuple(interaction_engine.SUPPORTED_OPERATORS) == ("eq", "contains", "gte", "lte")


# ---------------------------------------------------------------------------
# 3. 缺字段拒绝
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", list(RULE_FIELDS))
def test_rejects_rule_missing_required_field(missing_field: str) -> None:
    """规则缺少任一必填字段 -> 拒绝。"""
    rule = make_rule()
    del rule[missing_field]

    ruleset = from_rules(rule)

    assert ruleset.rules == ()
    assert len(ruleset.rejected) == 1
    assert "缺少必填字段" in ruleset.rejected[0].reason


@pytest.mark.parametrize("missing_field", list(MATCH_FIELDS))
def test_rejects_match_missing_required_field(missing_field: str) -> None:
    """match 缺少 field / op / value 任一 -> 拒绝。"""
    match = {"field": "payload.x", "op": "eq", "value": 1}
    del match[missing_field]

    ruleset = from_rules(make_rule(match=match))

    assert ruleset.rules == ()
    assert "match 缺少必填字段" in ruleset.rejected[0].reason


def test_rejects_unknown_rule_field() -> None:
    """出现未定义字段 -> 拒绝（防止 'prioritiy' 这类静默拼写错误）。"""
    rule = make_rule()
    rule["prioritiy"] = 90

    ruleset = from_rules(rule)

    assert ruleset.rules == ()
    assert "未定义字段" in ruleset.rejected[0].reason


def test_rejects_unknown_match_field() -> None:
    """match 出现未定义字段 -> 拒绝（例如把 value 写成 values）。"""
    ruleset = from_rules(
        make_rule(match={"field": "payload.x", "op": "eq", "values": 1})
    )

    assert ruleset.rules == ()
    assert "match" in ruleset.rejected[0].reason


def test_rejects_non_dict_match() -> None:
    """match 非 object -> 拒绝。"""
    ruleset = from_rules(make_rule(match="payload.gift_name"))

    assert ruleset.rules == ()
    assert "match 必须是 object" in ruleset.rejected[0].reason


def test_rule_field_set_is_frozen() -> None:
    """规则字段集固定为 6 个（契约 §3.2）。"""
    assert RULE_FIELDS == ("id", "event_type", "match", "action", "priority", "enabled")
    assert MATCH_FIELDS == ("field", "op", "value")


# ---------------------------------------------------------------------------
# 类型与取值校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_priority", ["50", None, 1.5, [], {}, True, False])
def test_rejects_non_numeric_priority(bad_priority: Any) -> None:
    """priority 非整数 -> 拒绝（bool 是 int 子类，必须排除）。"""
    ruleset = from_rules(make_rule(priority=bad_priority))

    assert ruleset.rules == ()
    assert "priority" in ruleset.rejected[0].reason


@pytest.mark.parametrize("bad_enabled", ["true", 1, None, "yes"])
def test_rejects_non_bool_enabled(bad_enabled: Any) -> None:
    """enabled 非布尔 -> 拒绝。"""
    ruleset = from_rules(make_rule(enabled=bad_enabled))

    assert ruleset.rules == ()
    assert "enabled" in ruleset.rejected[0].reason


@pytest.mark.parametrize("bad_event_type", ["follow", "share", "", None, 123])
def test_rejects_event_type_outside_whitelist(bad_event_type: Any) -> None:
    """event_type 必须在事件白名单内（Phase 1 不含 follow）。"""
    ruleset = from_rules(make_rule(event_type=bad_event_type))

    assert ruleset.rules == ()
    assert "event_type" in ruleset.rejected[0].reason


@pytest.mark.parametrize("bad_action", ["", None, 1, []])
def test_rejects_invalid_action(bad_action: Any) -> None:
    """action 必须是非空字符串。"""
    ruleset = from_rules(make_rule(action=bad_action))

    assert ruleset.rules == ()
    assert "action" in ruleset.rejected[0].reason


@pytest.mark.parametrize("bad_id", ["", None, 1])
def test_rejects_invalid_id(bad_id: Any) -> None:
    """id 必须是非空字符串。"""
    ruleset = from_rules(make_rule(id=bad_id))

    assert ruleset.rules == ()
    assert ruleset.rejected[0].reason


def test_rejects_duplicate_id() -> None:
    """同文件内 id 重复 -> 后者拒绝。"""
    ruleset = from_rules(make_rule(), make_rule(match={"field": "payload.gift_count", "op": "gte", "value": 2}))

    assert len(ruleset.rules) == 1
    assert "id 重复" in ruleset.rejected[0].reason


def test_rejects_non_mapping_rule_entry() -> None:
    """rules 数组元素非 object -> 拒绝该条。"""
    ruleset = RuleLoader.from_mapping({"version": "1.0", "rules": ["not-a-rule"]})

    assert ruleset.rules == ()
    assert "规则必须是 object" in ruleset.rejected[0].reason


# ---------------------------------------------------------------------------
# 4. disabled rule 过滤
# ---------------------------------------------------------------------------


def test_filters_disabled_rule() -> None:
    """enabled = false 的规则不得进入有效规则集，但 id 要可观测。"""
    ruleset = from_rules(
        make_rule(id="on", enabled=True),
        make_rule(id="off", enabled=False),
    )

    assert [rule.id for rule in ruleset.rules] == ["on"]
    assert ruleset.disabled_ids == ("off",)
    assert ruleset.rejected == ()


def test_all_rules_disabled_yields_empty_but_not_error() -> None:
    """全部规则被关闭 -> 合法状态，不视为错误。"""
    ruleset = from_rules(make_rule(enabled=False))

    assert ruleset.rules == ()
    assert ruleset.is_empty is True
    assert ruleset.rejected == ()


# ---------------------------------------------------------------------------
# defaults 校验
# ---------------------------------------------------------------------------


def test_reads_valid_defaults() -> None:
    """合法 defaults 原样保留。"""
    ruleset = from_rules(make_rule(), defaults={"gift": "heart", "like": "dance"})

    assert ruleset.defaults == {"gift": "heart", "like": "dance"}


def test_drops_invalid_defaults_entries() -> None:
    """defaults 中非法条目逐条丢弃，不影响合法条目。"""
    ruleset = from_rules(
        make_rule(),
        defaults={"gift": "heart", "follow": "wave", "like": "", "system": 1},
    )

    assert ruleset.defaults == {"gift": "heart"}


def test_ignores_non_mapping_defaults() -> None:
    """defaults 非 object -> 忽略（不崩溃）。"""
    ruleset = from_rules(make_rule(), defaults=["gift"])

    assert ruleset.defaults == {}


# ---------------------------------------------------------------------------
# 容错：失败不崩溃（契约 §6.3）
# ---------------------------------------------------------------------------


def test_missing_file_returns_empty_ruleset(tmp_path: Path) -> None:
    """文件不存在 -> 空规则集，不抛异常。"""
    ruleset = RuleLoader.load(tmp_path / "nope.json")

    assert ruleset.is_empty is True
    assert ruleset.rules == ()


def test_invalid_json_returns_empty_ruleset(tmp_path: Path) -> None:
    """非法 JSON -> 空规则集，不抛异常。"""
    target = tmp_path / "broken.json"
    target.write_text("{ this is not json", encoding="utf-8")

    ruleset = RuleLoader.load(target)

    assert ruleset.is_empty is True


@pytest.mark.parametrize("payload", [None, [], "x", 1, [] , {}])
def test_load_never_raises_on_garbage(payload: Any) -> None:
    """任意畸形输入都不得抛出异常。"""
    ruleset = RuleLoader.from_mapping(payload)

    assert isinstance(ruleset, RuleSet)


def test_non_mapping_top_level_returns_empty() -> None:
    """顶层非 object -> 空规则集。"""
    ruleset = RuleLoader.from_mapping(["rule"])

    assert ruleset.is_empty is True


def test_one_bad_rule_does_not_block_others() -> None:
    """单条坏规则被拒绝，其余规则继续加载。"""
    ruleset = from_rules(
        make_rule(id="good_1"),
        make_rule(id="bad", match={"field": "payload.x", "op": "==", "value": 1}),
        make_rule(id="good_2", event_type="like"),
    )

    assert [rule.id for rule in ruleset.rules] == ["good_1", "good_2"]
    assert [rejection.rule_id for rejection in ruleset.rejected] == ["bad"]
    assert ruleset.rejected[0].index == 1


def test_rules_without_array_are_tolerated() -> None:
    """缺少 rules 字段 -> 按空数组处理。"""
    ruleset = RuleLoader.from_mapping({"version": "1.0"})

    assert ruleset.rules == ()


@pytest.mark.parametrize("version", [None, 1, "", "2.0"])
def test_version_anomaly_does_not_block_loading(version: Any) -> None:
    """version 缺失 / 类型错误 / 版本不符 -> 告警但继续加载（容错优先）。"""
    ruleset = RuleLoader.from_mapping({"version": version, "rules": [make_rule()]})

    assert len(ruleset.rules) == 1


# ---------------------------------------------------------------------------
# 声明顺序与来源
# ---------------------------------------------------------------------------


def test_declaration_order_is_preserved() -> None:
    """规则顺序必须与文件声明顺序一致（同优先级仲裁依赖它）。"""
    ruleset = from_rules(
        make_rule(id="c", priority=50),
        make_rule(id="a", priority=50),
        make_rule(id="b", priority=50),
    )

    assert [rule.id for rule in ruleset.rules] == ["c", "a", "b"]


def test_source_is_recorded() -> None:
    """来源标识写入 RuleSet.source（排障用）。"""
    assert RuleLoader.load(DEFAULT_RULES_PATH).source == str(DEFAULT_RULES_PATH)


def test_event_type_whitelist_is_shared_with_event_model() -> None:
    """规则层的事件白名单必须与事件契约一致（不得各写一份）。"""
    assert ALLOWED_EVENT_TYPES == ("comment", "gift", "like", "system")
