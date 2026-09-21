# Phase 2.2-8 WebSocket Observability / Monitoring Boundary（**v1.0 FROZEN**）

> 状态：**v1.0 FROZEN**（2026-09-21，Phase 2.2-8-1 指令）——**已冻结决策文档**
> 性质：**仅文档冻结**——零代码、零依赖、零测试改动。
> 契约编号：**`OB-1 ~ OB-6`**（本文件为 `OB-*` 的**唯一事实来源**；编号与 8-0 审计保持**逐条不变**）。
> 上游：`phase2_websocket_observability_boundary_audit_draft.md`（v0.1 DRAFT，8-0，**已由本文件取代并删除**）。
> 输入冻结文档：`phase2_websocket_boundary_decision.md`（WS-*）、`phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、`phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_websocket_push_boundary_decision.md`（WP-*）、`phase2_websocket_commit_point_decision.md`（WC-*）、
> `phase2_websocket_connection_lifecycle_boundary_decision.md`（WL-*）、
> `phase2_websocket_lifecycle_implementation_boundary_decision.md`（LI-*）、
> `phase2_frontend_push_channel_decision.md`（PC-*）、
> `phase2_websocket_event_coverage_boundary_decision.md`（WE-*）、
> `phase2_websocket_runtime_event_gap_resolution_decision.md`（GR-*）。
>
> **定位**：本文件冻结 **WebSocket 可观测性边界**（现有信号、可见性边界、失败可观测性、Deferred 项、scope），
> **只记录、不实现**。任何 observability 实现（logger 改造 / metrics / tracing）**不在**本文件范围。

---

## Step 0 审计证据（来自 8-0 只读审计）

### Q1 —— Connection Observability Points（7 候选，3 存在）

| point | exists | owner | current behavior |
|---|---|---|---|
| connect log | ❌ | transport（`api/ws.py:103`） | `accept()` —— 无日志 |
| receive log | ❌ | transport（`api/ws.py:106`） | `receive_text()` —— 无日志 |
| reject log | ✅ | adapter（WA-4，`websocket_adapter.py:68/73/79/84`） | 4 类非法各 1 条 `self._logger(...)`（INFO，无结构） |
| commit log | ❌ | runtime（`pipeline.py:109-143`） | `apply_event()` 前后**均无日志** |
| send log（success） | ❌ | dispatcher | **成功无日志** |
| send failure log | ✅ | dispatcher（WP-5，`:135`） | `self._logger("websocket push failed: event_type=%s", ...)`（`logging.exception`，带栈） |
| disconnect log | ✅ | transport（WS-5，`api/ws.py:120`） | `logger.info("websocket disconnected: path=/api/ws")` |

> **附带发现（日志命名空间不一致）**：`api/ws.py`、`platform/websocket_{adapter,dispatcher}.py`、
> `services/{pipeline,action_engine,playback_manager,...}.py` 用**裸** `logging.getLogger(__name__)`（**不在** `pet_live` 命名空间下）；
> 而 `core/logging_config.setup_logging()` **只配置** `pet_live` logger（`propagate=False` + StreamHandler），**未配置 root**。
> ⇒ 传输/引擎日志**不经**该 handler，回落 root（`lastResort`，仅 `WARNING+`）；
> **`logger.info("websocket disconnected")` 等 INFO 级传输信号事实上被吞**。（登记事实；修复属 logger framework / namespace 改动，**见 OB-6 禁止项**。）

### Q2 —— Runtime Commit Boundary（`pipeline.py`）

| 调查项 | 结论 |
|---|---|
| commit point 是否已有日志 | ❌ **无** |
| mutation 是否产生 correlation id | ❌ **无**（全仓 0 命中） |
| `event_type` 是否进入日志上下文 | ❌ **否**（成功路径无日志；仅 reject 日志含 `event_type`） |
| payload 是否被记录 | ❌ **日志中无**（仅经 `DataManager.write_event` **入 DB**） |

> `pipeline.py` 现存 2 处日志均为**旁路告警**（`_expire_if_due` 超上限 warning:213、`_find_metadata` 素材失败 warning:255），**与 commit 无关**。

### Q3 —— Dispatcher（`websocket_dispatcher.py`）

| 调查项 | 结论 |
|---|---|
| send success 是否可观测 | ❌ **否** |
| send failure 是否可观测 | ✅ **是**（`except` → `self._logger(...)` → `return False`） |
| 是否存在 metrics hook | ❌ **无** |
| 是否保存状态 | ❌ **无**（`__dict__ == {_now, _logger}`，LI-3） |

### Q4 —— Frontend Lifecycle（`frontend/src/**`）

| 调查项 | 结论 |
|---|---|
| `open` / `error` / `close` 是否监听 | ❌ **均未监听**（只订阅 `message`） |
| console logging 是否存在 | ❌ **无**（零 `console.` 命中） |
| reconnect / heartbeat 是否存在 | ❌ **未实现**（仅 Deferred 登记） |

---

## OB-1 ~ OB-6（**FROZEN**）

### OB-1 Observability Ownership Boundary

- **transport logs 属 transport**（`api/ws.py` + `platform/websocket_*`）；
- **runtime mutation logs 属 runtime**（`services/pipeline.py`）；
- **frontend diagnostics 属 client**（`frontend/src/**`）。
- **禁止**：跨层注入 logger；**global event logger**；**observer bus**。

### OB-2 Existing Signals Inventory

- **已有**：`logger`（stdlib logging，`core/logging_config.py`，`pet_live` 命名空间）· `exception logging`（`logger.exception` 多处）·
  `test order tracing`（测试侧 `order` 序列断言 commit/send 次序）。
- **缺失**：`metrics` · `tracing id` · `connection id` · `delivery acknowledgement`。
- **不一致（既有信号质量缺口）**：① 日志命名空间不统一（传输/引擎用裸 logger，见 Q1 附带发现）；
  ② 传输侧**无结构化字段**；③ 成功路径**不可观测**（connect / receive / commit / send-success）。

### OB-3 Commit / Send Visibility Boundary

**确认可观察性链路**：`receive ↓ apply_event() ↓ commit ↓ dispatch ↓ send_json()` —— 逐节点：

| 节点 | 可观察 | 说明 |
|---|---|---|
| `receive` | ❌ | 无日志 |
| `apply_event()` | ❌ | 无日志 |
| `commit`（apply_event 返回） | ❌ | 无日志 |
| `dispatch`（组装 envelope） | ❌ | 成功无日志 |
| `send_json()` | ⚠️ 仅失败 | 成功 ❌ / 失败 ✅ |

- **禁止改变**：**commit point**（WC-1）· **dispatcher ownership**（WP-1）· **WM-1 envelope**（恰 4 字段）。

### OB-4 Failure Observability Boundary

| 失败类别 | logged | surfaced | retried |
|---|---|---|---|
| **adapter reject** | ✅ adapter `_logger`（INFO） | ❌（不向客户端回执，连接继续） | ❌ 否 |
| **apply_event reject** | — **无显式 reject 语义**；理论异常**无捕获、无日志、原样传播**（WL-3） | ❌ | ❌ 否 |
| **send failure** | ✅ dispatcher `logger.exception` | ❌ | ❌ 否（WP-5 禁 retry/reconnect/buffer/ack） |
| **disconnect** | ✅ `api/ws.py` INFO（**可能被吞**，见 Q1） | — | ❌ 否（WS-5 禁 reconnect/recovery） |

### OB-5 Deferred Observability Features

**登记但不实现**：`metrics` · `tracing` · `OpenTelemetry` · `connection id` · `delivery receipt` · `dashboards` · `alerting`。

### OB-6 Scope Freeze

- **本阶段允许**：**audit** + **boundary definition**。
- **本阶段禁止**：`logger framework` 改造 · `logger namespace` 修复 · `metrics` · `tracing` · `OpenTelemetry` ·
  `connection id` · `delivery receipt` · `dashboard` · `alerting` · `frontend telemetry` · `websocket protocol change` ·
  任何 `backend` / `frontend` 代码改动。

---

## Resolution Record

- **R-OB-1（只冻边界，不实现）**：OB-* **只冻结可观测性边界与现状快照**，**不引入任何 observability 实现**；
  已知缺口（Q1 日志命名空间 / INFO 被吞、Q2 无 commit instrumentation、OB-2 缺失信号）**登记不修复**（修复属 OB-6 禁止项）。
- **R-OB-2（不修改上游）**：OB **不修改** WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR；
  纯追加，不删不重排；未改 commit point / dispatcher ownership / WM-1 envelope / lifecycle ownership。
- **R-OB-3（文件地位）**：OB-* = **observability boundary**（可观测性边界清单），**非** feature spec、**非授权文件**；
  **不授权**任何实现。

---

## 冲突矩阵

| 检查项 | 结果 | 说明 |
|---|---|---|
| 编号冲突 `OB-*` | ✅ **无** | 全仓 tracked files 0 命中（起草前核查） |
| OB ↔ WS / WM | ✅ 无 | 未改事件模型 / envelope / 白名单 |
| OB ↔ WA / WG | ✅ 无 | 未改 adapter 三职责 / gateway 单一入口 |
| OB ↔ WP | ✅ 无 | 未改 push ownership / send 语义 |
| OB ↔ WC | ✅ 无 | 未改 commit point / per-message |
| OB ↔ WL / LI | ✅ 无 | 未改 lifecycle ownership / dispatcher 中性 |
| OB ↔ WE / GR | ✅ 无 | 未新增 event_type / 未引入 observer·listener·event bus / 未触 G1 |
| **STOP 触发器**（新增 event schema / 改 envelope / 改 lifecycle ownership / 改 commit point / 引入 observer·listener） | ❌ **均未触发** | 纯边界冻结 |

---

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 8-0 草案（`..._audit_draft.md`，已删除）转正式冻结：OB-1 ~ OB-6（编号不变）+ 审计证据 + Resolution Record + 冲突矩阵；零代码变更 |
