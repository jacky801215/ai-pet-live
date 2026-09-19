"""资产时长提取测试（Step 1.1 任务 A）。

验证目标：
    asset file → ffprobe → duration(ms) → Asset Metadata

覆盖点（对应工作指令 T1~T4）：
    T1  正常读取：1 秒素材 → ~1000ms
    T2  非 1 秒素材：3 秒素材 → 3000ms ± 100ms
    T3  文件不存在 → ASSET_METADATA_ERROR
    T4  AssetManager 集成：duration 不再来自固定值
    +   显式 duration 覆盖、非法媒体、ffprobe 路径解析等边界

说明：
    本文件需要**真实可解析的媒体文件**，由 ffmpeg 在临时目录生成，
    不使用 ``FAKE_MP4_BYTES`` 占位字节。
    时长断言允许容差 —— 编码器在容器层写入的 duration 可能与
    请求值有毫秒级差异（如 1.0s 可能读作 1.033s）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.exceptions import (
    AssetMetadataError,
    InvalidRequestError,
)
from app.services.asset_duration import (
    get_duration_ms,
    resolve_ffprobe,
)
from tests.conftest import FFMPEG_BIN, make_action_file, make_media_file

pytestmark = pytest.mark.skipif(
    FFMPEG_BIN is None,
    reason="需要有 ffmpeg 才能生成真实媒体文件",
)

#: 时长断言容差（毫秒）
TOLERANCE_MS = 100


# ---------------------------------------------------------------------------
# T1 正常读取
# ---------------------------------------------------------------------------


def test_read_one_second_file(tmp_path) -> None:
    """T1: 1 秒素材应读出约 1000ms。"""
    media = make_media_file(tmp_path / "heart.mp4", seconds=1)

    measured = get_duration_ms(media)

    assert isinstance(measured, int)
    assert abs(measured - 1000) <= TOLERANCE_MS


def test_duration_is_integer_milliseconds(tmp_path) -> None:
    """返回值必须是整数毫秒，而非浮点秒。"""
    media = make_media_file(tmp_path / "idle.mp4", seconds=1)

    measured = get_duration_ms(media)

    assert isinstance(measured, int)
    assert not isinstance(measured, bool)


# ---------------------------------------------------------------------------
# T2 非 1 秒素材
# ---------------------------------------------------------------------------


def test_read_three_second_file(tmp_path) -> None:
    """T2: 3 秒素材应读出 3000ms ± 100ms。

    这条是"时长真值化"的核心证据 —— 旧实现无论文件多长都返回 1000。
    """
    media = make_media_file(tmp_path / "test_3s.mp4", seconds=3)

    measured = get_duration_ms(media)

    assert abs(measured - 3000) <= TOLERANCE_MS


def test_different_durations_are_distinguished(tmp_path) -> None:
    """不同时长素材读出不同结果（排除固定值嫌疑）。"""
    short = make_media_file(tmp_path / "short.mp4", seconds=1)
    long = make_media_file(tmp_path / "long.mp4", seconds=3)

    short_ms = get_duration_ms(short)
    long_ms = get_duration_ms(long)

    assert long_ms > short_ms
    assert long_ms - short_ms > 1500


def test_sub_second_precision_preserved(tmp_path) -> None:
    """亚秒级时长不被粗暴取整为整秒。"""
    media = make_media_file(tmp_path / "half.mp4", seconds=1.5)

    measured = get_duration_ms(media)

    assert abs(measured - 1500) <= TOLERANCE_MS


# ---------------------------------------------------------------------------
# T3 异常处理
# ---------------------------------------------------------------------------


def test_missing_file_raises_metadata_error(tmp_path) -> None:
    """T3: 文件不存在必须抛 ASSET_METADATA_ERROR，不得崩溃或返回 0。"""
    with pytest.raises(AssetMetadataError) as exc:
        get_duration_ms(tmp_path / "missing.mp4")

    assert exc.value.code == "ASSET_METADATA_ERROR"
    assert "Cannot read media duration" in str(exc.value) or "不存在" in exc.value.message


def test_directory_instead_of_file_raises(tmp_path) -> None:
    """传入目录同样报错，不得误判为可用媒体。"""
    folder = tmp_path / "not_a_file.mp4"
    folder.mkdir()

    with pytest.raises(AssetMetadataError):
        get_duration_ms(folder)


def test_invalid_media_content_raises(tmp_path) -> None:
    """内容非法（非媒体）的文件必须报 ASSET_METADATA_ERROR。"""
    fake = make_action_file(tmp_path, "cat", "broken")

    with pytest.raises(AssetMetadataError) as exc:
        get_duration_ms(fake)

    assert exc.value.code == "ASSET_METADATA_ERROR"


def test_explicit_missing_ffprobe_path_raises(tmp_path) -> None:
    """显式指定的 ffprobe 路径不存在时报错。"""
    media = make_media_file(tmp_path / "heart.mp4", seconds=1)

    with pytest.raises(AssetMetadataError):
        get_duration_ms(media, ffprobe_path=tmp_path / "no_such_ffprobe.exe")


def test_resolve_ffprobe_rejects_bad_path(tmp_path) -> None:
    """resolve_ffprobe 对不存在的显式路径必须失败。"""
    with pytest.raises(AssetMetadataError):
        resolve_ffprobe(tmp_path / "ghost_ffprobe")


def test_resolve_ffprobe_finds_path_binary() -> None:
    """未显式指定时应能从 PATH 解析到 ffprobe，且确实指向 ffprobe。"""
    resolved = resolve_ffprobe()

    assert resolved
    assert Path(resolved).is_file()
    assert "ffprobe" in Path(resolved).name.lower()


def test_error_payload_carries_context(tmp_path) -> None:
    """异常应携带可序列化上下文，便于 API 层透出。"""
    with pytest.raises(AssetMetadataError) as exc:
        get_duration_ms(tmp_path / "missing.mp4")

    payload = exc.value.to_dict()
    assert payload["code"] == "ASSET_METADATA_ERROR"
    assert "context" in payload


# ---------------------------------------------------------------------------
# T4 AssetManager 集成
# ---------------------------------------------------------------------------


def test_register_probes_real_duration(env: SimpleNamespace) -> None:
    """T4: register 未显式传 duration 时应读取真实时长。"""
    relative = "assets/pets/cat/actions/test/test.mp4"
    make_media_file(env.project_root / relative, seconds=3)

    metadata = env.manager.register("cat", "test", relative)

    assert abs(metadata.duration - 3000) <= TOLERANCE_MS
    # 关键断言：不再是旧的固定占位值
    assert metadata.duration != 1000


def test_register_duration_is_not_hardcoded(env: SimpleNamespace) -> None:
    """两个真实时长不同的素材，登记后 duration 必须不同。"""
    short_rel = "assets/pets/cat/actions/idle/idle.mp4"
    long_rel = "assets/pets/cat/actions/heart/heart.mp4"
    make_media_file(env.project_root / short_rel, seconds=1)
    make_media_file(env.project_root / long_rel, seconds=3)

    env.manager.register("cat", "idle", short_rel)
    env.manager.register("cat", "heart", long_rel)

    idle = env.manager.get_asset("cat", "idle")
    heart = env.manager.get_asset("cat", "heart")

    assert heart.duration > idle.duration
    assert heart.duration - idle.duration > 1500


def test_duration_persisted_to_database(env: SimpleNamespace) -> None:
    """探测到的 duration 必须落库，而非只存在于返回值。"""
    relative = "assets/pets/cat/actions/happy/happy.mp4"
    make_media_file(env.project_root / relative, seconds=3)

    env.manager.register("cat", "happy", relative)
    record = env.repository.find("cat", "happy")

    assert record is not None
    assert abs(record.duration - 3000) <= TOLERANCE_MS


def test_register_with_explicit_duration_skips_probe(
    env: SimpleNamespace,
) -> None:
    """显式传入 duration 时不做探测 —— 测试注入路径必须仍可用。

    用非媒体内容验证：如果走了 ffprobe，这里会抛 AssetMetadataError。
    """
    make_action_file(env.project_root, "cat", "later")

    metadata = env.manager.register(
        "cat",
        "later",
        "assets/pets/cat/actions/later/later.mp4",
        duration=1234,
    )

    assert metadata.duration == 1234


def test_register_missing_file_without_duration_raises(
    env: SimpleNamespace,
) -> None:
    """素材缺失且未显式给时长 → ASSET_METADATA_ERROR（无法声明时长）。"""
    with pytest.raises(AssetMetadataError):
        env.manager.register(
            "cat",
            "ghost",
            "assets/pets/cat/actions/ghost/ghost.mp4",
        )


def test_register_rejects_invalid_explicit_duration(
    env: SimpleNamespace,
) -> None:
    """显式 duration 仍受非法值校验保护。"""
    with pytest.raises(InvalidRequestError):
        env.manager.register(
            "cat", "heart", "assets/x.mp4", duration=-5
        )


def test_register_rejects_bool_duration(env: SimpleNamespace) -> None:
    """bool 是 int 的子类，但不应被当作合法时长。"""
    with pytest.raises(InvalidRequestError):
        env.manager.register("cat", "heart", "assets/x.mp4", duration=True)
