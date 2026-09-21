"""WebSocket adapter 契约测试（Phase 2.2-3A，测试先行 —— WA-1 ~ WA-6 / WM-1 / WS-2 行为守卫）。

**性质声明（必读）**：本文件是"契约即测试"（spec-as-test）——
`ReferenceAdapter` 是**测试夹具层的契约参考模型**（mock/fixture，指令允许范围），
**不是生产实现**（src/ 零改动）。它把 WA 冻结文档中的 adapter 行为规则固化为可执行规范：

- 未来 `app/platform/websocket_adapter.py` 落地时，将 fixture 替换为真实 import，
  测试结构与断言不变（WT-1 ~ WT-6 逐条映射为对真实实现的验收）；
- 在 adapter 实现落地前，本文件守卫的是**契约规则本身**：
  任何对 WA/WM 冻结条款的偏离（例如有人试图让 adapter 调用引擎）都会先在这里被发现。

契约来源：
- WA-1：职责恰三项（协议接收 / 格式检查 / 转交 normalize），禁业务判断；
- WA-3：输出只有两种（交付 Gateway / 拒收）；禁调引擎 / Store / repositories；
- WA-4：非法 JSON / 字段 / event_type / payload 统一 reject + log，禁自动修复；
- WM-1：envelope 恰 4 字段（event_type / payload / timestamp / source）；
- WS-2：唯一入口 EventGateway.normalize()，event_type ∈ 契约 v1.1 白名单。
"""

import json
from unittest.mock import MagicMock

import pytest

from app.services.event_gateway import EventGateway

# ---------------------------------------------------------------------------
# 契约常量（镜像 WA / WM / 事件契约 v1.1 冻结，禁止在此放宽）
# ---------------------------------------------------------------------------

#: WM-1：envelope 恰 4 字段
ENVELOPE_KEYS = {"event_type", "payload", "timestamp", "source"}
#: WS-2 / 事件契约 v1.1：Phase 1 事件类型白名单
ALLOWED_EVENT_TYPES = ("comment", "gift", "like", "system")

VALID_ENVELOPE = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
    "timestamp": "2026-09-21T03:00:00Z",
    "source": "ws",
}


class Reject(Exception):
    """adapter 对非法输入的唯一出路之一（WA-4：reject + log）。"""


class ReferenceAdapter:
    """契约参考模型（fixture，非生产实现）。

    依赖面恰好体现 WA-1/WA-3：normalize（EventGateway 的入口）+ logger，仅此两个；
    spy 依赖（action_engine / playback_manager / repositories）仅用于 WT-5 的
    "零调用"断言注入——契约模型本身**从不**触碰它们。
    """

    def __init__(self, normalize, logger, *, forbidden_spies=None):
        self._normalize = normalize
        self._logger = logger
        self._forbidden = tuple(forbidden_spies or ())

    def handle(self, raw_message: str) -> dict:
        """处理一条原始 WS 文本消息（WA-1：协议接收 → 格式检查 → 转交 normalize）。"""
        # 1) 协议接收：非 JSON → reject + log（WA-4）
        try:
            envelope = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError):
            self._logger("reject: invalid json")
            raise Reject("invalid json")

        # 2) 格式检查：envelope 恰 4 字段（WM-1）
        if not isinstance(envelope, dict) or set(envelope.keys()) != ENVELOPE_KEYS:
            self._logger("reject: envelope shape")
            raise Reject("envelope shape")

        # 3) 格式检查：event_type ∈ 契约白名单（WS-2）
        event_type = envelope["event_type"]
        if event_type not in ALLOWED_EVENT_TYPES:
            self._logger(f"reject: unknown event_type {event_type!r}")
            raise Reject("unknown event_type")

        # 4) 格式检查：payload 必须是对象（事件契约）
        if not isinstance(envelope["payload"], dict):
            self._logger("reject: payload shape")
            raise Reject("payload shape")

        # 5) 转交 normalize（WA-3：唯一出口）——含 envelope → 内部事件契约的字段映射：
        #    timestamp / source 是传输元数据（WM-1），不进入核心事件契约
        #    （normalize 顶层只接受 event_type / user_id / user_name / payload）；
        #    user_id / user_name 身份承载待实现步裁决（WM-1），本模型省略（后端补默认）。
        contract_event = {
            "event_type": envelope["event_type"],
            "payload": envelope["payload"],
        }
        return self._normalize(contract_event)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def gateway_spy():
    """EventGateway.normalize 的 spy（以真实 Gateway 包一层调用记录）。"""
    real = EventGateway()
    calls = []

    def normalize(raw_event: dict):
        calls.append(raw_event)
        return real.normalize(raw_event)

    normalize.calls = calls
    return normalize


