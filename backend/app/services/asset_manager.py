"""资产管理器（Phase 1 支撑模块）。

验证链路：
    Action Identifier → Asset Manager → Asset Metadata → Playable Resource

职责（做什么）：
    - 校验动作标识
    - 查询资产元数据
    - 解析可播放资源路径
    - 校验资源可用性

明确不做（Step 1 禁止事项）：
    - 不负责播放
    - 不管理播放状态（idle / playing）
    - 不推荐动作
    - 不做 AI 决策
    - 不做上传 / CDN / 缓存优化

设计约束：
    - 查询失败必须显式报错，**禁止**自动拼接路径兜底
    - **禁止**出现硬编码角色名（红线 C3）
"""

from __future__ import annotations

from pathlib import Path

from app.config.settings import Settings
from app.core.exceptions import (
    AssetFileMissingError,
    AssetNotFoundError,
    InvalidRequestError,
)
from app.core.logging_config import get_logger
from app.models.asset import AssetMetadata, AssetRecord
from app.repositories.asset_repository import AssetRepository
from app.services.asset_duration import get_duration_ms

logger = get_logger(__name__)

#: 标识符中禁止出现的字符（路径穿越与系统保留字符）
_FORBIDDEN_CHARS = frozenset('/\\:*?"<>|')


