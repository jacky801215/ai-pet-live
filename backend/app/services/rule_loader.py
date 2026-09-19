"""RuleLoader（规则加载器）—— 规则文件进入核心业务的唯一入口。

契约来源：

    - ``docs/development/step3_interaction_engine.md``（v1.0 FROZEN）§三 / §六
    - ``docs/development/step3_interaction_engine_decision.md``（v1.0 FROZEN）§三 / §六

职责边界::

    rules.json  ->  RuleLoader  ->  validated rules  ->  InteractionEngine
                        |
                        +-- 加载 / 校验 / 容错（失败不崩溃）

**本模块负责**（且只有本模块负责）：

    - 文件读取
    - JSON 解析
    - schema 检查（字段完备、类型正确、``op`` 在白名单内、``id`` 不重复）
    - 非法规则拒绝
    - 过滤 ``enabled = false``
    - 容错降级

**本模块不负责**：规则匹配、条件求值、动作选择、优先级仲裁（属 Interaction Engine）。

.. important::
   **容错策略（契约 §6.3 冻结）**：规则问题**不得导致启动失败**。

   - 单个规则非法 -> **拒绝该规则**，其余继续加载（记录告警）
   - 文件缺失 / 非法 JSON -> **空规则集** + 告警，进程照常启动

   因此本模块在正常路径上**不抛业务异常** —— 拒绝通过 :attr:`RuleSet.rejected`
   显式记录，而不是靠异常传播。调用方需要按 ``code`` 分流的是「事件非法」，
   规则文件非法属**配置问题**，其正确形态是「降级 + 告警 + 可观测」。

.. note::
   ``SUPPORTED_OPERATORS`` 定义在 :mod:`app.services.interaction_engine`
   （**单一事实来源**），此处导入用于加载期校验 —— 即「上游校验依赖下游能力」。
   若两处各写一份白名单，就会出现「规则加载通过、引擎却不认识该操作符」，
   表现为**规则永不命中且系统不报错**，正是本项目最需要避免的失效形态。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.models.event import ALLOWED_EVENT_TYPES
from app.services.interaction_engine import SUPPORTED_OPERATORS

__all__ = [
    "DEFAULT_RULES_PATH",
    "SUPPORTED_RULE_VERSION",
    "RULE_FIELDS",
    "MATCH_FIELDS",
    "Rule",
    "RuleRejection",
    "RuleSet",
    "RuleLoader",
]

logger = logging.getLogger(__name__)

#: 规则文件默认位置（``backend/app/config/rules.json``）
DEFAULT_RULES_PATH: Path = Path(__file__).resolve().parents[1] / "config" / "rules.json"

#: Phase 1 支持的规则文件版本
SUPPORTED_RULE_VERSION: str = "1.0"

#: 规则对象字段集（**冻结，仅此 6 个**；契约 §3.2 / §3.5）
RULE_FIELDS: tuple[str, ...] = (
    "id",
    "event_type",
    "match",
    "action",
    "priority",
    "enabled",
)

#: ``match`` 子结构字段集（**冻结，仅此 3 个**；契约 §3.3）
MATCH_FIELDS: tuple[str, ...] = ("field", "op", "value")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """一条已校验的规则（契约 §3.2）。

    本对象是 :class:`~app.services.interaction_engine.InteractionEngine` 的输入。
    引擎以**结构化方式**消费它（具备 ``event_type`` / ``match`` / ``action`` /
    ``priority`` / ``enabled`` 即可），因此引擎无需导入本模块。
    """

    id: str
    event_type: str
    match: dict[str, Any]
    action: str
    priority: int
    enabled: bool


@dataclass(frozen=True)
class RuleRejection:
    """一条被拒绝的规则及其原因（**可观测性**用，不参与匹配）。"""

    index: int
    rule_id: str
    reason: str


@dataclass(frozen=True)
class RuleSet:
    """已校验的规则集合 —— ``RuleLoader`` 的产物、``InteractionEngine`` 的输入。

    Attributes:
        version: 规则文件声明的版本。
        rules: **有效规则**（``enabled = true``），保持文件中的**声明顺序**。
        defaults: ``event_type`` -> ``action`` 兜底映射。
        rejected: 被拒绝的规则（含原因）。
        disabled_ids: 被 ``enabled = false`` 过滤掉的规则 id。
        source: 来源标识（文件路径），用于排障。
    """

    version: str
    rules: tuple[Rule, ...]
    defaults: dict[str, str]
    rejected: tuple[RuleRejection, ...] = ()
    disabled_ids: tuple[str, ...] = ()
    source: str = ""

    @property
    def is_empty(self) -> bool:
        """是否为空规则集（无有效规则且无兜底）。

        空规则集是**合法状态** —— 配置文件损坏时的降级结果，进程照常启动。
        """
        return not self.rules and not self.defaults


class _RuleRejected(Exception):
    """内部信号：单条规则校验失败（立即捕获，不外泄）。"""


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------


class RuleLoader:
    """规则加载器（**无状态**，全部为静态方法）。"""

    @staticmethod
    def load(path: str | Path | None = None) -> RuleSet:
        """从文件加载并校验规则。

        失败（文件不存在 / 读取失败 / 非法 JSON）时**返回空规则集**并记录告警 ——
        不抛异常、中断启动（契约 §6.3）。

        Args:
            path: 规则文件路径。省略时使用 :data:`DEFAULT_RULES_PATH`。

        Returns:
            已校验的规则集合（失败时为其空形态）。
        """
        target = Path(path) if path is not None else DEFAULT_RULES_PATH
        source = str(target)

        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("规则文件不可读，降级为空规则集: %s (%s)", source, exc)
            return RuleLoader._empty(source)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("规则文件不是合法 JSON，降级为空规则集: %s (%s)", source, exc)
            return RuleLoader._empty(source)

        return RuleLoader.from_mapping(data, source=source)

    @staticmethod
    def from_mapping(data: Any, *, source: str = "") -> RuleSet:
        """从已解析的映射校验并构造规则集。

        Args:
            data: 规则文件解析结果（期望为 mapping）。
            source: 来源标识，写入 :attr:`RuleSet.source`。

        Returns:
            已校验的规则集合。
        """
        if not isinstance(data, Mapping):
            logger.warning("规则文件顶层必须是 object，降级为空规则集: %s", source or "<mapping>")
            return RuleLoader._empty(source)

        version = RuleLoader._read_version(data)
        rules_raw = data.get("rules")
        if not isinstance(rules_raw, (list, tuple)):
            logger.warning("rules 必须是数组，按空数组处理: %s", source or "<mapping>")
            rules_raw = []

        rules: list[Rule] = []
        rejected: list[RuleRejection] = []
        disabled_ids: list[str] = []
        seen_ids: set[str] = set()

        for index, raw in enumerate(rules_raw):
            try:
                rule = RuleLoader._build_rule(raw, index, seen_ids)
            except _RuleRejected as exc:
                raw_id = raw.get("id") if isinstance(raw, Mapping) else None
                rid = raw_id if isinstance(raw_id, str) else ""
                rejected.append(RuleRejection(index=index, rule_id=rid, reason=str(exc)))
                logger.warning("拒绝第 %d 条规则 (id=%r): %s", index, rid, exc)
                continue

            seen_ids.add(rule.id)
            if rule.enabled:
                rules.append(rule)
            else:
                disabled_ids.append(rule.id)

        defaults = RuleLoader._read_defaults(data.get("defaults"), source)

        return RuleSet(
            version=version,
            rules=tuple(rules),
            defaults=defaults,
            rejected=tuple(rejected),
            disabled_ids=tuple(disabled_ids),
            source=source,
        )

    # -- 内部：文件级字段 ----------------------------------------------------

    @staticmethod
    def _empty(source: str) -> RuleSet:
        """构造空规则集（降级形态）。

        空规则集**不是错误状态** —— 它是配置损坏时的确定性降级结果：
        引擎收到它后对任何事件都返回 ``None``，主流程不受影响。
        """
        return RuleSet(version="", rules=(), defaults={}, source=source)

    @staticmethod
    def _read_version(data: Mapping[str, Any]) -> str:
        """读取并检查 ``version``（不匹配仅告警，不拒绝 —— 容错优先）。"""
        version = data.get("version")
        if not isinstance(version, str) or not version:
            logger.warning("规则文件缺少合法的 version 字段")
            return ""
        if version != SUPPORTED_RULE_VERSION:
            logger.warning(
                "规则文件版本 %r 与当前支持的 %r 不一致（继续加载）",
                version,
                SUPPORTED_RULE_VERSION,
            )
        return version

    @staticmethod
    def _read_defaults(raw: Any, source: str) -> dict[str, str]:
        """校验 ``defaults``：``event_type`` -> 非空 ``action``。

        非法条目**逐条丢弃**（告警），不影响其余条目与启动。
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            logger.warning("defaults 必须是 object，已忽略: %s", source or "<mapping>")
            return {}

        defaults: dict[str, str] = {}
        for event_type, action in raw.items():
            if event_type not in ALLOWED_EVENT_TYPES:
                logger.warning("defaults 键 %r 不在事件白名单内，已忽略", event_type)
                continue
            if not isinstance(action, str) or not action:
                logger.warning("defaults[%r] 必须是非空字符串，已忽略", event_type)
                continue
            defaults[event_type] = action
        return defaults

    # -- 内部：单条规则 ------------------------------------------------------

    @staticmethod
    def _build_rule(raw: Any, index: int, seen_ids: set[str]) -> Rule:
        """校验并构造一条规则。

        Raises:
            _RuleRejected: 任一校验失败（由调用方捕获并记为 rejected）。
        """
        if not isinstance(raw, Mapping):
            raise _RuleRejected(f"规则必须是 object，实际为 {type(raw).__name__}")

        # 字段集冻结：多字段与缺字段都拒绝（防止 "prioritiy" 这类静默拼写错误）
        unknown = sorted(set(raw) - set(RULE_FIELDS))
        if unknown:
            raise _RuleRejected(f"出现未定义字段 {unknown}；只允许 {list(RULE_FIELDS)}")
        missing = [name for name in RULE_FIELDS if name not in raw]
        if missing:
            raise _RuleRejected(f"缺少必填字段 {missing}")

        rule_id = raw["id"]
        if not isinstance(rule_id, str) or not rule_id:
            raise _RuleRejected("id 必须是非空字符串")
        if rule_id in seen_ids:
            raise _RuleRejected(f"id 重复: {rule_id!r}")

        event_type = raw["event_type"]
        if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
            raise _RuleRejected(
                f"event_type {event_type!r} 不在白名单 {list(ALLOWED_EVENT_TYPES)}"
            )

        match = RuleLoader._build_match(raw["match"])

        action = raw["action"]
        if not isinstance(action, str) or not action:
            raise _RuleRejected("action 必须是非空字符串")

        priority = raw["priority"]
        # 注意：bool 是 int 的子类，必须排除 —— 否则 True/False 会被当成 1/0
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise _RuleRejected(f"priority 必须是整数，实际为 {type(priority).__name__}")

        enabled = raw["enabled"]
        if not isinstance(enabled, bool):
            raise _RuleRejected(f"enabled 必须是布尔值，实际为 {type(enabled).__name__}")

        return Rule(
            id=rule_id,
            event_type=event_type,
            match=match,
            action=action,
            priority=priority,
            enabled=enabled,
        )

    @staticmethod
    def _build_match(raw: Any) -> dict[str, Any]:
        """校验 ``match`` 子结构（``{field, op, value}``）。

        Raises:
            _RuleRejected: 非 mapping、字段集不符、``field`` 非字符串、
                ``op`` 不在白名单。
        """
        if not isinstance(raw, Mapping):
            raise _RuleRejected(f"match 必须是 object，实际为 {type(raw).__name__}")

        unknown = sorted(set(raw) - set(MATCH_FIELDS))
        if unknown:
            raise _RuleRejected(f"match 出现未定义字段 {unknown}；只允许 {list(MATCH_FIELDS)}")
        missing = [name for name in MATCH_FIELDS if name not in raw]
        if missing:
            raise _RuleRejected(f"match 缺少必填字段 {missing}")

        field = raw["field"]
        if not isinstance(field, str) or not field:
            raise _RuleRejected("match.field 必须是非空字符串")

        op = raw["op"]
        if not isinstance(op, str) or op not in SUPPORTED_OPERATORS:
            raise _RuleRejected(
                f"match.op {op!r} 不在白名单 {list(SUPPORTED_OPERATORS)}"
                "（禁止 == >= <= 等符号形式）"
            )

        # value 允许任意类型（含 null），但键必须存在 —— 与「缺失」区分
        return {"field": field, "op": op, "value": raw["value"]}
