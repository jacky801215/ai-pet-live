"""Data Query API —— 只读统计与事件追溯（API-3）。

契约来源：``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-3**；
读路径归属见 ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 = B**；
查询参数边界见 ``docs/development/step4_api_query_boundary_decision.md``（v1.0 FROZEN）的 **CR-1**（新铸 **QP-6**）；
pet 作用域语义见 ``docs/development/phase3_pet_scoped_http_api_decision.md``（v1.0 FROZEN）**MB-2 / MB-3 / MB-4**。

- ``GET /api/stats`` → ``{"events": {...}, "actions": {...}, "total": int}``
- ``GET /api/stats?pet_id=<key>`` → 该宠物的 **canonical 桶**（CR-1 / QP-6）
- ``GET /api/events/recent?limit=20`` → ``{"items": [...], "count": int}``
- ``GET /api/events/recent?limit=20&pet_id=<key>`` → 仅该宠物的行（CR-1 / QP-6）

**禁止**：

- ❌ API 层直接 SQL / 持有 ``sqlite3`` 连接 / 绕过数据层 —— 读路径**只**经仓储；
- ❌ 任何写操作（写路径是 Event API，唯一出口是 ``DataManager``）；
- ❌ 未知查询参数静默忽略（与 DA-7 同口径，见 ``app/api/_query.py``，QP-2 三端点统一）；
- ❌ 在 query 校验里承载业务判断（QP-4）—— 本层只做白名单比对；pet 作用域语义交由
  ``services/pet_context.py`` 与冻结的合法键集 ``known_pet_keys`` 决定。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api._query import reject_unknown_query
from app.api.ws import get_ws_settings
from app.config.settings import Settings
from app.core.exceptions import InvalidRequestError
from app.core.logging_config import get_logger
from app.services.pet_context import normalize_pet_key
from app.services.pipeline import SimulationPipeline, get_pipeline
from app.services.runtime_factory import known_pet_keys

__all__ = ["router", "StatsResponse", "EventItem", "RecentEventsResponse"]

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["data"])

#: ``limit`` 默认值与边界（API-3 冻结：``1..200``）
DEFAULT_LIMIT: int = 20
MIN_LIMIT: int = 1
MAX_LIMIT: int = 200


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


def _resolve_read_pet_scope(raw: str | None, settings: Settings) -> str | None:
    """把 ``?pet_id=`` 的原始值折算为**读侧 canonical 作用域键**（CR-1 / QP-6）。

    与 ``api/ws.py`` 的 pet 上下文判定**同一口径**（``pet_id.strip()`` +
    ``known_pet_keys(settings)`` 成员判定）—— 本层只**引用**冻结的合法键集，
    **不自行定义**任何新的合法集或业务规则（QP-4：「query 校验只做白名单比对」）。

    Args:
        raw: 查询参数原始值；``None`` = 未提供该参数。
        settings: 合法宠物键的来源配置（P-3：经 ``get_ws_settings`` 依赖注入）。

    Returns:
        ``None``（未提供 ⇒ 默认作用域，A2=W / A3=S-1），或该宠物 **canonical** 键。

    Raises:
        InvalidRequestError: 提供了参数却为空 / 不在合法键集内 / 合法但无 canonical 映射
            —— 由 ``app/main.py`` 全局处理器折为 ``400 INVALID_REQUEST``
            （**不新增错误码**，AS-1；亦**不**降级为默认作用域，fail-closed）。
    """
    if raw is None:
        return None

    legal_keys = known_pet_keys(settings)
    key = raw.strip()
    if not key or key not in legal_keys:
        raise InvalidRequestError(
            f"未知 pet 上下文: pet_id={raw!r}；只允许 {legal_keys}",
            pet_id=raw,
            known_pet_keys=legal_keys,
        )

    canonical = normalize_pet_key(key)
    if canonical is None:
        # 合法键却取不到 canonical 映射 ⇒ 视为非法（不静默降级到默认作用域）
        raise InvalidRequestError(
            f"pet 上下文缺少 canonical 映射: pet_id={raw!r}",
            pet_id=raw,
            known_pet_keys=legal_keys,
        )
    return canonical


@router.get("/stats", response_model=StatsResponse)
def read_stats(
    request: Request,
    pet_id: str | None = Query(
        default=None,
        description="宠物上下文键（canonical 如 cat_001，或别名如 cat）；省略则读默认作用域",
    ),
    settings: Settings = Depends(get_ws_settings),
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> StatsResponse:
    """读取互动统计（只读；数据来自 ``interactions`` 聚合行，D6）。

    ``?pet_id=<key>``（CR-1 / QP-6）：读该宠物的 **canonical 桶**；
    省略 ⇒ 读 ``pet_id IS NULL`` 桶（默认作用域，A2=W / A3=S-1，行为**逐字不变**）。
    """
    reject_unknown_query(request.query_params, frozenset({"pet_id"}))
    scope = _resolve_read_pet_scope(pet_id, settings)
    return StatsResponse(**pipeline.stat_repository.stats(scope))


@router.get("/events/recent", response_model=RecentEventsResponse)
def read_recent_events(
    request: Request,
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=MIN_LIMIT,
        le=MAX_LIMIT,
        description="返回条数上限（1..200，默认 20）",
    ),
    pet_id: str | None = Query(
        default=None,
        description="宠物上下文键（canonical 如 cat_001，或别名如 cat）；省略则不按宠物筛选",
    ),
    settings: Settings = Depends(get_ws_settings),
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> RecentEventsResponse:
    """查询最近事件明细（只读）。

    排序 ``created_at DESC, id DESC``（API-3 冻结，同秒内按 ``id`` 兜底）；
    ``limit`` 越界（``<1`` / ``>200`` / 非整数）⇒ ``400 INVALID_REQUEST``。

    ``?pet_id=<key>``（CR-1 / QP-6）：仅返回该 **canonical 键** 的行；
    省略 ⇒ 维持原有**全表**口径（行为**逐字不变**）。
    """
    reject_unknown_query(request.query_params, frozenset({"limit", "pet_id"}))
    scope = _resolve_read_pet_scope(pet_id, settings)
    rows = pipeline.event_repository.list_recent(limit, scope)
    items = [_to_event_item(row) for row in rows]
    return RecentEventsResponse(items=items, count=len(items))
