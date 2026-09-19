"""资产数据模型。

本模块只定义数据结构，不包含任何 IO 或业务逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import ASSET_ID_TEMPLATE


def build_asset_id(pet_type: str, action: str) -> str:
    """构造资产唯一标识。

    Args:
        pet_type: 角色类型，如 ``cat``。
        action: 动作名，如 ``heart``。

    Returns:
        形如 ``cat_action_heart`` 的标识符。
    """
    return ASSET_ID_TEMPLATE.format(pet_type=pet_type, action=action)


@dataclass(frozen=True)
class AssetRecord:
    """数据库 ``assets`` 表中的一行。"""

    pet_type: str
    action: str
    #: 相对项目根目录的素材路径，如 assets/pets/cat/actions/heart/heart.mp4
    path: str
    #: 时长（毫秒）
    duration: int
    id: int | None = None

    @property
    def asset_id(self) -> str:
        """资产唯一标识。"""
        return build_asset_id(self.pet_type, self.action)


@dataclass(frozen=True)
class AssetMetadata:
    """对外输出的资产元数据。

    ``to_dict()`` 的输出结构由 Step 1 指令约定：
        {"asset_id": ..., "asset_path": ..., "duration": ...}
    """

    asset_id: str
    pet_type: str
    action: str
    #: 相对路径（对外暴露）
    asset_path: str
    #: 绝对路径（内部校验用，不对外输出）
    absolute_path: str
    #: 时长（毫秒）
    duration: int

    def to_dict(self) -> dict[str, Any]:
        """按对外契约序列化（仅 3 个约定字段）。"""
        return {
            "asset_id": self.asset_id,
            "asset_path": self.asset_path,
            "duration": self.duration,
        }

    def to_detail_dict(self) -> dict[str, Any]:
        """序列化完整信息（供 API 层调试使用）。"""
        return {
            "asset_id": self.asset_id,
            "pet_type": self.pet_type,
            "action": self.action,
            "asset_path": self.asset_path,
            "duration": self.duration,
        }
