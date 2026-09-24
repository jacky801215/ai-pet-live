# Phase 2.2-7D WebSocket Runtime Event Coverage Boundary（**v1.0 FROZEN**）

> 状态：**v1.0 FROZEN**（2026-09-21，Phase 2.2-7D-1 指令）——**已冻结决策文档**
> 性质：**仅文档冻结**——零代码、零依赖、零测试改动；**不实现 G1**。
> 契约编号：**`WE-1 ~ WE-6`**（本文件为 `WE-*` 的**唯一事实来源**）。
> 上游：`phase2_websocket_event_coverage_audit_draft.md`（v0.1 DRAFT，7D-0）——**已由本文件取代并删除**。
> 输入冻结文档：`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_websocket_push_boundary_decision.md`（WP-*）、
> `phase2_websocket_commit_point_decision.md`（WC-*）、
> `phase2_websocket_connection_lifecycle_boundary_decision.md`（WL-*）、
> `phase2_websocket_lifecycle_implementation_boundary_decision.md`（LI-*）、
> `phase2_frontend_push_channel_decision.md`（PC-*）。
>
> **定位**：本文件冻结 **outbound push 的事件覆盖边界**（哪些事件可推送、哪些被排除、无事件 mutation 如何登记），
> **只记录、不解决、不扩张、不实现**。任何「补齐缺口」（新增事件类型 = 修订 **WM-1 FROZEN**）**不在**本文件范围。

---

## Step 0 审计证据（来自 7D-0 只读审计）

### Q1 —— Event Source Inventory

`pipeline.py` mutation 位点（穷举）：

| 行 | 语句 | 所属函数 | 触发源 | 是否承载 Event |
|---|---|---|---|---|
| 128 | `action_engine.execute(command, pet_id)` | `apply_event` | WS / HTTP 事件 | ✅ 承载（触发事件） |
| 132 | `self._playback_clock.arm(...)` | `apply_event` | 同上 | ✅ 承载 |
| 134–141 | `self._record(...)` → DataManager 写入 | `apply_event` | 同上 | ✅ 承载 |
| 142 | `self._last_event = event.event_type` | `apply_event` | 同上 | ✅ 承载 |
| 216 / 219 | `self._playback_clock.disarm()` | `_expire_if_due` | `snapshot()` | ❌ **无 Event** |
| 220 | `action_engine.restore_idle(pet_id)` | `_expire_if_due` | `snapshot()` | ❌ **无 Event** |
| 232 | `self._playback_clock.arm(...)` | `_rearm_from_current` | `snapshot()` | ❌ **无 Event** |

事件来源表：

| Event | Source | apply_event | dispatcher path |
|---|---|---|---|
| **action event** | WS `adapter.handle()` → `EventGateway.normalize()` → `Event`（4 类型白名单） | ✅ 进入（`ws.py:113`） | ✅ **可达**（`ws.py:116`） |
| **playback event** | **不存在**——无独立 playback 事件类型；`PlaybackManager.play()` 不产生 `Event` | — | ❌ 不可达 |
| **idle restore** | `snapshot() → _expire_if_due() → restore_idle()`（**轮询驱动到期**） | ❌ 无 Event（`restore_idle` 收 `pet_id`） | ❌ 不可达 |
| **reject event** | `adapter.handle()` 非法帧 → `WebSocketAdapterRejectError` | ❌ 未进入（`ws.py:109-111` `except` → `continue`） | ❌ 不可达 |
| **unknown event** | `event_type` 白名单外（如 `follow`）→ 同一 reject 路径 | ❌ 未进入 | ❌ 不可达 |
| HTTP `POST /api/events/simulate` | `simulate()` → `apply_event(platform="simulator")` | ✅ 进入 | ❌ 不可达（**WC-4**） |

> **核心事实**：runtime mutation **并非**都有对应 Event——`apply_event()` 的 4 个位点**全部**由触发事件承载；
> `_expire_if_due()` 的 3 个位点（+232 续发）**无任何 Event**（时间 / 读取驱动）。

### Q2 —— Push Reachable Boundary

链路：`adapter.handle(raw) → Event → apply_event(event, platform="ws") →（commit point, WC-1）→ dispatcher.send_event(event, websocket) → send_json(WM-1 envelope)`。

**可达集恰一类**：`api/ws.py` 接收循环内经 adapter 接受、且 `apply_event()` 正常返回的 `Event`（**1 message ↔ 1 frame**）。

### Q3 —— Coverage Gap 分类

| 类别 | 定义 | 实例 |
|---|---|---|
| **G1 — missing event trigger** | mutation 存在 + 无 Event + 未被冻结条款排除 | 队列溢出丢弃（无独立 Event）／「播放完成」无信号（生产 `on_finished` 留空） |
| **G2 — intentionally excluded** | 被冻结条款**显式排除** | `_expire_if_due → restore_idle`（**WC-3**）；可见性由 HTTP pull（RF-1/RF-2）承担 |
| **G3 — transport excluded** | 传输层事件，不进 outbound push | reject / unknown / disconnect / 发送失败 / adapter 拒收 |

---

## WE-1 ~ WE-6（**FROZEN**）

### WE-1 Event Source Boundary

- **outbound push event source = inbound WebSocket Event**；
- event **必须**经过：`adapter` ↓ `Event` ↓ `apply_event()` ↓ `dispatcher`；
- **禁止**：`pipeline` **自发 emit** / `timer emit` / `observer emit` / `background emit`。

### WE-2 Reachable Push Event

