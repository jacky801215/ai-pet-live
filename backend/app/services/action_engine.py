"""Action Engine（动作引擎）—— 「动作怎么执行」。

契约来源：

    - ``docs/development/step3_action_engine_decision.md``（v1.0 FROZEN）
    - ``docs/development/step3_action_command_decision.md``（v1.0 FROZEN）

职责边界::

    ActionCommand + pet_id  -->  ActionEngine  -->  bool
                                     |
                                     +--> PlaybackCommand --> 播放层（Step 4）

**负责**：动作域校验（经 Asset Manager）、动作状态机（``idle`` / ``playing``）、
FIFO 队列（上限 3，满丢最旧）、生成 :class:`~app.models.playback_command.PlaybackCommand`。

**不负责**（越界即破坏分层）：

    - 规则匹配 / 条件判断      —— 属 Interaction Engine
    - ``Event``                —— 本模块**不接收、不导入** ``Event``
    - 播放实现                 —— 属 PlaybackManager（本模块只产出播放请求）
    - 数据记录 / 聚合          —— 属 DataManager
    - 文件 / 配置读取          —— 属 Asset Manager

**无 IO**：不做文件与 JSON 读取、不读取规则配置、不写数据库、不起线程。
外部依赖只有两个，均**构造注入**：``asset_manager`` 与可选的 ``playback_port``。

.. note::
    本模块**不得**导入 ``rule_loader`` / ``interaction_engine`` / ``event`` /
    ``data_manager`` / ``playback_manager``（契约 §十一 禁止项）。

.. note::
    **唯一公开入口**是 :meth:`ActionEngine.execute`（契约 §四）。
    ``process`` / ``trigger`` / ``handle`` 等别名一律禁止。
    动作队列以内部状态 ``_pending`` 保存（队首即「当前/下一个」），
    仅供测试与遥测只读查看，**不是**命令入口。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Callable, Optional

from app.models.playback_command import PlaybackCommand

__all__ = ["ActionEngine", "DEFAULT_QUEUE_LIMIT"]

logger = logging.getLogger(__name__)

#: 队列上限（Phase 1 冻结值，见契约 §九）
DEFAULT_QUEUE_LIMIT: int = 3

_STATE_IDLE = "idle"
_STATE_PLAYING = "playing"


class ActionEngine:
    """动作引擎：``ActionCommand`` + ``pet_id`` → ``bool``。

    **有状态**：持有动作队列与状态机（链路上第一个有状态模块）。
    Phase 1 假设单宠物、非并发访问，不加锁（契约 §9.6）。

    Args:
        asset_manager: **唯一外部依赖**。只需提供
            ``has_action(pet_id, action_type) -> bool`` 一个方法；
            本模块**不关心**其实现，也**不**自行读取 ``config.json``。
        playback_port: 可选。接收 :class:`PlaybackCommand` 的可调用对象
            （播放层端口）。Phase 1 可为 ``None``（仅单测 / 尚未接入播放层）。
        queue_limit: 队列上限，默认 :data:`DEFAULT_QUEUE_LIMIT`（3）。
    """

    def __init__(
        self,
        asset_manager: Any,
        *,
        playback_port: Optional[Callable[[PlaybackCommand], Any]] = None,
        queue_limit: int = DEFAULT_QUEUE_LIMIT,
    ) -> None:
        self._asset_manager = asset_manager
        self._playback_port = playback_port
        self._queue_limit = int(queue_limit)

        #: 待执行序列（队首 = 当前/下一个）。FIFO；满时丢队首（最旧）。
        self._pending: deque[PlaybackCommand] = deque()
        self._state: str = _STATE_IDLE

    # -- 公开 API（唯一） ----------------------------------------------------

    def execute(self, command: Any, pet_id: str) -> bool:
        """执行一条动作指令。

        顺序::

            校验 pet_id（非空 str）
              -> 校验 action_type（非空 str）
              -> 动作域校验（asset_manager.has_action）
              -> 队列满则丢队首（最旧）
              -> 入队并生成 PlaybackCommand
              -> 若当前 idle，则开始播放（下发播放端口）

        Args:
            command: 动作指令（:class:`~app.models.action_command.ActionCommand`）。
                只读取其 ``action_type``；**不接收** ``Event``。
            pet_id: 目标宠物标识（执行上下文，契约 O1）。

        Returns:
            ``True``  = 指令已被接受（已播放 或 已入队）。
            ``False`` = 未被接受（pet_id / action_type 非法，或动作越域 / 不存在）。

        .. important::
            本方法**永不抛异常**（契约 §八）。任何非法输入与降级均返回 ``False``，
            并记录日志 —— 「素材不存在不得导致系统停止」（红线 C4）。
        """
        action_type = getattr(command, "action_type", None)

        if not self._is_non_empty_str(pet_id):
            logger.warning("execute 拒绝：pet_id 非法 (type=%s)", type(pet_id).__name__)
            return False
        if not self._is_non_empty_str(action_type):
            logger.warning(
                "execute 拒绝：action_type 非法 (pet_id=%s, type=%s)",
                pet_id,
                type(action_type).__name__,
            )
            return False

        if not self._has_action(pet_id, action_type):
            logger.warning(
                "动作越域 / 不存在，降级 idle：pet_id=%s action_type=%s",
                pet_id,
                action_type,
            )
            return False

        if len(self._pending) >= self._queue_limit:
            dropped = self._pending.popleft()
            logger.warning(
                "队列已满(%d)，丢弃最旧：pet_id=%s action_type=%s",
                self._queue_limit,
                dropped.pet_id,
                dropped.action_type,
            )

        playback = PlaybackCommand(pet_id=pet_id, action_type=action_type)
        self._pending.append(playback)

        if self._state == _STATE_IDLE:
            self._state = _STATE_PLAYING
            self._emit(playback)

        return True

    # -- 内部（不对外暴露） --------------------------------------------------

    @staticmethod
    def _is_non_empty_str(value: Any) -> bool:
        """``value`` 是否为非空字符串。"""
        return isinstance(value, str) and bool(value)

    def _has_action(self, pet_id: str, action_type: str) -> bool:
        """经 Asset Manager 判定动作是否存在于该宠物。

        依赖仅为 ``asset_manager.has_action(pet_id, action_type) -> bool``。
        Asset Manager 自身异常**不外泄**，按「不存在」处理（返回 ``False``）。
        """
        try:
            return bool(self._asset_manager.has_action(pet_id, action_type))
        except Exception:  # pragma: no cover - 防御：Asset Manager 异常不得上抛
            logger.error(
                "asset_manager.has_action 异常，按不存在处理：pet_id=%s action_type=%s",
                pet_id,
                action_type,
                exc_info=True,
            )
            return False

    def _emit(self, playback: PlaybackCommand) -> None:
        """将播放请求下发到播放端口（未注入端口时为空操作）。

        播放端口异常**不外泄** —— 播放失败不得中断主流程（红线 C4）。
        """
        if self._playback_port is None:
            return
        try:
            self._playback_port(playback)
        except Exception:  # pragma: no cover - 防御：播放层异常不得上抛
            logger.error(
                "playback_port 异常，已忽略：pet_id=%s action_type=%s",
                playback.pet_id,
                playback.action_type,
                exc_info=True,
            )
