# Phase 2.2-6 Frontend Push Channel Decision v1.1（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-6 指令确认执行；
> **CR-6 修订 v1.1** = 2026-09-29：**PC-2 / PC-4 追加受权增量** —— 出站帧在原「WM-1 envelope」之外
> **新增第二类 = 状态帧**，前端据此**按帧型分流**并新增写出口 `applyPlaybackSnapshot`；
> **事件帧的格式、校验与拒收口径逐字不变**；PC-1 / PC-3 / PC-5 / PC-6 **均不变**）
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

> **受权增量（CR-6 / 2026-09-29）—— PC-2 帧型分流**：
> 以上冻结文字**逐字保留**，且**仅适用于事件帧**；本节**追加**第二类入站帧的形态与分流边界，
> **不修改** WM-1、**不新增** envelope 字段、**不改动**事件帧的任何校验与拒收口径。
>
> 1. **事件帧（= 上述 WM-1 envelope）**：**保持现状** —— 恰 4 字段（`event_type` / `payload` /
>    `timestamp` / `source`）、白名单与逐字段类型校验、**非法拒收**（丢弃 + 可选审计回调 + **不写 store**）
>    **一律逐字不变**。
> 2. **状态帧（第二类，`CR-6` 新增）**：形态 = `{"type": "playback_state", "snapshot": <API-2 的
>    `PlaybackState` 7 字段>}`；**载荷原样取自服务端推送**（`pipeline.snapshot()` 经 API-2 序列化的结果）。
>    - **source 约束（PC-2 不变量）**：状态快照的**唯一来源 = 服务端推送的状态帧**；
>      **禁止**由客户端**推断 / 合成 / 本地推导**状态（`client inferred state` 一律不允许）。
> 3. **分流边界（可判定）**：**入站帧顶层出现 `type` 字段且取值 `"playback_state"` ⇒ 状态帧分支**；
>    **否则** ⇒ 走**既有** WM-1 envelope 路径（**逐字不变**）。两类帧互斥，**不得**互相回退解析。
> 4. **非法帧拒收规则保持**：① 事件帧的四类非法定义（非字符串 / 非 JSON / 键数不为 4 / 白名单外
>    `event_type` / `payload` 非对象 / `timestamp`·`source` 非字符串）**逐字不变**；
>    ② 状态帧形状非法（`snapshot` 缺失或非对象 / 字段集**不等于** API-2 的 7 字段）**同样拒收**
>    （丢弃 + 可选审计回调，**不写 store**）；③ 拒收**不污染**既有 `playback` 快照、**不影响**事件通道。
> 5. **不变**：`WS-2` 的第二事件体系禁令、PC-3（push 不触发 refresh）、PC-5（UI 必须经 store）。

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

> **受权增量（CR-6 / 2026-09-29）—— PC-4 写出口扩展**：
> 以上冻结文字**逐字保留**；本节**追加**状态帧的写出口，**不改动** `applyPushEvent` 的任何语义。
>
> 1. **保留** `applyPushEvent(envelope)`：**事件帧**的写出口（第 4 个），写入语义
>    （`recentEvents` 头部并入派生明细项 + 同步 `playback.last_event`）**逐字不变**。
> 2. **新增** `applyPlaybackSnapshot(snapshot)`：**状态帧**的写出口（**第 6 个** —— 计数口径 =
>    `cr-6_idle_return_push.md` §五 **K5**：`setPlayback` / `setRecentEvents` / `setStats` /
>    `setSelectedPet` / `applyPushEvent` 之后为本项）；
>    语义 = **整份替换** `playback`（与 `setPlayback` 同级、**来源不同**：服务端推送），**天然幂等**
>    （重复帧无额外副作用）；**不合并 / 不归一化 / 不派生**任何业务状态。
> 3. **两条 push 写通道的关系**：
>    - **同一**「唯一写出口集合」**内**的两个成员（**不是**第二 store、**不是**新切片）；
>    - **事件帧 ⇒ `applyPushEvent`**（唯一去处，逐字不变）；**状态帧 ⇒ `applyPlaybackSnapshot`**（唯一去处）；
>    - 状态帧**只写** `playback` 切片：**不**触 `recentEvents` / `stats` / `petContext`；
>    - **禁止**把事件 `payload` 当状态快照写入（`event frame ≠ playback state`），
>      亦**禁止**由事件帧反推/合成 `playback` 的 `state` / `asset_url` / `action` / `loop`。
> 4. **不变**：schema 零变化（不新增切片 / 不新增字段 / 不新建第二 store）、
>    「唯一 store」约束、以及 PC-3 与 PC-5 的全部禁止项。

