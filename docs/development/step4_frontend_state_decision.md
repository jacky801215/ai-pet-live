# Step 4.1-C Frontend State Decision v1.1（FROZEN）

> **状态**：v1.1 **FROZEN**（**CR-6 修订** = 2026-09-29）。本文冻结 UB-2「State 层」的**实现边界**（关闭 D-FC-2 的一部分：
> 状态容器选型；轮询节奏仍归后续 Step）。生效后变更须经 Change Request。
>
> **CR-6 修订（受权增量，2026-09-29）**：**仅**修订 **FS-3（Store Shape）** —— ① actions 集合自现行
> 集合**扩展**；② **登记** `applyPlaybackSnapshot`；③ 明确 **snapshot 写入责任**。
> **FS-1 / FS-2 / FS-4 / FS-5 逐字不变**。依据：`cr-6_idle_return_push.md` §五 **K5**；
> 与 `phase2_frontend_push_channel_decision.md`（**PC-2 / PC-4 v1.1**）配套。

## 编号空间声明

本文使用 **`FS-1..FS-5`**（Frontend State）。既有编号空间（**不重复使用**）：`API-*`（后端契约）、
`UI-*`（Step 4.1-B 原型）、`UB-*`（边界决策）、`FE-*`（骨架）、`FC-*`（API Client）。

## Input（§二 只读调查记录，2026-09-20）

1. **API DTO 映射确认**：`src/types/api.ts` 已有 `PlaybackState`（**7 字段**；**CR-1** 授权增量 + `loop`，本条原记为 6 字段）/ `EventItem`（9 字段）/
   `RecentEventsResponse` / `StatsResponse` / `SimulateEventRequest` / `ApiErrorBody`，与后端契约逐字段一致。
2. **Store 职责边界确认**（准绳 `step4_ui_boundary_decision.md` UB-2）：store 只负责
   `playback snapshot` / `recent events` / `statistics` 三类服务器快照的消费态；
   **禁止** HTTP 请求、fetch、URL 拼接、asset path 处理、动画计时器、React component state 重复。
3. **技术选型裁决（D-UB-1 剩余部分）**：现状无任何 store 实现 / Context /Redux / MobX / 事件总线
   （frontend 全源码扫描 0 命中，非 STOP）⇒ **采用 Zustand**：
   React 生态成熟、单文件 store 无 boilerplate、selector 粒度订阅与 UB-2「组件只读状态」天然对齐、
   可脱离 React 单测（vanilla `getState`/`setState`）。

## Decision（裁决总表 FS-1 ~ FS-5）

| 编号 | 冻结项 | 裁决 |
|---|---|---|
| **FS-1** | Store Boundary | 唯一位置 `src/stores/`；负责 server snapshot 的 UI 消费状态；**禁止** API transport / fetch / DTO 转换 |
| **FS-2** | Store Technology | **Zustand**（v5，`create<PetStoreState>()`）；**禁止** Redux / Context state / MobX / 自建 event bus / 第二个状态库 |
| **FS-3** | Store Shape | 单一 store `usePetStore`：`{playback: PlaybackState\|null, recentEvents: EventItem[], stats: StatsResponse\|null}` + actions `setPlayback()` / `setRecentEvents()` / `setStats()`；**禁止**业务 action（**v1.1**：actions **受权扩展** + 登记 `applyPlaybackSnapshot`，增量见下） |
| **FS-4** | Data Flow | 固定单向：`Component → Store ← API Client`；**禁止** `Component → API`、`Component → fetch`、`Store → fetch` |
| **FS-5** | Scope | 本步实现：状态容器 + setter + 初始空状态 + 单测；**不实现** polling、websocket、动画状态、派生业务逻辑 |

### FS-1 —— Store Boundary（冻结）

- 服务器快照的消费状态**只能**放 `src/stores/`；组件不经 store 不得触达服务器数据。
- store 内**禁止**：`fetch`、API 路径 / URL 拼接、DTO 字段归一化或改名（快照**整份**原样入存）。

### FS-2 —— Store Technology（冻结）