- **可推送集合** = `Event accepted by adapter` **+** `apply_event() successful return` **+** `active websocket connection`；
- **对应关系**：**1 inbound message = 1 commit = 1 outbound frame**；
- **保持**：**WM-1 envelope 不扩展**（恰 4 字段）。

### WE-3 Excluded Event Boundary

**冻结排除**：

| # | 排除项 | 依据（继承） |
|---|---|---|
| E1 | **reject** | **WC-4** / WA-4 / WL-3 / LI-5 |
| E2 | **unknown event**（`event_type` 白名单外） | 同 E1 |
| E3 | **disconnect**（`WebSocketDisconnect`） | **WL-4** / WS-5 / WL-3 |
| E4 | **send failure**（`send_json` 异常） | **WL-4** / WP-5 |
| E5 | **adapter rejection**（`WebSocketAdapterRejectError`，不进入 `apply_event`） | WA-4 / **WC-4** |
| E6 | **HTTP simulate** | **WC-4** |
| E7 | **snapshot expire / restore_idle** | **WC-3** |

> 原因：**继承 WC-3 / WC-4 / WL-4**（零新增排除理由）。

### WE-4 Mutation Without Event

**冻结：登记但不解决**：

| # | mutation | 驱动 | 状态 |
|---|---|---|---|
| M1 | `expire side effect`（`_expire_if_due → restore_idle`，`pipeline.py:216/219/220`，+`_rearm_from_current` 232） | 时间 / 读取 | ❌ 无 Event（被 **WC-3** 排除 ⇒ G2） |
| M2 | `queue overflow drop`（`action_engine.py:139-147` `popleft()`） | 事件驱动（`apply_event` 栈内） | ❌ **无独立 Event** ⇒ **G1** |
| M3 | `playback finished`（生产 `on_finished` 留空，`runtime_factory.py:133`） | 播放下发 | ❌ **无信号** ⇒ **G1** |
| M4 | `future runtime mutation`（未来任何运行时变更） | 待定 | 登记位（默认无 Event） |

- **规则**：**mutation without Event 不属于 7D scope**——本阶段**不解决**、**不新增**事件类型。

### WE-5 Coverage Freeze

**冻结禁止**：

- ❌ 新 **`event_type`**；
- ❌ 修改 **WM-1 envelope**（4 字段）；
- ❌ 修改 **PC whitelist**（PC-2）；
- ❌ 新 **PlaybackState 字段**（**7 字段**；**CR-1** 授权增量 + `loop`，此后不再增加）；
- ❌ **observer / listener / event bus**。

- **G1 修复必须**：**先修订 `WM-1 FROZEN` + `PC-2` + separate decision**（另立冻结文档）。

### WE-6 Scope Freeze

本阶段**禁止**：`reconnect` / `heartbeat` / `auth` / `multi-client` / `persistence` / `replay` / `offline queue` / `lifecycle callback`。

---

## Resolution Record

- **R-WE-1（索引口径）**：本冻结按**指令口径**统一 E / M 索引。相对 7D-0 草案：
  「snapshot expire」由草案 E1 调整为 **E7**；「队列溢出丢弃」由草案 E7 **移入 M2**（语义上属 mutation 而非传输排除项）。
  **仅为编号对齐，实体集合未变**；**不涉及**任何既有冻结文档的修改。
- **R-WE-2（不解决缺口）**：**WE 只冻结覆盖率边界，不解决 G1**（`M1 ~ M4`）；G1 修复须**先修订 WM-1 FROZEN + PC-2**，
  并**另立冻结文档**（下一阶段 = Phase 2.2-7D-2 Runtime Event Gap Resolution Design，**须单独授权**）。
- **R-WE-3（文件地位）**：**WE-*** = **coverage boundary**（覆盖率边界清单），**非 feature spec**、**非授权文件**；
  **不授权**任何实现。**不修改** WS / WM / WA / WG / WP / WC / WL / LI / PC。

---

## 冲突矩阵

| 检查项 | 结果 | 说明 |
|---|---|---|
| 编号冲突 `WE-*` | ✅ **无** | 全仓 tracked files 0 命中（起草前核查） |
| WE ↔ WC | ✅ 无 | WE-3/E7 = WC-3；E1/E5/E6 = WC-4；WE-5 不改 commit point |
| WE ↔ WP | ✅ 无 | WE-2 envelope = WP-3；E4 = WP-5；WE-6 = WP-6 |
| WE ↔ WL | ✅ 无 | E3/E4 = WL-3/WL-4；WE-6 = WL-6 |
| WE ↔ LI | ✅ 无 | E1/E5 = LI-5；WE-5 不改 dispatcher ownership（LI-1/LI-3） |
| WE ↔ PC | ✅ 无 | WE-5 守 PC-2 whitelist 与 PC-6；E1 = PC-2 口径 |
| WE ↔ WS | ✅ 无 | E2 白名单 = WS-2；E3 = WS-5；WE-6 = WS-6 |
| WE ↔ WM | ✅ 无（且不触碰） | 零修改 schema / envelope；G1 仅登记为未来 WM 修订事项 |
| **STOP 触发器**（新 schema / envelope 改 / PlaybackState 扩 / commit point 改 / ownership 改） | ❌ **均未触发** | 纯覆盖边界冻结 |

---

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 7D-0 草案（`..._audit_draft.md`，已删除）转正式冻结：WE-1 ~ WE-6 + 审计证据 + Resolution Record + 冲突矩阵；零代码变更 |
