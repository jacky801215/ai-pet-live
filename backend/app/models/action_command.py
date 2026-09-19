"""动作指令模型（ActionCommand）。

契约来源：

    - ``docs/development/step3_interaction_engine.md``（v1.0 FROZEN）§七
    - ``docs/development/step3_interaction_engine_decision.md``（v1.0 FROZEN）§八

职责：表达 Interaction Engine 的**决策结果** —— 「要执行哪个动作」。

    InteractionEngine  --evaluate-->  ActionCommand | None

**它不是事件的投影。** 最小字段固定为 2 个，不得增删改名：

    action_type / payload

明确**不包含**（Step 3.0-A 裁决，理由见契约 §7.2）：

    - ``event_id`` —— 事件契约的 4 个顶层字段中没有 ``id``；凭空生成 ID 会制造
      「可追溯」的假象，排障时反而误导。
    - ``user_id``   —— 指令表达「做什么」，不表达「谁触发的」。身份信息由持有
      :class:`~app.models.event.Event` 的调用方直接交给 Data Manager。指令一旦携带
      ``user_id``，会逐步演变为「Event 的副本」，两条边界随之消失。
    - ``priority``  —— 由 Engine 仲裁得出，但其消费者是 Action Engine，属 Step 4。

.. note::
   为什么复用 :class:`~app.core.exceptions.InvalidRequestError` 而不新增异常类：
   Step 3.1 的允许文件清单（§三）**不含** ``app/core/exceptions.py``，
   不得为新增异常而改动该文件。``InvalidRequestError``（``INVALID_REQUEST``）
   的既有语义正是「请求参数非法（缺失、类型错误、格式不合法）」，与本模块的
   校验失败语义完全吻合，无需另造。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import InvalidRequestError

__all__ = ["ActionCommand"]

#: 动作指令的顶层字段（冻结，**仅此 2 个**）
ACTION_COMMAND_FIELDS: tuple[str, ...] = ("action_type", "payload")


@dataclass(frozen=True)
class ActionCommand:
    """动作指令（Phase 1）。

    只含 2 个字段 —— **禁止**新增 ``event_id`` / ``user_id`` / ``priority``
    等字段（见模块文档）。

    Args:
        action_type: 动作名，必须是非空字符串。取值域（动作字典）属 Step 4。
        payload: 动作参数桶。Phase 1 允许为空 ``{}``，为后续参数化动作预留。

    Raises:
        InvalidRequestError: ``action_type`` 非非空字符串，或 ``payload`` 非 ``dict``。

    .. note::
        ``frozen=True`` 只阻止字段被重新绑定，不会冻结 ``payload`` 内部的
        可变对象。跨模块传递时如需防止被下游修改，调用方应自行复制
        （:meth:`to_dict` 已返回 payload 的浅拷贝）。
    """

    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """对象级不变量校验 —— 任何构造路径都绕不过。"""
        self._check_action_type(self.action_type)
        self._check_payload(self.payload)

    # -- 校验 ---------------------------------------------------------------

    @staticmethod
    def _check_action_type(value: Any) -> None:
        """校验 ``action_type`` 必须是非空字符串。

        不做任何静默修正（不 strip、不转小写、不填默认动作）——
        动作名漂移会表现为「播了不该播的动作」或「动作不存在」，
        静默修正只会掩盖上游 bug。

        Raises:
            InvalidRequestError: 类型不是 ``str``，或为空串。
        """
        if not isinstance(value, str):
            raise InvalidRequestError(
                "action_type 必须是 str",
                field="action_type",
                received_type=type(value).__name__,
            )
        if not value:
            raise InvalidRequestError(
                "action_type 必须是非空字符串",
                field="action_type",
                received_type="str",
            )

    @staticmethod
    def _check_payload(value: Any) -> None:
        """校验 ``payload`` 必须是 ``dict``。

        与 :class:`~app.models.event.Event` 的 payload 规则保持一致：
        显式 ``None`` 与非 ``dict`` 同样拒绝 —— 无参数请传 ``{}``。

        Raises:
            InvalidRequestError: 类型不是 ``dict``。
        """
        if not isinstance(value, dict):
            raise InvalidRequestError(
                "payload 必须是 dict；无参数请传 {}",
                field="payload",
                received_type=type(value).__name__,
            )

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """按契约序列化为 dict（始终输出全部 2 个字段）。

        Returns:
            含 ``action_type`` / ``payload`` 的字典，``payload`` 为浅拷贝。
        """
        return {
            "action_type": self.action_type,
            "payload": dict(self.payload),
        }
