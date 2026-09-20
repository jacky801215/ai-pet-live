"""Query 参数契约 —— 只读端点查询参数白名单的**唯一**落地 helper。

契约来源：``docs/development/step4_api_query_boundary_decision.md``（v1.0 FROZEN）
**QP-1 / QP-2 / QP-4**（``step4_api_stability_decision.md`` **AS-D1** 的落地项 L-QP-1）。

职责**仅此一项**：判定「请求的查询参数是否都在调用方给定的白名单内」，
白名单之外 ⇒ 抛 :class:`InvalidRequestError`，由 ``app/main.py`` 的全局
异常处理器按既有折叠表归并为 ``400`` + 统一业务码（**错误码集合不变**）。

**禁止**（本模块边界，AS-D1 / §九 分层）：

- ❌ ``import`` 任何 service / repository；
- ❌ 访问数据库或出现 SQL；
- ❌ 业务判断 —— **不做任何**「哪些参数该被允许」的决定，白名单由各路由传入；
- ❌ 新增错误码、静默忽略未知参数、按默认值纠偏。
"""

from __future__ import annotations

from starlette.datastructures import QueryParams

from app.core.exceptions import InvalidRequestError

__all__ = ["reject_unknown_query"]


def reject_unknown_query(
    query_params: QueryParams, allowed_keys: frozenset[str]
) -> None:
    """未知查询参数一律拒绝（QP-2：三个只读端点**同一**口径，禁静默忽略）。

    Args:
        query_params: 请求的查询参数（即 ``request.query_params``）。
        allowed_keys: 该路由**允许**的参数名白名单，
            如 ``frozenset({"limit"})``；无参数路由传 ``frozenset()``。

    Raises:
        InvalidRequestError: 存在白名单之外的参数名
            （由 ``app/main.py`` 折叠为 ``400`` + 统一业务码）。
    """
    unknown = sorted(set(query_params.keys()) - allowed_keys)
    if unknown:
        raise InvalidRequestError(
            f"出现未定义查询参数: {unknown}；只允许 {sorted(allowed_keys)}",
            unknown_params=unknown,
            allowed_params=sorted(allowed_keys),
        )