- 依赖仅 `zustand`；**禁止**再引入第二个状态方案（含 React Context 作状态总线、Redux、MobX、Jotai、自建 event bus）。
- store 文件**禁止**直接 `import React`（zustand hook 形态即可）。

### FS-3 —— Store Shape（冻结）

- Phase 1 **单一 store**：`usePetStore`（含 `playback` / `recentEvents` / `stats` 三个切片）；
  **禁止**拆多 store / slice 组合 / 新建平行 store。
- actions 仅 `setPlayback(snapshot)` / `setRecentEvents(events)` / `setStats(stats)` —— 整份替换语义
  （不合并、不去重、不排序：排序与 `count` 口径归后端 API-3）。
- **禁止**业务 action（如 `triggerEvent()` / `refreshStats()`）—— 那类编排归后续 Step 的组件/服务层。

> **受权增量（CR-6 / 2026-09-29）—— FS-3 actions 扩展与 snapshot 写入责任**：
> 以上冻结文字**逐字保留**；本节**追加** push 通道带来的写出口与写入责任，
> **不改动** schema（三切片）、**不新增**切片 / 字段 / 第二 store、**不派生**业务状态。
>
> 1. **actions 自现行集合扩展**：沿用 PC-4 的既有受权增量 `applyPushEvent(envelope)`，
>    **再新增** `applyPlaybackSnapshot(snapshot)`（**第 6 个**写出口 —— 计数口径 =
>    `cr-6_idle_return_push.md` §五 **K5**：`setPlayback` / `setRecentEvents` / `setStats` /
>    `setSelectedPet` / `applyPushEvent` 之后为本项）。
>    - `applyPlaybackSnapshot(snapshot)` 语义 = **整份替换** `playback`（沿用 `setPlayback` 的替换口径，
>      **仅来源不同**：入参来自服务端**状态帧**推送），**天然幂等**（重复帧无额外副作用）；
>      **不合并 / 不去重 / 不归一化 / 不排序**。
> 2. **snapshot 写入责任（唯一去处）**：**状态帧 ⇒ `applyPlaybackSnapshot`**（唯一归宿，**只写** `playback` 切片）；
>    **事件帧 ⇒ `applyPushEvent`**（**逐字不变**）。二者**互不代偿**：
>    - **禁止**由事件 `payload` 反推 / 合成 `playback` 的 `state` / `action` / `asset_url` / `loop`；
>    - **禁止**状态帧写入 `recentEvents` / `stats`（这两片只接受**事件帧**与 `set*`）；
>    - **禁止**客户端**推断**状态（**`server pushed ≠ client inferred`** —— PC-2 不变量在本文件的落点）。
> 3. **setter 语义不变**：既有 `setPlayback` / `setRecentEvents` / `setStats` 的**整份替换**语义、
>    以及「**禁止**业务 action（`triggerEvent()` / `refreshStats()`）」**逐字不变**。
>    本条新增项属**写通道**（第 1 条第 2 项口径），**不是**业务 action：无编排 / 无请求 / 无派生。
> 4. **不变项**：单一 store、三切片、零 fetch / 零 `/api/` / 零 timer（**FS-1 / FS-4** 原样有效）。

### FS-4 —— Data Flow（冻结）

- 唯一合法流向：**Component → Store ← API Client**（组件触发 API 调用方把结果 `set*` 进 store）。
- **禁止**：`Component → API`（绕过 store 直取）、`Component → fetch`、`Store → fetch`。

### FS-5 —— Scope（冻结）

- 本步交付：依赖接入、`src/stores/usePetStore.ts`、初始空状态、setter、vitest 单测。
- **不实现**：polling（轮询节奏）、websocket、动画状态、派生业务逻辑（`counts` 合并等）。

## Verification（本步验收记录）

- `npm install`（+zustand ^5.0.2 / vitest ^2.1.8 devDep，**无** axios / react-query / socket.io / 动画库）
- `npm run build`（`tsc --noEmit && vite build`）→ **exit code 0**；`npm test`（vitest run）→ 全部通过
- 边界扫描：`src/stores/**` 中 `fetch(` = 0、`/api/` = 0、`import … src/api` = 0；store 源文件无 React import
- 测试覆盖：初始状态 / 三 setter 整份替换 / 切片独立 / store 源码静态边界断言（FS-1 / FS-4）

