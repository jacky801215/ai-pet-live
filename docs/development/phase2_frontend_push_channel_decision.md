# Phase 2.2-6 Frontend Push Channel Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-6 指令确认执行）
> 输入：`phase2_websocket_boundary_decision.md`（WS-*）、`phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、`phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `step4_frontend_data_flow_decision.md`（FD-*）、`step4_frontend_refresh_boundary_decision.md`（RF-*）、
> `step4_frontend_state_decision.md`（FS-*）、`step4_frontend_api_client_decision.md`（FC-*，既有）
> 编号空间声明：本文档使用 **PC-***（Push Channel）。
> **编号裁决记录（用户裁决，2026-09-21）**：Phase 2.2-6 指令原文要求使用 `FC-1 ~ FC-6`，但 **`FC-*` 已是
> `step4_frontend_api_client_decision.md` 的已冻结命名空间（FC-1~FC-5，含义为 Client 唯一出口 /
> Transport Boundary / DTO / API Modules / Error Boundary，且被 FD/ES/FS 三份文档引用）**，属编号撞车。
> 经用户裁决**改用 `PC-1 ~ PC-6`**（创建前核查：全仓 0 命中），与 4.1-C-0（UI-* → UB-*）同处置。

## Input

- 指令：Phase 2.2-6 —— 把已完成的 backend 闭环
  （WS → adapter → EventGateway → SimulationPipeline → ActionEngine → Playback / Runtime State）
  接入 Frontend Desktop UI：`Backend Runtime State 变化 → WebSocket push → Frontend push channel → UI 自动更新`。
- 前置检查（Step 0，只读）：branch = `phase1-step1-foundation`，HEAD = `1779f88`，working tree clean；
  `frontend/src/{api,stores,components,hooks,types}` 存在，`src/services/` **不存在**（本步新建）。

## Investigation（只读调查记录，2026-09-21）

| 事实 | 现状 |
|---|---|
| Runtime 数据来源 | `usePetRuntime()` → `loadRuntimeData()`（Promise.all 三路 HTTP 拉取）→ store 三 setter（FD-1/FD-3，**不可删除**） |
| 刷新 | `refresh()` 唯一来源 hook、仅人工 button click（RF-1/RF-2，**不变**） |
| Store | zustand 单 store：`playback` / `recentEvents` / `stats` + 三个 setter（FS-1/FS-3）；零 fetch / 零 `/api/` 字面量 / 零 timer（既有静态守卫） |
| 组件消费面 | StatusBar ← `stats`；EventList ← `recentEvents`（`key={event.id}`，要求 id 唯一）；PetPlayer ← `playback`；App 无 useState / 无 API import（RF-3 守卫） |
| 测试环境 | vitest **node 环境（无 jsdom）**：纯模块 + `react-dom/server` 静态渲染 + 源码静态守卫；零新增依赖（`package.json` dependencies 恰 3 个为既有守卫） |
| Backend WS | `/api/ws`（2.2-5）：只**接收**（adapter → normalize → `apply_event`），**不向客户端推送任何帧** |

### ⚠️ 缺口声明（本步已裁决，必读）

指令目标链路含「Backend Runtime State 变化 → WebSocket push」，但 backend 端点在 2.2-5 尚未实现
**服务端推送帧**，且本步指令明令**禁止修改 backend websocket endpoint**。

> **用户裁决（2026-09-21）：前端通道先行。**
> 本步交付：websocketClient + push channel + `applyPushEvent` + UI 接线，并以**注入式假 socket**
> 喂 WM-1 envelope 完成全部验证；**真实服务端推送帧（server → client 发送）留待后续授权步**，
> 届时须同步明确推送载荷形态（WG-4 预留：载荷与 API-2 快照同构的口径）。

## Decision（裁决总表 PC-1 ~ PC-6）

### PC-1 —— Push Channel Ownership（冻结）

- Frontend **新增 push channel**，位置与职责：
  - `src/services/websocketClient.ts`：**仅** transport——`connect()` / `close()` / `onMessage()`；
  - `src/hooks/useRuntimePush.ts`：**唯一**接线点——mount 时 `connect()`、cleanup 时 `close()`，
    把 envelope 交给 store 写通道；
- push channel 职责**恰一条**：接收 websocket runtime update 并写入 store；
- **禁止**：调用 API refresh / `loadRuntimeData()`；禁止 socket 直写组件状态；禁止业务处理
  （客户端不判定动作、不消费队列、不修改素材）。

### PC-2 —— 数据来源（冻结）

- 前端推送数据**唯一来源** = WebSocket message；
- 消息格式 = **WM-1 envelope 逐字段保持**（`event_type` / `payload` / `timestamp` / `source` 恰 4 字段），
  **不增加字段、不改名、不裁剪**；
- 客户端对入站帧做**形状校验**（4 字段齐全 + `event_type` ∈ 契约白名单 + `payload` 为对象 +
  `timestamp`/`source` 为字符串）；非法帧**拒收**（丢弃 + 可选审计回调），**不写入 store**；
- `WS-2` 重申：本通道不构成第二事件体系——envelope 与 HTTP 侧同一契约。

### PC-3 —— 与 Refresh 的关系（冻结）

- `HTTP refresh = 主动拉取`（人工触发，RF-1/RF-2 **不变**）；`WebSocket push = 被动更新`；
- **禁止** `socket → loadRuntimeData()`；**禁止** push 触发 refresh、或 refresh 伪装成 push（WS-3/WG-4 重申）；
- 两条数据来源**长期并存、互不替代**；`loadRuntimeData()` 与既有三 setter **保持原样、不可删除**（本步硬要求）。

