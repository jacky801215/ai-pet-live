"""WebSocket dispatcher —— platform 层**出站推送**端口（WP-1 ~ WP-5 / WC-4 / WC-5）。

与 :mod:`app.platform.websocket_adapter` 严格对称、但**方向相反**（WP-1「dispatcher != adapter」）：

===============  =========  ================================  ==========================
模块              方向        职责                              输出
===============  =========  ================================  ==========================
``...adapter``    inbound    接收 / 格式检查 / 转交 normalize   交付内部事件 **或** 拒收
``...dispatcher`` outbound   组装 envelope / ``send_json``     已发送 **或** 已 log
===============  =========  ================================  ==========================

职责**恰三项**（WP-1 / WP-3 / WP-5）：

1. 接收**已 commit** 的内部事件（``Event``）——由 transport 在 :meth:`SimulationPipeline.apply_event`
   **成功返回之后**传入（WC-1 / WC-2：commit point = ``apply_event()`` 返回前）；
2. 组装出站帧 —— **事件帧** = **WM-1 envelope**（恰 4 字段 ``event_type`` / ``payload`` /
   ``timestamp`` / ``source``，WP-3）；**状态帧** = CR-6 第二类帧（七字段快照）；
   **音效帧** = CR-11 第三类帧（4 字段载荷 + 判别键 ``type``）；
3. 经 transport socket 发出（``websocket.send_json``）；**失败只 log**，不上抛（WP-5 / WC-5）。

**两类出站帧**（**WP-3 v1.1**，CR-6 受权增量）：

1. **事件帧** —— 上述 **WM-1 envelope**（恰 4 字段，**逐字不变**），由 :meth:`send_event` 发出；
2. **状态帧** —— ``{"type": "playback_state", "snapshot": <API-2 七字段>}``，由
   :meth:`send_state_frame` 在**连接空闲**时发出（**CR-6**：idle 到期后的**状态同步**，
   **不是**播放驱动机制）。

**音效帧（第三类，CR-11 受权增量）** —— ``{"type": "playback_audio", "pet_id", "action",
"audio_url", "seq"}``，由 :meth:`send_audio_frame` 在**动作被受理**时发出。
⛔ 它与状态帧**语义相反**：状态帧是**电平触发 + 变化去重**（仅变化时推），而音效帧是
**边缘触发**（每次受理各推一次）；把音效塞进状态帧会让「同动作连触两次」的第二次**静默漏播**。
契约见 ``docs/change_request/cr-11_audio_feedback_design.md`` §4.3。

**禁止**（WP-1 / WP-2 / WP-4 / WC-4 / WC-6）：

- ❌ runtime mutation；❌ 调用 ``pipeline`` / ``ActionEngine`` / ``PlaybackManager``；
- ❌ 持有 ``EventGateway``（``gateway``）；
- ❌ connection registry / room / broadcast / multi client；
- ❌ retry / reconnect / buffer（缓冲队列）/ ack / replay；
- ❌ 增删 **envelope** 字段（该约束**仅**适用于事件帧）、❌ 发送**播放派生字段**
  （``duration`` / ``progress`` / ``video_state`` / ``queue``）；**CR-6** 起状态帧
  **只允许**原样携带 API-2 的 ``PlaybackState`` **7 字段**（不新增 / 不改名 / 不派生）；
  **CR-11** 音效帧**只允许** :data:`AUDIO_FRAME_FIELDS` 声明的字段（不新增 / 不改名）。

状态（对齐 WA-2「连接不得携带业务状态」）：本类**无业务状态**——仅持有可注入的时钟与
logger；连接对象由调用方（transport 端点）**逐次传入**，本类**不持有** socket（WP-4：
connection 生命周期归 transport）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Protocol

if TYPE_CHECKING:  # 仅类型引用：运行期零新依赖（不 import services / 不 import 引擎）
    from app.models.event import Event

__all__ = [
    "PUSH_SOURCE",
    "ENVELOPE_FIELDS",
    "STATE_FRAME_TYPE",
    "AUDIO_FRAME_TYPE",
    "AUDIO_FRAME_FIELDS",
    "SupportsSendJSON",
    "WebSocketDispatcher",
]

_logger = logging.getLogger(__name__)

#: WP-3 / WM-1：出站帧 ``source`` 固定取值（transport 侧元数据）
PUSH_SOURCE = "ws"

#: WM-1：envelope **恰 4 字段**（顺序即输出顺序，便于契约阅读与逐字比对）
ENVELOPE_FIELDS: tuple[str, ...] = ("event_type", "payload", "timestamp", "source")

#: CR-6：状态帧顶层 ``type`` 取值 —— 前端**帧型判别键**（``type`` **仅**存在于状态帧，
#: 事件帧（WM-1）逐字不变 ⇒ 两类帧可由 ``type`` 在场与否无损区分）
STATE_FRAME_TYPE = "playback_state"

#: **CR-11**：音效帧顶层 ``type`` 取值 —— 第三类出站帧的**帧型判别键**。
#: 与 :data:`STATE_FRAME_TYPE`、WM-1 envelope **三者两两互斥**（前端据 ``type`` 无损分流）。
AUDIO_FRAME_TYPE = "playback_audio"

#: **CR-11**：音效帧**恰 4 个载荷字段**（**不含**判别键 ``type``，顺序即输出顺序）。
#: ⛔ 不得增删改名 —— 前端按**精确键集**做形状校验（``PLAYBACK_AUDIO_KEYS`` 含 ``type``）。
AUDIO_FRAME_FIELDS: tuple[str, ...] = ("pet_id", "action", "audio_url", "seq")


class SupportsSendJSON(Protocol):
    """transport socket 的**最小**形状——只依赖 ``send_json``，不绑定具体实现。

    （``fastapi.WebSocket`` / Starlette WebSocket 天然满足；测试可用替身对象。）
    """

    async def send_json(self, data: Any) -> None:  # pragma: no cover - 协议声明
        ...


def _utc_now() -> datetime:
    """当前 UTC 时刻（transport 侧生成 ``timestamp``；可注入以便测试固定）。"""
    return datetime.now(timezone.utc)


def _format_utc(moment: datetime) -> str:
    """UTC 时刻 → ISO-8601（``YYYY-MM-DDTHH:MM:SSZ``）——WM-1 ``timestamp`` 口径。

    无 tzinfo 的朴素时刻按 UTC 解释（防御：避免本地时区泄漏进线上帧）。
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WebSocketDispatcher:
    """platform 层出站推送端口（transport outbound only，WP-1）。

    依赖面体现 WP-1 / WP-4：**不持有** socket / gateway / 连接集合；仅持有可注入的
    时钟与 logger。调用方（``api/ws.py``）在 commit 之后**逐次**传入 ``event`` 与 ``websocket``。
    """

    def __init__(
        self,
        *,
        now: Optional[Callable[[], datetime]] = None,
        logger: Optional[Callable[..., None]] = None,
    ) -> None:
        self._now = now if now is not None else _utc_now
        # 默认走 logging.exception（发送失败需带栈）；测试可注入捕获函数
        self._logger = logger if logger is not None else _logger.exception

    # -- 组装（WP-3） -------------------------------------------------------

    def build_envelope(self, event: Event) -> dict[str, Any]:
        """由**已 commit** 的内部事件组装 **WM-1 envelope**（恰 4 字段，WP-3）。

        - ``event_type`` / ``payload``：取自内部事件（``payload`` 做浅拷贝，避免与
          入库对象共享可变引用）；
        - ``timestamp``：**transport 侧生成**（内部 ``Event`` 不含二者——adapter 在
          normalize 时已按 WM-1 丢弃传输元数据）；
        - ``source``：固定 :data:`PUSH_SOURCE`（``"ws"``）。

        **不**新增 envelope 字段；**不**在本帧内携带任何 PlaybackState 字段
        （状态同步走 :meth:`send_state_frame` 的**独立状态帧**，WP-3 v1.1 / CR-6）。
        """
        return {
            "event_type": event.event_type,
            "payload": dict(event.payload),
            "timestamp": _format_utc(self._now()),
            "source": PUSH_SOURCE,
        }

    # -- 发送（WP-5 / WC-5） ------------------------------------------------

    def build_state_frame(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """由**已序列化**的 API-2 快照组装 **状态帧**（**CR-6** / WP-3 v1.1 第二类出站帧）。

        - ``type``：固定 :data:`STATE_FRAME_TYPE`（帧型判别键）；
        - ``snapshot``：API-2 的 ``PlaybackState`` **7 字段原样**（浅拷贝，**不**新增派生字段）。

        仍**不**发送 ``duration`` / ``progress`` / ``video_state`` / ``queue``。
        """
        return {"type": STATE_FRAME_TYPE, "snapshot": dict(snapshot)}

    def build_audio_frame(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """由**已解析**的音频载荷组装 **音效帧**（**CR-11** / 第三类出站帧）。

        - ``type``：固定 :data:`AUDIO_FRAME_TYPE`（帧型判别键）；
        - 其余字段：**恰** :data:`AUDIO_FRAME_FIELDS` 声明的 4 项（浅拷贝，**不**派生、
          **不**改写 ``audio_url`` —— URL 由后端 ``AssetManager`` + ``to_asset_url()`` 产出）。

        仍**不**发送 ``duration`` / ``progress`` / ``video_state`` / ``queue``。
        """
        return {"type": AUDIO_FRAME_TYPE, **{k: payload[k] for k in AUDIO_FRAME_FIELDS}}

    async def send_event(self, event: Event, websocket: SupportsSendJSON) -> bool:
        """在 runtime **commit point 之后**把该事件以 WM-1 envelope 推送（WC-4）。

        Returns:
            ``True`` = 已发出；``False`` = 发送失败（**仅 log**，WP-5）。

        **不抛异常**（WC-5）：任何组装 / 发送异常都收敛为 ``log`` + ``False``，
        绝不向上抛入 inbound 处理循环，也不回滚已提交的 runtime mutation。
        """
        try:
            envelope = self.build_envelope(event)
            await websocket.send_json(envelope)
        except Exception:  # noqa: BLE001 - WP-5：失败只 log，不上抛、不重试
            self._logger(
                "websocket push failed: event_type=%s",
                getattr(event, "event_type", None),
            )
            return False
        return True

    async def send_state_frame(
        self, snapshot: Mapping[str, Any], websocket: SupportsSendJSON
    ) -> bool:
        """在**连接空闲**时推送**状态帧**（**CR-6**：到期后的状态同步，非播放驱动）。

        Returns:
            ``True`` = 已发出；``False`` = 发送失败（**仅 log**，WP-5）。

        **不抛异常**（WC-5）：组装 / 发送异常一律收敛为 ``log`` + ``False``，绝不向上
        抛入 inbound 处理循环，也不回滚已提交的 runtime mutation。
        """
        try:
            frame = self.build_state_frame(snapshot)
            await websocket.send_json(frame)
        except Exception:  # noqa: BLE001 - WP-5：失败只 log，不上抛、不重试
            self._logger("websocket state push failed: type=%s", STATE_FRAME_TYPE)
            return False
        return True

    async def send_audio_frame(
        self, payload: Mapping[str, Any], websocket: SupportsSendJSON
    ) -> bool:
        """在**动作被受理**时推送**音效帧**（**CR-11**：边缘触发，不参与状态去重）。

        Returns:
            ``True`` = 已发出；``False`` = 发送失败（**仅 log**，WP-5）。

        **不抛异常**（WC-5）：组装 / 发送异常一律收敛为 ``log`` + ``False``，
        绝不向上抛入 inbound 处理循环 —— 音效失败**不得**影响已提交的 runtime mutation，
        也**不得**影响同一次事件的事件帧 / 状态帧推送。
        """
        try:
            frame = self.build_audio_frame(payload)
            await websocket.send_json(frame)
        except Exception:  # noqa: BLE001 - WP-5：失败只 log，不上抛、不重试
            self._logger("websocket audio push failed: type=%s", AUDIO_FRAME_TYPE)
            return False
        return True
