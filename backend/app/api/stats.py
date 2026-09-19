"""Data Query API —— 只读统计与事件追溯（API-3）。

契约来源：``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-3**；
读路径归属见 ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 = B**。

- ``GET /api/stats`` → ``{"events": {...}, "actions": {...}, "total": int}``
- ``GET /api/events/recent?limit=20`` → ``{"items": [...], "count": int}``

**禁止**：

- ❌ API 层直接 SQL / 持有 ``sqlite3`` 连接 / 绕过数据层 —— 读路径**只**经仓储；
- ❌ 任何写操作（写路径是 Event API，唯一出口是 ``DataManager``）；
- ❌ 未知查询参数静默忽略（与 DA-7 同口径，见 ``_reject_unknown_query``）。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.exceptions import InvalidRequestError
from app.core.logging_config import get_logger
from app.services.pipeline import SimulationPipeline, get_pipeline

__all__ = ["router", "StatsResponse", "EventItem", "RecentEventsResponse"]

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["data"])

#: ``limit`` 默认值与边界（API-3 冻结：``1..200``）
DEFAULT_LIMIT: int = 20
MIN_LIMIT: int = 1
MAX_LIMIT: int = 200

#: 各路由允许的查询参数（其余一律拒绝）
_STATS_QUERY_KEYS: frozenset[str] = frozenset()
_RECENT_QUERY_KEYS: frozenset[str] = frozenset({"limit"})


class StatsResponse(BaseModel):
    """互动统计（``phase1_design.md`` §4.4 逐字一致）。

    ``events`` / ``actions`` 分别对应 ``interactions.stat_type ∈ {event, action}``（D6）；
    ``total`` 为**事件计数之和**（动作是事件的派生结果，不重复计入）。
    """

    events: dict[str, int]
    actions: dict[str, int]
    total: int


class EventItem(BaseModel):
    """事件明细项（API-3 **冻结 9 字段**）。

    ``payload`` 在响应中为**对象** —— 库内是 JSON 字符串（D1），
    反序列化由本层完成（API-3 明示）。
    """

    id: int
    event_type: str
    user_id: str | None = None
    user_name: str | None = None
    pet_id: str | None = None
    action_name: str | None = None
    platform: str | None = None
    payload: dict
    created_at: str | None = None


class RecentEventsResponse(BaseModel):
    """最近事件列表（``count`` = ``items`` 实际条数，可能小于请求的 ``limit``）。"""

    items: list[EventItem]
    count: int


def _reject_unknown_query(request: Request, allowed: frozenset[str]) -> None:
    """未知查询参数一律拒绝 ⇒ ``400 INVALID_REQUEST``。

    口径与 DA-7（未知顶层请求字段拒绝）**统一**：拒绝比忽略更容易暴露契约错误，
    笔误不会静默通过（``4.3-B-0/DB-5`` 残留项在本 Step 落定）。
    """
    unknown = sorted(set(request.query_params.keys()) - allowed)
    if unknown:
        raise InvalidRequestError(
            f"出现未定义查询参数: {unknown}；只允许 {sorted(allowed)}",
            unknown_params=unknown,
            allowed_params=sorted(allowed),
        )


def _decode_payload(raw: object) -> dict:
    """库内 JSON 字符串 → 对象（D1：库内保持字符串，反序列化在 API 层）。

    异常数据（``NULL`` / 非字符串 / 非法 JSON / 非对象）一律回落 ``{}`` 并记警告 ——
    单行脏数据**不得**让整个列表接口失败（红线 C4 同理）。
    """
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("events.payload 不是合法 JSON，按空对象返回")
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _to_event_item(row: dict) -> EventItem:
    """数据行（``dict``）→ 对外事件项（字段集由模型冻结，多余键无法外泄）。"""
    return EventItem(
        id=int(row.get("id") or 0),
        event_type=str(row.get("event_type") or ""),
        user_id=row.get("user_id"),
        user_name=row.get("user_name"),
        pet_id=row.get("pet_id"),
        action_name=row.get("action_name"),
        platform=row.get("platform"),
        payload=_decode_payload(row.get("payload")),
        created_at=row.get("created_at"),
    )


@router.get("/stats", response_model=StatsResponse)
def read_stats(
    request: Request,
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> StatsResponse:
    """读取互动统计（只读；数据来自 ``interactions`` 聚合行，D6）。"""
    _reject_unknown_query(request, _STATS_QUERY_KEYS)
    return StatsResponse(**pipeline.stat_repository.stats())


@router.get("/events/recent", response_model=RecentEventsResponse)
def read_recent_events(
    request: Request,
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=MIN_LIMIT,
        le=MAX_LIMIT,
        description="返回条数上限（1..200，默认 20）",
    ),
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> RecentEventsResponse:
    """查询最近事件明细（只读）。

    排序 ``created_at DESC, id DESC``（API-3 冻结，同秒内按 ``id`` 兜底）；
    ``limit`` 越界（``<1`` / ``>200`` / 非整数）⇒ ``400 INVALID_REQUEST``。
    """
    _reject_unknown_query(request, _RECENT_QUERY_KEYS)
    rows = pipeline.event_repository.list_recent(limit)
    items = [_to_event_item(row) for row in rows]
    return RecentEventsResponse(items=items, count=len(items))
