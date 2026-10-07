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

对外主键（Step 4.1-A 起，准绳 ``docs/development/step4_playback_data_decision.md`` D2）：

    - 对外主键统一为 ``pet_id``；``pet_id → pet_type`` 映射由本模块**内部**完成
    - 映射来源：各宠物 ``assets/pets/{pet_type}/config.json`` 的 ``pet_id`` / ``pet_type``
    - 本模块是全项目**唯一**素材解析点；其他模块不得自行读 ``config.json`` 或拼接路径
    - 兼容路径：键未登记为 ``pet_id`` 时**按 ``pet_type`` 直用**
      （存量调用点过渡用，见 Deferred E29；参数非法仍抛异常）
"""

from __future__ import annotations

import json
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

#: 宠物配置文件（``pet_id → pet_type`` 映射的唯一来源）
_PET_CONFIG_FILENAME = "config.json"

#: 宠物配置中的映射字段
_PET_ID_FIELD = "pet_id"
_PET_TYPE_FIELD = "pet_type"

#: 待机动作名（**CR-1**）：待机态（``PlaybackState.action`` 为 ``null``）下发给前端的素材动作
IDLE_ACTION: str = "idle"

#: 循环播放的动作集合（**CR-1**：仅待机循环、其余动作单次）。
#: **硬编码策略表** —— 不入库、不读配置；判定归素材层（``step3_playback_decision.md`` P1）。
LOOPING_ACTIONS: frozenset[str] = frozenset({IDLE_ACTION})


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
        #: ``pet_id → pet_type`` 索引；None = 尚未加载（懒加载，见 _pet_index_map）
        self._pet_index: dict[str, str] | None = None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_asset(self, pet_id: str, action: str) -> AssetMetadata:
        """查询资产元数据。

        这是模块的主入口。未登记或资源缺失时**抛出异常**，
        绝不返回空值或自动拼接路径（验收标准 A2）。
        需要"查不到返回 ``None``"的调用点请用 :meth:`find_asset`。

        Args:
            pet_id: 宠物标识（对外主键），如 ``cat_001``。
                未登记为 ``pet_id`` 时按 ``pet_type`` 直用（兼容路径）。
            action: 动作名，如 ``heart``。

        Returns:
            AssetMetadata 实例。

        Raises:
            InvalidRequestError: 参数非法。
            AssetNotFoundError: 资产未在元数据中登记。
            AssetFileMissingError: 资产已登记但物理文件缺失。
        """
        pet_type = self._resolve_pet_type(pet_id)
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

    def find_asset(self, pet_id: str, action: str) -> AssetMetadata | None:
        """宽容版查询：未登记返回 None。

        播放链（PlaybackManager）使用的入口 —— "查不到"以 ``None`` 表达，
        不抛 ``AssetNotFoundError``。

        注意：参数非法仍然抛异常 —— 宽容仅针对"查不到"，
        不针对"参数错"。

        Args:
            pet_id: 宠物标识（对外主键），如 ``cat_001``。
            action: 动作名。

        Returns:
            AssetMetadata 或 None。
        """
        try:
            return self.get_asset(pet_id, action)
        except AssetNotFoundError:
            return None

    def exists(self, pet_id: str, action: str) -> bool:
        """判断资产是否可用（已登记且物理文件存在）。

        Args:
            pet_id: 宠物标识（对外主键），如 ``cat_001``。
            action: 动作名。

        Returns:
            ``True`` = 已登记**且**物理文件存在。
        """
        return self.find_asset(pet_id, action) is not None

    def resolve_playback_asset(self, pet_id: str, action: str | None) -> str | None:
        """解析**播放链路**的素材相对路径（**CR-1**）。

        与 :meth:`find_asset` 同为宽容版（未登记 → ``None``）；``action`` 为空
        （待机态，``PlaybackState.action`` 为 ``null``）时**回落** :data:`IDLE_ACTION`。
        参数非法仍抛 ``InvalidRequestError``（宽容只针对「查不到」，不针对「参数错」）。

        Args:
            pet_id: 宠物标识（对外主键），如 ``cat_001``。
            action: 动作名；``None`` / 空串 = 待机。

        Returns:
            素材相对路径（``assets/pets/...``）；未登记时 ``None``。
        """
        metadata = self.find_asset(pet_id, self._effective_action(action))
        if metadata is None:
            return None
        path = metadata.asset_path
        return path if isinstance(path, str) and path else None

    def resolve_audio_asset(self, pet_id: str, action: str | None) -> str | None:
        """解析动作的**伴随音效**相对路径（**CR-11**）。

        与 :meth:`resolve_playback_asset` 严格同构（同为宽容版、同走 :meth:`find_asset`、
        同样回落 :data:`IDLE_ACTION`），仅取值列不同（``audio_path`` 而非 ``asset_path``）。

        ⛔ **本方法是全项目唯一的音效路径解析点** —— 上层（transport）只消费其返回值并
        经 ``to_asset_url()`` 转为对外 URL；**禁止**任何模块自行按同名规则推导
        ``{action}.ogg``（违反 RB-2：禁前端/上层拼接素材路径）。

        未登记音频（``audio_path`` 为 ``NULL``）⇒ 返回 ``None``（**不是错误**）：
        调用方据此**不下发** ``playback_audio`` 帧。

        Args:
            pet_id: 宠物标识（对外主键），如 ``cat_001``。
            action: 动作名；``None`` / 空串 = 待机。

        Returns:
            音效相对路径（``assets/pets/.../*.ogg``）；未登记或无音效时 ``None``。
        """
        metadata = self.find_asset(pet_id, self._effective_action(action))
        if metadata is None:
            return None
        path = metadata.audio_path
        return path if isinstance(path, str) and path else None

    def is_looping(self, action: str | None) -> bool:
        """判断动作是否**循环播放**（**CR-1**）：``action`` 为空（待机）视作 :data:`IDLE_ACTION`。

        Args:
            action: 动作名；``None`` / 空串 = 待机。

        Returns:
            ``True`` = 循环播放（当前仅待机）；``False`` = 单次播放。
        """
        return self._effective_action(action) in LOOPING_ACTIONS

    @staticmethod
    def _effective_action(action: str | None) -> str:
        """把「待机」统一表达为 :data:`IDLE_ACTION`（``None`` / 空串 / 非 ``str`` 均回落）。"""
        return action if isinstance(action, str) and action else IDLE_ACTION

    def list_actions(self, pet_id: str) -> list[str]:
        """列出某宠物已登记的全部动作名。

        Args:
            pet_id: 宠物标识（对外主键）。

        Returns:
            动作名列表（按字母序）。
        """
        pet_type = self._resolve_pet_type(pet_id)
        return [r.action for r in self._repo.list_by_pet(pet_type)]

    def list_assets(self, pet_id: str) -> list[AssetMetadata]:
        """列出某宠物的全部资产元数据。"""
        pet_type = self._resolve_pet_type(pet_id)
        result: list[AssetMetadata] = []
        for record in self._repo.list_by_pet(pet_type):
            metadata = self._try_to_metadata(record)
            if metadata is not None:
                result.append(metadata)
        return result

    def pet_ids(self) -> list[str]:
        """列出全部已登记的宠物对外主键（``pet_id``），按字典序排序。

        只读投影接口：供上层（组合根）消费「宠物全集」，
        **不**暴露内部索引对象本身。

        行为约束（Step 4.3-B-2-L3 冻结）：

            - **只读**：不修改索引、不重新扫描磁盘、不加载配置、不写缓存。
              首次调用会触发索引懒加载（来源 ``assets/pets/*/config.json``，
              由本模块统一构建，见 D2），此后复用进程内缓存。
            - **返回副本并排序**：调用方增删返回值**不会**污染内部状态，
              且顺序稳定 —— 调用方可安全地取首元素。
            - **空索引返回 ``[]``**：无宠物配置**不是错误**，不抛异常。

        Returns:
            ``pet_id`` 列表（字典序）；无任何宠物配置时为空列表。
        """
        return sorted(list(self._pet_index_map().keys()))

    # ------------------------------------------------------------------
    # 登记
    # ------------------------------------------------------------------
    def register(
        self,
        pet_type: str,
        action: str,
        path: str,
        duration: int | None = None,
        audio_path: str | None = None,
    ) -> AssetMetadata:
        """登记或更新一条资产。

        新增动作只需调用本方法写入元数据，无需修改任何查询代码
        （验收标准 A3）。

        ``duration`` 行为（Step 1.1 起）：
            - ``None``（默认，生产路径）：调用 ffprobe 读取**真实时长**
            - 显式传入整数：直接采用（仅供测试注入或特殊场景）

        ``audio_path`` 行为（**CR-11**）：
            - ``None``（默认）= 该动作**无音效** ⇒ 写入 ``NULL``（**全量覆盖**语义）
            - 非空字符串 ⇒ 登记伴随音效相对路径

        **注意**：登记是"声明"行为，素材文件允许后补，
        因此本方法**不做文件存在性校验**（缺失时仅记录警告）；
        但无法读取 duration 时会抛 ``AssetMetadataError``。
        音效文件同理**不做存在性校验**。

        Args:
            pet_type: 角色类型。
            action: 动作名。
            path: 素材路径（相对项目根或绝对路径）。
            duration: 显式时长（毫秒）；None 表示自动探测。
            audio_path: 伴随音效相对路径（**CR-11**）；None 表示无音效。

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
        if audio_path is not None and (
            not isinstance(audio_path, str) or not audio_path.strip()
        ):
            raise InvalidRequestError(
                f"audio_path 必须为非空字符串或 None: {audio_path!r}",
                audio_path=audio_path,
            )

        resolved_duration = self._resolve_duration(path, duration)

        record = AssetRecord(
            pet_type=pet_type,
            action=action,
            path=str(path),
            duration=resolved_duration,
            audio_path=str(audio_path) if audio_path is not None else None,
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
    # 宠物主键映射（pet_id → pet_type）
    # ------------------------------------------------------------------
    def _pet_index_map(self) -> dict[str, str]:
        """``pet_id → pet_type`` 索引（懒加载 + 缓存）。

        首次调用时扫描素材根目录下的宠物配置；此后复用缓存，
        不做文件监听（Phase 1 配置在进程生命周期内不变）。
        """
        if self._pet_index is None:
            self._pet_index = self._scan_pet_index()
        return self._pet_index

    def _scan_pet_index(self) -> dict[str, str]:
        """扫描 ``assets/pets/*/config.json`` 构建映射。

        Returns:
            ``{pet_id: pet_type}``；目录缺失或配置损坏时返回已成功解析的部分。
        """
        root = Path(self._settings.assets_root)
        index: dict[str, str] = {}

        if not root.is_dir():
            logger.debug("素材根目录不存在，pet_id 映射为空: %s", root)
            return index

        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            config_path = child / _PET_CONFIG_FILENAME
            if not config_path.is_file():
                continue

            payload = self._read_pet_config(config_path)
            if payload is None:
                continue

            pet_id = payload.get(_PET_ID_FIELD)
            if not isinstance(pet_id, str) or not pet_id.strip():
                logger.warning("宠物配置缺少有效 pet_id，已跳过: %s", config_path)
                continue

            # pet_type 缺失时回退到目录名（素材目录即角色目录）
            pet_type = payload.get(_PET_TYPE_FIELD) or child.name
            index[pet_id] = str(pet_type)

        logger.info("pet_id → pet_type 映射已加载：%d 条", len(index))
        return index

    @staticmethod
    def _read_pet_config(config_path: Path) -> dict | None:
        """读取并解析单个宠物配置；失败时返回 ``None``（不中断整体扫描）。"""
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            logger.warning("宠物配置无法读取或解析，已跳过: %s", config_path)
            return None

        if not isinstance(payload, dict):
            logger.warning("宠物配置不是 JSON 对象，已跳过: %s", config_path)
            return None
        return payload

    def _resolve_pet_type(self, pet_id: str) -> str:
        """将对外主键解析为 ``pet_type``。

        解析顺序：

            1. ``pet_id`` 索引命中（来源各宠物 ``config.json``）→ 对应 ``pet_type``
            2. 未命中 → **按 ``pet_type`` 直用**（存量调用点兼容路径）

        参数非法（空值 / 非法字符 / 路径穿越）仍抛 ``InvalidRequestError``
        —— 兼容只针对"查不到"，不针对"参数错"。

        Args:
            pet_id: 对外主键。

        Returns:
            解析后的 ``pet_type``。

        Raises:
            InvalidRequestError: ``pet_id`` 非法。
        """
        self._validate_identifier(pet_id, "pet_id")
        mapped = self._pet_index_map().get(pet_id)
        if mapped is not None:
            return mapped
        logger.debug("键未登记为 pet_id，按 pet_type 直用: %s", pet_id)
        return pet_id

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
            audio_path=(
                record.audio_path.replace("\\", "/")
                if isinstance(record.audio_path, str) and record.audio_path
                else None
            ),
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
