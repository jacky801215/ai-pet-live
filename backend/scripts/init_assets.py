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
    - **素材选择是「显式映射」而非「推断」**（CR-9）：
      仅 ``ALPHA_ACTIONS`` 中显式列出的「角色 + 动作」会在其 webm **确实存在**时
      登记 alpha 素材，其余一律回退 mp4。**禁止**扫描目录 / glob / 按后缀猜测 ——
      未命中的组合（``dog`` / ``panda`` / ``sad`` / ``surprise`` / 未来新增角色）
      永远保持 mp4 行为不变。
    - **伴随音效同样是「显式映射」**（**CR-11**）：仅 ``AUDIO_ACTIONS`` 中显式列出的
      「角色 + 动作」会在其 ogg **确实存在**时登记 ``assets.audio_path``；
      其余一律写 ``NULL``（= 无音效）。判定纪律与 ``ALPHA_ACTIONS`` **逐字一致**。
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

#: alpha（WebM / VP9，``alpha_mode=1``）素材的**显式映射**（CR-9）。
#:
#: 结构：``{pet_type: {action: 文件名}}``，值为 ``<action>`` 目录下的**文件名**。
#: 选择规则（见 ``resolve_action_asset``）：
#:     ① 命中本映射 **且** 该文件真实存在 ⇒ 登记 alpha 素材；
#:     ② 否则 ⇒ 回退 ``{action}.mp4``。
#:
#: ⚠️ 本表是唯一的 alpha 判定来源：**不得**改为扫描目录 / glob / 后缀猜测，
#: 也不得用「文件存在性」单独推断 alpha（那样会让未来新增的任意 webm 静默生效）。
ALPHA_ACTIONS: dict[str, dict[str, str]] = {
    "cat": {
        "idle": "idle.webm",
        "heart": "heart.webm",
        "happy": "happy.webm",
    },
}

#: 伴随音效素材的**显式映射**（**CR-11**）。
#:
#: 结构：``{pet_type: {action: 文件名}}``，值为 ``<action>`` 目录下的**文件名**。
#: 选择规则（见 ``resolve_action_audio``）：命中本映射 **且** 该文件真实存在
#: ⇒ 登记 ``assets.audio_path``；否则 ⇒ ``NULL``（无音效）。
#:
#: ⚠️ 与 :data:`ALPHA_ACTIONS` **同一纪律**：本表是唯一的音效判定来源，
#: **禁止**扫描目录 / glob / 后缀猜测，**禁止**按同名规则推导。
#:
#: 范围（first stage frozen）：**仅 cat 的 heart / happy** 有声；``idle`` 静音，
#: ``sad`` / ``surprise`` / dog / panda **暂不覆盖**。
#: 契约见 ``docs/change_request/cr-11_audio_feedback_design.md`` §一。
#: ⚠️ 当前仓库**尚无**任何 ``.ogg`` 素材（CR-11 第一阶段只验证管线）⇒
#: 命中映射也因「文件不存在」而不登记，``audio_path`` 恒为 ``NULL``。
AUDIO_ACTIONS: dict[str, dict[str, str]] = {
    "cat": {
        "heart": "heart.ogg",
        "happy": "happy.ogg",
    },
}


@dataclass
class SeedReport:
    """登记结果报告。

    Attributes:
        written: 成功登记数。
        skipped: 因素材缺失或元数据不可读而跳过数。
        errors: 跳过项的 (asset_id, code, message) 明细。
        alpha: 实际登记为 alpha 素材的 (pet_type, action, relative_path) 明细。
        audio: **CR-11** 实际登记了伴随音效的 (pet_type, action, relative_path) 明细。
    """

    written: int = 0
    skipped: int = 0
    errors: list[tuple[str, str, str]] = field(default_factory=list)
    alpha: list[tuple[str, str, str]] = field(default_factory=list)
    audio: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """尝试登记的总数。"""
        return self.written + self.skipped


def _asset_relative_path(pet_type: str, action: str, file_name: str) -> str:
    """动作素材的相对路径（视觉与音效**共用同一模板**，避免第二处拼接口径）。"""
    return f"assets/pets/{pet_type}/actions/{action}/{file_name}"


def resolve_action_asset(
    pet_type: str,
    action: str,
    assets_root: Path | None = None,
) -> str:
    """为「角色 + 动作」选择素材文件名（CR-9）。

    选择顺序**完全显式**，不含任何推断：

        1. ``ALPHA_ACTIONS`` 命中该组合 **且** 文件在磁盘上存在 ⇒ 返回 alpha 文件名；
        2. 其余情况 ⇒ 返回 ``{action}{ACTION_ASSET_SUFFIX}``。

    Args:
        pet_type: 角色类型。
        action: 动作名。
        assets_root: 素材根目录（``<project_root>/assets/pets``）。
            ``None`` 表示**不检查文件存在性**（仅用于纯枚举场景），此时一律回退 mp4。

    Returns:
        素材文件名，如 ``idle.webm`` 或 ``idle.mp4``。
    """
    alpha_name = ALPHA_ACTIONS.get(pet_type, {}).get(action)
    if alpha_name is not None and assets_root is not None:
        candidate = assets_root / pet_type / "actions" / action / alpha_name
        if candidate.is_file():
            return alpha_name
    return f"{action}{ACTION_ASSET_SUFFIX}"


