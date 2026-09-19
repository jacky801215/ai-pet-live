"""Interaction Engine（互动引擎）—— 「事件该做什么」。

契约来源：

    - ``docs/development/step3_interaction_engine.md``（v1.0 FROZEN）
    - ``docs/development/step3_interaction_engine_decision.md``（v1.0 FROZEN）

职责边界::

    Event  ->  InteractionEngine  ->  ActionCommand | None

**负责**：规则匹配、条件计算、动作选择（含优先级仲裁）。

**不负责**（越界即破坏分层）：

    - 文件读取 / JSON 解析      —— 属 RuleLoader
    - ``Event`` 校验            —— 属 Event Model / Event Gateway
    - 平台事件接入              —— 属 Platform Adapter
    - 播放执行                  —— 属 Playback Manager
    - 数据库存储                —— 属 Data Manager

本模块**只做一件事**：在**已校验的规则集**上对事件求值，产出动作指令。

**无 IO**：不 ``open()``、不 ``json.load()``、不读网络、不写数据库、不起线程。
规则集由构造参数注入 —— 因此本模块是**纯函数式**的，可在零外部依赖下完整单测。

.. note::
   本模块**不得**导入 ``app.services.rule_loader``（契约 §六）。
   规则集以**结构化（duck typing）**方式消费 —— 只要对象具备
   ``event_type`` / ``match`` / ``action`` / ``priority`` / ``enabled`` 属性即可，
   不需要知道 :class:`~app.services.rule_loader.Rule` 这个具体类型。
   ``SUPPORTED_OPERATORS`` 定义在本模块（**单一事实来源**），
   由 RuleLoader 导入用于加载期校验 —— 方向为「上游校验依赖下游能力」，
   从而杜绝「白名单与实现两份、悄悄漂移」。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from app.models.action_command import ActionCommand
from app.models.event import Event

__all__ = ["SUPPORTED_OPERATORS", "RuleLike", "InteractionEngine"]

logger = logging.getLogger(__name__)

#: ``match.op`` 白名单（**单一事实来源**，与契约 §五 一致）
#:
#: 只允许这 4 个。**禁止**符号形式（``==`` / ``>=`` / ``<=``）—— 双语法会让规则
#: 在「看起来对」的情况下永不命中，且系统不报错。
SUPPORTED_OPERATORS: tuple[str, ...] = ("eq", "contains", "gte", "lte")

#: 字段路径解析失败的哨兵（与「值为 None」区分开）
_MISSING: Any = object()


@runtime_checkable
class RuleLike(Protocol):
    """引擎消费的**结构化**规则接口（不绑定任何具体实现类型）。

    该协议由 :class:`~app.services.rule_loader.Rule` 结构化满足。
    引擎只依赖这 5 个属性，因此**不需要**导入 RuleLoader。
    """

    event_type: str
    match: Mapping[str, Any]
    action: str
    priority: int
    enabled: bool


class InteractionEngine:
    """互动引擎：``Event`` → ``ActionCommand | None``。

    **无状态**：除构造时注入的规则集外不持有任何可变状态，
    不缓存、不计数、不留上次输入。因此单例或每请求实例均可，行为完全一致。

    Args:
        rules: **已校验的规则集合**。两种形态均可：

            - 规则集对象（具备 ``rules`` / ``defaults`` 属性，即
              :class:`~app.services.rule_loader.RuleSet`）；
            - 规则对象序列（每个元素满足 :class:`RuleLike`）。

            引擎**不校验**规则 —— 校验是 RuleLoader 的职责。
        defaults: ``event_type`` → ``action`` 的兜底映射。当 ``rules`` 本身携带
            ``defaults`` 时可省略。

    .. note::
        本类**不定义任何 IO**：不读文件、不解析 JSON、不连数据库、不起线程。
        测试必须能在零外部依赖的前提下构造引擎。
    """

    def __init__(
        self,
        rules: Iterable[RuleLike] | Any,
        *,
        defaults: Mapping[str, str] | None = None,
    ) -> None:
        # 规则集 duck typing：兼容「RuleSet 对象」与「规则序列」两种注入方式。
        # 注意：此处的 getattr 只做结构解包，不做任何校验（校验属 RuleLoader）。
        raw_defaults = defaults
        if raw_defaults is None:
            raw_defaults = getattr(rules, "defaults", None)
            if raw_defaults is not None and hasattr(rules, "rules"):
                rules = rules.rules

        #: 规则按**声明顺序**保存 —— 同优先级仲裁依赖它，禁止改成 set / dict。
        self._rules: tuple[Any, ...] = tuple(rules)
        self._defaults: dict[str, str] = dict(raw_defaults or {})

    # -- 公开 API（唯一） ----------------------------------------------------

    def evaluate(self, event: Event) -> ActionCommand | None:
        """对事件求值，产出动作指令。

        顺序（契约 §四 冻结）::

            receive Event
                  -> filter enabled = true
                  -> match event_type（精确相等）
                  -> evaluate match
                  -> select highest priority（同优先级取声明顺序靠前者）
                  -> create ActionCommand

        无命中时查 ``defaults[event_type]``；仍无则返回 ``None``。

        Args:
            event: 已校验的统一事件对象。

        Returns:
            命中时的动作指令；无任何规则命中且无兜底时返回 ``None``。

        .. important::
            ``None`` 是**正常业务结果**，不是异常 —— 例如一条不含「跳舞」的
            普通评论。因此本方法**不抛异常**，调用方也**不得**把 ``None``
            当作错误处理。
        """
        best: Any = None

        for rule in self._rules:
            # 步骤 1：enabled = true —— 关闭的规则不参与匹配
            if not bool(getattr(rule, "enabled", True)):
                continue

            # 步骤 2：event_type 精确匹配（不做前缀 / 包含 / 模糊匹配）
            if getattr(rule, "event_type", None) != event.event_type:
                continue

            # 步骤 3：求值 match
            if not self._eval_match(getattr(rule, "match", None), event):
                continue

            # 步骤 4：取 priority 最大者；**严格大于**才替换 ⇒ 同优先级保留先声明者
            if best is None or self._priority_of(rule) > self._priority_of(best):
                best = rule

        if best is not None:
            return ActionCommand(action_type=str(getattr(best, "action", "")), payload={})

        # 步骤 5：兜底
        fallback = self._defaults.get(event.event_type)
        if fallback is None:
            return None
        return ActionCommand(action_type=str(fallback), payload={})

    # -- 内部：匹配（不对外暴露） --------------------------------------------

    def _eval_match(self, match: Any, event: Event) -> bool:
        """求值一条规则的 ``match`` 表达式。

        任何结构问题都**返回 False**（不抛异常）：非法结构本应由 RuleLoader
        在加载期拒绝；此处是二道防线，保证运行期不因规则问题中断主流程。
        """
        if not isinstance(match, Mapping):
            return False

        field = match.get("field")
        op = match.get("op")
        if not isinstance(field, str) or not field:
            return False
        if not isinstance(op, str):
            return False
        if "value" not in match:
            return False

        actual = self._get_field_value(event, field)
        return self._compare(op, actual, match["value"])

    def _get_field_value(self, event: Event, path: str) -> Any:
        """按点号路径从**事件顶层**取值（契约 §3.3）。

        例：``payload.gift_name``、``payload.content``、``payload.like_count``。

        Returns:
            取到的值；路径不存在时返回内部哨兵 ``_MISSING``
            （与「值为 ``None``」区分 —— ``None`` 是合法取值，可参与 ``eq`` 比较）。
        """
        current: Any = {
            "event_type": event.event_type,
            "user_id": event.user_id,
            "user_name": event.user_name,
            "payload": event.payload,
        }

        for part in path.split("."):
            if not part or not isinstance(current, Mapping):
                return _MISSING
            if part not in current:
                return _MISSING
            current = current[part]

        return current

    def _compare(self, op: str, actual: Any, expected: Any) -> bool:
        """按操作符比较。未知操作符与类型不匹配一律返回 ``False``。

        Args:
            op: 操作符（应为 :data:`SUPPORTED_OPERATORS` 之一）。
            actual: 从事件取到的值（可能是 ``_MISSING``）。
            expected: 规则中配置的比较值。

        Returns:
            是否匹配。
        """
        if actual is _MISSING:
            # 字段缺失 ⇒ 不匹配（契约 §5.3）。不报错：like 事件本就没有
            # gift_name，这是正常情况，不是错误。
            return False

        if op == "eq":
            return bool(actual == expected)

        if op == "contains":
            if isinstance(actual, str):
                return isinstance(expected, str) and expected in actual
            if isinstance(actual, (list, tuple, set, frozenset)):
                try:
                    return expected in actual
                except TypeError:  # pragma: no cover - 不可哈希元素保护
                    return False
            return False

        if op in ("gte", "lte"):
            try:
                return bool(actual >= expected) if op == "gte" else bool(actual <= expected)
            except TypeError:
                logger.warning(
                    "match 类型不匹配，按不命中处理: op=%s actual_type=%s expected_type=%s",
                    op,
                    type(actual).__name__,
                    type(expected).__name__,
                )
                return False

        # 未知操作符：RuleLoader 应在加载期拒绝，此处防御性返回 False
        logger.warning("match 出现未知操作符，按不命中处理: op=%r", op)
        return False

    @staticmethod
    def _priority_of(rule: Any) -> int:
        """读取规则优先级；缺失或非数字时按 ``0`` 参与比较（不抛异常）。"""
        value = getattr(rule, "priority", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0
