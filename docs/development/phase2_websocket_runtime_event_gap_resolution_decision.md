# Phase 2.2-7D WebSocket Runtime Event Gap Resolution Boundary（**v1.0 FROZEN**）

> 状态：**v1.0 FROZEN**（2026-09-21，Phase 2.2-7D-3 指令）——**已冻结决策文档**
> 性质：**仅文档冻结**——零代码、零依赖、零测试改动。
> 契约编号：**`GR-1 ~ GR-6`**（本文件为 `GR-*` 的**唯一事实来源**）。
> 上游：`phase2_websocket_runtime_event_gap_resolution_draft.md`（v0.1 DRAFT，7D-2，**已由本文件取代并删除**；
> 草案编号 `GD-*` 随之废止，正式编号为 `GR-*`）。
> 输入冻结文档：`phase2_websocket_event_coverage_boundary_decision.md`（**WE-***）、
> `phase2_websocket_push_boundary_decision.md`（WP-*）、`phase2_websocket_commit_point_decision.md`（WC-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、`phase2_frontend_push_channel_decision.md`（PC-*）、
> `phase2_websocket_boundary_decision.md`（WS-*）。
>
> **定位**：本文件**冻结 G1（mutation-without-event）的处置裁决 = Option A（维持现状）**，
> 并声明 **gap resolution ≠ implementation authorization**（**不授权任何实现**）。
> 任何补齐（新增事件类型 / 补齐信号）**不在**本文件范围；其硬前置见 GR-5。

---

## Step 0 审计证据（来自 7D-2 只读调查）

### Q1 —— Queue Overflow Mutation Map（`action_engine.py:139-147`）

| 调查项 | 结论 |
|---|---|
| overflow 当前行为 | 队列满（`len(_pending) >= 3`，`DEFAULT_QUEUE_LIMIT=3`）时 `popleft()` **丢最旧**，随即 append ⇒ 净长不变（3→2→3） |
| 是否产生 Event | ❌ **否**——`ActionEngine` 契约「**不接收、不导入 `Event`**」；仅 `logger.warning` |
| 是否改变 PlaybackState | ⚠️ **无净变化**——`queue_size = max(0, len(pending)-1)`（`pipeline.py:158`）；被丢指令**无状态痕迹** |
| 是否触发 DataManager | ❌ **否**——只记录**被受理**的动作 |
| 是否进入 `apply_event` | ✅ 是（`pipeline.py:128` 栈内），但只 commit 触发事件本身 |

### Q2 —— Playback Finished Gap

| 调查项 | 结论 |
|---|---|
| `on_finished` 当前状态 | ❌ **未注入**——`PlaybackManager(asset_manager)`（`runtime_factory.py:133`）⇒ `_on_finished is None` ⇒ `_notify()` 立即返回 |
| 谁拥有 finished 语义 | **编排层**——「轮询驱动到期」：`PlaybackClock` 按**时长**判定，推进点唯一在 `pipeline._expire_if_due()`（205-221） |
| 是否已有事件类型空间 | ❌ **否**——白名单恰 4（`comment`/`gift`/`like`/`system`），无 `playback_*`/`idle`/`finished` |
| 是否触碰 WM-1 | ❌ **当前零触碰** |

### Q3 —— Resolution Options

| Option | 合规 |
|---|---|
| **A 保持现状**（HTTP pull only） | ✅ **完全合规** |
| **B 新增 runtime event** | ❌ 违 **WE-5 + WE-1**，与 **WC-4** 冲突 |
| **C 内部 mutation notification** | ❌ 违 **WE-1 + WC-4**（+ WP-1/LI-3 张力） |

---

## GR-1 ~ GR-6（**FROZEN**）

### GR-1 Gap Ownership Boundary

- gap 属 **runtime visibility limitation**（运行时可见性限制）；
- **不属于** **websocket transport failure**；
- **不属于** **push delivery failure**。

### GR-2 Queue Overflow Resolution

- **当前行为**：`overflow → discard oldest pending action`（`action_engine.py:139-147`，丢最旧、只记日志）；
- **决策**：**Option A —— retain existing behavior**；
- **明确**：
  - **不生成 Event**；
  - **不进入 push pipeline**；
  - **不新增 envelope**；
  - **不记录 PlaybackState 字段**。