def resolve_action_audio(
    pet_type: str,
    action: str,
    assets_root: Path | None = None,
) -> str | None:
    """为「角色 + 动作」选择**伴随音效**文件名（**CR-11**）。

    选择顺序与 :func:`resolve_action_asset` **逐字同构**，只是缺省结果不同
    （视觉素材必然存在 ⇒ 回退 mp4；音效是**可选**的 ⇒ 回退 ``None``）：

        1. ``AUDIO_ACTIONS`` 命中该组合 **且** 文件在磁盘上存在 ⇒ 返回音效文件名；
        2. 其余情况 ⇒ 返回 ``None``（= 该动作**无音效**，登记 ``NULL``）。

    ⛔ 本函数**只认显式映射**：**不得**改为扫描目录 / glob / 后缀猜测，
    也不得以「文件存在性」单独推断（否则未来任意落盘的 ogg 会静默生效）。

    Args:
        pet_type: 角色类型。
        action: 动作名。
        assets_root: 素材根目录（``<project_root>/assets/pets``）。
            ``None`` 表示**不检查文件存在性**（纯枚举场景），此时一律返回 ``None``。

    Returns:
        音效文件名（如 ``heart.ogg``）；未映射或文件缺失时 ``None``。
    """
    audio_name = AUDIO_ACTIONS.get(pet_type, {}).get(action)
    if audio_name is None or assets_root is None:
        return None
    candidate = assets_root / pet_type / "actions" / action / audio_name
    return audio_name if candidate.is_file() else None


def iter_seed_targets(
    pet_types: tuple[str, ...] = DEFAULT_PET_TYPES,
    actions: tuple[str, ...] = ALLOWED_ACTIONS,
    assets_root: Path | None = None,
) -> list[tuple[str, str, str, bool]]:
    """枚举待登记的资产目标。

    路径约定（禁止硬编码角色名，此处由参数驱动）：
        assets/pets/{pet_type}/actions/{action}/{action}<后缀>

    后缀由 ``resolve_action_asset`` 决定（CR-9：alpha 优先，缺失回退 mp4）。

    Args:
        pet_types: 角色类型集合。
        actions: 动作名集合。
        assets_root: 素材根目录；用于判断 alpha 素材是否存在。
            ``None`` ⇒ 一律 mp4（保持纯枚举、不触碰文件系统）。

    Returns:
        ``(pet_type, action, relative_path, is_alpha)`` 四元组列表。
    """
    targets: list[tuple[str, str, str, bool]] = []
    for pet_type in pet_types:
        for action in actions:
            file_name = resolve_action_asset(pet_type, action, assets_root)
            relative = _asset_relative_path(pet_type, action, file_name)
            is_alpha = file_name != f"{action}{ACTION_ASSET_SUFFIX}"
            targets.append((pet_type, action, relative, is_alpha))
    return targets


def seed(
    pet_types: tuple[str, ...] = DEFAULT_PET_TYPES,
    reset: bool = False,
    settings: Settings | None = None,
) -> SeedReport:
    """执行登记。

    每条资产均通过 ``AssetManager.register()`` 写入，
    时长由 ffprobe 从真实素材读取。素材文件名由 ``resolve_action_asset``
    按 ``ALPHA_ACTIONS`` 显式映射选择（CR-9）；伴随音效由 ``resolve_action_audio``
    按 ``AUDIO_ACTIONS`` 显式映射选择（**CR-11**），未命中 ⇒ ``audio_path = NULL``
    （**全量覆盖**语义：每次运行都以「文件系统的事实」重写该列）。

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

    for pet_type, action, relative, is_alpha in iter_seed_targets(
        pet_types, assets_root=cfg.assets_root
    ):
        audio_name = resolve_action_audio(pet_type, action, cfg.assets_root)
        audio_relative = (
            _asset_relative_path(pet_type, action, audio_name)
            if audio_name is not None
            else None
        )
        try:
            metadata = manager.register(
                pet_type, action, relative, audio_path=audio_relative
            )
        except PetLiveError as exc:
            report.skipped += 1
            report.errors.append((f"{pet_type}_action_{action}", exc.code, exc.message))
            logger.warning(
                "跳过 %s/%s：%s（%s）", pet_type, action, exc.code, exc.message
            )
            continue

        report.written += 1
        if is_alpha:
            report.alpha.append((pet_type, action, relative))
        if audio_relative is not None:
            report.audio.append((pet_type, action, audio_relative))
        logger.debug(
            "已登记 %s/%s -> %s（%dms，audio=%s）",
            pet_type,
            action,
            relative,
            metadata.duration,
            audio_relative,
        )

    logger.info(
        "资产登记完成: 成功 %d 条 / 跳过 %d 条（alpha %d 条，audio %d 条，角色: %s）",
        report.written,
        report.skipped,
        len(report.alpha),
        len(report.audio),
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
    if report.alpha:
        print(f"其中 alpha 素材 {len(report.alpha)} 条:")  # noqa: T201 - CLI 输出
        for pet_type, action, relative in report.alpha:
            print(f"  - {pet_type}/{action}: {relative}")  # noqa: T201 - CLI 输出
    if report.audio:
        print(f"其中伴随音效 {len(report.audio)} 条:")  # noqa: T201 - CLI 输出
        for pet_type, action, relative in report.audio:
            print(f"  - {pet_type}/{action}: {relative}")  # noqa: T201 - CLI 输出
    if report.skipped:
        print(f"跳过 {report.skipped} 条:")  # noqa: T201 - CLI 输出
        for asset_id, code, message in report.errors:
            print(f"  - {asset_id}: {code} {message}")  # noqa: T201 - CLI 输出
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
