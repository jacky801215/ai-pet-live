"""WebSocket transport endpoint（Phase 2.2-3B-2 / 2.2-5）—— WS 消息的**唯一**后端入口。

契约来源（均 v1.0 FROZEN）：``phase2_websocket_boundary_decision.md``（WS-1 ~ WS-6）、
``phase2_websocket_event_model_decision.md``（WM-1 ~ WM-6）、
``phase2_websocket_adapter_boundary_decision.md``（WA-1 ~ WA-6）、
``phase2_websocket_runtime_integration_decision.md``（WG-1 ~ WG-6）。

流转**单向且固定**（WA-3 / WM-3 / WG-3）::

    socket message → transport（api/ws.py）→ platform adapter（格式检查 + normalize）
                    → 内部事件（Event）→ SimulationPipeline.apply_event()（编排内核）
                    → InteractionEngine / ActionEngine / Playback / Runtime State

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
  不进入 pipeline，连接继续服务后续消息；
- **WS-5 / WG-4**：``disconnect`` 只记日志；push-to-frontend channel **不在本步**
  （FD 修订须授权）；本端点**不调用、不复用、不替代** ``refresh``（RF-1 不变）；
- **WA-6 / WS-6 / WG-5 / WG-6**：无 broadcast / room / session / connection manager /
  reconnect / heartbeat / 多客户端——每个连接独立处理，服务端不持有连接集合。

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
from app.services.pipeline import PLATFORM_WS, SimulationPipeline, get_pipeline

__all__ = ["router", "get_ws_adapter"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


def get_ws_adapter(
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> WebSocketAdapter:
    """FastAPI 依赖：websocket adapter（WG-2 方案 A——消费组合根共享 gateway）。

    测试可用 ``app.dependency_overrides[get_ws_adapter]`` 覆盖（transport 级单测），
    或只覆盖 :func:`get_pipeline`（runtime integration 集成测）。
    """
    return build_websocket_adapter(pipeline.gateway)


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    adapter: WebSocketAdapter = Depends(get_ws_adapter),
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> None:
    """接收循环：合法帧 → adapter → 编排内核；非法帧消息级拒收；断线只记日志。"""
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event = adapter.handle(raw)  # WA-3 唯一出口：合法 → 交付 Gateway
            except WebSocketAdapterRejectError:
                # WA-4：reject + log 已在 adapter 内；消息级拒收，**不进入** pipeline
                continue
            # WG-3：EventGateway 之后的下一跳 = 编排内核（normalize 恰一次，不重复校验）；
            # 快照返回值在此刻意不消费——push-to-frontend 归 FD push channel（WG-4，须授权）
            pipeline.apply_event(event, platform=PLATFORM_WS)
    except WebSocketDisconnect:
        # WS-5：断线策略只设计 connect/disconnect/error——这里只记日志，
        # 不产生**额外**业务事件（零广播 / 零重连 / 零恢复）
        logger.info("websocket disconnected: path=/api/ws")
