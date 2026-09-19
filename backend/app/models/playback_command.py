"""播放请求模型（PlaybackCommand）。

契约来源：

    - ``docs/development/step3_action_engine_decision.md``（v1.0 FROZEN）§六
    - ``docs/development/step3_action_command_decision.md``（v1.0 FROZEN）§7.2

职责：表达 Action Engine 的**产出** —— 「要播放什么」::

    ActionEngine  --execute-->  PlaybackCommand  -->  播放层（PlaybackManager，Step 4）

最小字段固定为 2 个，不得增删改名：

    pet_id / action_type

明确**不包含**（Step 3.2-B §6.1 裁决）：

    - ``asset_path`` —— 素材路径由**播放层**向 Asset Manager 解析；
      路径构造只在 Asset Manager 一处，播放请求不携带路径。
    - ``priority``   —— 属 Action Engine 内部仲裁（队列 / 抢占），播放层不需要。

.. note::
   复用 :class:`~app.core.exceptions.InvalidRequestError`，不新增异常类
   （与 :class:`~app.models.action_command.ActionCommand` 保持一致）。
   模型只做**对象级不变量校验**，不做动作域校验 —— 动作是否存在于某宠物，
   由 Action Engine 经 Asset Manager 判定（见 action_engine 契约）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import InvalidRequestError

__all__ = ["PlaybackCommand"]

#: 播放请求的顶层字段（冻结，**仅此 2 个**）
PLAYBACK_COMMAND_FIELDS: tuple[str, ...] = ("pet_id", "action_type")


@dataclass(frozen=True)
class PlaybackCommand:
    """播放请求（Phase 1）。

    只含 2 个字段 —— **禁止**新增 ``asset_path`` / ``priority`` 等字段。

    Args:
        pet_id: 目标宠物标识，必须是非空字符串（素材解析所需的上下文）。
        action_type: 要播放的动作名，必须是非空字符串。

    Raises:
        InvalidRequestError: ``pet_id`` / ``action_type`` 非非空字符串。
    """

    pet_id: str
    action_type: str

    def __post_init__(self) -> None:
        """对象级不变量校验 —— 任何构造路径都绕不过。"""
        self._check_non_empty_str(self.pet_id, "pet_id")
        self._check_non_empty_str(self.action_type, "action_type")

    # -- 校验 ---------------------------------------------------------------

    @staticmethod
    def _check_non_empty_str(value: Any, field: str) -> None:
        """校验字段必须是**非空字符串**。

        不做静默修正（不 strip、不填补默认值）—— 空 pet_id 会导致素材无法解析，
        静默修正只会把上游 bug 推迟到播放层才暴露。

        Raises:
            InvalidRequestError: 类型不是 ``str``，或为空串。
        """
        if not isinstance(value, str):
            raise InvalidRequestError(
                f"{field} 必须是 str",
                field=field,
                received_type=type(value).__name__,
            )
        if not value:
            raise InvalidRequestError(
                f"{field} 必须是非空字符串",
                field=field,
                received_type="str",
            )

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """按契约序列化为 dict（始终输出全部 2 个字段）。"""
        return {"pet_id": self.pet_id, "action_type": self.action_type}