> ⚠️ **计数口径澄清（文档一致性笔 / 2026-10-03）**：上文第 1 项「（**第 4 个**）」与第 2 项「（**第 6 个**）」
> **分属两个基数**、**并非同一口径** ——
> - 「**第 4 个**」= **v1.0（Phase 2.2-6）时点基数**：**FS-3 三 setter**（`setPlayback` / `setRecentEvents` /
>   `setStats`）+ `applyPushEvent` ⇒ 第 4 个（**该时点正确，逐字保留**；v1.0 的 §PC-4 与 Step 3 表
>   「**第 4 个** / **3 → 4**」**同此基数**）；
> - 「**第 6 个**」= **K5 统一基数**（**含 Phase 3 新增的 `setSelectedPet`**）：`setPlayback` /
>   `setRecentEvents` / `setStats` / `setSelectedPet` / `applyPushEvent` + `applyPlaybackSnapshot` ⇒ 第 6 个。
> ⇒ **两值不矛盾**，仅**基数不同**；**统一读数以 K5 基数（第 6 个）为准**。**本注记不改写上文任何文字。**

> ⚠️ **派生项口径登记（CR-6 #7 / 2026-10-03）**：本 PC-4 的写入语义（第 2 项 **`platform` = `envelope.source`**）
> 在 **CR-6 第 7 笔（F4 = α：事件触发通道由 HTTP `/simulate` 改走 push）** 后，其**可观测值随之变化** ——
> WS 触发的入站 envelope `source = "ws"`（原 HTTP 路径落库为 `"simulator"`）⇒
> 前端 `recentEvents` 派生项的 **`platform` 由 `"simulator"` 变为 `"ws"`**。
> **属语义变化的如实登记（非缺陷）**；写入语义本身（`platform = envelope.source`）**逐字不变**。
> 详见 `docs/change_request/cr-6_idle_return_push.md` §十 · 「#7 引入的可观测语义变化」。

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
| **PC ↔ CR-6（2026-09-29）** | ⚠️ **本笔修订点** | **PC-2 / PC-4 追加受权增量**（状态帧分流 + 第 2 条 push 写通道）；**PC-1 / PC-3 / PC-5 / PC-6 逐字不变** |
| **PC ↔ WS-4 / API-2** | ✅ **无冲突** | 状态帧载荷 = API-2 的 **7 字段原样**；**不扩张** PlaybackState、**不新增**派生字段（`duration`/`progress`/`video_state`/`queue` 一律不发送） |
| **修改既有冻结（CR-6 范围更正）** | ⚠️ **是（限 PC-2 / PC-4）** | 本小节下方的「结论」句为 **v1.0 时点**结论，**逐字保留**；**CR-6 起**以本行**更正**：WS / WM / WA / WG / RF / FC **仍全部原样**，**PC-2 / PC-4 已追加受权增量**（FD、FS 的既有受权增量不受影响） |

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
| **CR-6**：帧型分流（事件帧 / 状态帧）+ 状态帧写出口（`applyPlaybackSnapshot`）| ⏳ **归 CR-6 前端实现笔**（本笔为**契约**笔，零代码） |
| **CR-6**：状态帧形状校验（`snapshot` 缺失/非对象/字段集 ≠ 7 ⇒ 拒收且不污染 `playback`） | ⏳ 同上 |

## 落地项（归后续授权步）

- **服务端推送帧**：`/api/ws` 向连接回推 envelope（含 WG-4 载荷形态裁决）——须修改 backend，另行授权；
- push 与 refresh 的**并发合并语义**（同一拍内 push 与 refresh 共存时的写入顺序）——Deferred；
- 断线可见性（RS 第五态「离线」表达）——Deferred（WS-5 已声明归后续 RS 修订）。

> **状态更新（CR-6 / 2026-09-29）—— 上述第 1 项已交付（仅 backend 侧）**：
> 服务端推送能力已由 **CR-6** 落地 —— 出站帧**两类形态**（事件帧 WM-1 + **状态帧**）见
> `phase2_websocket_push_boundary_decision.md`（**WP-3 v1.1**）；实现笔 = **`b92f82e`**
> （`feat: push playback state on action expiry`）；契约笔 = `02abb81`。
> **前端消费侧尚未实现** ⇒ 归 **CR-6 前端实现笔**（本条不影响上面第 2、3 项，二者仍 Deferred）。
> ⚠️ 本注记**不改写**上面三行原文。

## CR-6 修订记录（**受权增量**）（2026-09-29）

> **依据（变更请求）**：`docs/change_request/cr-6_idle_return_push.md`（**CR-6**）§五
> **K4**（PC-2 / PC-4 修订口径）· **K5**（FS-3 写出口增项）。
> **性质**：**零代码** —— 本笔只修订契约文字；前端实现归 CR-6 后续笔。

