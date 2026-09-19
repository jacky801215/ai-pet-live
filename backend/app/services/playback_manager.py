"""播放管理器（PlaybackManager）—— 「播放怎么执行」。

契约来源：

    - ``docs/development/step4_playback_data_decision.md``（v1.0 FROZEN）D1–D6
    - ``docs/development/step3_playback_decision.md``（v1.0 FROZEN）P1–P6

职责边界::

    PlaybackCommand ──▶ PlaybackManager ──▶ bool
                              │
                              ├─▶ AssetManager.find_asset(pet_id, action)  唯一素材解析点
                              ├─▶ playback_port.play(path)                 播放端口（可空）
                              └─▶ on_finished(pet_id)                      注入回调 → ActionEngine.restore_idle

**负责**：接收 :class:`~app.models.playback_command.PlaybackCommand`、向 AssetManager
索取素材、调用播放端口、在成功 / 失败后经**注入回调**通知状态恢复。

**不负责**（越界即破坏分层）：

    - 决定「播什么」    —— 不读 ``rules.json``、不做规则匹配
    - 解析素材路径      —— 唯一解析点 = AssetManager（P3），不得出现 ``assets/pets/...`` 拼接
    - 拥有业务状态      —— ``idle`` / ``playing`` 归 ActionEngine（P6），本模块不得自行置 idle
    - 数据记录 / 聚合   —— 属 DataManager，由调用方触发（C5）
    - 接收 ``Event`` / ``ActionCommand``

**无 IO**：不读文件与规则、不写数据库、不起线程。
依赖全部**构造注入**：``asset_manager`` 必填，``on_finished`` / ``playback_port`` 可选。

.. note::
    本模块**不得** ``import`` ActionEngine —— 完成 / 失败一律通过注入回调通知，
    以保持 ``ActionEngine → PlaybackManager`` 单向依赖、避免循环 import（D3）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

__all__ = ["PlaybackManager"]

logger = logging.getLogger(__name__)


class PlaybackManager:
    """播放管理器：``PlaybackCommand`` → ``bool``。

    **无业务状态**：不持有 ``idle`` / ``playing``，一次 :meth:`play` 即一次完整处理。

    Args:
        asset_manager: **唯一素材来源**。只需提供
            ``find_asset(pet_id, action) -> metadata | None`` 一个方法；
            本模块**不关心**其实现，也**不**自行读取 ``config.json`` 或拼接路径。
        on_finished: 可选。完成 / 失败后通知状态恢复的回调，签名为
            ``on_finished(pet_id) -> None``；生产接线为
            ``ActionEngine.restore_idle``（D3）。
        playback_port: 可选。播放端口，需提供 ``play(path) -> Any``（§六）。
            为 ``None`` 时只做素材解析与通知，不实际播放（单测 / 未接线）。
    """

    def __init__(
        self,
        asset_manager: Any,
        *,
        on_finished: Optional[Callable[[str], Any]] = None,
        playback_port: Optional[Any] = None,
    ) -> None:
        self._asset_manager = asset_manager
        self._on_finished = on_finished
        self._playback_port = playback_port

    # -- 公开 API（唯一入口） ------------------------------------------------

    def play(self, command: Any) -> bool:
        """执行一条播放指令。

        顺序::

            校验 command.pet_id / command.action_type（非空 str）
              -> AssetManager.find_asset(pet_id, action_type)     不存在则 False
              -> 取素材路径（AssetManager 给出，本模块不拼接）
              -> playback_port.play(path)                         异常则 False
              -> on_finished(pet_id) 通知状态恢复
              -> True

        Args:
            command: 播放指令（:class:`~app.models.playback_command.PlaybackCommand`）。
                只读取其 ``pet_id`` / ``action_type``。

        Returns:
            ``True``  = 播放已成功下发。
            ``False`` = 未能播放（素材缺失 / 路径缺失 / 端口异常）。

        .. important::
            本方法**永不抛异常**。失败一律 ``return False`` —— 播放失败不得中断
            系统（红线 C4 / D4 / ``PROJECT_RULES.md`` §十一）。

        .. note::
            ``on_finished`` 在**成功与失败两条路径上都会触发**
            —— 播放是否成功，动作状态都必须回到 ``idle``（D3 + D4 合并结果），
            否则状态机会永久停在 ``playing``。
        """
        pet_id = getattr(command, "pet_id", None)
        action_type = getattr(command, "action_type", None)

        if not self._is_non_empty_str(pet_id):
            logger.warning("play 拒绝：pet_id 非法 (type=%s)", type(pet_id).__name__)
            return False
        if not self._is_non_empty_str(action_type):
            logger.warning(
                "play 拒绝：action_type 非法 (pet_id=%s, type=%s)",
                pet_id,
                type(action_type).__name__,
            )
            return False

        metadata = self._find_asset(pet_id, action_type)
        if metadata is None:
            return self._fail(pet_id, action_type, "素材不存在")

        path = self._path_of(metadata)
        if not path:
            return self._fail(pet_id, action_type, "素材元数据缺少路径")

        if not self._invoke_port(pet_id, action_type, path):
            return self._fail(pet_id, action_type, "播放端口调用失败")

        logger.info(
            "播放已下发：pet_id=%s action_type=%s path=%s", pet_id, action_type, path
        )
        self._notify(pet_id)
        return True

    # -- 内部（不对外暴露） --------------------------------------------------

    @staticmethod
    def _is_non_empty_str(value: Any) -> bool:
        """``value`` 是否为非空字符串。"""
        return isinstance(value, str) and bool(value)

    def _find_asset(self, pet_id: str, action_type: str) -> Any:
        """向 AssetManager 索取素材元数据（等价 ``exists`` + ``get``，一次查询）。

        AssetManager 自身异常**不外泄**，按「素材缺失」处理（返回 ``None``）。
        """
        try:
            return self._asset_manager.find_asset(pet_id, action_type)
        except Exception:  # pragma: no cover - 防御：Asset Manager 异常不得上抛
            logger.error(
                "asset_manager.find_asset 异常，按素材缺失处理：pet_id=%s action_type=%s",
                pet_id,
                action_type,
                exc_info=True,
            )
            return None

    @staticmethod
    def _path_of(metadata: Any) -> str:
        """取素材路径。

        只读取 AssetManager 给出的值，**不做任何拼接**（P3 不变量）。
        优先 ``asset_path``（P3 冻结格式
        ``assets/pets/{pet_type}/{res_type}/{action}/{asset}``），
        退而取 ``absolute_path``。
        """
        for field in ("asset_path", "absolute_path"):
            value = getattr(metadata, field, None)
            if isinstance(value, str) and value:
                return value
        return ""

    def _invoke_port(self, pet_id: str, action_type: str, path: str) -> bool:
        """调用播放端口；未注入端口时视为成功（只做解析与通知）。"""
        if self._playback_port is None:
            logger.debug(
                "未注入播放端口，跳过实际播放：pet_id=%s action_type=%s",
                pet_id,
                action_type,
            )
            return True

        try:
            self._playback_port.play(path)
        except Exception:  # pragma: no cover - 防御：播放异常不得上抛
            logger.error(
                "播放端口异常：pet_id=%s action_type=%s path=%s",
                pet_id,
                action_type,
                path,
                exc_info=True,
            )
            return False
        return True

    def _notify(self, pet_id: str) -> None:
        """通知状态恢复（回调异常不外泄）。"""
        if self._on_finished is None:
            return
        try:
            self._on_finished(pet_id)
        except Exception:  # pragma: no cover - 防御：回调异常不得上抛
            logger.error("on_finished 回调异常，已忽略：pet_id=%s", pet_id, exc_info=True)

    def _fail(self, pet_id: str, action_type: str, reason: str) -> bool:
        """统一失败出口：记 ``error`` 日志 + 通知恢复 + 返回 ``False``（D4）。"""
        logger.error(
            "播放失败：pet_id=%s action_type=%s reason=%s", pet_id, action_type, reason
        )
        self._notify(pet_id)
        return False
