"""Event API —— 事件模拟入口（API-1）。

契约来源：``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-1**
（方案 A），未知顶层字段口径见
``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-7 = A**。

- 唯一路由：``POST /api/events/simulate``
- UI **只发原始事件**（``event_type`` / ``user_id`` / ``user_name`` / ``payload``）
- 后端**补齐** ``pet_id`` / ``action`` / 时间戳 —— 三者都不是请求参数
- 响应与 ``GET /api/playback/state`` **同构**（复用 ``PlaybackState``）

**禁止**（PROJECT_RULES §十四「API 与跨进程边界」）：SQL、业务规则、
素材路径解析、直接调用引擎（引擎装配在 ``app/services/pipeline.py``）。
本模块**只**做协议转换与调用编排。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.playback import PlaybackState, build_playback_state
from app.services.pipeline import SimulationPipeline, get_pipeline

__all__ = ["router", "SimulateEventRequest"]

router = APIRouter(prefix="/api/events", tags=["events"])


class SimulateEventRequest(BaseModel):
    """事件模拟请求。

    允许键**仅此 4 个**；``extra="forbid"`` ⇒ 出现契约外顶层字段一律
    ``400 INVALID_REQUEST``（DA-7 = A：拒绝而非忽略，让契约错误在首轮调用即暴露）。

    ``payload`` 声明为 ``dict | None`` 是**刻意**的：``null`` 必须能被接收后再
    由事件模型拒绝 —— 若用校验器直接拒绝，就会丢掉「缺失补 ``{}``」与
    「显式 ``null`` 拒绝」的差异（``step2_event_schema.md`` §2.4）。
    """

    model_config = ConfigDict(extra="forbid")

    #: 白名单：``gift`` / ``comment`` / ``like`` / ``system``（事件契约 v1.1）
    event_type: str
    #: 缺失补 ``null``；**禁止**补常量（会造成独立用户数坍缩）
    user_id: str | None = None
    #: 缺失补 ``""``；显式 ``null`` 保留
    user_name: str | None = None
    #: 省略补 ``{}``；显式 ``null`` **拒绝**
    payload: dict | None = None


@router.post("/simulate", response_model=PlaybackState)
def simulate_event(
    request: SimulateEventRequest,
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> PlaybackState:
    """模拟产生一条原始事件，注入网关并返回最新播放态快照。

    ``model_dump(exclude_unset=True)`` 保留「**字段缺失**」与「**显式 null**」的差异 ——
    该差异的裁定者是事件模型（``Event.from_dict``），本层**不得**自行补齐或修正
    （补齐逻辑一旦出现两份必然漂移）。

    事件契约校验失败（``EVENT_*``）由 API 层全局异常处理器折叠为
    ``400 INVALID_REQUEST``（API-4）。

    Returns:
        最新 ``PlaybackState`` 快照（与 ``GET /api/playback/state`` 同构）。
    """
    raw_event = request.model_dump(exclude_unset=True)
    return build_playback_state(
        pipeline.simulate(raw_event), pipeline.asset_manager
    )
