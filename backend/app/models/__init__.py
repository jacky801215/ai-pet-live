"""数据模型包。

只导出数据结构定义与契约常量，不包含 IO 或业务逻辑。
"""

from __future__ import annotations

from app.models.asset import AssetMetadata, AssetRecord, build_asset_id
from app.models.event import ALLOWED_EVENT_TYPES, TOP_LEVEL_FIELDS, Event

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "TOP_LEVEL_FIELDS",
    "AssetMetadata",
    "AssetRecord",
    "Event",
    "build_asset_id",
]
