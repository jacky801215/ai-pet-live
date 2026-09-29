"""WebSocket transport endpoint（Phase 2.2-3B-2 / 2.2-5 / 2.2-7B-2）—— WS 消息的**唯一**后端入口。

契约来源（均 v1.0 FROZEN）：``phase2_websocket_boundary_decision.md``（WS-1 ~ WS-6）、
``phase2_websocket_event_model_decision.md``（WM-1 ~ WM-6）、
``phase2_websocket_adapter_boundary_decision.md``（WA-1 ~ WA-6）、
``phase2_websocket_runtime_integration_decision.md``（WG-1 ~ WG-6）、
``phase2_websocket_push_boundary_decision.md``（WP-1 ~ WP-6）、
``phase2_websocket_commit_point_decision.md``（WC-1 ~ WC-6）。

流转**单向且固定**（WA-3 / WM-3 / WG-3），并在 commit point 之后回推（WC-4）::

    socket message → transport（api/ws.py）→ platform adapter（格式检查 + normalize）
                    → 内部事件（Event）→ SimulationPipeline.apply_event()（编排内核）
                    → InteractionEngine / ActionEngine / Playback / Runtime State
                    ↓（commit point = apply_event 返回，WC-1 / WC-2）
                    → platform dispatcher（组装 WM-1 envelope）→ websocket.send_json()

边界（Phase 2.2-5 runtime integration 后的口径）：

- **WG-1**：WS 事件进入系统唯一入口 = ``EventGateway.normalize()``（在本模块内只经
  adapter 一扇门；transport **不**自行解析、不拼事件 dict、不 bypass）；
- **WG-2 方案 A 落地**：adapter 消费**组合根共享 gateway**（``pipeline.gateway``）——
  WS 与 HTTP simulate 用同一个 ``EventGateway`` 实例，杜绝双体系漂移；
- **WG-3**：``EventGateway`` 之后的下一跳 = :meth:`SimulationPipeline.apply_event`
  （编排内核，**不重复** normalize）；责任方 = 本 transport 层；**禁止** adapter 调
  pipeline（adapter 只做门卫，本模块是唯一的 transport→编排接线点）；本模块只经
  组合根入口（``get_pipeline`` / ``apply_event``）触达 runtime，**禁止**直调引擎 /
  仓储 / DataManager（「socket 调 services」禁令指绕过编排入口的直调）；
- **WA-4**：非法消息（JSON / envelope / event_type / payload）的 reject + log 在
  adapter 内完成；本端点捕获 :class:`WebSocketAdapterRejectError` 后**消息级拒收**，
  不进入 pipeline（**亦不发送**出站帧），连接继续服务后续消息；
- **WS-5 / WG-4**：``disconnect`` 只记日志、**不发送**任何出站帧；本端点**不调用、
  不复用、不替代** ``refresh``（RF-1 不变）；
- **WP-1 / WP-3 / WP-5 · WC-1 / WC-4 / WC-5（Phase 2.2-7B-2）**：出站推送归
  **transport**——``apply_event()`` **成功返回之后**（commit point，WC-1）由
  :class:`~app.platform.websocket_dispatcher.WebSocketDispatcher` 组装 **WM-1 envelope**
  （恰 4 字段）并 ``send_json``；**失败只 log**（WP-5：不上抛 / 不重试 / 不回滚已提交的
  runtime mutation）；pipeline 异常或 disconnect 时**不发送**；
- **CR-6（idle 到期推送 / F1 = A-1′ / WP-3 v1.1 / WC-3 v1.2）**：连接循环改为**带超时收帧** ——
  用**常驻收帧任务 + ``asyncio.wait(timeout=...)``**（节拍 :data:`STATE_PUSH_TICK_SECONDS`）；
  **到期观察**分支走**既有** :meth:`SimulationPipeline.snapshot` 读路径（其内部即既有到期推进
  ``_expire_if_due()``），与基线比对后**仅在变化时**经 ``send_state_frame`` 推送**状态帧**
  （``{"type": "playback_state", "snapshot": <API-2 七字段>}``）。⇒ 事件帧（WM-1，恰 4 字段）
  **逐字不变**；**不新增**推进实现（无 ``PlaybackTimer`` / ``PlaybackScheduler`` /
  ``StateMachine``）；**不引入** registry / 后台任务 / 跨连接广播（**WP-4 / WP-6 逐字不变**），
  亦**不发送** ping / pong（超时只是**接收超时**）；
- **CR-6 / C1（状态推送语义冻结）**：状态帧**触发集 = 事件受理（event accepted）+ 到期观察
  （expiry observed）** —— 两条路径**共用同一套**「变化才推」口径；**比较基准 = 上一条
  *已成功推送* 的状态帧**（``send_state_frame`` 返回 ``True`` 才前移基线；失败只 log、
  **不重试 / 不回滚**，**WP-5 / WC-5 逐字不变**）。事件帧**不承载**任何 ``PlaybackState``
  字段 ⇒ 状态帧是前端 ``playback`` 切片的**唯一推送来源**；连接建立时**不推首帧**
  （``initial_state_frame = deferred``，初始化仍走既有 HTTP ``/state``）；
- ⚠️ **U-6a 修法（实测驱动）**：初始方案用 ``asyncio.wait_for(receive_text(), timeout)``，
  **实测会丢帧** —— 超时取消在途 ``receive_text()`` 时，已在 ASGI 队列中送达但尚未返回的
  消息被吞掉（20 条丢 1 条）。故改为**不取消在途收帧**：接收任务跨 tick 存活，
  超时**只观察不打断** ⇒ 结构上不存在「取消吞帧」窗口；
- **WA-6 / WS-6 / WG-5 / WG-6 / WP-4 / WP-6**：无 broadcast / room / session / connection
  manager / reconnect / heartbeat / 多客户端——每个连接独立处理，服务端不持有连接集合。
- **MP-1 / MP-2 / MP-3（Phase 3.2-A 用户裁决）**：``?pet_id=<key>`` 走**连接级**
  pet 上下文（方案 B，**不改 WM-1 / Event schema / 数据库 schema**），解析为 per-connection
  runtime + pipeline；无 ``pet_id`` 时沿用默认 pipeline（向后兼容）；非法 key 拒收连接。

写库口径（Phase 2.2-5 裁决）：WS 事件 ``platform="ws"``（:data:`PLATFORM_WS`），
HTTP simulate 仍为 ``"simulator"``（行为不变）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.api.playback import build_playback_state
from app.config.settings import Settings
from app.platform.websocket_adapter import (
    WebSocketAdapter,
    WebSocketAdapterRejectError,
    build_websocket_adapter,
)
from app.platform.websocket_dispatcher import WebSocketDispatcher
from app.services.pipeline import PLATFORM_WS, SimulationPipeline, get_pipeline
from app.services.runtime_factory import build_pipeline_for_pet, known_pet_keys

__all__ = [
    "router",
    "get_ws_adapter",
    "get_ws_dispatcher",
    "get_ws_settings",
]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

#: 进程级无状态 dispatcher（WP-4：单连接阶段无 registry；dispatcher 不含业务状态）
_default_dispatcher = WebSocketDispatcher()

#: **CR-6**（F1 = A-1）：连接空闲时的**到期观察**节拍（秒）——模块级常量，测试可覆盖以固定时序。
#: 仅决定「隔多久看一眼」，**不是**心跳：本循环**不发送** ping / pong（WP-6 逐字不变）。
STATE_PUSH_TICK_SECONDS: float = 0.25


def _read_state_frame(pipeline: SimulationPipeline) -> dict[str, Any]:
    """**CR-6**：读取状态帧载荷 = API-2 的 ``PlaybackState`` **7 字段原样**。

    与 ``GET /api/playback/state`` **同源同构**（复用 :func:`build_playback_state` 与组合根
    注入的只读 ``AssetManager``），杜绝两处口径漂移。

    推进来源 = :meth:`SimulationPipeline.snapshot` —— 其内部即**既有**的到期推进
    (``_expire_if_due()``，CR-3) ⇒ 本模块**不新增**任何推进实现。
    """
    snapshot = pipeline.snapshot()
    return build_playback_state(snapshot, pipeline.asset_manager).model_dump()


def get_ws_adapter(
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> WebSocketAdapter:
    """FastAPI 依赖：websocket adapter（WG-2 方案 A——消费组合根共享 gateway）。

    测试可用 ``app.dependency_overrides[get_ws_adapter]`` 覆盖（transport 级单测），
    或只覆盖 :func:`get_pipeline`（runtime integration 集成测）。
    """
    return build_websocket_adapter(pipeline.gateway)


def get_ws_dispatcher() -> WebSocketDispatcher:
    """FastAPI 依赖：出站推送 dispatcher（WP-1：transport outbound）。

    dispatcher **无业务状态**（仅时钟 + logger，WP-4：单连接阶段无 registry），
    进程级共享即可；测试可用 ``app.dependency_overrides[get_ws_dispatcher]`` 覆盖
    （发送失败策略单测）。
    """
    return _default_dispatcher


def get_ws_settings() -> Settings:
    """FastAPI 依赖：WS 层运行配置（Phase 3.2-A / MP-1）。

    仅用于 **pet 上下文**路径（``?pet_id=``）：判定合法 pet 键、装配 per-pet
    runtime/pipeline。默认 / 旧客户端路径**不消费**本依赖，行为不变。

    测试可用 ``app.dependency_overrides[get_ws_settings]`` 覆盖为隔离配置
    （否则 pet 路径会落到真实 ``Settings.default()``）。
    """
    return Settings.default()


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    pet_id: Optional[str] = Query(
        default=None,
        description="宠物上下文键（pet_id 如 cat_001，或 pet_type 如 cat）；省略则用默认宠物",
    ),
    adapter: WebSocketAdapter = Depends(get_ws_adapter),
    pipeline: SimulationPipeline = Depends(get_pipeline),
    dispatcher: WebSocketDispatcher = Depends(get_ws_dispatcher),
    settings: Settings = Depends(get_ws_settings),
) -> None:
    """接收循环：合法帧 → adapter → 编排内核 → commit → 回推；非法帧拒收；断线只记日志。

    顺序硬约束（Step 2 / WC-4）：**必须先** ``apply_event()`` **成功返回**（commit point），
    **再**出站推送；故 reject 帧 / pipeline 异常 / disconnect 一律**不发送**。

    **CR-6（F1 = A-1）**：循环由「纯阻塞收帧」改为「**带超时收帧**」——
    常驻收帧任务 + ``asyncio.wait(timeout=STATE_PUSH_TICK_SECONDS)``；**超时**分支
    走**既有** ``pipeline.snapshot()`` 读路径（内含既有到期推进），与基线比对后
    **仅在变化时**推 **状态帧**（``{"type": "playback_state", "snapshot": <API-2 七字段>}``）。
    基线在**连接建立时**与**每次事件受理后**同步 ⇒ 空闲但无变化时**零帧**。
    ⚠️ **U-6a**：**不**用 ``asyncio.wait_for``（其超时会取消在途 ``receive_text()``，
    实测丢帧）——改为**不取消**在途收帧。

    Phase 3.2-A（MP-1 / MP-2 / MP-3）：

    - **MP-1**：``?pet_id=<key>`` → 该 key 的 ``Runtime`` / ``SimulationPipeline``；
      缺省（无 query）→ 沿用既有默认 pipeline（**向后兼容**，行为不变）；
      **非法 key** → ``close(1008)`` 拒收连接，**不装配 runtime**、**不建 fallback pet**；
    - **MP-2**：per-connection 装配独立物件图（自有状态机 / 数据库句柄），
      服务端**不持有**「当前宠物」全局态、**不建立** pet registry、**无**后台宠物状态；
    - **MP-3**：聚合计数作用域由 ``build_runtime(pet_id=...)`` 注入 —— 仅显式 pet
      连接写 ``pet_id = <key>``，默认 / 旧路径仍写 ``NULL``（与冻结读路径一致）。
    """
    if pet_id is not None:
        key = pet_id.strip()
        if not key or key not in known_pet_keys(settings):
            # MP-1：非法 / 空 pet 上下文 → 拒收连接（不装配 runtime、不落 fallback pet）
            logger.info("websocket rejected: unknown pet context pet_id=%r", pet_id)
            await websocket.close(code=1008)
            return
        # MP-1 / MP-2：per-connection pet 上下文 → 独立 runtime + 绑定其 gateway 的 adapter
        pipeline = build_pipeline_for_pet(key, settings)
        adapter = build_websocket_adapter(pipeline.gateway)

    await websocket.accept()
    # CR-6：连接建立时取一次基线 —— 「变化才发送」的参照系（未变化 ⇒ 一个帧都不推）
    last_state = _read_state_frame(pipeline)
    # CR-6 / **U-6a 修法**：常驻收帧任务 —— 超时**只观察、不取消在途收帧**。
    # （ ``asyncio.wait_for`` 会在超时取消 ``receive_text()``：已送达但未返回的消息会被
    #   吞掉 —— 实测 20 条丢 1 条。故接收任务跨 tick 存活，结构上消除该窗口。）
    receive_task = asyncio.ensure_future(websocket.receive_text())
    try:
        while True:
            done, _ = await asyncio.wait(
                {receive_task}, timeout=STATE_PUSH_TICK_SECONDS
            )
            if not done:
                # CR-6 / F1 = A-1′：**超时 = 到期观察点** —— 服务端自己走一次既有读路径，
                # 仅当状态**变化**时才推状态帧（不是每 tick 推送 = 无 heartbeat 语义）。
                # CR-6 / C1：比较基准 = **上一条已成功推送**的状态帧 ⇒ **成功才前移**基线
                # （失败只 log、不重试 ⇒ 基线不前移，下个观察点自然重新比对；WP-5 不变）。
                current_state = _read_state_frame(pipeline)
                if current_state != last_state:
                    if await dispatcher.send_state_frame(current_state, websocket):
                        last_state = current_state
                continue
            raw = receive_task.result()  # 在途异常（含 WebSocketDisconnect）在此重新抛出
            receive_task = asyncio.ensure_future(websocket.receive_text())
            try:
                event = adapter.handle(raw)  # WA-3 唯一出口：合法 → 交付 Gateway
            except WebSocketAdapterRejectError:
                # WA-4：reject + log 已在 adapter 内；消息级拒收，**不进入** pipeline、不推送
                continue
            # WG-3：EventGateway 之后的下一跳 = 编排内核（normalize 恰一次，不重复校验）
            pipeline.apply_event(event, platform=PLATFORM_WS)
            # WC-4：commit point（apply_event 返回）之后 → transport 出站推送 WM-1 envelope；
            # WP-5 / WC-5：失败只 log（dispatcher 内部收敛），不影响已提交的 runtime mutation
            await dispatcher.send_event(event, websocket)
            # CR-6 / C1：状态帧触发集 = **事件受理** + 到期观察（**同一套**比较基准）。
            # 事件帧（WM-1）不携带 ``asset_url`` / ``loop`` 等播放字段 ⇒ 此处按同一基准补推状态帧，
            # 使前端 ``playback`` 切片有**唯一**推送来源（仍**不引入** scheduler / timer）。
            current_state = _read_state_frame(pipeline)
            if current_state != last_state:
                if await dispatcher.send_state_frame(current_state, websocket):
                    last_state = current_state
    except WebSocketDisconnect:
        # WS-5：断线策略只设计 connect/disconnect/error——这里只记日志，
        # 不产生**额外**业务事件（零广播 / 零重连 / 零恢复 / 零出站帧）
        logger.info("websocket disconnected: path=/api/ws")
    except Exception:  # HR-1：unexpected runtime exception containment（transport robustness）
        # 非 disconnect 异常（receive_text / apply_event / send_event）在端点层就地收敛，
        # 干净关闭连接；不 reconnect / 不 retry / 不 heartbeat / 不回滚已提交 mutation / 不向客户端发帧。
        logger.warning(
            "websocket endpoint unexpected error, terminating connection: path=/api/ws",
            exc_info=True,
        )
    finally:
        # CR-6：连接结束即回收常驻收帧任务（**不**为取消而丢弃已送达消息 —— 连接已终止）
        if not receive_task.done():
            receive_task.cancel()
