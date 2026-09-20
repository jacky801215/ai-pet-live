"""Simulation Pipeline —— Web 层**组合根**（composition root）。

契约来源：

    - ``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-1 / API-2 / API-3**
    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 / DA-3 / DA-5**
    - ``docs/development/step4_api_runtime_decision.md``（v1.0 FROZEN）**DB-3 / DB-4 / DB-6**

职责：把既有 service 与仓储**装配**成一条完整链路，并向 ``app/api/**`` 提供
**唯一**编排入口::

    raw dict ─▶ EventGateway ─▶ InteractionEngine ─▶ ActionEngine ─▶ PlaybackManager
                    │                  │                  │                │
                    └──────────────────┴──────────────────┴────────────────┘
                                        │
                            DataManager（写）· EventRepository / StatRepository（读）

**为什么需要本模块**（Step 4.3-B-1 硬矛盾与用户裁决）：

    ``api/**`` 既要输出规则产物 ``action``（必须调用引擎），又被 §九 的 AST 守卫
    禁止 ``import`` 引擎；``main.py`` 也不得调用引擎（DB-3）。二者的交集是空集
    ⇒ 引擎装配必须落在**第三个位置**，即本模块。``app/api/**`` 只 ``import`` 本模块。

**边界**：

- 本模块是 Web 侧**唯一** ``import`` ``ActionEngine`` / ``InteractionEngine`` /
  ``PlaybackManager`` 的模块（``main.py`` 与 ``api/**`` 均不 ``import``）。
- 本模块**不做**规则匹配、**不做**动作决策、**不拼素材路径** —— 全部委托给对应 service。
- 本模块**零 SQL**：写经 ``DataManager``（唯一写入出口），读经仓储。
- 本模块**不接收 / 不返回模型对象给 HTTP 层**：对外只暴露
  :class:`PlaybackSnapshot`（基本类型容器）。

.. note::
    **「轮询驱动到期」**（Step 4.3-B-1 用户裁决）：本模块**不**把
    ``ActionEngine.restore_idle`` 注入 ``PlaybackManager.on_finished`` —— 否则
    ``execute()`` 会在**同一次调用内**同步排空队列，快照将恒为 ``idle``，
    与 API-2「``state`` 可为 ``playing``」直接矛盾。播放何时结束改由本模块按
    **素材真实时长**计时，在**下一次状态查询**时推进 ``restore_idle()``。
    动作状态机仍**唯一**归 ``ActionEngine``，本模块只提供「播放时钟」。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.repositories.event_repository import EventRepository
from app.repositories.stat_repository import StatRepository
from app.services.action_engine import ActionEngine
from app.services.asset_manager import AssetManager
from app.services.data_manager import STAT_TYPE_EVENT, DataManager
from app.services.event_gateway import EventGateway
from app.services.interaction_engine import InteractionEngine
from app.services.playback_manager import PlaybackManager
from app.services.rule_loader import RuleLoader

__all__ = ["PlaybackSnapshot", "SimulationPipeline", "get_pipeline"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
STATE_IDLE: str = "idle"
STATE_PLAYING: str = "playing"

#: 素材元数据不可用时使用的兜底播放窗口（毫秒）
DEFAULT_DURATION_MS: int = 1000

#: 单次快照最多推进的播放步数。快速路径下队列最多 3 条，
#: 本上限仅为「异常状态下不得死循环」的防御（PROJECT_RULES 第十一条）。
MAX_EXPIRY_STEPS: int = 64

#: 记录进 ``events.platform`` 的来源平台（Phase 1 只有模拟器，无真实平台接入）。
PLATFORM_SIMULATOR: str = "simulator"


@dataclass(frozen=True)
class PlaybackSnapshot:
    """播放态快照的**内部**形态（API-2 六字段的来源）。

    Attributes:
        pet_id: 对外主键（与 ``AssetManager`` 一致）。
        state: ``"idle"`` 或 ``"playing"``。
        action: 当前动作名；``idle`` 时为 ``None``。
        asset_path: 素材**相对路径**（``assets/pets/...``）。
            ⚠️ 内部字段：对外 URL 由 **API 层**拼（DA-5），**不得**直接下发。
        queue_size: 待播队列长度（``>= 0``，不含正在播放的一条）。
        last_event: 最近一次被受理的 ``event_type``；无则 ``None``。
    """

    pet_id: str
    state: str
    action: Optional[str]
    asset_path: Optional[str]
    queue_size: int
    last_event: Optional[str]


class SimulationPipeline:
    """Web 层组合根：装配完整链路并提供编排入口。

    Args:
        settings: 运行配置；``None`` 时使用 ``Settings.default()``（生产路径）。
        clock: 单调时钟（单位：秒），用于「轮询驱动到期」。默认 ``time.monotonic``；
            测试可注入假时钟，以确定性验证播放窗口的到期回落。

    .. note::
        生产用单例由 :func:`get_pipeline` 惰性提供；测试**不应**复用该单例，
        而应自行构造实例并覆盖 FastAPI 依赖（``dependency_overrides``），
        以保证临时数据库与临时素材目录的隔离。
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._settings: Settings = settings or Settings.default()
        self._settings.ensure_directories()
        self._clock: Callable[[], float] = clock or time.monotonic

        # -- 存储 / 素材链 ---------------------------------------------------
        self._database = Database(
            self._settings.database_path, self._settings.schema_path
        )
        self._database.initialize()
        #: 唯一素材解析点（P3）：其它模块一律向它索取路径 / 时长
        self._asset_manager = AssetManager(AssetRepository(self._database), self._settings)

        # -- 播放链 ----------------------------------------------------------
        # on_finished **刻意留空**：播放何时结束由本模块按时长判定（见 _expire_if_due）。
        self._playback_manager = PlaybackManager(self._asset_manager)
        self._action_engine = ActionEngine(
            self._asset_manager,
            playback_port=self._playback_manager.play,
        )

        # -- 规则链 ----------------------------------------------------------
        # rules.json 的唯一入口是 RuleLoader（本模块不自行解析规则文件）。
        self._interaction_engine = InteractionEngine(RuleLoader.load())
        self._gateway = EventGateway()

        # -- 数据链（写 / 读分离，DA-1） --------------------------------------
        self._data_manager = DataManager(self._database)
        self._event_repository = EventRepository(self._database)
        self._stat_repository = StatRepository(self._database)

        # -- 运行态（本模块自持，**不是**第二套状态机） ----------------------
        #: 对外主键：由 AssetManager 的 pet 索引派生，**不硬编码**（红线 C3）
        self._pet_id: str = self._derive_pet_id()
        #: 最近一次被受理的 event_type（纯投影，供快照展示）
        self._last_event: Optional[str] = None
        #: 当前动作的播放到期时刻（单调时钟秒）；``None`` = 无进行中的播放窗口
        self._playing_until: Optional[float] = None

    # -- 只读访问器（供 API 层获取装配好的依赖） ------------------------------

    @property
    def pet_id(self) -> str:
        """对外主键（Phase 1 默认 ``cat_001``，由 config.json 派生）。"""
        return self._pet_id

    @property
    def event_repository(self) -> EventRepository:
        """只读事件仓储（DA-1 读路径）。"""
        return self._event_repository

    @property
    def stat_repository(self) -> StatRepository:
        """只读统计仓储（DA-1 读路径）。"""
        return self._stat_repository

    # -- 编排入口 -----------------------------------------------------------

    def simulate(self, raw_event: dict) -> PlaybackSnapshot:
        """受理一条原始事件，走完整链路并返回最新播放态快照。

        顺序（API-1 冻结）::

            raw dict
              -> EventGateway.normalize            校验并补齐（唯一入口）
              -> InteractionEngine.evaluate        规则匹配（可能无命中，属正常）
              -> ActionEngine.execute              动作执行（失败降级，永不抛异常）
              -> DataManager                       记录（C5 / D5：记录由调用方发起）
              -> PlaybackSnapshot                  最新快照（与 GET state 同构）

        Args:
            raw_event: 原始事件字典。**允许键只有** ``event_type`` /
                ``user_id`` / ``user_name`` / ``payload``（顶层未知键由 API 层
                按 DA-7 拦截；本层仍由事件模型做最终裁定）。

        Returns:
            最新播放态快照（内部形态；对外 URL 由 API 层拼）。

        Raises:
            EventTypeInvalidError: ``event_type`` 缺失 / 非法。
            EventPayloadInvalidError: ``payload`` 类型或事件级字段不合规。
            EventSchemaInvalidError: 事件顶层结构非法。

        .. important::
            三类事件异常**原样上抛** —— 由 API 层的全局异常处理器按 API-4 折叠表
            映射为 ``400 INVALID_REQUEST``。本层**不**改写 ``code``、
            **不**包装、**不**吞掉（事件契约是唯一裁定者）。
        """
        event = self._gateway.normalize(raw_event)
        command = self._interaction_engine.evaluate(event)

        action_name: Optional[str] = None
        if command is not None and self._action_engine.execute(command, self._pet_id):
            accepted = str(getattr(command, "action_type", "") or "")
            if accepted:
                action_name = accepted
                self._playing_until = self._clock() + self._duration_seconds(accepted)

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

        查询副作用**仅限**「到期推进」：若当前动作的播放窗口已过，
        先调用 ``ActionEngine.restore_idle()`` 回落，再读取状态 ——
        即状态机的推进由**状态查询**驱动（Phase 1 无 push 通道，见模块文档）。
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
            pet_id=self._pet_id,
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
        """把一次受理结果交给 ``DataManager``（唯一写入出口）。

        只传**基本类型**参数（D4：DataManager 不接收模型对象，对上游零依赖）。

        - ``write_event``：``events`` 明细一行（``action_name`` 非空 = 动作已执行）；
        - ``aggregate_counter('event', ...)``：事件计数（``GET /api/stats`` 的 ``events``）；
        - ``record_action``：动作计数（**只记聚合、不记明细**，D5）。

        Args:
            event_type: 事件类型（来自 ``Event``）。
            payload: 事件负载（基本类型映射）。
            action_name: 已执行的动作名；``None`` = 未命中动作。
            user_id: 触发用户 ID（来自 ``Event.user_id``；``None`` = 未知，
                **不补常量**）。
            user_name: 触发用户昵称（来自 ``Event.user_name``；``""`` 为合法值）。

        .. note::
            **身份字段接线**（Step 4.3-B-2-L2，AS-2 授权）：
            ``user_id`` / ``user_name`` 取自 ``Event``；``pet_id`` 取组合根自身的
            ``self._pet_id``（由 ``AssetManager`` 派生，**不硬编码**）；
            ``platform`` 固定 ``"simulator"``。⇒ ``events`` 九字段完整落库。
        """
        self._data_manager.write_event(
            event_type,
            payload,
            action_name,
            user_id=user_id,
            user_name=user_name,
            pet_id=self._pet_id,
            platform=PLATFORM_SIMULATOR,
        )
        self._data_manager.aggregate_counter(STAT_TYPE_EVENT, event_type, 1)
        if action_name:
            self._data_manager.record_action(action_name)

    # -- 播放窗口（轮询驱动到期） -------------------------------------------

    def _expire_if_due(self) -> None:
        """把「已到期」的播放推进下去（**轮询驱动到期**，Step 4.3-B-1 裁决）。

        每推进一步即调用一次 ``ActionEngine.restore_idle(pet_id)``：由该钩子
        弹出队首、状态复位 ``idle``，并在仍有待播指令时继续下发下一条 ——
        推进逻辑**全部**在 ActionEngine 内，本模块只负责「什么时候到点」。

        循环上限 :data:`MAX_EXPIRY_STEPS` 是防御性的：正常路径下队列上限为 3，
        必然在数步内收敛；上限只保证异常状态下**不死循环**。
        """
        steps = 0
        while self._playing_until is not None and self._clock() >= self._playing_until:
            if steps >= MAX_EXPIRY_STEPS:
                logger.warning(
                    "播放到期推进超过上限(%d)，强制回落 idle", MAX_EXPIRY_STEPS
                )
                self._playing_until = None
                return
            steps += 1
            self._playing_until = None
            self._action_engine.restore_idle(self._pet_id)
            self._playing_until = self._deadline_of_current()

    def _deadline_of_current(self) -> Optional[float]:
        """当前队首动作的到期时刻；无待播动作时返回 ``None``。"""
        if self._engine_state() != STATE_PLAYING:
            return None
        pending = self._pending()
        if not pending:
            return None
        action = self._action_of(pending[0])
        if not action:
            return None
        return self._clock() + self._duration_seconds(action)

    def _duration_seconds(self, action: str) -> float:
        """动作的播放窗口（秒）。

        来源是 **AssetManager** 给出的素材真实时长（``AssetMetadata.duration``，
        单位毫秒；Step 1.1 起由 ``ffprobe`` 实测写入）。元数据不可用时使用兜底窗口
        :data:`DEFAULT_DURATION_MS`；时长为 ``0`` 视为**瞬时完成**。
        """
        metadata = self._find_metadata(action)
        duration_ms: Any = (
            getattr(metadata, "duration", None) if metadata is not None else None
        )
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
            duration_ms = DEFAULT_DURATION_MS
        return max(duration_ms, 0) / 1000.0

    # -- 素材（解析唯一归 AssetManager，P3） --------------------------------

    def _find_metadata(self, action: str) -> Any:
        """向 AssetManager 索取素材元数据（异常按「无素材」处理，红线 C4）。"""
        if not self._pet_id:
            return None
        try:
            return self._asset_manager.find_asset(self._pet_id, action)
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

    # -- ActionEngine 遥测（只读） ------------------------------------------

    def _engine_state(self) -> str:
        """读取动作状态机的**当前状态**（只读遥测）。

        ``idle`` / ``playing`` 的 Owner 始终是 ``ActionEngine``（P6），
        本模块只做投影，**不**自行置状态。
        """
        state = getattr(self._action_engine, "_state", STATE_IDLE)
        return state if state in (STATE_IDLE, STATE_PLAYING) else STATE_IDLE

    def _pending(self) -> list:
        """读取待播队列快照（只读遥测）。

        ``ActionEngine`` 文档已声明 ``_pending`` 「仅供测试与遥测只读查看」，
        队首即「当前/下一个」。本方法**不**写入、**不**改动队列。
        """
        pending = getattr(self._action_engine, "_pending", None)
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

    # -- 对外主键派生（禁止硬编码角色名，红线 C3） --------------------------

    def _derive_pet_id(self) -> str:
        """派生对外主键：取 AssetManager 宠物主键列表中**字典序首个** ``pet_id``。

        主键全集来源是各宠物 ``assets/pets/*/config.json``，由 ``AssetManager``
        **统一构建**（D2）并经其**公开只读接口** ``pet_ids()`` 暴露；
        本模块只**消费**，绝不自行读取配置文件或拼接目录。

        Returns:
            ``pet_id``（Phase 1 为 ``cat_001``）；无任何宠物配置时返回空串
            （下游动作会全部降级，但**进程不得因此崩溃**，PROJECT_RULES 第十一条）。
        """
        try:
            pet_ids = self._asset_manager.pet_ids()
        except Exception:  # noqa: BLE001 - 索引不可用时退化为空（不崩溃）
            logger.exception("读取 pet 索引失败，按空索引处理")
            return ""
        if not pet_ids:
            logger.warning("未发现任何宠物配置，pet_id 为空：动作将全部降级")
            return ""
        return pet_ids[0]


# ---------------------------------------------------------------------------
# 进程级单例（惰性）：FastAPI 依赖提供者
# ---------------------------------------------------------------------------
_default_pipeline: Optional[SimulationPipeline] = None


def get_pipeline() -> SimulationPipeline:
    """FastAPI 依赖：返回进程级单例组合根（**惰性构造**）。

    惰性构造是刻意的：模块级 ``app`` 导入时**不得**触碰数据库
    （``tests/test_api_contract.py`` 会用临时库覆盖本依赖）。
    """
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = SimulationPipeline()
    return _default_pipeline