### PC-4 —— Runtime Store（冻结）

- **允许新增** `applyPushEvent(envelope)`（Phase 2.2-6 指令明确授权），语义 = push 通道的**唯一写出口**；
- **禁止**：改变 runtime state schema（不新增切片、不新增字段、不新建第二 store、不派生业务状态）；
- 写入语义（只写既有切片，纯函数式、无隐藏状态）：
  1. `recentEvents` **头部并入**一条 envelope 派生的明细项（9 字段沿用 `EventItem` 形状：
     `created_at` = `envelope.timestamp`、`platform` = `envelope.source`、`payload` 原样、
     `action_name`/`user_id`/`user_name`/`pet_id` = `null`；`id` = **本地负值占位**
     （由既有条目中负值 id 条数推导，保证唯一且无额外状态））；
  2. 若 `playback !== null`，同步 `playback.last_event = envelope.event_type`（其余 5 字段原样保留）；
- **FS-3 关系声明**：FS-3 冻结「store 公开 setter 恰 3 个」。本决策经 Phase 2.2-6 指令授权，将 push 通道
  **受权扩展为第 4 个写出口** `applyPushEvent`；语义与三个 setter 同级（唯一写出口集合的成员），
  schema 与「唯一 store」约束**一律不变**；重叠处以更严格者为准（禁止新字段/新 store/派生状态）。

### PC-5 —— UI 更新（冻结）

- 允许更新 `StatusBar` / `EventList` / `PetStage`——**必须经过 store**（既有订阅链路自动重渲，
  组件零改动；本步不改任何组件文件）；
- **禁止**：socket callback 直接 `setState`、组件内建 websocket、组件直接消费 socket；
- `PlaybackState` **7 字段（CR-1）冻结不变**（WS-4/WG-4 重申）；前端**零新增状态字段**。

### PC-6 —— Scope Freeze（冻结）

本阶段**不实现**：reconnect（自动重连）、heartbeat（心跳）、queue sync、multi client、multi pet、
offline recovery（离线恢复）、message replay、新依赖、backend 任何修改。

## Step 3 冲突检查结果（WS / WM / WA / WG / FD / RF / FS / FC）

| 冲突项 | 结论 |
|---|---|
| **WS-1~6 / WM-1~6 / WA-1~6 / WG-1~6** | ✅ 无冲突：PC 是 WG-4「FD 层新增 push channel」的落地；envelope 逐字段沿用 WM-1；不改 backend |
| **FD-1~5** | ⚠️ **受权增量**：FD 本体**不动**；FD-3「只实现 usePetRuntime()」由本决策在 push 通道维度**增补**
  `useRuntimePush()`（FD-5 明列的「不实现 websocket」亦由此解禁，依据 = Phase 2.2-6 指令 + 用户裁决）；
  FD-1 单向数据流与「Hook → Store」路径**不变**；
  **既有静态守卫同步扩展 3 处**（FD-2/§七、§五、FCM-3 的「App import 白名单」增加
  `./hooks/useRuntimePush`）——仅扩展允许项，App 的全部禁止项（零 API import / 零 store setter /
  零 fetch / 零 useState）**原样保留** |
| **RF-1~5** | ✅ 无冲突：refresh 唯一来源 / 人工触发 / 错误通道**全不变**；push 不调用 refresh（PC-3） |
| **FS-1 / FS-3 / FS-4** | ⚠️ **受权增量**：公开写出口由 3 个扩展为 4 个（`applyPushEvent`，PC-4 声明）；
  schema / 唯一 store / 零 fetch / 零 timer **全部不变** |
| **FC-1~5**（既有 API Client 边界） | ✅ 无冲突：push channel **不经 API Client**（不走 HTTP、不 import `src/api/**`）；
  既有 FC-* 命名空间**零修改**（本决策改用 PC-* 编号，见文首裁决记录） |
| **PlaybackState（API-2 / WS-4）** | ✅ 无冲突：**7 字段（CR-1）**冻结不变，仅 `last_event` 值更新 |

**结论：本次冻结不需要修改任何既有冻结规则**（WS/WM/WA/WG/RF/FC 保持原样；FD、FS 为**受权增量**，
已在文档内显式声明，本体不修改）。

## 设计验证清单

| 检查项 | 结果 |
|---|---|
| 编号空间 PC-* 全仓 0 命中（创建前核查） | ✅ |
| 唯一来源声明（PC-2）+ 缺口声明（服务端推送帧 Deferred） | ✅ |
| `loadRuntimeData()` / 三 setter 零删除零修改（PC-3） | ✅ 代码级保证（本步不触碰 hooks/usePetRuntime.ts 既有函数） |
| store schema 不变（PC-4）；新增写出口已显式声明 FS-3 增量 | ✅ |
| UI 更新必须经 store；组件零改动（PC-5） | ✅ |
| 零新依赖（PC-6；WebSocket 为运行时内建） | ✅ |
| 测试：连接 / 收帧入 store / 禁止 refresh / 非法拒收 / 断线不重连 | 见 `frontend/tests/websocket/` |

## 落地项（归后续授权步）

- **服务端推送帧**：`/api/ws` 向连接回推 envelope（含 WG-4 载荷形态裁决）——须修改 backend，另行授权；
- push 与 refresh 的**并发合并语义**（同一拍内 push 与 refresh 共存时的写入顺序）——Deferred；
- 断线可见性（RS 第五态「离线」表达）——Deferred（WS-5 已声明归后续 RS 修订）。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-21 | 首版冻结（PC-1 ~ PC-6；编号经用户裁决由指令 FC-* 改为 PC-*） |