@pytest.fixture()
def logger_spy():
    calls = []

    def log(message: str):
        calls.append(message)

    log.calls = calls
    return log


@pytest.fixture()
def forbidden_spies():
    """WA-3：adapter 禁止触碰的对象（spy 注入，期望全程零调用）。"""
    return {
        "action_engine": MagicMock(name="ActionEngine"),
        "playback_manager": MagicMock(name="PlaybackManager"),
        "repositories": MagicMock(name="repositories"),
    }


@pytest.fixture()
def adapter(gateway_spy, logger_spy, forbidden_spies):
    return ReferenceAdapter(
        gateway_spy,
        logger_spy,
        forbidden_spies=tuple(forbidden_spies.values()),
    )


# ---------------------------------------------------------------------------
# WT-1 ~ WT-6
# ---------------------------------------------------------------------------

def test_wt1_valid_envelope_reaches_normalize_once(adapter, gateway_spy):
    """WT-1：合法 envelope 恰好进入 normalize 一次（WA-3 唯一出口）。

    映射口径：normalize 只收契约字段（event_type / payload）；
    timestamp / source 是传输元数据，不出传输层。
    """
    result = adapter.handle(json.dumps(VALID_ENVELOPE))

    assert len(gateway_spy.calls) == 1
    assert gateway_spy.calls[0] == {
        "event_type": "gift",
        "payload": {"gift_name": "小心心", "gift_count": 1},
    }
    assert result is not None  # normalize 返回内部事件（Event）


def test_wt2_invalid_json_rejected(adapter, gateway_spy, logger_spy):
    """WT-2：非法 JSON → reject + log，normalize 零调用（WA-4）。"""
    with pytest.raises(Reject):
        adapter.handle("{not-json")

    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1


def test_wt3_missing_event_type_rejected(adapter, gateway_spy, logger_spy):
    """WT-3：缺 event_type → reject（WM-1 恰 4 字段），normalize 零调用。"""
    broken = {k: v for k, v in VALID_ENVELOPE.items() if k != "event_type"}
    with pytest.raises(Reject):
        adapter.handle(json.dumps(broken))

    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1


def test_wt4_unknown_event_type_rejected_and_logged(adapter, gateway_spy, logger_spy):
    """WT-4：未知 event_type → reject + log（含原因），normalize 零调用。"""
    unknown = dict(VALID_ENVELOPE, event_type="follow")
    with pytest.raises(Reject):
        adapter.handle(json.dumps(unknown))

    assert len(gateway_spy.calls) == 0
    assert len(logger_spy.calls) == 1
    assert "follow" in logger_spy.calls[0]  # log 记录拒收原因


def test_wt5_adapter_never_touches_engines_or_repositories(
    adapter, forbidden_spies, logger_spy
):
    """WT-5：adapter 不调用 ActionEngine / PlaybackManager / repositories（WA-3）。"""
    adapter.handle(json.dumps(VALID_ENVELOPE))
    with pytest.raises(Reject):
        adapter.handle("bad json")

    for name, spy in forbidden_spies.items():
        assert not spy.called, name  # WA-3：全程零触碰
    # logger 是 adapter 唯一允许的副通道
    assert logger_spy.calls  # 非法消息确实走了 log 通道


def test_wt6_adapter_keeps_no_business_state(adapter, gateway_spy):
    """WT-6：adapter 不保存业务状态（WA-2）：处理前后实例属性不变、无缓存去重。"""
    before = set(vars(adapter).keys())
    raw = json.dumps(VALID_ENVELOPE)

    adapter.handle(raw)
    after_first = set(vars(adapter).keys())

    adapter.handle(raw)  # 同一消息再次处理 → normalize 再被调用（无去重缓存）
    after_second = set(vars(adapter).keys())

    assert before == after_first == after_second
    assert len(gateway_spy.calls) == 2
