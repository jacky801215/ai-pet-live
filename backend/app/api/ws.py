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
- **MP-1 / MP-2 / MP-3（Phase 3.2-A 用户裁决）**：``?pet_id=<key>`` 走**连接级**
  pet 上下文（方案 B，**不改 WM-1 / Event schema / 数据库 schema**），解析为 per-connection
  runtime + pipeline；无 ``pet_id`` 时沿用默认 pipeline（向后兼容）；非法 key 拒收连接。

写库口径（Phase 2.2-5 裁决）：WS 事件 ``platform="ws"``（:data:`PLATFORM_WS`），
HTTP simulate 仍为 ``"simulator"``（行为不变）。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

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
