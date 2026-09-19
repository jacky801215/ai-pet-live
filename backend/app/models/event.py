"""统一事件模型（Event Model）。

本模块实现 Phase 1 Event Schema **v1.1**：
    ``docs/development/step2_event_schema.md``

顶层字段固定为 4 个，不得增删改名：

    event_type / user_id / user_name / payload

职责边界 —— 本模块**只做**这一条链路：

    输入事件数据 → 校验 → 标准对象 → 序列化

本模块**不做**（越界即破坏分层）：

    - 事件接入（Event Gateway / Platform Adapter / Simulator）
    - 规则匹配（Interaction Engine）
    - 播放控制（Playback Manager）
    - 任何 IO（文件 / 数据库 / 网络）

异常语义分工（三种 code 触发面互不重叠，不得混用）：

    EVENT_TYPE_INVALID     event_type 缺失 / 空 / 非 str / 不在 Phase 1 白名单
    EVENT_PAYLOAD_INVALID  payload 类型错误，或事件级 payload 字段不合规
    EVENT_SCHEMA_INVALID   其余顶层结构问题（多余字段、user_id/user_name 类型错误）

「字段缺失」与「显式 null」必须区分处理（契约 §2.4）：

    payload     缺失 → 补 ``{}``     显式 ``null`` → **拒绝**（null 是非法类型）
    user_id     缺失 → 补 ``None``   显式 ``null`` → 保留 ``None``
    user_name   缺失 → 补 ``""``     显式 ``null`` → 保留 ``None``

注意 ``user_id`` / ``user_name`` 的 ``None`` 与 ``payload`` 的 ``None`` 语义完全不同：
前者表示「无用户」（合法契约形态），后者表示「桶缺失」（非法类型）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.exceptions import (
    EventPayloadInvalidError,
    EventSchemaInvalidError,
    EventTypeInvalidError,
)

# ---------------------------------------------------------------------------
# 契约常量（来源：docs/development/step2_event_schema.md v1.1）
# ---------------------------------------------------------------------------

#: 顶层字段（冻结，**仅此 4 个**）
TOP_LEVEL_FIELDS: tuple[str, ...] = ("event_type", "user_id", "user_name", "payload")

#: Phase 1 事件类型白名单（最小闭环集合，不含 follow）
ALLOWED_EVENT_TYPES: tuple[str, ...] = ("comment", "gift", "like", "system")

#: 系统事件类型
SYSTEM_EVENT_TYPE: str = "system"

#: ``user_name`` 字段缺失时的默认值（字段存在性保证）
DEFAULT_USER_NAME: str = ""

#: 事件级 payload 规则：{event_type: (必填字段, 禁止字段)}
#
#: ``like`` 不设必填与禁止项 —— 契约 §五 规定其 payload 允许为空 ``{}``，
#: 阈值判断属 Interaction Engine 职责，不在模型层。
_PAYLOAD_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "comment": (("content",), ("text", "message")),
    "gift": (("gift_name", "gift_count"), ("count", "number")),
    "like": ((), ()),
    "system": (("command",), ("action",)),
}


# ---------------------------------------------------------------------------
# 校验原语（from_dict 与 __post_init__ 共用，避免两套规则漂移）
# ---------------------------------------------------------------------------


def _check_event_type(value: Any) -> str:
    """校验 ``event_type`` 合法性并返回其值。

    Args:
        value: 待校验的 event_type。

    Returns:
        校验通过时的 event_type 原值。

    Raises:
        EventTypeInvalidError: 缺失 / 空串 / 非字符串 / 不在 Phase 1 白名单。
    """
    if not isinstance(value, str) or not value:
        raise EventTypeInvalidError(
            "event_type 必须是非空字符串",
            event_type=value,
            allowed=list(ALLOWED_EVENT_TYPES),
        )
    if value not in ALLOWED_EVENT_TYPES:
        raise EventTypeInvalidError(
            f"event_type 不在 Phase 1 白名单: {value!r}",
            event_type=value,
            allowed=list(ALLOWED_EVENT_TYPES),
        )
    return value


def _check_identity(name: str, value: Any) -> str | None:
    """校验 ``user_id`` / ``user_name`` 类型。

    Args:
        name: 字段名（用于错误信息）。
        value: 待校验的值。

    Returns:
        校验通过时的原值（``str`` 或 ``None``）。

    Raises:
        EventSchemaInvalidError: 类型既不是 ``str`` 也不是 ``None``。
    """
    if value is not None and not isinstance(value, str):
        raise EventSchemaInvalidError(
            f"{name} 必须是 str 或 None",
            field=name,
            received_type=type(value).__name__,
        )
    return value


def _check_payload(event_type: str, payload: Any) -> dict[str, Any]:
    """校验 ``payload`` 类型与事件级字段规则。

    Args:
        event_type: 已校验通过的事件类型（用作规则表键）。
        payload: 待校验的 payload。

    Returns:
        校验通过时的 payload 原对象。

    Raises:
        EventPayloadInvalidError: 非 ``dict``、含禁止字段，或缺少必填字段。
    """
    if not isinstance(payload, dict):
        # 显式 None 与非 dict 都落在这里：契约规定 payload 只能是 object
        raise EventPayloadInvalidError(
            "payload 必须是 object；显式 null 属非法类型（无扩展字段请传 {}）",
            event_type=event_type,
            received_type=type(payload).__name__,
        )

    required, forbidden = _PAYLOAD_RULES[event_type]

    present = [key for key in forbidden if key in payload]
    if present:
        raise EventPayloadInvalidError(
            f"{event_type} 的 payload 含禁止字段: {present}",
            event_type=event_type,
            forbidden_fields=present,
            hint=f"请改用: {list(required)}",
        )

    missing = [key for key in required if key not in payload]
    if missing:
        raise EventPayloadInvalidError(
            f"{event_type} 的 payload 缺少必填字段: {missing}",
            event_type=event_type,
            missing_fields=missing,
            required_fields=list(required),
        )

    return payload


# ---------------------------------------------------------------------------
# 事件对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """统一事件对象（Phase 1 Event Schema v1.1）。

    只含 4 个业务字段 —— 顶层字段集已冻结，**禁止**新增
    ``timestamp`` / ``id`` / ``source`` / ``platform`` / ``device`` / ``room_id``
    等字段。平台特有字段一律放入 :attr:`payload`。

    构造方式：

    - :meth:`from_dict` —— **推荐**。会按契约补齐缺失字段（``{}`` / ``None`` / ``""``），
      是外部数据进入系统的唯一入口。
    - ``Event(...)`` —— 直接构造。同样校验，但**不补齐**（4 个参数已有默认值，
      省略即视为显式使用默认值）。

    .. note::
       ``frozen=True`` 只阻止字段被重新绑定，不会冻结 ``payload`` 内部的
       可变对象。跨模块传递时如需防止被下游修改，调用方应自行复制
       （:meth:`to_dict` 已返回 payload 的浅拷贝）。
    """

    event_type: str
    user_id: str | None = None
    user_name: str | None = DEFAULT_USER_NAME
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """对象级不变量校验 —— 任何构造路径都绕不过。"""
        _check_event_type(self.event_type)
        _check_identity("user_id", self.user_id)
        _check_identity("user_name", self.user_name)
        _check_payload(self.event_type, self.payload)

    # -- 构造 ---------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
        """从字典构造统一事件（契约的唯一入口）。

        处理顺序与契约 §2.4 一致：

        1. 顶层结构检查 —— 出现 4 个冻结字段之外的字段即拒绝（平台字段上浮兜底）
        2. ``event_type`` 校验 —— 缺失 / 空 / 非白名单即拒绝
        3. 字段补齐 —— ``user_id`` → ``None``，``user_name`` → ``""``，``payload`` → ``{}``
        4. 显式 ``null`` 语义 —— ``payload: null`` 拒绝；``user_id``/``user_name`` 的
           ``null`` 原样保留（不得替换为 ``""`` 或 ``"anonymous"``）

        Args:
            data: 原始事件字典。

        Returns:
            校验通过的统一事件对象。

        Raises:
            EventSchemaInvalidError: 入参不是 mapping，或顶层有多余字段。
            EventTypeInvalidError: ``event_type`` 缺失或非法。
            EventPayloadInvalidError: ``payload`` 显式为 ``null``，或事件级字段不合规。
        """
        if not isinstance(data, Mapping):
            raise EventSchemaInvalidError(
                "事件必须是 mapping（dict）",
                received_type=type(data).__name__,
            )

        extra = sorted(set(data) - set(TOP_LEVEL_FIELDS))
        if extra:
            raise EventSchemaInvalidError(
                f"顶层出现未定义字段: {extra}；契约只允许 {list(TOP_LEVEL_FIELDS)}",
                extra_fields=extra,
                allowed_top_level=list(TOP_LEVEL_FIELDS),
            )

        if "event_type" not in data:
            raise EventTypeInvalidError(
                "缺少必填字段 event_type",
                allowed=list(ALLOWED_EVENT_TYPES),
            )
        event_type = _check_event_type(data["event_type"])

        # 缺失补默认值；显式 null 原样保留（不得自动转成 "anonymous" / "" / "unknown"）
        user_id = data["user_id"] if "user_id" in data else None
        user_name = data["user_name"] if "user_name" in data else DEFAULT_USER_NAME

        # 缺失补 {}；显式 null 必须拒绝，不得静默修正
        if "payload" not in data:
            payload: Any = {}
        else:
            payload = data["payload"]
            if payload is None:
                raise EventPayloadInvalidError(
                    "payload 显式传入 null 属非法类型；无扩展字段请传 {}",
                    event_type=event_type,
                )

        return cls(
            event_type=event_type,
            user_id=user_id,
            user_name=user_name,
            payload=payload,
        )

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """按契约序列化为 dict（始终输出全部 4 个顶层字段）。

        ``None`` / ``{}`` / ``""`` 三者在契约中语义不同，
        序列化时**不得归一化**，必须原样保留。

        Returns:
            含 4 个冻结字段的字典，``payload`` 为浅拷贝。
        """
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "payload": dict(self.payload),
        }

    # -- 便捷属性 -----------------------------------------------------------

    @property
    def is_system_event(self) -> bool:
        """是否为系统事件。"""
        return self.event_type == SYSTEM_EVENT_TYPE

    @property
    def has_user(self) -> bool:
        """事件是否关联到真实用户（``user_id`` 非 ``None``）。"""
        return self.user_id is not None
