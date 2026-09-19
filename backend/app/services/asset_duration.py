"""资产时长提取器。

职责（单一）：
    file_path → duration_ms

禁止事项：
    - 禁止手工解析 MP4 容器
    - 禁止写死时长
    - 禁止根据文件名推断时长

依赖：
    ffprobe（FFmpeg 套件），通过子进程调用
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.exceptions import AssetMetadataError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: ffprobe 可执行文件名
FFPROBE_BIN = "ffprobe"

#: 子进程超时（秒）
DEFAULT_TIMEOUT_SECONDS = 10

#: ffprobe 参数：只取 format 层的 duration，纯数值输出
_PROBE_ARGS = (
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
)


def resolve_ffprobe(ffprobe_path: str | Path | None = None) -> str:
    """解析 ffprobe 可执行文件路径。

    解析顺序：
        1. 显式传入的路径
        2. PATH 上的 ffprobe

    Args:
        ffprobe_path: 显式指定的 ffprobe 路径。

    Returns:
        ffprobe 可执行文件路径。

    Raises:
        AssetMetadataError: 未找到可用的 ffprobe。
    """
    if ffprobe_path is not None:
        candidate = Path(ffprobe_path)
        if not candidate.is_file():
            raise AssetMetadataError(
                f"指定的 ffprobe 不存在: {candidate}",
                ffprobe=str(candidate),
            )
        return str(candidate)

    found = shutil.which(FFPROBE_BIN)
    if found is None:
        raise AssetMetadataError(
            "未找到 ffprobe，请安装 FFmpeg 或显式指定路径",
            ffprobe=FFPROBE_BIN,
        )
    return found


def get_duration_ms(
    file_path: str | Path,
    ffprobe_path: str | Path | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """读取媒体文件时长（毫秒）。

    实现方式：调用 ffprobe 读取 format 层 duration（单位秒），
    乘以 1000 后四舍五入为整数毫秒。

    Args:
        file_path: 媒体文件路径。
        ffprobe_path: 可选的 ffprobe 路径，默认从 PATH 查找。
        timeout: 子进程超时秒数。

    Returns:
        时长（毫秒），始终为正整数。

    Raises:
        AssetMetadataError: 文件不存在 / ffprobe 不可用 / 执行失败 /
            输出无法解析 / 时长非正。
    """
    path = Path(file_path)

    if not path.is_file():
        logger.error("读取时长失败，文件不存在: %s", path)
        raise AssetMetadataError(
            f"文件不存在: {path}",
            path=str(path),
        )

    probe = resolve_ffprobe(ffprobe_path)
    cmd = [probe, *_PROBE_ARGS, str(path)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("ffprobe 超时: %s", path)
        raise AssetMetadataError(
            f"ffprobe 执行超时: {path.name}",
            path=str(path),
            timeout=timeout,
        ) from exc
    except OSError as exc:
        logger.error("ffprobe 无法执行: %s", exc)
        raise AssetMetadataError(
            f"ffprobe 执行失败: {exc}",
            path=str(path),
        ) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error(
            "ffprobe 返回非零退出码 %s: %s", result.returncode, stderr[:200]
        )
        raise AssetMetadataError(
            "Cannot read media duration",
            path=str(path),
            returncode=result.returncode,
            stderr=stderr[:500],
        )

    raw = (result.stdout or "").strip()
    if not raw:
        logger.error("ffprobe 输出为空: %s", path)
        raise AssetMetadataError(
            "Cannot read media duration",
            path=str(path),
            reason="empty_output",
        )

    duration_ms = _parse_seconds_to_ms(raw, path)
    logger.debug("时长读取成功: %s -> %sms", path.name, duration_ms)
    return duration_ms


def _parse_seconds_to_ms(raw: str, path: Path) -> int:
    """将 ffprobe 输出的秒数文本转换为毫秒整数。

    Args:
        raw: ffprobe 标准输出（形如 ``1.000000``）。
        path: 文件路径（用于错误上下文）。

    Returns:
        毫秒整数。

    Raises:
        AssetMetadataError: 无法解析或结果非正。
    """
    try:
        seconds = float(raw.splitlines()[0].strip())
    except (ValueError, IndexError) as exc:
        logger.error("ffprobe 输出无法解析为数值: %r", raw[:100])
        raise AssetMetadataError(
            "Cannot read media duration",
            path=str(path),
            reason="unparsable_output",
            raw=raw[:100],
        ) from exc

    duration_ms = int(round(seconds * 1000))

    if duration_ms <= 0:
        logger.error("解析出的时长非正: %s -> %sms", path, duration_ms)
        raise AssetMetadataError(
            "Cannot read media duration",
            path=str(path),
            reason="non_positive_duration",
            seconds=seconds,
        )

    return duration_ms
