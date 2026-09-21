"""WebSocket adapter 实现测试（Phase 2.2-3B-1）——验证真实 :mod:`app.platform.websocket_adapter`。

与契约测试（``test_websocket_adapter_contract.py``，基于 ReferenceAdapter 规范模型）互补：
本文件对**真实 adapter** 逐条复验 WT-1 ~ WT-6 行为，并追加实现细节守卫：

- timestamp / source 丢弃（WM-1 映射口径，通过包装 gateway 捕获交付参数验证）；
- 源码静态守卫：零引擎 / repositories / services import（WA-3，剥注释）；
- 合法消息产出真实内部事件（Event）。
"""

import json
import re
from pathlib import Path

import pytest

from app.platform.websocket_adapter import (
    WebSocketAdapter,
    WebSocketAdapterRejectError,
)
from app.services.event_gateway import EventGateway

VALID_ENVELOPE = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
    "timestamp": "2026-09-21T03:00:00Z",
    "source": "ws",
}


class GatewaySpy:
    """包装真实 EventGateway：记录交付参数、复用真实 normalize。"""

    def __init__(self):
        self._real = EventGateway()
        self.calls = []

    def normalize(self, raw_event: dict):
        self.calls.append(raw_event)
        return self._real.normalize(raw_event)


@pytest.fixture()
def gateway_spy():
    return GatewaySpy()


@pytest.fixture()
def logger_spy():
    calls = []

    def log(message: str):
        calls.append(message)

    log.calls = calls
    return log


@pytest.fixture()
def adapter(gateway_spy, logger_spy):
    return WebSocketAdapter(gateway_spy, logger_spy)


# ---------------------------------------------------------------------------
# WT 等价行为（对真实 adapter 复验契约规则）
# ---------------------------------------------------------------------------

def test_wt1_impl_valid_envelope_returns_event(adapter, gateway_spy):
    """合法 envelope → normalize 恰一次，产出真实内部事件。"""
    event = adapter.handle(json.dumps(VALID_ENVELOPE))

    assert len(gateway_spy.calls) == 1
    assert event.event_type == "gift"  # 真实 Event 对象
    assert event.payload == {"gift_name": "小心心", "gift_count": 1}


def test_wt2_impl_invalid_json_rejected(adapter, gateway_spy, logger_spy):
    with pytest.raises(WebSocketAdapterRejectError):
        adapter.handle("{not-json")
    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1


def test_wt3_impl_missing_event_type_rejected(adapter, gateway_spy, logger_spy):
    broken = {k: v for k, v in VALID_ENVELOPE.items() if k != "event_type"}
    with pytest.raises(WebSocketAdapterRejectError):
        adapter.handle(json.dumps(broken))
    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1


def test_wt4_impl_unknown_event_type_rejected_and_logged(adapter, gateway_spy, logger_spy):
    unknown = dict(VALID_ENVELOPE, event_type="follow")
    with pytest.raises(WebSocketAdapterRejectError):
        adapter.handle(json.dumps(unknown))
    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1
    assert "follow" in logger_spy.calls[0]


def test_wt6_impl_keeps_no_business_state(adapter, gateway_spy):
    """处理前后实例属性集不变；同消息重复处理无缓存。"""
    before = set(vars(adapter).keys())
    raw = json.dumps(VALID_ENVELOPE)

    adapter.handle(raw)
    after_first = set(vars(adapter).keys())
    adapter.handle(raw)
    after_second = set(vars(adapter).keys())

    assert before == after_first == after_second
    assert len(gateway_spy.calls) == 2


# ---------------------------------------------------------------------------
# 实现细节守卫（WM-1 映射口径 / WA-3 静态边界）
# ---------------------------------------------------------------------------

def test_impl_drops_transport_metadata(adapter, gateway_spy):
    """timestamp / source 是传输元数据：不出现在交付给 normalize 的契约字段中。"""
    adapter.handle(json.dumps(VALID_ENVELOPE))

    delivered = gateway_spy.calls[0]
    assert set(delivered.keys()) == {"event_type", "payload"}  # 恰 2 键
    assert "timestamp" not in delivered
    assert "source" not in delivered


def test_impl_source_imports_static_guard():
    """WA-3 静态守卫：adapter 源码零引擎 / repositories / services 业务 import。"""
    source = Path(__file__).resolve().parents[2] / "app" / "platform" / "websocket_adapter.py"
    code = source.read_text(encoding="utf-8")
    # 剥离注释后断言
    stripped = re.sub(r'"""[\s\S]*?"""', "", code)
    stripped = re.sub(r"^\s*#.*$", "", stripped, flags=re.M)

    assert "ActionEngine" not in stripped
    assert "PlaybackManager" not in stripped
    assert "DataManager" not in stripped
    assert "repositories" not in stripped
    # 精确口径（WA-3）：services 引用允许且仅允许 event_gateway（唯一出口的类型引用）
    services_imports = re.findall(r"from\s+app\.services\.(\w+)", stripped)
    assert services_imports == ["event_gateway"]


def test_impl_no_new_dependencies():
    """RB/WA-6：零新依赖——requirements 不含 websocket 库（本步零 requirements 变更）。"""
    req = (
        Path(__file__).resolve().parents[2] / "requirements.txt"
    )
    if req.exists():
        text = req.read_text(encoding="utf-8").lower()
        for banned in ("websockets", "socketio", "python-socketio"):
            assert banned not in text
