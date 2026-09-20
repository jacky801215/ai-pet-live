"""Playback State API —— 播放态快照（API-2）。

契约来源：``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-2**。

- 唯一路由：``GET /api/playback/state``
- 输出：``PlaybackState`` 快照 —— **6 字段，不得增删改名**
- ``POST /api/events/simulate`` 与本路由**同构**返回（共用同一个模型与转换函数）

**禁止返回**（API-2 明示反例）：

    ``action_type`` / ``path`` / ``asset_path`` / ``pet_type`` /
    ``PlaybackCommand`` / ``AssetMetadata`` 原文 / ``thinking`` / ``mood``

职责：**协议转换**（内部快照 → 线协议）+ 调用编排。**不**做规则判断、
**不**解析素材路径（归 ``AssetManager``）、**不**出现 SQL。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api._query import reject_unknown_query
from app.services.pipeline import PlaybackSnapshot, SimulationPipeline, get_pipeline

__all__ = ["router", "PlaybackState", "build_playback_state", "to_asset_url"]

router = APIRouter(prefix="/api/playback", tags=["playback"])


class PlaybackState(BaseModel):
    """播放态快照（API-2 **冻结 6 字段**）。

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
    #: 已解析的对外素材 URL；无动作时为 ``null``（UI 只消费本字段，P3 / UI-6）
    asset_url: str | None = None
    #: 待播队列长度（``>= 0``）
    queue_size: int
    #: 最近一次被受理的 ``event_type``；无则 ``null``
    last_event: str | None = None


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


def build_playback_state(snapshot: PlaybackSnapshot) -> PlaybackState:
    """协议转换：内部快照 → 对外 6 字段快照。

    **内部字段在此被丢弃**：``asset_path`` 被转换为 ``asset_url`` 后**不再出现**，
    内部动作命名（``action_type``）以对外字段 ``action`` 呈现。
    """
    return PlaybackState(
        pet_id=snapshot.pet_id,
        state=snapshot.state,
        action=snapshot.action,
        asset_url=to_asset_url(snapshot.asset_path),
        queue_size=max(int(snapshot.queue_size), 0),
        last_event=snapshot.last_event,
    )


@router.get("/state", response_model=PlaybackState)
def read_playback_state(
    request: Request,
    pipeline: SimulationPipeline = Depends(get_pipeline),
) -> PlaybackState:
    """读取当前播放态快照。

    进程启动后尚未受理任何事件时返回 ``state="idle"`` 快照（API-2）；
    Phase 1 无 push 通道，UI 以轮询本接口获取状态。

    查询参数白名单为**空集**（QP-1）：任何未知 query 一律拒绝 ——
    与 ``/api/stats``、``/api/events/recent`` 同一口径（QP-2 / L-QP-1 落地）。
    """
    reject_unknown_query(request.query_params, frozenset())
    return build_playback_state(pipeline.snapshot())
