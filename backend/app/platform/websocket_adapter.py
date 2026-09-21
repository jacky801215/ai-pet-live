"""WebSocket adapter —— platform 层实时输入适配（WA-1 ~ WA-6 / WM-1 ~ WM-6）。

职责**恰三项**（WA-1，adapter 是门卫，不是裁判）：
1. 协议接收（原始 WS 文本消息）；
2. 格式检查（WM-1 envelope 恰 4 字段 + event_type ∈ 契约白名单 + payload 结构）；
3. 转交 `EventGateway.normalize()`（WA-3 唯一出口）。

**禁止**（PB-2 / WA-3）：任何业务判断；调用 ActionEngine / PlaybackManager /
repositories / DataManager 或任何 ``services/**`` 业务对象。

字段映射（WM-1，实现步已裁决口径，与契约测试 ``test_websocket_adapter_contract.py`` 一致）：
- ``timestamp`` / ``source`` 是**传输元数据，不出传输层**（丢弃，不出现在交付给
  normalize 的契约字段中——normalize 顶层只接受 event_type / user_id / user_name / payload）；
- ``event_type`` / ``payload`` 直传；
- ``user_id`` / ``user_name`` 不在本版承载（省略，由后端补默认；身份承载归实现步后续裁决）。

错误口径（WA-4）：非法 JSON / 字段 / event_type / payload 统一 **reject + log**，
不自动修复业务字段；reject 以 :class:`WebSocketAdapterRejectError` 表达。

状态（WA-2）：本类**无业务状态**——仅持有注入的 gateway 与 logger。
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from app.services.event_gateway import EventGateway

#: WM-1：envelope 恰 4 字段
ENVELOPE_KEYS = {"event_type", "payload", "timestamp", "source"}

#: WS-2 / 事件契约 v1.1：Phase 1 事件类型白名单（禁止 adapter 私自放宽）
ALLOWED_EVENT_TYPES = ("comment", "gift", "like", "system")

_logger = logging.getLogger(__name__)


class WebSocketAdapterRejectError(Exception):
    """WA-4：非法消息的唯一出路（reject + log）；不携带业务修复建议。"""


class WebSocketAdapter:
    """platform 层 WebSocket adapter（协议接收 / 格式检查 / 转交 normalize）。

    依赖面恰好体现 WA-1/WA-3：仅持有 ``gateway``（唯一出口）与可选 ``logger``；
    连接层（accept/close）归 transport，本类不管理连接（WA-2）。
    """

    def __init__(
        self,
        gateway: EventGateway,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self._gateway = gateway
        self._logger = logger if logger is not None else _logger.info

    def handle(self, raw_message: str):
        """处理一条原始 WS 文本消息，返回 normalize 产出的内部事件。

        非法消息 raise :class:`WebSocketAdapterRejectError`（已 log，调用方无须再记）。
        """
        # 1) 协议接收：非 JSON → reject + log（WA-4）
        try:
            envelope = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError):
            self._logger("reject: invalid json")
            raise WebSocketAdapterRejectError("invalid json")

        # 2) 格式检查：envelope 恰 4 字段（WM-1）
        if not isinstance(envelope, dict) or set(envelope.keys()) != ENVELOPE_KEYS:
            self._logger("reject: envelope shape")
            raise WebSocketAdapterRejectError("envelope shape")

        # 3) 格式检查：event_type ∈ 契约白名单（WS-2 / PB-3）
        event_type = envelope["event_type"]
        if event_type not in ALLOWED_EVENT_TYPES:
            self._logger(f"reject: unknown event_type {event_type!r}")
            raise WebSocketAdapterRejectError("unknown event_type")

        # 4) 格式检查：payload 必须是对象（事件契约）
        if not isinstance(envelope["payload"], dict):
            self._logger("reject: payload shape")
            raise WebSocketAdapterRejectError("payload shape")

        # 5) 转交 normalize（WA-3 唯一出口）——envelope → 内部事件契约字段映射：
        #    timestamp / source 丢弃（传输元数据，不出传输层，WM-1）；
        #    user_id / user_name 省略（后端补默认；身份承载归后续裁决）。
        contract_event = {
            "event_type": envelope["event_type"],
            "payload": envelope["payload"],
        }
        return self._gateway.normalize(contract_event)


def build_websocket_adapter(gateway: EventGateway | None = None) -> WebSocketAdapter:
    """platform 层装配点：构造 adapter 并注入无状态 :class:`EventGateway`。

    ``EventGateway`` 是**无状态**的规范化入口，adapter 级实例与组合根实例在
    「传输层只到 normalize」的本阶段语义下等价；「WS 事件与 ``simulate`` 共用
    组合根 gateway 并进入动作链」的完整接线**不在本步**——那需要修改
    ``app/services/pipeline.py``（不在 2.2-3B-2 授权范围）且须新决策文档授权。

    Args:
        gateway: 显式注入（测试用 spy）；``None`` 时新建无状态实例。
    """
    return WebSocketAdapter(gateway if gateway is not None else EventGateway())
