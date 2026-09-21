"""API 层包 —— HTTP ↔ JSON 协议转换与调用编排。

契约来源：``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）。

路由**按契约分组**（``step4_api_runtime_decision.md`` DB-4 冻结）::

    events.py     POST /api/events/simulate              （API-1）
    playback.py   GET  /api/playback/state                （API-2）
    stats.py      GET  /api/stats、GET /api/events/recent （API-3）
    ws.py         WS   /api/ws           （WebSocket transport，Phase 2.2-3B-2）

本包**只**做协议转换（HTTP ↔ 基本类型）、参数校验、调用编排、响应组装。
**禁止**：SQL / 业务规则 / 素材路径解析 / 直接 ``import`` 引擎类
（引擎装配在 ``app/services/pipeline.py``；入口 ``app/main.py`` 只负责挂载本包）。

.. note::
   本包**不得**再引入第二个应用入口（``api/app.py``）或第二个编排层
   （``services/api_service.py``）—— 见 DB-3 / DB-4 的「唯一性」要求。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import events, playback, stats, ws

__all__ = ["api_router"]

#: 全量 API 路由（``app/main.py`` 唯一 ``include_router`` 的对象）
api_router = APIRouter()
api_router.include_router(events.router)
api_router.include_router(playback.router)
api_router.include_router(stats.router)
api_router.include_router(ws.router)
