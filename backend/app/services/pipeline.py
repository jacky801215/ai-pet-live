"""Simulation Pipeline —— Web 层**组合根**的**编排**部分（AS-4 拆分模块 ③）。

契约来源（均 v1.0 FROZEN）：``step4_api_contract_decision.md``（**API-1 / API-2 / API-3**）、
``step4_api_implementation_boundary.md``（**DA-1 / DA-3 / DA-5**）、
``step4_api_runtime_decision.md``（**DB-3 / DB-4 / DB-6**）、
``step4_api_stability_decision.md``（**AS-4**：三模块拆分）。

组合根三件套（AS-4）::

    services/runtime_factory.py   装配：Runtime / build_runtime（引擎装配在此）
    services/playback_state.py    值对象：PlaybackSnapshot / PlaybackClock / 常量
    services/pipeline.py          编排：SimulationPipeline / get_pipeline   ← 本模块

**边界**：本模块只编排 —— 不匹配规则 / 不决策动作 / 不拼素材路径；**零 SQL**（写经
``DataManager``、读经仓储）；**不接收 / 不返回模型对象给 HTTP 层**，只暴露
:class:`PlaybackSnapshot`；该快照**必须**仍可从本模块 ``import``（AS-4 re-export）⇒
``app/api/playback.py`` 零改动、§九 AST 守卫继续成立。

.. note::
    **「轮询驱动到期」**（Step 4.3-B-1 用户裁决）：``on_finished`` **刻意留空**（注入
    ``restore_idle`` 会让 ``execute()`` 同调用内排空队列 ⇒ 快照恒 ``idle``，与 API-2
    「``state`` 可为 ``playing``」矛盾）。何时到点**判定**归 :class:`PlaybackClock`，
    **推进时机只**在 :meth:`~SimulationPipeline._expire_if_due`。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.repositories.event_repository import EventRepository
from app.repositories.stat_repository import StatRepository
from app.services.data_manager import STAT_TYPE_EVENT
from app.services.playback_state import (
    DEFAULT_DURATION_MS,
    MAX_EXPIRY_STEPS,
    STATE_IDLE,
    STATE_PLAYING,
    PlaybackClock,
    PlaybackSnapshot,  # AS-4：必须 re-export（api/playback.py 依赖此 import 路径）
)
from app.services.runtime_factory import build_runtime

__all__ = ["PlaybackSnapshot", "SimulationPipeline", "get_pipeline"]

logger = logging.getLogger(__name__)

#: 记录进 ``events.platform`` 的来源平台（Phase 1 只有模拟器，无真实平台接入）。
PLATFORM_SIMULATOR: str = "simulator"


class SimulationPipeline:
    """Web 层组合根（编排）：装配由 :func:`build_runtime` 提供（AS-4）。

    Args:
        settings: 运行配置；``None`` 时使用 ``Settings.default()``（生产路径）。
        clock: 单调时钟（秒），用于「轮询驱动到期」；测试可注入假时钟。

    .. note::
        生产单例由 :func:`get_pipeline` 惰性提供；测试**不应**复用（会污染真实库与素材）。
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        #: 已装配的运行期依赖（装配职责归 runtime_factory，本模块只消费）
        self._runtime = build_runtime(settings, clock=clock)
        #: 播放窗口（**轮询驱动到期**）：只在状态查询时推进，见 _expire_if_due
        self._playback_clock = PlaybackClock(self._runtime.clock)
        #: 最近一次被受理的 event_type（纯投影，供快照展示）
        self._last_event: Optional[str] = None

    # -- 只读访问器（供 API 层获取装配好的依赖） ------------------------------
    @property
    def pet_id(self) -> str:
        """对外主键（Phase 1 默认 ``cat_001``，由 config.json 派生）。"""
        return self._runtime.pet_id

    @property
    def event_repository(self) -> EventRepository:
        """只读事件仓储（DA-1 读路径）。"""
        return self._runtime.event_repository

    @property
    def stat_repository(self) -> StatRepository:
        """只读统计仓储（DA-1 读路径）。"""
        return self._runtime.stat_repository

    # -- 编排入口 -----------------------------------------------------------
    def simulate(self, raw_event: dict) -> PlaybackSnapshot:
        """受理一条原始事件，走完整链路并返回最新播放态快照。

        顺序（API-1 冻结）：``EventGateway.normalize``（唯一入口）→
        ``InteractionEngine.evaluate``（可无命中，属正常）→ ``ActionEngine.execute``
        （失败降级，永不抛异常）→ ``DataManager`` 记录（C5 / D5：由调用方发起）→ 快照。

        Args:
            raw_event: 原始事件字典。**允许键只有** ``event_type`` / ``user_id`` /
                ``user_name`` / ``payload``（顶层未知键由 API 层按 DA-7 拦截）。

        Returns:
            快照（内部形态；对外 URL 由 API 层拼）。

        Raises:
            EventTypeInvalidError / EventPayloadInvalidError / EventSchemaInvalidError:
                三类事件异常**原样上抛**，由 API 层按 API-4 折叠为 ``400 INVALID_REQUEST``。
        """
        runtime = self._runtime
        event = runtime.gateway.normalize(raw_event)
        command = runtime.interaction_engine.evaluate(event)

        action_name: Optional[str] = None
        if command is not None and runtime.action_engine.execute(command, runtime.pet_id):
            accepted = str(getattr(command, "action_type", "") or "")
            if accepted:
                action_name = accepted
                self._playback_clock.arm(self._duration_seconds(accepted))

        self._record(
            event.event_type,
            dict(event.payload),
            action_name,
            user_id=event.user_id,
            user_name=event.user_name,
        )
        self._last_event = event.event_type
        return self.snapshot()

    def snapshot(self) -> PlaybackSnapshot:
        """返回当前播放态快照。

        查询副作用**仅限**「到期推进」：窗口已过则先 ``ActionEngine.restore_idle()``
        回落再读状态 —— 状态机由**状态查询**驱动推进（Phase 1 无 push 通道）。
        """
        self._expire_if_due()

        state = self._engine_state()
        action: Optional[str] = None
        asset_path: Optional[str] = None
        queue_size = 0

        pending = self._pending()
        if state == STATE_PLAYING and pending:
            action = self._action_of(pending[0])
            queue_size = max(0, len(pending) - 1)
            asset_path = self._asset_path_of(action) if action else None

        return PlaybackSnapshot(
            pet_id=self._runtime.pet_id,
            state=state,
            action=action,
            asset_path=asset_path,
            queue_size=queue_size,
            last_event=self._last_event,
        )

    # -- 数据记录（C5 / D5：记录由调用方 = 本编排层发起） ----------------------
    def _record(
        self,
        event_type: str,
        payload: dict,
        action_name: Optional[str],
        *,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> None:
        """把一次受理结果交给 ``DataManager``（唯一写入出口，D4：只传基本类型）。

        Args:
            event_type: 事件类型（来自 ``Event``）。
            payload: 事件负载（基本类型映射）。
            action_name: 已执行的动作名；``None`` = 未命中动作（仍记事件、不记动作）。
            user_id: 触发用户 ID（``None`` = 未知，**不补常量**）。
            user_name: 触发用户昵称（``""`` 为合法值）。

        .. note::
            身份字段接线（``step4_api_stability_decision.md`` **AS-2**）：``pet_id`` 取
            组合根派生的 ``pet_id``（**不硬编码**），``platform`` 固定 ``"simulator"``。
        """
        data_manager = self._runtime.data_manager
        data_manager.write_event(
            event_type,
            payload,
            action_name,
            user_id=user_id,
            user_name=user_name,
            pet_id=self._runtime.pet_id,
            platform=PLATFORM_SIMULATOR,
        )
        data_manager.aggregate_counter(STAT_TYPE_EVENT, event_type, 1)
        if action_name:
            data_manager.record_action(action_name)

    # -- 播放窗口（轮询驱动到期，Step 4.3-B-1 裁决） --------------------------
    def _expire_if_due(self) -> None:
        """把「已到期」的播放推进下去：每步调用一次 ``ActionEngine.restore_idle(pet_id)``，
        由该钩子弹队首、复位 ``idle``、继续下发下一条（推进逻辑全在 ActionEngine 内）；
        本模块只负责「什么时候到点」。循环上限 :data:`MAX_EXPIRY_STEPS` 仅保证异常状态下
        **不死循环**（PROJECT_RULES 第十一条）。
        """
        steps = 0
        while self._playback_clock.is_due():
            if steps >= MAX_EXPIRY_STEPS:
                logger.warning(
                    "播放到期推进超过上限(%d)，强制回落 idle", MAX_EXPIRY_STEPS
                )
                self._playback_clock.disarm()
                return
            steps += 1
            self._playback_clock.disarm()
            self._runtime.action_engine.restore_idle(self._runtime.pet_id)
            self._rearm_from_current()

    def _rearm_from_current(self) -> None:
        """按**当前队首**动作重新备好播放窗口；无待播动作时保持未备状态。"""
        if self._engine_state() != STATE_PLAYING:
            return
        pending = self._pending()
        if not pending:
            return
        action = self._action_of(pending[0])
        if action:
            self._playback_clock.arm(self._duration_seconds(action))

    def _duration_seconds(self, action: str) -> float:
        """动作的播放窗口（秒）：取自 ``AssetManager`` 的素材真实时长（毫秒 → 秒）；
        元数据不可用时用兜底 :data:`DEFAULT_DURATION_MS`，时长 ``0`` 视为瞬时完成。
        """
        metadata = self._find_metadata(action)
        duration_ms: Any = (
            getattr(metadata, "duration", None) if metadata is not None else None
        )
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
            duration_ms = DEFAULT_DURATION_MS
        return max(duration_ms, 0) / 1000.0

    # -- 素材（解析唯一归 AssetManager，P3）与 ActionEngine 遥测（只读） --------
    def _find_metadata(self, action: str) -> Any:
        """向 AssetManager 索取素材元数据（异常按「无素材」处理，红线 C4）。"""
        pet_id = self._runtime.pet_id
        if not pet_id:
            return None
        try:
            return self._runtime.asset_manager.find_asset(pet_id, action)
        except Exception:  # noqa: BLE001 - 素材问题不得中断请求
            logger.warning("素材解析失败（按无素材处理）: action=%s", action)
            return None

    def _asset_path_of(self, action: str) -> Optional[str]:
        """取素材**相对路径**；对外 URL 由 API 层拼（DA-5）。"""
        metadata = self._find_metadata(action)
        if metadata is None:
            return None
        path = getattr(metadata, "asset_path", None)
        return path if isinstance(path, str) and path else None

    def _engine_state(self) -> str:
        """读状态机当前状态（只读遥测）：Owner 始终是 ``ActionEngine``（P6）。"""
        state = getattr(self._runtime.action_engine, "_state", STATE_IDLE)
        return state if state in (STATE_IDLE, STATE_PLAYING) else STATE_IDLE

    def _pending(self) -> list:
        """读待播队列快照（只读遥测）：``_pending`` 已被声明「仅供测试与只读查看」。"""
        pending = getattr(self._runtime.action_engine, "_pending", None)
        if pending is None:
            return []
        try:
            return list(pending)
        except TypeError:  # pragma: no cover - 防御：不可迭代即视为空队列
            return []

    @staticmethod
    def _action_of(command: Any) -> Optional[str]:
        """从播放指令读取动作名（非空 ``str`` 才算有效）。"""
        action = getattr(command, "action_type", None)
        return action if isinstance(action, str) and action else None


# ---------------------------------------------------------------------------
# 进程级单例（惰性）：FastAPI 依赖提供者
# ---------------------------------------------------------------------------
_default_pipeline: Optional[SimulationPipeline] = None


def get_pipeline() -> SimulationPipeline:
    """FastAPI 依赖：返回进程级单例组合根（**惰性构造**）。

    惰性是刻意的：模块级 ``app`` 导入时**不得**触碰数据库（``test_api_contract.py``
    会用临时库覆盖本依赖）。
    """
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = SimulationPipeline()
    return _default_pipeline
