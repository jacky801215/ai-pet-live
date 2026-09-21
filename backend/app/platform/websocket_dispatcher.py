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
2. 组装 **WM-1 envelope**（恰 4 字段 ``event_type`` / ``payload`` / ``timestamp`` / ``source``，WP-3）；
3. 经 transport socket 发出（``websocket.send_json``）；**失败只 log**，不上抛（WP-5 / WC-5）。

**禁止**（WP-1 / WP-2 / WP-4 / WC-4 / WC-6）：

- ❌ runtime mutation；❌ 调用 ``pipeline`` / ``ActionEngine`` / ``PlaybackManager``；
- ❌ 持有 ``EventGateway``（``gateway``）；
- ❌ connection registry / room / broadcast / multi client；
- ❌ retry / reconnect / buffer（缓冲队列）/ ack / replay；
- ❌ 增删 envelope 字段、❌ 发送 PlaybackState 快照（WS-4 / WP-3：6 字段冻结，禁
  ``duration`` / ``progress`` / ``video_state`` / ``queue``）。

状态（对齐 WA-2「连接不得携带业务状态」）：本类**无业务状态**——仅持有可注入的时钟与
logger；连接对象由调用方（transport 端点）**逐次传入**，本类**不持有** socket（WP-4：
connection 生命周期归 transport）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional, Protocol

if TYPE_CHECKING:  # 仅类型引用：运行期零新依赖（不 import services / 不 import 引擎）
    from app.models.event import Event

__all__ = [
    "PUSH_SOURCE",
    "ENVELOPE_FIELDS",
    "SupportsSendJSON",
    "WebSocketDispatcher",
]

_logger = logging.getLogger(__name__)

#: WP-3 / WM-1：出站帧 ``source`` 固定取值（transport 侧元数据）
PUSH_SOURCE = "ws"

#: WM-1：envelope **恰 4 字段**（顺序即输出顺序，便于契约阅读与逐字比对）
ENVELOPE_FIELDS: tuple[str, ...] = ("event_type", "payload", "timestamp", "source")


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

        **不**新增字段、**不**发送 PlaybackState 快照（WS-4 / WP-3）。
        """
        return {
            "event_type": event.event_type,
            "payload": dict(event.payload),
            "timestamp": _format_utc(self._now()),
            "source": PUSH_SOURCE,
        }

    # -- 发送（WP-5 / WC-5） ------------------------------------------------

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
