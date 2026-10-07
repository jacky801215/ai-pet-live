"""CR-11 音效帧（``playback_audio``）transport 测试 —— 端到端 + 单元。

契约来源：``docs/change_request/cr-11_audio_feedback_design.md`` §4.3。

被锁定的行为：

    ① **边缘触发**：动作被受理 ⇒ 各下发**一条**音效帧；**同动作连触两次 ⇒ 恰 2 条**
       （若把音效挂在状态帧的「变化才推」上，第二次会被静默吞掉 —— 本测试即该负对照的守卫）；
    ② **`seq` 单调递增**（前端判定「新触发」的唯一依据）；
    ③ **不下发**情形（均为正常）：未受理动作（未命中规则）、动作未登记音效；
    ④ **既有帧零变化**：事件帧仍恰 WM-1 **4 字段**；状态帧仍 `{type, snapshot}` 且
       `snapshot` 恰 API-2 **7 字段**（三类帧两两互斥、可无损区分）；
    ⑤ `audio_url` **由后端产出**（`AssetManager` + `to_asset_url()`），transport 不拼路径。

隔离：临时 ``project_root`` + 临时 SQLite + 真实 DDL，**绝不触碰**真实 ``database/pet_live.db``。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import ws as ws_module
from app.api.ws import get_pipeline, get_ws_dispatcher
from app.config.settings import Settings
from app.core import constants
from app.main import create_app
from app.platform.websocket_dispatcher import (
    AUDIO_FRAME_FIELDS,
    AUDIO_FRAME_TYPE,
    WebSocketDispatcher,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.services.asset_manager import AssetManager
from app.services.pipeline import SimulationPipeline
from tests.conftest import (
    audio_rel_path,
    make_action_file,
    register_asset,
)

#: 命中规则：``gift`` + ``小心心`` ⇒ ``heart``（与 ``test_pipeline.py`` 同源）
GIFT_HEART: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
}
#: 不命中任何规则（⇒ 无动作 ⇒ 不下发音效帧）
COMMENT: dict = {"event_type": "comment", "payload": {"content": "你好"}}

#: 素材时长取得足够大，避免测试期间播放窗口到期（不依赖假时钟）
ASSET_DURATION_MS: int = 3_600_000

#: 音效帧顶层键集（含帧型判别键 ``type``）
AUDIO_FRAME_KEYS: frozenset[str] = frozenset({"type", *AUDIO_FRAME_FIELDS})
#: WM-1 envelope（WP-3：恰 4 字段）
ENVELOPE_KEYS: frozenset[str] = frozenset(
    {"event_type", "payload", "timestamp", "source"}
)
#: API-2 ``PlaybackState``（恰 7 字段）
STATE_KEYS: frozenset[str] = frozenset(
    {"pet_id", "state", "action", "asset_url", "queue_size", "last_event", "loop"}
)


def _envelope(raw: dict) -> dict:
    """把内部事件 dict 包成 WM-1 传输 envelope（transport 侧元数据由 adapter 丢弃）。"""
    return {**raw, "timestamp": "2026-10-07T00:00:00Z", "source": "ws"}


class AudioFrameRecorder(WebSocketDispatcher):
    """记录音效帧（**真实发出** + 记录载荷）——用于断言「每次受理各推一次」。"""

    def __init__(self) -> None:
        super().__init__()
        self.audio_frames: list[dict] = []

    async def send_audio_frame(self, payload, websocket) -> bool:
        sent = await super().send_audio_frame(payload, websocket)
        self.audio_frames.append(dict(payload))
        return sent


@pytest.fixture()
def audio_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """隔离环境：cat 的 ``heart`` / ``happy`` **登记了音效**，``idle`` **无音效**。"""
    monkeypatch.setattr(ws_module, "STATE_PUSH_TICK_SECONDS", 0.01)

    assets_root = tmp_path / "assets" / "pets"
    cat_dir = assets_root / "cat"
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "config.json").write_text(
        json.dumps({"pet_id": "cat_001", "pet_type": "cat"}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = Settings(
        project_root=tmp_path,
        assets_root=assets_root,
        database_path=tmp_path / "audio_push.db",
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    database = Database(settings.database_path, settings.schema_path)
    database.initialize()
    manager = AssetManager(AssetRepository(database), settings)

    for action, with_audio in (("idle", False), ("heart", True), ("happy", True)):
        make_action_file(tmp_path, "cat", action)
        register_asset(
            manager,
            "cat",
            action,
            duration=ASSET_DURATION_MS,
            audio_path=audio_rel_path("cat", action) if with_audio else None,
        )

    pipeline = SimulationPipeline(settings=settings)
    dispatcher = AudioFrameRecorder()

    app = create_app(static_dir=assets_root)
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_ws_dispatcher] = lambda: dispatcher

    return SimpleNamespace(
        client=TestClient(app),
        pipeline=pipeline,
        dispatcher=dispatcher,
        manager=manager,
    )


# ---------------------------------------------------------------------------
# ① / ② 边缘触发 + seq 递增（核心：同动作连触两次不得被去重吞掉）
# ---------------------------------------------------------------------------


def test_same_action_twice_pushes_two_audio_frames(audio_env: SimpleNamespace) -> None:
    """**核心**：同动作连续受理两次 ⇒ 音效帧**恰 2 条**，``seq`` 严格递增。"""
    with audio_env.client.websocket_connect("/api/ws") as ws:
        for _ in range(2):
            ws.send_text(json.dumps(_envelope(GIFT_HEART)))
            ws.receive_json()  # 事件帧
            ws.receive_json()  # 音效帧
            ws.receive_json()  # 状态帧（队列 / 状态变化）

    frames = audio_env.dispatcher.audio_frames
    assert len(frames) == 2, frames
    assert [f["action"] for f in frames] == ["heart", "heart"]
    assert [f["pet_id"] for f in frames] == ["cat_001", "cat_001"]
    assert all(
        f["audio_url"] == "/assets/pets/cat/actions/heart/heart.ogg" for f in frames
    )
    assert frames[0]["seq"] < frames[1]["seq"], frames


def test_audio_frame_is_edge_triggered_though_state_frame_dedupes(
    audio_env: SimpleNamespace,
) -> None:
    """对照：状态帧「变化才推」**不影响**音效帧 —— 第二次受理的状态帧内容可不同，
    但即便完全相同时音效帧仍必须各推一次（这就是音效不能挂在状态帧上的原因）。"""
    with audio_env.client.websocket_connect("/api/ws") as ws:
        for _ in range(3):
            ws.send_text(json.dumps(_envelope(GIFT_HEART)))
            for _ in range(3):
                ws.receive_json()

    seqs = [f["seq"] for f in audio_env.dispatcher.audio_frames]
    assert len(seqs) == 3
    assert seqs == sorted(set(seqs))  # 严格单调、无重复


# ---------------------------------------------------------------------------
# ③ 不下发（正常情形）
# ---------------------------------------------------------------------------


def test_no_audio_frame_when_event_has_no_action(audio_env: SimpleNamespace) -> None:
    """未命中规则 ⇒ 无动作 ⇒ **不下发**音效帧（且不报错、连接继续可用）。"""
    with audio_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(_envelope(COMMENT)))
        ws.receive_json()  # 事件帧（WM-1）
        ws.receive_json()  # 状态帧（last_event 变化）

    assert audio_env.dispatcher.audio_frames == []


def test_no_audio_frame_when_action_has_no_registered_audio(
    audio_env: SimpleNamespace,
) -> None:
    """动作**未登记音效**（``audio_path`` 为 ``NULL``）⇒ 不下发；解除登记后即可下发。"""
    pipeline = audio_env.pipeline
    monkeypatch_manager = audio_env.manager
    pipeline._last_action = "idle"  # 直接构造「受理了 idle」的边缘（idle 无音效）
    assert ws_module._read_audio_frame(pipeline) is None

    # 对照：heart 已登记音效 ⇒ 可解析
    pipeline._last_action = "heart"
    payload = ws_module._read_audio_frame(pipeline)
    assert payload is not None
    assert payload["audio_url"] == "/assets/pets/cat/actions/heart/heart.ogg"

    # 对照：把 heart 的音效撤掉 ⇒ 立即不下发（全量覆盖语义）
    register_asset(monkeypatch_manager, "cat", "heart", duration=ASSET_DURATION_MS)
    assert ws_module._read_audio_frame(pipeline) is None


def test_no_audio_frame_without_action_edge(audio_env: SimpleNamespace) -> None:
    """未受理动作（``last_action`` 为空）⇒ ``None``（不下发）。"""
    audio_env.pipeline._last_action = None
    assert ws_module._read_audio_frame(audio_env.pipeline) is None


# ---------------------------------------------------------------------------
# ④ 既有帧零变化（三类帧两两互斥、可无损区分）
# ---------------------------------------------------------------------------


def test_three_frame_types_are_mutually_exclusive(audio_env: SimpleNamespace) -> None:
    """事件帧 / 状态帧 / 音效帧 的键集**两两不相交**（``type`` 只存在于后两类）。"""
    with audio_env.client.websocket_connect("/api/ws") as ws:
        ws.send_text(json.dumps(_envelope(GIFT_HEART)))
        envelope, audio, state = (ws.receive_json() for _ in range(3))

    assert set(envelope) == ENVELOPE_KEYS  # WM-1 恰 4 字段，逐字不变
    assert AUDIO_FRAME_TYPE == "playback_audio"
    assert set(audio) == AUDIO_FRAME_KEYS
    assert audio["type"] == AUDIO_FRAME_TYPE
    assert set(state) == {"type", "snapshot"}
    assert set(state["snapshot"]) == STATE_KEYS  # API-2 恰 7 字段

    # 互斥性：音效帧不含 snapshot / event_type；状态帧不含 action/seq 等音效字段
    assert ENVELOPE_KEYS.isdisjoint(AUDIO_FRAME_KEYS)
    assert "type" not in envelope and "type" not in state["snapshot"]


def test_dispatcher_build_audio_frame_is_strict(audio_env: SimpleNamespace) -> None:
    """``build_audio_frame``：**恰** :data:`AUDIO_FRAME_FIELDS` + 判别键，多余键被丢弃。"""
    dispatcher = WebSocketDispatcher()
    frame = dispatcher.build_audio_frame(
        {
            "pet_id": "cat_001",
            "action": "heart",
            "audio_url": "/assets/pets/cat/actions/heart/heart.ogg",
            "seq": 3,
            "duration": 999,
            "progress": 0.5,
        }
    )
    assert set(frame) == AUDIO_FRAME_KEYS
    assert frame == {
        "type": AUDIO_FRAME_TYPE,
        "pet_id": "cat_001",
        "action": "heart",
        "audio_url": "/assets/pets/cat/actions/heart/heart.ogg",
        "seq": 3,
    }


def test_dispatcher_send_audio_frame_swallows_failure() -> None:
    """``send_audio_frame``：发送异常只 log + ``False``（**不上抛** —— WP-5 / WC-5）。"""
    import asyncio

    logs: list[str] = []

    class Boom:
        async def send_json(self, data: object) -> None:
            raise RuntimeError("boom")

    dispatcher = WebSocketDispatcher(logger=lambda *a, **k: logs.append(str(a[0])))
    sent = asyncio.run(
        dispatcher.send_audio_frame(
            {
                "pet_id": "cat_001",
                "action": "heart",
                "audio_url": "/x.ogg",
                "seq": 1,
            },
            Boom(),
        )
    )
    assert sent is False
    assert logs == ["websocket audio push failed: type=%s"]
