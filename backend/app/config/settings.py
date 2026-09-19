"""运行时配置。

配置优先级：
1. 显式构造参数（测试注入用）
2. 环境变量
3. 默认常量

禁止在代码中硬编码密钥，敏感项一律走 .env（PROJECT_RULES 第九条）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core import constants


def _env_flag(name: str, default: bool = True) -> bool:
    """读取布尔型环境变量，支持 1/true/yes/on。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """资产模块运行配置。"""

    #: 项目根目录（相对路径资产的解析基准）
    project_root: Path

    #: 宠物素材根目录
    assets_root: Path

    #: SQLite 数据库文件路径
    database_path: Path

    #: 建表脚本路径
    schema_path: Path

    #: 是否在查询时校验物理文件存在性
    strict_file_check: bool = True

    #: ffprobe 可执行文件路径；None 表示从 PATH 自动查找
    ffprobe_path: str | None = None

    @classmethod
    def default(cls) -> "Settings":
        """基于项目常量与环境变量构造默认配置。"""
        return cls(
            project_root=constants.PROJECT_ROOT,
            assets_root=constants.ASSETS_ROOT,
            database_path=constants.DATABASE_PATH,
            schema_path=constants.SCHEMA_PATH,
            strict_file_check=_env_flag("ASSET_STRICT_FILE_CHECK", True),
            ffprobe_path=os.getenv("FFPROBE_PATH") or None,
        )

    def resolve_path(self, path: str | Path) -> Path:
        """将资产路径解析为绝对路径。

        - 绝对路径：原样返回
        - 相对路径：相对 ``project_root`` 解析

        Args:
            path: 资产路径。

        Returns:
            绝对路径。
        """
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate

    def ensure_directories(self) -> None:
        """确保运行所需目录存在（幂等）。"""
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
