"""播放窗口与播放态快照 —— **纯值对象 / 纯时间逻辑**（AS-4 拆分模块 ②）。

契约来源：

    - ``docs/development/step4_api_stability_decision.md``（v1.0 FROZEN）**AS-4**
    - ``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-2**

本模块回答三个问题，且**只**回答这三个：

    1. 「播放态快照长什么样」—— :class:`PlaybackSnapshot`（API-2 六字段的内部形态）；
    2. 「当前这条动作播完了没有」—— :class:`PlaybackClock`（**轮询驱动到期**的计时器）；
    3. 「引擎 / 播放指令的**只读遥测**怎么读」—— :func:`engine_state` /
       :func:`pending_queue` / :func:`read_action_name`。

边界（AS-4 硬约束）：

- **零 service 依赖**：本模块**禁止** ``import`` 任何 ``app.services.*`` /
  仓储 / 数据库 —— 只有常量、一个 ``frozen`` dataclass、一个纯时间对象，
  以及与第 3 条同类的**纯函数**（零 import、仅 ``getattr`` 只读、不抛异常、不写入）。
- **不推进状态机**：``idle`` / ``playing`` 的 Owner 始终是 ``ActionEngine``。
  本模块只提供「到点了吗」的判定；**何时**调用 ``restore_idle`` 由编排层
  （``app/services/pipeline.py``）决定 —— :class:`PlaybackClock` **不得**回调引擎
  （AS-4：保持「轮询驱动到期」裁决）。

.. note::
    **第 3 条是 Phase 3.2-A1 的授权增量**（用户裁决 **Option A：先腾挪、再迁移**）：
    ``pipeline.py`` 已达 AS-4 上限（299 行 / 余量 **+0**），而后续步骤须为其新增
    显式构造参数；故把三个**只读遥测投影**等价迁入本模块以腾出行数预算。
    三者原本就是 ``getattr(…)`` 形式的**纯函数、不依赖任何 service**，迁移**零行为变化**；
    其只读约束的准绳仍是 ``PROJECT_RULES`` §十四
    ``### FastAPI Runtime Boundary``（只读遥测**必须**经 ``getattr(…, 默认值)``）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# 常量（AS-4：自 ``pipeline.py`` 迁入本模块）
# ---------------------------------------------------------------------------
STATE_IDLE: str = "idle"
STATE_PLAYING: str = "playing"

#: 素材元数据不可用时使用的兜底播放窗口（毫秒）
DEFAULT_DURATION_MS: int = 1000

#: 单次快照最多推进的播放步数。快速路径下队列最多 3 条，
#: 本上限仅为「异常状态下不得死循环」的防御（PROJECT_RULES 第十一条）。
MAX_EXPIRY_STEPS: int = 64

__all__ = [
    "DEFAULT_DURATION_MS",
    "MAX_EXPIRY_STEPS",
    "STATE_IDLE",
    "STATE_PLAYING",
    "PlaybackClock",
    "PlaybackSnapshot",
    "engine_state",
    "pending_queue",
    "read_action_name",
]


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


class PlaybackClock:
    """播放窗口计时器（**轮询驱动到期**，Step 4.3-B-1 用户裁决）。

    只做一件事：记住「当前这条动作播到什么时候」，并回答「到点了吗」。
    它**不**知道播放链的存在，也**不**调用任何引擎 —— 到点后的推进由编排层负责。

    语义（与拆分前 ``pipeline._playing_until`` 逐条等价）：

        - ``arm(duration_s)``：窗口到期时刻 = **当前时刻 + 时长**；
        - ``is_due()``：窗口**存在**（已 arm 且未 disarm）**且** ``now >= deadline``；
        - ``disarm()``：清空窗口（幂等）；
        - ``deadline()``：只读返回到期时刻；无窗口时 ``None``。

    Args:
        clock: 单调时钟（单位：秒）。默认 ``time.monotonic``；
            测试可注入假时钟，以确定性验证播放窗口的到期回落。
    """

    def __init__(self, clock: Optional[Callable[[], float]] = None) -> None:
        self._clock: Callable[[], float] = clock or time.monotonic
        #: 当前动作的播放到期时刻（单调时钟秒）；``None`` = 无进行中的播放窗口
        self._playing_until: Optional[float] = None

    def arm(self, duration_s: float) -> None:
        """开始一个 ``duration_s`` 秒的播放窗口（覆盖既有窗口）。"""
        self._playing_until = self._clock() + duration_s

    def disarm(self) -> None:
        """清空窗口（无进行中的播放）。幂等：重复调用无副作用。"""
        self._playing_until = None

    def is_due(self) -> bool:
        """窗口是否存在**且**已到期（``now >= deadline``）。"""
        return self._playing_until is not None and self._clock() >= self._playing_until

    def deadline(self) -> Optional[float]:
        """当前窗口的到期时刻（单调时钟秒）；无窗口时 ``None``。"""
        return self._playing_until


# ---------------------------------------------------------------------------
# 只读遥测投影（Phase 3.2-A1 行数预算腾挪：自 ``pipeline.py`` **等价迁入**）
# ---------------------------------------------------------------------------
# 约束（``PROJECT_RULES`` §十四 ``### FastAPI Runtime Boundary``）：对 ``ActionEngine``
# 的 ``_state`` / ``_pending`` 读取**仅限**「只读遥测」，且**必须**经
# ``getattr(…, 默认值)`` —— 不抛异常、不写入、不改动队列、不新增引擎公开方法。


def engine_state(engine: Any) -> str:
    """读状态机当前状态（只读遥测）：Owner 始终是 ``ActionEngine``（P6）。"""
    state = getattr(engine, "_state", STATE_IDLE)
    return state if state in (STATE_IDLE, STATE_PLAYING) else STATE_IDLE


def pending_queue(engine: Any) -> list:
    """读待播队列快照（只读遥测）：``_pending`` 已被声明「仅供测试与只读查看」。"""
    pending = getattr(engine, "_pending", None)
    if pending is None:
        return []
    try:
        return list(pending)
    except TypeError:  # pragma: no cover - 防御：不可迭代即视为空队列
        return []


def read_action_name(command: Any) -> Optional[str]:
    """从播放指令读取动作名（非空 ``str`` 才算有效）。"""
    action = getattr(command, "action_type", None)
    return action if isinstance(action, str) and action else None