### GR-3 Playback Finished Resolution

- **当前行为**：`expire_if_due() ↓ restore_idle() ↓ HTTP snapshot visibility`；
- **决策**：**Option A —— retain HTTP pull visibility**；
- **明确**：
  - **不新增 finished event**；
  - **不修改 `on_finished` wiring**；
  - **不修改 `PlaybackManager`**。

### GR-4 Resolution Matrix

| Gap | Option | Decision |
|---|---|---|
| queue overflow | A / B / C | **A** |
| playback finished | A / B / C | **A** |

### GR-5 Frozen Constraints

**继承（逐条为硬前置，本冻结不动它们）**：

| 约束 | 要点 |
|---|---|
| **WE-1** | outbound push event source = **inbound WebSocket Event**；禁 pipeline/timer/observer/background emit |
| **WE-4** | mutation-without-event **登记不解决**；不属 7D scope |
| **WE-5** | 禁新 event_type / 改 WM-1 envelope / 改 PC whitelist / 新 PlaybackState 字段 / observer bus |
| **WC-3** | `snapshot()→_expire_if_due()` 读路径副作用，**不作 push trigger** |
| **WC-4** | 通知路径 **per-message**；禁订阅 / 后台任务 / 定时器 |
| **WP-1 / WP-2** | push ownership = **platform websocket transport**；触发只在 **commit point 之后** |
| **WM-1** | envelope 恰 4 字段；`event_type` 白名单冻结 |
| **PC-2** | 前端数据源 = WM-1 逐字；白名单冻结 |
| **PlaybackState** | 6 字段冻结 |

**冻结声明**：**gap resolution ≠ implementation authorization**——本文件**只冻结处置裁决**，**不授权任何实现**。

### GR-6 Scope Freeze

本阶段**禁止**：

- ❌ **new `event_type`**；
- ❌ **event bus**；
- ❌ **observer**；
- ❌ **notifier**；
- ❌ **callback expansion**；
- ❌ **queue event**；
- ❌ **finished event**；
- ❌ **websocket schema change**；
- ❌ **frontend subscription change**。

---

## Resolution Record

- **R-GR-1（编号口径）**：正式冻结编号为 **`GR-*`**；7D-2 草案编号 `GD-*` **废止**。映射：
  GD-1→GR-1 · GD-2→GR-2 · GD-3→GR-3 · GD-4→GR-4 · GD-5→GR-5 · GD-6→GR-6。**仅编号对齐，裁决内容一致**。
- **R-GR-2（gap resolution ≠ authorization）**：本冻结**不授权**任何实现；**G1 维持未解决**（详见 WE-4 / GR-5）。
- **R-GR-3（不修改上游）**：GR **不修改** WS / WM / WA / WG / WP / WC / WL / LI / PC / WE 及 **websocket transport**、
  **PlaybackState**、`PlaybackManager`、`on_finished` wiring；纯追加，不删不重排。

---

## 冲突矩阵

| 检查项 | 结果 | 说明 |
|---|---|---|
| 编号冲突 `GR-*` | ✅ **无** | 全仓 tracked files 0 命中（起草前核查） |
| GR ↔ WE | ✅ 无 | WE-4 + 本冻结 = 「登记不解决」；GR-5 逐条重申 WE-1/WE-4/WE-5 |
| GR ↔ WC | ✅ 无 | GR-2 = WC-3（读路径不作 trigger）/ WC-4（per-message）；未提修改 |
| GR ↔ WP | ✅ 无 | GR-1 归因与 WP-1/WP-2 ownership 一致；未提修改 |
| GR ↔ WM | ✅ 无（且不触碰） | GR-6 禁 websocket schema change；零修改 WM-1 |
| GR ↔ PC | ✅ 无 | GR-6 禁 frontend subscription change；零修改 PC-2 |
| GR ↔ PlaybackState | ✅ **无扩张** | GR-2/GR-3 明确不新增字段 |
| **STOP 触发器**（新 event_type / envelope 改 / PlaybackState 扩 / transport 改 / 实现） | ❌ **均未触发** | 纯边界冻结 |

---

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 7D-2 草案（`..._draft.md`，已删除）转正式冻结：GR-1 ~ GR-6（Option A 裁决）+ 审计证据 + Resolution Record + 冲突矩阵；零代码变更 |
