"""Playback State API —— 播放态快照（API-2）。

契约来源：``docs/development/step4_api_contract_decision.md``（**v1.1** FROZEN）**API-2**。

- 唯一路由：``GET /api/playback/state``
- 输出：``PlaybackState`` 快照 —— **7 字段，不得增删改名**（**CR-1** 增量 + ``loop``）
- ``POST /api/events/simulate`` 与本路由**同构**返回（共用同一个模型与转换函数）

**禁止返回**（API-2 明示反例）：

    ``action_type`` / ``path`` / ``asset_path`` / ``pet_type`` /
    ``PlaybackCommand`` / ``AssetMetadata`` 原文 / ``thinking`` / ``mood``

职责：**协议转换**（内部快照 → 线协议）+ 调用编排。**不**做规则判断、
**不**自行解析素材路径（素材解析与循环判定一律归 ``AssetManager``，本层只把组合根
注入的只读依赖当作不透明对象调用其公开方法）、**不**出现 SQL。

.. note::
    **CR-1（待机循环）**：待机态（快照 ``asset_path`` 为空）时向 ``AssetManager``
    取该宠物的**待机素材**，并按动作取**循环值** —— 判定全归 ``AssetManager``（P1），
    本层只做协议转换，前端只消费。裁决见 ``docs/change_request/cr-1_idle_loop.md``。
    **素材问题不得中断请求**（红线 C4）：未配置宠物 / 未登记 / 文件缺失一律降级为「无素材」。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api._query import reject_unknown_query
from app.services.pipeline import PlaybackSnapshot, SimulationPipeline, get_pipeline

__all__ = ["router", "PlaybackState", "build_playback_state", "to_asset_url"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playback", tags=["playback"])


class PlaybackState(BaseModel):
    """播放态快照（API-2 **冻结 7 字段**）。

    ``extra="forbid"`` 是防御性的：任何内部字段（``action_type`` /
    ``asset_path`` / ``pet_type`` …）一旦混入，会立即失败而不是静默外泄。
    """

    model_config = ConfigDict(extra="forbid")

    #: 对外主键（与 ``AssetManager`` / ``PetContext`` 一致）
    pet_id: str
    #: **仅** ``"idle"`` | ``"playing"``
    state: str
    #: 当前动作名；``idle`` 时为 ``null``（不内建动作枚举，UI-3）
    action: str | None = None
    #: 已解析的对外素材 URL；**待机时 = 该宠物的待机素材**，素材不可解析时为 ``null``
    #: （UI 只消费本字段，P3 / UI-6）
    asset_url: str | None = None
    #: 待播队列长度（``>= 0``）
    queue_size: int
    #: 最近一次被受理的 ``event_type``；无则 ``null``
    last_event: str | None = None
    #: **CR-1**：当前媒体是否循环播放 —— 待机 ``true``、其余动作 ``false``；
    #: 判定归 ``AssetManager``，前端只消费（FP-3 v1.2）
    loop: bool = False


def to_asset_url(asset_path: str | None) -> str | None:
    """素材**相对路径** → 对外 URL（DA-5 冻结口径：``"/" + asset_path``）。

    ``asset_path`` 形如 ``assets/pets/{pet_type}/actions/{action}/{action}.mp4``，
    已自带 ``assets/pets/`` 前缀，因此结果与 ``constants.ASSET_URL_PREFIX``
    （``"/assets/pets"``）**天然自洽**::

        assets/pets/cat/actions/heart/heart.mp4
          -> /assets/pets/cat/actions/heart/heart.mp4

    UI **永不**拼接路径（UI-6）；URL 一律由后端生成。
    """
    if not asset_path:
        return None
    return "/" + str(asset_path).replace("\\", "/").lstrip("/")


def build_playback_state(
    snapshot: PlaybackSnapshot, assets: Any = None
) -> PlaybackState:
    """协议转换：内部快照 → 对外 7 字段快照。

    **内部字段在此被丢弃**：``asset_path`` 被转换为 ``asset_url`` 后**不再出现**，
    内部动作命名（``action_type``）以对外字段 ``action`` 呈现。

    Args:
        snapshot: 内部播放态快照（``PlaybackSnapshot``）。
        assets: 组合根注入的 ``AssetManager`` **只读**依赖（**CR-1**）。本层只调用其
            公开只读方法（``resolve_playback_asset`` / ``is_looping``），**不**触碰私有成员、
            **不**自行判断动作语义。``None``（不经组合根的历史直调路径）退化为改动前行为：
            ``asset_url`` 沿用快照路径、``loop=False``。

    Returns:
        对外 ``PlaybackState``（API-2 七字段）。
    """
    asset_path = snapshot.asset_path
    # ``is_looping`` 是纯动作判定（不触库、不解析路径），与素材可用性无关 ⇒ 先算
    loop = bool(assets.is_looping(snapshot.action)) if assets is not None else False

    if asset_path is None and assets is not None and snapshot.pet_id:
        # 待机态（无动作）→ 由素材层回落该宠物的待机素材。
        # **素材问题不得中断请求**（红线 C4，与 ``playback_state.find_asset_metadata`` 同口径）：
        # 未配置宠物（pet_id 为空）/ 未登记 / 文件缺失时一律降级为「无素材」。
        try:
            asset_path = assets.resolve_playback_asset(
                snapshot.pet_id, snapshot.action
            )
        except Exception:  # noqa: BLE001 - 素材问题不得中断请求
            logger.warning(
                "待机素材解析失败（按无素材处理）: pet_id=%r", snapshot.pet_id
            )
            asset_path = None

    return PlaybackState(
        pet_id=snapshot.pet_id,
        state=snapshot.state,
        action=snapshot.action,
        asset_url=to_asset_url(asset_path),
        queue_size=max(int(snapshot.queue_size), 0),
        last_event=snapshot.last_event,
        loop=loop,
    )


@router.get("/state", response_model=PlaybackState)
def read_playback_state(
    request: Request,
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> PlaybackState:
    """读取当前播放态快照。

    进程启动后尚未受理任何事件时返回 ``state="idle"`` 快照（API-2）——
    **CR-1** 起该快照携带该宠物的**待机素材**且 ``loop=true``；
    Phase 1 无 push 通道，UI 以轮询本接口获取状态。

    查询参数白名单为**空集**（QP-1）：任何未知 query 一律拒绝 ——
    与 ``/api/stats``、``/api/events/recent`` 同一口径（QP-2 / L-QP-1 落地）。
    """
    reject_unknown_query(request.query_params, frozenset())
    return build_playback_state(pipeline.snapshot(), pipeline.asset_manager)
