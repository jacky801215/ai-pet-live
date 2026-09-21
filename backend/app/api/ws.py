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
- **WA-6 / WS-6 / WG-5 / WG-6 / WP-4 / WP-6**：无 broadcast / room / session / connection
  manager / reconnect / heartbeat / 多客户端——每个连接独立处理，服务端不持有连接集合。

写库口径（Phase 2.2-5 裁决）：WS 事件 ``platform="ws"``（:data:`PLATFORM_WS`），
HTTP simulate 仍为 ``"simulator"``（行为不变）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.platform.websocket_adapter import (
    WebSocketAdapter,
    WebSocketAdapterRejectError,
    build_websocket_adapter,
)
from app.platform.websocket_dispatcher import WebSocketDispatcher
from app.services.pipeline import PLATFORM_WS, SimulationPipeline, get_pipeline

__all__ = ["router", "get_ws_adapter", "get_ws_dispatcher"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

#: 进程级无状态 dispatcher（WP-4：单连接阶段无 registry；dispatcher 不含业务状态）
_default_dispatcher = WebSocketDispatcher()


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


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    adapter: WebSocketAdapter = Depends(get_ws_adapter),
    pipeline: SimulationPipeline = Depends(get_pipeline),
    dispatcher: WebSocketDispatcher = Depends(get_ws_dispatcher),
) -> None:
    """接收循环：合法帧 → adapter → 编排内核 → commit → 回推；非法帧拒收；断线只记日志。

    顺序硬约束（Step 2 / WC-4）：**必须先** ``apply_event()`` **成功返回**（commit point），
    **再**出站推送；故 reject 帧 / pipeline 异常 / disconnect 一律**不发送**。
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
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