## CR-6 修订记录（**受权增量**）（2026-09-29）

> **依据（变更请求）**：`docs/change_request/cr-6_idle_return_push.md`（**CR-6**）§五 **K5**
> （FS-3 写出口增项）；配套 `phase2_frontend_push_channel_decision.md`（**PC-2 / PC-4 v1.1**）。
> **性质**：**零代码** —— 本笔只修订契约文字；前端实现（store 新写出口等）归 CR-6 后续笔。

### 一、本次授权范围（**仅** FS-3）

1. **actions 从现行集合扩展**：保留 3 个 `set*`，追加 `applyPushEvent`（PC-4 既有增量）与
   `applyPlaybackSnapshot`（本笔新增，第 6 个写出口）；
2. **登记 `applyPlaybackSnapshot`**：**状态帧**的**唯一**写出口，整份替换 `playback`、**天然幂等**；
3. **明确 snapshot 写入责任**：**状态帧 ⇒ `applyPlaybackSnapshot`**、**事件帧 ⇒ `applyPushEvent`**；
   两片不得互串、**不得**由客户端推断状态（`server pushed ≠ client inferred`）。

### 二、存活禁止项（**逐字不变**）

- **不新增**切片 / 字段 / 第二 store；**不派生**业务状态；
- 三个 `set*` 的**整份替换**语义与「**禁止**业务 action」**逐字不变**；
- **FS-1**（**禁止** `fetch` / API 路径 / DTO 归一化改名）、**FS-2**（**仅** `zustand`，禁第二状态方案 /
  store 内禁 `import React`）、**FS-4**（**禁止** `Component → API` / `Component → fetch` /
  `Store → fetch`）**原样有效**；
- **FS-5** 范围冻结（本步**不实现** polling / websocket / 动画状态 / 派生业务逻辑）**原样有效**。

### 三、本笔**未触及**（登记，供后续笔核对）

| 项 | 状态 |
|---|---|
| **前端实现**（`stores/usePetStore.ts` 新增 `applyPlaybackSnapshot` / `services/websocketClient.ts` 帧型分流 / `hooks/useRuntimePush.ts` 接线 / 前端测试） | **未做** —— 归 CR-6 前端实现笔 |
| **`initial_state_frame`**（连接建立首帧是否推送） | **Deferred** —— 连接首帧**不推**，初始化仍走**既有 HTTP `/state`** |
| **F4 = α**（`pet_selected_runtime_consistency`） | **Deferred** —— 不在 CR-6 范围内解决 |
| **WS-4 文档一致性登记**（`phase2_websocket_boundary_decision.md`） | **NOT NOW** —— 归后续「文档一致性笔」 |

### 四、变更记录

| 项 | 内容 |
|---|---|
| **原冻结约束** | FS-3：单一 store（`playback` / `recentEvents` / `stats` 三切片）+ actions **仅** `setPlayback()` / `setRecentEvents()` / `setStats()`（整份替换）；**禁止**业务 action |
| **本次增量** | FS-3 **追加**写出口 `applyPlaybackSnapshot`（**第 6 个**），并明确 **snapshot 写入责任**（状态帧 / 事件帧各自的**唯一去处**）；**schema 与三切片零变化** |
| **不受影响** | **FS-1 / FS-2 / FS-4 / FS-5** 逐字不变；**PC-2 / PC-4** 为**配套**增量；**UB-2 / FD-\* / FC-\*** 不变 |

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-20 | 首次冻结。裁决 FS-1..FS-5（状态库选 Zustand，关闭 D-UB-1 剩余部分）；落地 usePetStore 与单测。 |
| v1.1 | 2026-09-29 | **CR-6**：**FS-3** 受权增量 —— actions 集合**扩展**（登记 `applyPlaybackSnapshot` = 状态帧唯一写出口，**第 6 个**）+ 明确 **snapshot 写入责任**；新增 §CR-6 修订记录；裁决总表 FS-3 行标注。**FS-1 / FS-2 / FS-4 / FS-5 不变**。见 `docs/change_request/cr-6_idle_return_push.md` §五 K5 |
