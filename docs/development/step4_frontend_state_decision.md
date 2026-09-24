# Step 4.1-C Frontend State Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-20）。本文冻结 UB-2「State 层」的**实现边界**（关闭 D-FC-2 的一部分：
> 状态容器选型；轮询节奏仍归后续 Step）。生效后变更须经 Change Request。

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
| **FS-3** | Store Shape | 单一 store `usePetStore`：`{playback: PlaybackState\|null, recentEvents: EventItem[], stats: StatsResponse\|null}` + actions `setPlayback()` / `setRecentEvents()` / `setStats()`；**禁止**业务 action |
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

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-20 | 首次冻结。裁决 FS-1..FS-5（状态库选 Zustand，关闭 D-UB-1 剩余部分）；落地 usePetStore 与单测。 |
