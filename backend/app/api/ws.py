"""WebSocket transport endpoint（Phase 2.2-3B-2）—— WS 消息的**唯一**后端入口。

契约来源（均 v1.0 FROZEN）：``phase2_websocket_boundary_decision.md``（WS-1 ~ WS-6）、
``phase2_websocket_event_model_decision.md``（WM-1 ~ WM-6）、
``phase2_websocket_adapter_boundary_decision.md``（WA-1 ~ WA-6）。

流转**单向且固定**（WA-3 / WM-3）::

    socket message → 本端点（transport）→ platform adapter（格式检查）
                    → EventGateway.normalize() → 内部事件

边界（本端点是**门卫的门卫**，不是业务层）：

- **只做 transport wiring**：接收文本帧 → 转交 adapter → 丢弃 normalize 返回值
  （事件进入动作链 = ``pipeline.simulate`` 路径的职责，属后续步，须新决策文档授权；
  本步与 WS-3 一致——推送通道**不**触发 refresh、**不**写库、**不**执行动作）；
- **WA-4**：非法消息（JSON / envelope / event_type / payload）的 reject + log 在
  adapter 内完成；本端点捕获 :class:`WebSocketAdapterRejectError` 后**消息级拒收**，
  连接继续服务后续消息；
- **WS-5**：``disconnect`` 只记日志——不产生业务事件、无重连/心跳/恢复；
- **WA-6 / WS-6**：无 broadcast / room / session / connection manager——每个
  websocket 连接独立处理，服务端**不**持有连接集合、**不**向任何其他连接发送数据。

adapter 来源：platform 层工厂 :func:`build_websocket_adapter`（api 层**禁** import
引擎；``EventGateway`` 引用被 WA-3 白名单收敛在 platform 层内）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.platform.websocket_adapter import (
    WebSocketAdapter,
    WebSocketAdapterRejectError,
    build_websocket_adapter,
)

__all__ = ["router", "get_ws_adapter"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


def get_ws_adapter() -> WebSocketAdapter:
    """FastAPI 依赖：websocket adapter（platform 层工厂提供，测试可覆盖）。"""
    return build_websocket_adapter()


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    adapter: WebSocketAdapter = Depends(get_ws_adapter),
) -> None:
    """接收循环：每条文本帧原样转交 adapter；非法帧消息级拒收；断线只记日志。"""
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                adapter.handle(raw)  # 返回的内部事件在本步刻意不消费（见模块 docstring）
            except WebSocketAdapterRejectError:
                # WA-4：reject + log 已在 adapter 内；消息级拒收，连接继续
                continue
    except WebSocketDisconnect:
        # WS-5：断线策略只设计 connect/disconnect/error——这里只记日志，
        # 不产生业务事件（零写库 / 零 simulate / 零广播）
        logger.info("websocket disconnected: path=/api/ws")
