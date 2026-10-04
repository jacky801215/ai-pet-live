"""pytest 全局配置与共享夹具。

提供完全隔离的测试环境：
    - 临时 project_root（不触碰真实 assets/database）
    - 临时 SQLite 文件
    - 可复用的素材构造工具
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

# 将 backend/ 加入 sys.path，使 `from app.xxx import ...` 可用
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import Settings  # noqa: E402
from app.core import constants  # noqa: E402
from app.repositories.asset_repository import AssetRepository  # noqa: E402
from app.repositories.db import Database  # noqa: E402
from app.services.asset_manager import AssetManager  # noqa: E402

#: 与真实素材无关的占位内容，AssetManager 只校验文件存在性
FAKE_MP4_BYTES = b"\x00\x00\x00\x18ftypmp42"

#: ffmpeg 可执行文件（生成测试媒体用），未安装时为 None
FFMPEG_BIN: str | None = shutil.which("ffmpeg")


def make_action_file(
    project_root: Path,
    pet_type: str,
    action: str,
    content: bytes = FAKE_MP4_BYTES,
) -> Path:
    """在临时 project_root 下创建一个动作素材文件（占位内容）。

    只用于验证「文件存在性」相关逻辑 —— 内容不是合法媒体，
    ``ffprobe`` 无法解析。需要真实时长的测试请用 ``make_media_file``。

    Args:
        project_root: 临时项目根目录。
        pet_type: 角色类型。
        action: 动作名。
        content: 文件内容。

    Returns:
        创建的文件路径。
    """
    target = (
        project_root
        / "assets"
        / "pets"
        / pet_type
        / "actions"
        / action
        / f"{action}.mp4"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def make_media_file(
    path: Path,
    seconds: float,
    color: str = "0x4A5568",
    size: str = "64x64",
) -> Path:
    """用 ffmpeg 生成指定时长的真实 MP4 文件。

    仅用于 duration 相关测试 —— 这类测试需要**真实可解析**的媒体文件，
    而非 ``FAKE_MP4_BYTES`` 这类占位字节。

    Args:
        path: 目标文件路径（父目录自动创建）。
        seconds: 视频时长（秒）。
        color: 纯色填充色。
        size: 分辨率，如 ``64x64``（取小尺寸加速生成）。

    Returns:
        生成的文件路径。

    Raises:
        RuntimeError: 环境未安装 ffmpeg。
        subprocess.CalledProcessError: ffmpeg 生成失败。
    """
    if FFMPEG_BIN is None:  # pragma: no cover - 环境缺失保护
        raise RuntimeError(
            "测试需要 ffmpeg 生成真实媒体文件，但未在 PATH 中找到可执行文件"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={size}:d={seconds}:r=10",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return path


def register_asset(
    manager: AssetManager,
    pet_type: str,
    action: str,
    duration: int = 1000,
) -> None:
    """登记一条资产（路径按素材规范生成，显式指定时长）。

    注意：显式传入 ``duration`` 是**测试专用**的快捷方式，
    生产路径应省略该参数由 ffprobe 自动探测。
    """
    manager.register(
        pet_type=pet_type,
        action=action,
        path=f"assets/pets/{pet_type}/actions/{action}/{action}.mp4",
        duration=duration,
    )


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[SimpleNamespace]:
    """构建隔离的 AssetManager 测试环境。

    Returns:
        含 ``manager`` / ``settings`` / ``database`` / ``repository``
        / ``project_root`` 的命名空间对象。
    """
    project_root = tmp_path
    assets_root = project_root / "assets" / "pets"
    assets_root.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        project_root=project_root,
        assets_root=assets_root,
        database_path=project_root / "test_pet_live.db",
        # 复用真实建表脚本，确保测试覆盖实际 DDL
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )

    database = Database(settings.database_path, settings.schema_path)
    database.initialize()
    repository = AssetRepository(database)
    manager = AssetManager(repository, settings)

    yield SimpleNamespace(
        manager=manager,
        settings=settings,
        database=database,
        repository=repository,
        project_root=project_root,
    )
    # CR-8：连接按线程复用（连接不随每次操作关闭）⇒ teardown 显式释放，
    # 避免长连接占用临时库文件句柄（Windows）。
    database.dispose()


@pytest.fixture()
def manager(env: SimpleNamespace) -> AssetManager:
    """便捷夹具：只取 AssetManager。"""
    return env.manager


@pytest.fixture()
def loose_env(tmp_path: Path) -> Iterator[SimpleNamespace]:
    """关闭文件存在性校验的环境（用于只测元数据的场景）。"""
    project_root = tmp_path
    settings = Settings(
        project_root=project_root,
        assets_root=project_root / "assets" / "pets",
        database_path=project_root / "test_pet_live.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=False,
    )
    database = Database(settings.database_path, settings.schema_path)
    database.initialize()
    repository = AssetRepository(database)
    yield SimpleNamespace(
        manager=AssetManager(repository, settings),
        settings=settings,
        repository=repository,
        project_root=project_root,
    )
    # CR-8：连接按线程复用 ⇒ teardown 显式释放。
    database.dispose()


# ---------------------------------------------------------------------------
# 常量导出，供测试断言引用
# ---------------------------------------------------------------------------
__all__ = [
    "env",
    "manager",
    "loose_env",
    "make_action_file",
    "make_media_file",
    "register_asset",
    "FAKE_MP4_BYTES",
    "FFMPEG_BIN",
]
