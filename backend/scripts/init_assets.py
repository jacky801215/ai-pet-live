"""初始化资产元数据。

用途：
    将 assets/pets 下的动作素材登记到 SQLite，供 AssetManager 查询。

用法：
    cd backend
    python -m scripts.init_assets            # 初始化默认（cat）
    python -m scripts.init_assets --all      # 初始化 cat/dog/panda
    python -m scripts.init_assets --reset    # 先清空再写入

设计说明：
    - 幂等：重复执行不会产生重复记录（依赖 UNIQUE(pet_type, action)）
    - 只登记元数据，不复制/修改素材文件
    - **duration 一律由 ffprobe 从素材文件真实读取**（Step 1.1），
      本脚本不再写死任何时长，也不自行调用 ffprobe ——
      统一走 ``AssetManager.register()`` 这一条路径，避免出现第二处时长来源。
    - 素材文件缺失时不中断整体流程：跳过并计入报告。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 允许以 `python scripts/init_assets.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import Settings  # noqa: E402
from app.core.constants import (  # noqa: E402
    ACTION_ASSET_SUFFIX,
    ALLOWED_ACTIONS,
)
from app.core.exceptions import PetLiveError  # noqa: E402
from app.core.logging_config import get_logger  # noqa: E402
from app.repositories.asset_repository import AssetRepository  # noqa: E402
from app.repositories.db import Database  # noqa: E402
from app.services.asset_manager import AssetManager  # noqa: E402

logger = get_logger(__name__)

#: 默认登记的角色（Step 1 指令要求）
DEFAULT_PET_TYPES: tuple[str, ...] = ("cat",)

#: 全部已备素材的角色
ALL_PET_TYPES: tuple[str, ...] = ("cat", "dog", "panda")


@dataclass
class SeedReport:
    """登记结果报告。

    Attributes:
        written: 成功登记数。
        skipped: 因素材缺失或元数据不可读而跳过数。
        errors: 跳过项的 (asset_id, code, message) 明细。
    """

    written: int = 0
    skipped: int = 0
    errors: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """尝试登记的总数。"""
        return self.written + self.skipped


def iter_seed_targets(
    pet_types: tuple[str, ...] = DEFAULT_PET_TYPES,
    actions: tuple[str, ...] = ALLOWED_ACTIONS,
) -> list[tuple[str, str, str]]:
    """枚举待登记的资产目标。

    路径约定（禁止硬编码角色名，此处由参数驱动）：
        assets/pets/{pet_type}/actions/{action}/{action}.mp4

    Args:
        pet_types: 角色类型集合。
        actions: 动作名集合。

    Returns:
        ``(pet_type, action, relative_path)`` 三元组列表。
    """
    targets: list[tuple[str, str, str]] = []
    for pet_type in pet_types:
        for action in actions:
            relative = (
                f"assets/pets/{pet_type}/actions/{action}"
                f"/{action}{ACTION_ASSET_SUFFIX}"
            )
            targets.append((pet_type, action, relative))
    return targets


def seed(
    pet_types: tuple[str, ...] = DEFAULT_PET_TYPES,
    reset: bool = False,
    settings: Settings | None = None,
) -> SeedReport:
    """执行登记。

    每条资产均通过 ``AssetManager.register()`` 写入，
    时长由 ffprobe 从真实素材读取。

    Args:
        pet_types: 要登记的角色。
        reset: 是否先清空 assets 表。
        settings: 可选配置（测试注入用）。

    Returns:
        SeedReport 结果报告。
    """
    cfg = settings or Settings.default()
    cfg.ensure_directories()

    database = Database(cfg.database_path, cfg.schema_path)
    database.initialize()
    repository = AssetRepository(database)
    manager = AssetManager(repository, cfg)

    if reset:
        repository.delete_all()

    report = SeedReport()

    for pet_type, action, relative in iter_seed_targets(pet_types):
        try:
            metadata = manager.register(pet_type, action, relative)
        except PetLiveError as exc:
            report.skipped += 1
            report.errors.append((f"{pet_type}_action_{action}", exc.code, exc.message))
            logger.warning(
                "跳过 %s/%s：%s（%s）", pet_type, action, exc.code, exc.message
            )
            continue

        report.written += 1
        logger.debug(
            "已登记 %s/%s -> %dms", pet_type, action, metadata.duration
        )

    logger.info(
        "资产登记完成: 成功 %d 条 / 跳过 %d 条（角色: %s）",
        report.written,
        report.skipped,
        ", ".join(pet_types),
    )
    return report


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="初始化资产元数据")
    parser.add_argument(
        "--all",
        action="store_true",
        help="登记全部角色（cat/dog/panda）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="写入前清空 assets 表",
    )
    args = parser.parse_args()

    pet_types = ALL_PET_TYPES if args.all else DEFAULT_PET_TYPES
    report = seed(pet_types=pet_types, reset=args.reset)
    print(f"写入 {report.written} 条资产记录")  # noqa: T201 - CLI 输出
    if report.skipped:
        print(f"跳过 {report.skipped} 条:")  # noqa: T201 - CLI 输出
        for asset_id, code, message in report.errors:
            print(f"  - {asset_id}: {code} {message}")  # noqa: T201 - CLI 输出
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