class AssetManager:
    """资产查询与解析服务。"""

    def __init__(self, repository: AssetRepository, settings: Settings) -> None:
        """初始化。

        Args:
            repository: 资产仓储。
            settings: 运行配置。
        """
        self._repo = repository
        self._settings = settings

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_asset(self, pet_type: str, action: str) -> AssetMetadata:
        """查询资产元数据。

        这是模块的主入口。未登记或资源缺失时**抛出异常**，
        绝不返回空值或自动拼接路径（验收标准 A2）。

        Args:
            pet_type: 角色类型，如 ``cat``。
            action: 动作名，如 ``heart``。

        Returns:
            AssetMetadata 实例。

        Raises:
            InvalidRequestError: 参数非法。
            AssetNotFoundError: 资产未在元数据中登记。
            AssetFileMissingError: 资产已登记但物理文件缺失。
        """
        self._validate_identifier(pet_type, "pet_type")
        self._validate_identifier(action, "action")

        record = self._repo.find(pet_type, action)
        if record is None:
            logger.warning(
                "资产未登记，拒绝查询: pet_type=%s action=%s", pet_type, action
            )
            raise AssetNotFoundError(
                f"资产未登记: {pet_type}/{action}",
                pet_type=pet_type,
                action=action,
            )

        return self._to_metadata(record)

    def find_asset(self, pet_type: str, action: str) -> AssetMetadata | None:
        """宽容版查询：未登记返回 None。

        注意：参数非法仍然抛异常 —— 宽容仅针对"查不到"，
        不针对"参数错"。

        Args:
            pet_type: 角色类型。
            action: 动作名。

        Returns:
            AssetMetadata 或 None。
        """
        try:
            return self.get_asset(pet_type, action)
        except AssetNotFoundError:
            return None

    def exists(self, pet_type: str, action: str) -> bool:
        """判断资产是否可用（已登记且文件存在）。"""
        return self.find_asset(pet_type, action) is not None

    def list_actions(self, pet_type: str) -> list[str]:
        """列出某角色已登记的全部动作名。

        Args:
            pet_type: 角色类型。

        Returns:
            动作名列表（按字母序）。
        """
        self._validate_identifier(pet_type, "pet_type")
        return [r.action for r in self._repo.list_by_pet(pet_type)]

    def list_assets(self, pet_type: str) -> list[AssetMetadata]:
        """列出某角色的全部资产元数据。"""
        self._validate_identifier(pet_type, "pet_type")
        result: list[AssetMetadata] = []
        for record in self._repo.list_by_pet(pet_type):
            metadata = self._try_to_metadata(record)
            if metadata is not None:
                result.append(metadata)
        return result

    # ------------------------------------------------------------------
    # 登记
    # ------------------------------------------------------------------
    def register(
        self,
        pet_type: str,
        action: str,
        path: str,
        duration: int | None = None,
    ) -> AssetMetadata:
        """登记或更新一条资产。

        新增动作只需调用本方法写入元数据，无需修改任何查询代码
        （验收标准 A3）。

        ``duration`` 行为（Step 1.1 起）：
            - ``None``（默认，生产路径）：调用 ffprobe 读取**真实时长**
            - 显式传入整数：直接采用（仅供测试注入或特殊场景）

        **注意**：登记是"声明"行为，素材文件允许后补，
        因此本方法**不做文件存在性校验**（缺失时仅记录警告）；
        但无法读取 duration 时会抛 ``AssetMetadataError``。

        Args:
            pet_type: 角色类型。
            action: 动作名。
            path: 素材路径（相对项目根或绝对路径）。
            duration: 显式时长（毫秒）；None 表示自动探测。

        Returns:
            登记后的 AssetMetadata。

        Raises:
            InvalidRequestError: 参数非法。
            AssetMetadataError: 未显式传入 duration 且无法从文件读取时长。
        """
        self._validate_identifier(pet_type, "pet_type")
        self._validate_identifier(action, "action")

        if not path or not str(path).strip():
            raise InvalidRequestError("path 不能为空", path=path)

        resolved_duration = self._resolve_duration(path, duration)

        record = AssetRecord(
            pet_type=pet_type,
            action=action,
            path=str(path),
            duration=resolved_duration,
        )
        self._repo.upsert(record)
        logger.info(
            "资产已登记: %s (duration=%dms)", record.asset_id, resolved_duration
        )

        metadata = self._build_metadata(record)
        if not Path(metadata.absolute_path).is_file():
            logger.warning(
                "资产已登记但文件尚未就位: %s -> %s",
                record.asset_id,
                metadata.absolute_path,
            )
        return metadata

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _resolve_duration(self, path: str, duration: int | None) -> int:
        """确定资产时长。

        规则（Step 1.1）：
            - 显式传入 → 校验后直接采用（测试注入 / 特殊场景）
            - 未传入 → 调用 ffprobe 读取真实时长（生产路径）

        Args:
            path: 素材路径。
            duration: 显式时长或 None。

        Returns:
            时长（毫秒）。

        Raises:
            InvalidRequestError: 显式 duration 非法。
            AssetMetadataError: ffprobe 无法读取时长。
        """
        if duration is not None:
            if isinstance(duration, bool) or not isinstance(duration, int):
                raise InvalidRequestError(
                    f"duration 必须为非负整数: {duration!r}", duration=duration
                )
            if duration < 0:
                raise InvalidRequestError(
                    f"duration 必须为非负整数: {duration!r}", duration=duration
                )
            return duration

        absolute = self._settings.resolve_path(path)
        return get_duration_ms(
            absolute, ffprobe_path=self._settings.ffprobe_path
        )

    def _validate_identifier(self, value: str, field: str) -> None:
        """校验标识符合法性（防路径穿越与非法字符）。"""
        if not isinstance(value, str) or not value.strip():
            raise InvalidRequestError(f"{field} 必须为非空字符串", field=field)

        stripped = value.strip()
        if stripped != value:
            raise InvalidRequestError(
                f"{field} 不允许包含首尾空白: {value!r}", field=field, value=value
            )
        if _FORBIDDEN_CHARS & set(value):
            raise InvalidRequestError(
                f"{field} 包含非法字符: {value!r}", field=field, value=value
            )
        if value in {".", ".."} or ".." in value:
            raise InvalidRequestError(
                f"{field} 不允许路径穿越: {value!r}", field=field, value=value
            )

    def _build_metadata(self, record: AssetRecord) -> AssetMetadata:
        """将记录转换为元数据（不校验文件存在性）。"""
        absolute = self._settings.resolve_path(record.path)
        return AssetMetadata(
            asset_id=record.asset_id,
            pet_type=record.pet_type,
            action=record.action,
            asset_path=record.path.replace("\\", "/"),
            absolute_path=str(absolute),
            duration=record.duration,
        )

    def _to_metadata(self, record: AssetRecord) -> AssetMetadata:
        """将记录转换为元数据，并按需校验物理文件。

        查询路径专用：文件缺失时抛 AssetFileMissingError。

        Raises:
            AssetFileMissingError: 文件不存在且启用了严格校验。
        """
        metadata = self._build_metadata(record)

        if self._settings.strict_file_check and not Path(
            metadata.absolute_path
        ).is_file():
            logger.error(
                "资产文件缺失: %s -> %s",
                record.asset_id,
                metadata.absolute_path,
            )
            raise AssetFileMissingError(
                f"资产文件不存在: {record.path}",
                asset_id=record.asset_id,
                path=metadata.absolute_path,
            )

        return metadata

    def _try_to_metadata(self, record: AssetRecord) -> AssetMetadata | None:
        """转换记录，文件缺失时跳过（用于列表场景，不中断整体）。"""
        try:
            return self._to_metadata(record)
        except AssetFileMissingError:
            return None


def build_default_manager(settings: Settings | None = None) -> AssetManager:
    """构造默认装配的 AssetManager。

    装配顺序：Settings → Database → Repository → Manager。

    Args:
        settings: 可选配置，默认使用 ``Settings.default()``。

    Returns:
        可直接使用的 AssetManager。测试可传入自定义配置实现隔离。
    """
    from app.repositories.db import Database  # 局部导入避免循环依赖

    cfg = settings or Settings.default()
    cfg.ensure_directories()

    database = Database(cfg.database_path, cfg.schema_path)
    database.initialize()

    return AssetManager(AssetRepository(database), cfg)
