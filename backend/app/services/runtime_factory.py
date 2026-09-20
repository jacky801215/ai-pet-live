"""运行期装配工厂 —— 组合根的**装配**部分（AS-4 拆分模块 ①）。

契约来源：

    - ``docs/development/step4_api_stability_decision.md``（v1.0 FROZEN）**AS-4**
    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 / DA-3**
    - ``docs/development/step4_api_runtime_decision.md``（v1.0 FROZEN）**DB-3 / DB-4 / DB-6**

职责：把既有 service 与仓储**装配**成一条完整链路，并以 :class:`Runtime`
（``frozen`` dataclass）交付给编排层。::

    raw dict ─▶ EventGateway ─▶ InteractionEngine ─▶ ActionEngine ─▶ PlaybackManager
                    │                  │                  │                │
                    └──────────────────┴──────────────────┴────────────────┘
                                        │
                            DataManager（写）· EventRepository / StatRepository（读）

**为什么需要组合根**（Step 4.3-B-1 硬矛盾与用户裁决）：

    ``api/**`` 既要输出规则产物 ``action``（必须调用引擎），又被 §九 的 AST 守卫
    禁止 ``import`` 引擎；``main.py`` 也不得调用引擎（DB-3）。二者的交集是空集
    ⇒ 引擎装配必须落在**第三个位置**，即 ``app/services/`` 的组合根。
    ``app/api/**`` 只 ``import`` ``services/pipeline.py``。

边界（AS-4）：

- 本模块**只装配、不编排**：不含任何事件处理流程，**不**持播放窗口。
- 本模块是 Web 侧 ``import`` ``ActionEngine`` / ``InteractionEngine`` /
  ``PlaybackManager`` 的模块之一（AS-4 允许的另一处为 ``services/pipeline.py``）；
  ``app/api/**`` 与 ``app/main.py`` 仍**零**引擎 ``import``（守卫不放松）。
- 本模块**零 SQL**：写经 ``DataManager``（唯一写入出口），读经仓储。
- ``on_finished`` **刻意留空**（Step 4.3-B-1 用户裁决「轮询驱动到期」）：
  若把 ``ActionEngine.restore_idle`` 注入回调，``execute()`` 会在**同一次调用内**
  同步排空队列 ⇒ 快照恒为 ``idle``，与 API-2「``state`` 可为 ``playing``」直接矛盾。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.config.settings import Settings
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.repositories.event_repository import EventRepository
from app.repositories.stat_repository import StatRepository
from app.services.action_engine import ActionEngine
from app.services.asset_manager import AssetManager
from app.services.data_manager import DataManager
from app.services.event_gateway import EventGateway
from app.services.interaction_engine import InteractionEngine
from app.services.playback_manager import PlaybackManager
from app.services.rule_loader import RuleLoader

__all__ = ["Runtime", "build_runtime"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Runtime:
    """已装配的运行期依赖集合（**不可变**）。

    拆分前这些引用以私有属性散落在 ``SimulationPipeline`` 里；现将它们收拢为一个
    值对象，使「装配」与「编排」的接缝显式化（AS-4）。字段语义：

    Attributes:
        settings: 运行配置（已 ``ensure_directories()``）。
        database: 已初始化的数据库句柄。
        clock: 单调时钟（单位：秒），供编排层的播放窗口计时使用。
        asset_manager: 唯一素材解析点（P3）。
        playback_manager: 播放链（``on_finished`` 刻意留空，见模块文档）。
        action_engine: 动作执行与状态机（``idle`` / ``playing`` 的唯一 Owner）。
        interaction_engine: 规则匹配（无状态）。
        gateway: 事件网关（``normalize`` 是事件进入系统的唯一入口）。
        data_manager: 写入**唯一出口**（``write_event`` / ``record_action`` /
            ``aggregate_counter``）。
        event_repository: 只读事件仓储（DA-1 读路径）。
        stat_repository: 只读统计仓储（DA-1 读路径）。
        pet_id: 对外主键，由 ``AssetManager.pet_ids()`` 派生（**不硬编码**，红线 C3）。
    """

    settings: Settings
    database: Database
    clock: Callable[[], float]
    asset_manager: AssetManager
    playback_manager: PlaybackManager
    action_engine: ActionEngine
    interaction_engine: InteractionEngine
    gateway: EventGateway
    data_manager: DataManager
    event_repository: EventRepository
    stat_repository: StatRepository
    pet_id: str


def build_runtime(
    settings: Optional[Settings] = None,
    *,
    clock: Optional[Callable[[], float]] = None,
) -> Runtime:
    """装配一条完整链路并返回 :class:`Runtime`。

    装配顺序：``Settings`` → ``Database`` → ``AssetManager`` → ``PlaybackManager``
    → ``ActionEngine`` → ``InteractionEngine`` / ``EventGateway`` →
    ``DataManager`` / 读写仓储 → ``pet_id``（由 ``AssetManager`` 派生）。

    Args:
        settings: 运行配置；``None`` 时使用 ``Settings.default()``（生产路径）。
        clock: 单调时钟（单位：秒）。默认 ``time.monotonic``；测试可注入假时钟。

    Returns:
        已完成装配的 :class:`Runtime`（不可变）。

    .. note::
        本函数是**纯装配**：只做构造与 ``initialize()``，不产生任何事件副作用，
        也不读取 ``events`` / ``counters`` 表（读路径由编排层按需走仓储）。
    """
    cfg = settings or Settings.default()
    cfg.ensure_directories()
    monotonic: Callable[[], float] = clock or time.monotonic

    # -- 存储 / 素材链 ---------------------------------------------------
    database = Database(cfg.database_path, cfg.schema_path)
    database.initialize()
    #: 唯一素材解析点（P3）：其它模块一律向它索取路径 / 时长
    asset_manager = AssetManager(AssetRepository(database), cfg)

    # -- 播放链 ----------------------------------------------------------
    # on_finished **刻意留空**：播放何时结束由编排层按时长判定（见 pipeline._expire_if_due）。
    playback_manager = PlaybackManager(asset_manager)
    action_engine = ActionEngine(asset_manager, playback_port=playback_manager.play)

    # -- 规则链 ----------------------------------------------------------
    # rules.json 的唯一入口是 RuleLoader（本模块不自行解析规则文件）。
    interaction_engine = InteractionEngine(RuleLoader.load())
    gateway = EventGateway()

    # -- 数据链（写 / 读分离，DA-1） --------------------------------------
    data_manager = DataManager(database)
    event_repository = EventRepository(database)
    stat_repository = StatRepository(database)

    return Runtime(
        settings=cfg,
        database=database,
        clock=monotonic,
        asset_manager=asset_manager,
        playback_manager=playback_manager,
        action_engine=action_engine,
        interaction_engine=interaction_engine,
        gateway=gateway,
        data_manager=data_manager,
        event_repository=event_repository,
        stat_repository=stat_repository,
        pet_id=_derive_pet_id(asset_manager),
    )


def _derive_pet_id(asset_manager: AssetManager) -> str:
    """派生对外主键：取 ``AssetManager`` 宠物主键列表中**字典序首个** ``pet_id``。

    主键全集来源是各宠物 ``assets/pets/*/config.json``，由 ``AssetManager``
    **统一构建**（D2）并经其**公开只读接口** ``pet_ids()`` 暴露；
    本模块只**消费**，绝不自行读取配置文件或拼接目录。

    Args:
        asset_manager: 已装配的素材管理器。

    Returns:
        ``pet_id``（Phase 1 为 ``cat_001``）；无任何宠物配置时返回空串
        （下游动作会全部降级，但**进程不得因此崩溃**，PROJECT_RULES 第十一条）。
    """
    try:
        pet_ids = asset_manager.pet_ids()
    except Exception:  # noqa: BLE001 - 索引不可用时退化为空（不崩溃）
        logger.exception("读取 pet 索引失败，按空索引处理")
        return ""
    if not pet_ids:
        logger.warning("未发现任何宠物配置，pet_id 为空：动作将全部降级")
        return ""
    return pet_ids[0]
