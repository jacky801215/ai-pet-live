"""Simulation Pipeline —— Web 层**组合根**的**编排**部分（AS-4 拆分模块 ③）。

契约来源（均 v1.0 FROZEN）：API 契约（**API-1/2/3**）、实现边界（**DA-1/3/5**）、
运行时（**DB-3/4/6**）、稳定化（**AS-4**）、runtime 集成（**WG-1~6**，见对应 decision 文档）。

组合根三件套（AS-4）：``runtime_factory.py``（装配 Runtime / build_runtime）、
``playback_state.py``（值对象 / PlaybackClock / 常量）、本模块（编排 / get_pipeline）。

**边界**：只编排（不匹配规则 / 不决策动作 / 不拼素材路径）；**零 SQL**（写经 ``DataManager``、
读经仓储）；对外只暴露 :class:`PlaybackSnapshot`（AS-4 re-export，§九 AST 守卫继续成立）。

.. note::
    「轮询驱动到期」（Step 4.3-B-1 用户裁决）：``on_finished`` 刻意留空（否则注入
    ``restore_idle`` 会让快照恒 ``idle``，与 API-2 矛盾）；到点判定归 :class:`PlaybackClock`，
    推进时机只在 :meth:`~SimulationPipeline._expire_if_due`。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.repositories.event_repository import EventRepository
from app.repositories.stat_repository import StatRepository
from app.services.data_manager import STAT_TYPE_EVENT
from app.services.event_gateway import EventGateway
from app.services.playback_state import (
    DEFAULT_DURATION_MS,
    MAX_EXPIRY_STEPS,
    STATE_IDLE,
    STATE_PLAYING,
    PlaybackClock,
    PlaybackSnapshot,  # AS-4：必须 re-export（api/playback.py 依赖此 import 路径）
    engine_state,  # Phase 3.2-A1：只读遥测投影自本模块迁出后回import（AS-4 行数预算腾挪）
    pending_queue,
    read_action_name,
)
from app.services.runtime_factory import build_runtime

__all__ = ["PlaybackSnapshot", "SimulationPipeline", "get_pipeline"]

logger = logging.getLogger(__name__)

#: 记录进 ``events.platform`` 的来源平台（Phase 1 只有模拟器，无真实平台接入）。
PLATFORM_SIMULATOR: str = "simulator"

#: WS 路径的来源平台（Phase 2.2-5 裁决：WS 事件写库口径，WG-2/WG-3 配套）。
PLATFORM_WS: str = "ws"


class SimulationPipeline:
    """Web 层组合根（编排）：装配由 :func:`build_runtime` 提供（AS-4）。

    Args:
        settings: 运行配置；``None`` 时用 ``Settings.default()``（生产路径）。
        clock: 单调时钟（秒），用于「轮询驱动到期」；测试可注入假时钟。

    .. note:: 生产单例由 :func:`get_pipeline` 惰性提供；测试**不应**复用（污染真实库）。
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

    @property
    def gateway(self) -> EventGateway:
        """组合根 gateway **只读**访问器（WG-2 方案 A：WS 与 HTTP simulate 共用同一实例）。

        返回装配期实例本身（无状态，共享零成本）；仅依赖暴露、**不是**业务修改接口；
        裁决理由见 ``phase2_websocket_runtime_integration_decision.md``（FROZEN）。
        """
        return self._runtime.gateway

    # -- 编排入口 -----------------------------------------------------------
    def simulate(self, raw_event: dict) -> PlaybackSnapshot:
        """受理一条原始事件（HTTP 门面，API-1 冻结顺序）：normalize → 编排内核 → 快照。

        **行为不变**（Phase 2.2-5）：本方法 = ``EventGateway.normalize``（唯一入口）+
        :meth:`apply_event`（``platform="simulator"``）。WS 门面见 :meth:`apply_event`，
        两门面共享同一编排内核。顶层未知键由 API 层按 DA-7 拦截。
        Raises: EVENT_* 三类事件异常**原样上抛**（API 层按 API-4 折叠为 ``400``）。
        """
        event = self._runtime.gateway.normalize(raw_event)
        return self.apply_event(event, platform=PLATFORM_SIMULATOR)

    def apply_event(
        self, event: Event, *, platform: str = PLATFORM_SIMULATOR
    ) -> PlaybackSnapshot:
        """受理一条**已规范化**的内部事件——``EventGateway`` 之后的编排内核（WS 门面）。

        WG-3 门面裁决（Phase 2.2-5）：HTTP 门面 = :meth:`simulate`（dict 先 normalize）；
        WS 门面 = 本方法（adapter → normalize 产物直接进入，normalize 恰一次）。两门面
        **共享同一编排内核 / 同一 ActionEngine 状态机 / 同一 DataManager**（WG-2 方案 A
        的 runtime 级延续，杜绝双体系漂移）；调用方 = transport 层（``api/ws.py``）。
        本方法**不重复**契约校验（EVENT_* 只可能来自 normalize）；引擎失败降级不抛异常。

        Args:
            event: 已规范化事件（共享 gateway 的 ``normalize`` 产物，WG-1 唯一入口）。
            platform: 写库来源平台；HTTP=``simulator``、WS=``ws``。
        """
        runtime = self._runtime
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
            platform=platform,
        )
        self._last_event = event.event_type
        return self.snapshot()

    def snapshot(self) -> PlaybackSnapshot:
        """返回当前播放态快照（查询副作用仅限「到期推进」：窗口已过先回落再读，
        状态机由**状态查询**驱动推进——Phase 1 无 push 通道）。"""
        self._expire_if_due()

        state = engine_state(self._runtime.action_engine)
        action: Optional[str] = None
        asset_path: Optional[str] = None
        queue_size = 0

        pending = pending_queue(self._runtime.action_engine)
        if state == STATE_PLAYING and pending:
            action = read_action_name(pending[0])
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
        platform: str = PLATFORM_SIMULATOR,
    ) -> None:
        """把一次受理结果交给 ``DataManager``（唯一写入出口，D4：只传基本类型）。

        Args:
            event_type: 事件类型；payload: 事件负载；action_name: 已执行动作名
                （``None`` = 未命中，仍记事件、不记动作）；user_id: 用户 ID
                （``None`` = 未知，**不补常量**）；user_name: 昵称（``""`` 合法）。
            platform: 来源平台（``events.platform`` 列）；HTTP=``simulator``、WS=``ws``
                （Phase 2.2-5 裁决）。AS-2：``pet_id`` 取组合根派生值，**不硬编码**。
        """
        data_manager = self._runtime.data_manager
        data_manager.write_event(
            event_type,
            payload,
            action_name,
            user_id=user_id,
            user_name=user_name,
            pet_id=self._runtime.pet_id,
            platform=platform,
        )
        data_manager.aggregate_counter(STAT_TYPE_EVENT, event_type, 1)
        if action_name:
            data_manager.record_action(action_name)

    # -- 播放窗口（轮询驱动到期，Step 4.3-B-1 裁决） --------------------------
    def _expire_if_due(self) -> None:
        """把「已到期」的播放推进下去：每步 ``ActionEngine.restore_idle(pet_id)`` 弹队首、
        复位 ``idle``、续发下一条（推进逻辑全在 ActionEngine 内，本模块只管「何时到点」）；
        循环上限 :data:`MAX_EXPIRY_STEPS` 保证异常状态**不死循环**（PROJECT_RULES 第十一条）。
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
        if engine_state(self._runtime.action_engine) != STATE_PLAYING:
            return
        pending = pending_queue(self._runtime.action_engine)
        if not pending:
            return
        action = read_action_name(pending[0])
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

    # -- 素材（解析唯一归 AssetManager，P3） ------------------------------------
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


# ---------------------------------------------------------------------------
# 进程级单例（惰性）：FastAPI 依赖提供者
# ---------------------------------------------------------------------------
_default_pipeline: Optional[SimulationPipeline] = None


def get_pipeline() -> SimulationPipeline:
    """FastAPI 依赖：进程级单例组合根（**惰性构造**——模块级 ``app`` 导入时不得触库）。"""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = SimulationPipeline()
    return _default_pipeline