### 一、本次授权范围

1. **PC-2**：在「WM-1 envelope 逐字段保持」之外**追加**第二类帧（**状态帧**）的形态、
   **来源约束**（server pushed ≠ client inferred）与**分流边界**；事件帧校验/拒收**逐字不变**；
2. **PC-4**：在**保留** `applyPushEvent` 的前提下**新增** `applyPlaybackSnapshot`，
   并明确**两条 push 写通道**的关系与各自的唯一去处；
3. 与 **FS-3** 的关系：写出口集合**受权扩展**（细则见 `step4_frontend_state_decision.md` 的 CR-6 增量）。

### 二、存活禁止项（**逐字不变**）

- **不新增** envelope 字段、**不改动** WM-1 的 4 字段形态与白名单；
- **不扩张** `PlaybackState`（仍 **7 字段**，CR-1 起冻结）；**不发送** `duration` / `progress` /
  `video_state` / `queue`（WS-4 / WG-4 重申）；
- **不新增**切片 / 字段 / 第二 store；**不派生**业务状态；
- **禁止** `socket → loadRuntimeData()`、push 触发 refresh（PC-3）；
- **禁止** socket 回调直写组件状态、组件内建 websocket（PC-5）；
- **禁止** reconnect / heartbeat / queue sync / multi client / multi pet / offline recovery /
  message replay / 新依赖（PC-6 原样有效）。

### 三、本笔**未触及**（登记，供后续笔核对）

| 项 | 状态 |
|---|---|
| **前端实现**（`services/websocketClient.ts` 分流 / `hooks/useRuntimePush.ts` 接线 / `stores/usePetStore.ts` 新写出口 / 前端测试） | **未做** —— 归 CR-6 前端实现笔 |
| **`initial_state_frame`**（连接建立首帧是否推送） | **Deferred** —— 本增量明确：连接首帧**不推**，初始化仍走**既有 HTTP `/state`**（RF-1 / RF-2 不变） |
| **F4 = α**（`pet_selected_runtime_consistency`） | **Deferred** —— 不在 CR-6 范围内解决 |
| **WS-4 文档一致性登记**（`phase2_websocket_boundary_decision.md`） | **NOT NOW** —— 归后续「文档一致性笔」 |

### 四、变更记录

| 项 | 内容 |
|---|---|
| **原冻结约束** | ① **PC-2**：消息格式 = WM-1 envelope 逐字段保持（恰 4 字段）；非法帧拒收、不写 store；② **PC-4**：允许新增 `applyPushEvent` = push 通道的**唯一**写出口；③ FS-3 关系：写出口由 3 → **4** |
| **本次增量** | ① PC-2 **追加**状态帧形态 + 来源约束 + 分流边界（事件帧侧**逐字不变**）；② PC-4 **追加** `applyPlaybackSnapshot`（状态帧唯一写出口），并明确两条 push 写通道关系；③ 与 FS-3 的扩展关系（新增 `applyPlaybackSnapshot` = **第 6 个**写出口，计数口径见 §五 K5） |
| **不受影响** | **PC-1 / PC-3 / PC-5 / PC-6** 逐字不变；**WS-2 / WS-3 / WS-4 / WG-4 / WM-1 / API-2 / RF-1~5 / FC-1~5** 不变；**唯一 store 与 schema 零变化** |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-21 | 首版冻结（PC-1 ~ PC-6；编号经用户裁决由指令 FC-* 改为 PC-*） |
| v1.1 | 2026-09-29 | **CR-6**：**PC-2** 追加**状态帧**（第二类出站帧）形态 / 来源约束 / **帧型分流边界**，事件帧校验与拒收口径**逐字不变**；**PC-4** 追加 `applyPlaybackSnapshot`（状态帧唯一写出口）并明确两条 push 写通道关系；新增 §CR-6 修订记录；Step 3 / 设计验证清单 / 落地项追加更正行。**PC-1 / PC-3 / PC-5 / PC-6 不变**。见 `docs/change_request/cr-6_idle_return_push.md` §五 K4 / K5 |
| —（**文档一致性笔** 澄清） | 2026-10-03 | **PC-4** 追加**计数口径澄清**（「第 4 个」= v1.0 三-setter 基数、「第 6 个」= K5 基数；**两值不矛盾**、统一以**第 6 个**为准）+ **派生项口径登记**（**#7** 后 `recentEvents.platform` 由 `"simulator"` → `"ws"`）。**原文逐字保留**、**零代码**、**不改任何条款语义** |
