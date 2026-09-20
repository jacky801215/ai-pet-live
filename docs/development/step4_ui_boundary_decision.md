# Step 4.1-C UI Boundary Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-20）。本文冻结 Phase 1 前端的**分层边界**与**范围**；
> 生效后任何违反均须走 Change Request 修订本文，不得在实现时静默突破。

## 编号空间声明（必读）

- 本文使用 **`UB-1 .. UB-5`**（UI Boundary）作为决策编号，沿用本仓库「每文档独立命名空间」惯例
  （既有：`API-*` / `DA-*` / `DB-*` / `AS-*` / `QP-*`）。
- `docs/development/step4_ui_prototype_decision.md`（Step 4.1-B，v1.0 FROZEN）已占用 **`UI-1..UI-6`**
  （窗口形态 / 组件边界 / 状态模型 / 事件产生位置 / 动作消费方式 / 动画资源责任），
  该含义**不变**、继续有效；**两者互不替代、互不改写**。
  - 实质重叠处（本文 UB-4 ≙ 既有 UI-6「只消费 `asset_url`」；本文 UB-3 ⊇ 既有 UI-2 组件划分）
    以**更严格者**为准，两者不矛盾。
- 全仓引用边界决策时，引用 `UB-*` 一律指本文；引用 `UI-*` 一律指 Step 4.1-B 原型决策文档。

## Input

- 本步指令：Step 4.1-C-0（只调查 + 冻结边界；禁止写组件 / 装 npm 包 / 改 frontend 与 backend 代码）
- 前置冻结文档：
  - `step4_api_contract_decision.md`（API-1..API-4，响应/错误契约）
  - `step4_api_implementation_boundary.md`（DA-1/DA-3/DA-5/DA-7）
  - `step4_api_runtime_decision.md`（DB-*）
  - `step4_api_stability_decision.md`（AS-1..AS-4）与 `step4_api_query_boundary_decision.md`（QP-1..QP-5）
  - `step4_ui_prototype_decision.md`（UI-1..UI-6）
- 后端基线：`7944308`（`feat: stabilize api query validation`），全量回归 **467 passed**

## Investigation（只读调查记录，2026-09-20）

### C-1 工程类型

- `frontend/` **尚未初始化**：无 `package.json` / `package-lock.json` / `pnpm-lock.yaml` / `yarn.lock`，
  无 `vite.config.*`、无 `tsconfig*.json` ⇒ **Vite / CRA / Next 均未选定，React 版本 / TypeScript / 包管理器均未定**。
  技术选型属 **Step 4.1-C-1（Frontend Skeleton Implementation）**，本文**不**裁决。

### C-2 当前目录结构

`frontend/` 仅有空占位（6 个 0 字节 `.gitkeep`，无任何代码）：

```
frontend/
├── src/
│   ├── api/          （空占位）  ← 对应 UB-1
│   ├── components/   （空占位）  ← 对应 UB-3
│   ├── player/       （空占位）  ← 对应 UB-3（播放区组件归组）
│   ├── stores/       （空占位）  ← 对应 UB-2
│   └── types/        （空占位）  ← DTO 类型归组（UB-1 的映射产物）
└── tests/            （空占位）
```

目录骨架已与本文 UB-1/UB-2/UB-3 一一对应 —— 冻结即确认该骨架，后续 Step 不得另设并行目录
（如 `services/` / `hooks/` 之外的第二个数据面）。

### C-3 依赖调查

- **无任何已装依赖**（无 manifest）：router / state manager / HTTP client / CSS framework 均未引入。
- 本文**不**选定具体库；唯一约束：HTTP 层必须收敛在 `src/api/`（UB-1），状态必须收敛在 `src/stores/`（UB-2），
  无论最终选 fetch 还是 axios、zustand 还是 pinia。

### C-4 后端 API 对接调查（冻结 API → 前端 DTO 需求）

| 冻结端点 | 前端所需 DTO（以 API 契约为准，字段集冻结） |
|---|---|
| `POST /api/events/simulate` | 请求 `{event_type, user_id?, user_name?, payload?}`（DA-7：未知顶层字段被拒）；响应 = `PlaybackState` |
| `GET /api/playback/state` | 响应 = `PlaybackState`（6 字段：`pet_id/state/action/asset_url/queue_size/last_event`） |
| `GET /api/stats` | 响应 `{events: {…: int}, actions: {…: int}, total: int}` |
| `GET /api/events/recent?limit=` | 响应 `{items: EventItem[], count: int}`；`EventItem` 恰 9 字段（`payload` 为对象） |
| 错误体（所有端点） | `{code, message}`；码恰 3 个（`INVALID_REQUEST`/`ASSET_NOT_FOUND`/`INTERNAL_ERROR`）；**UI 不得依赖细码** |

### §三 冲突检查结果（全部无冲突）

- **API client 重复**：`grep fetch(` / `grep axios` 于 `frontend/` → **0 命中**（尚无 HTTP 层）。
- **状态重复**：`grep playback` / `grep recent` 于 `frontend/` → **0 命中**（尚无状态管理）。
- **组件重复**：`src/components/` 仅有 `.gitkeep`，无 Pet/Player/Stats/Event 组件。
- ⇒ 不触发「发现冲突即 STOP」；本文即为**首个**前端边界裁决。

## Decision（裁决总表 UB-1 ~ UB-5）

| 编号 | 冻结项 | 裁决 |
|---|---|---|
| **UB-1** | API Client Boundary | `frontend/src/api/` 独占 HTTP；**禁止** React state / 动画 / 播放计时器 |
| **UB-2** | State Boundary | `frontend/src/stores/` 独占状态（快照 / 统计 / 最近事件）；**禁止**直接 `fetch` / 拼 URL |
| **UB-3** | Component Boundary | `frontend/src/components/`（含 `player/`）只做展示；**禁止** API 调用 / 数据持久化 |
| **UB-4** | Asset URL | 前端**只消费** `asset_url`；**禁止**自行生成 `/assets/pets/...` |
| **UB-5** | Phase 1 Scope | 实现：单宠物展示 / 当前动作播放 / 最近事件 / 基础统计；**不实现**：WebSocket / 登录 / 多用户 / 上传素材 / 实时推流 |

### UB-1 —— API Client Boundary（冻结）

- **归 `frontend/src/api/`**：全部 HTTP request / response、DTO 映射、错误体解析、查询参数组装。
- **职责**：
  - 按冻结端点封装 4 个调用（simulate / playback state / stats / recent events）；
  - 响应 → `src/types/` 内 DTO 的映射（字段集 = API 契约，**不得增删改名**）；
  - `{code, message}` 错误体的统一解析与抛出。
- **禁止**：
  - React state / 组件引用 / 任何 UI 概念；
  - 动画、播放计时器、轮询调度（何时轮询属 store 或编排层，**不**属 api）；
  - 业务判断（事件合法性与后端同源规则**不得**在前端复刻一份）。

### UB-2 —— State Boundary（冻结）

- **归 `frontend/src/stores/`**：`playback snapshot` / `stats` / `recent events` 三类状态的唯一持有地。
- **职责**：缓存最新快照、驱动轮询节奏（Phase 1 无 push 通道）、向组件提供只读状态。
- **禁止**：
  - 直接 `fetch`（必须经 `src/api/`）；
  - URL 拼接（含 `asset_url` 之外的任何资源地址）；
  - 把 DTO 原样散落进组件 props 之外的全局可变对象。

### UB-3 —— Component Boundary（冻结）

- **归 `frontend/src/components/`（及 `player/`）**：纯展示 + 用户交互**发射**（把用户行为交给 store/api 触发）。
- **职责**：渲染 `PlaybackState` / 统计 / 事件列表；提交原始事件（仅 4 键，见 DA-7 / UI-4）。
- **禁止**：
  - API 调用（组件不得 import `src/api/`）；
  - 数据持久化（localStorage / IndexedDB 等一律不做）；
  - 自持第二份播放状态（快照唯一来源 = store，UI-3 / UB-2）。

### UB-4 —— Asset URL（冻结）

- 前端**只消费**后端下发的 `asset_url`（后端口径 `"/" + asset_path`，DA-5 冻结）。
- **禁止**前端自行生成 / 拼接 / 猜测 `/assets/pets/...` 任何形态的素材地址；
  **禁止**内建「动作 → 文件名」映射（P3 / UI-6 同源：素材解析全项目只有 AssetManager 一个点）。
- `asset_url` 为 `null`（idle）时按「无素材可播」展示，**不得**回退到本地占位拼接。

### UB-5 —— Phase 1 Scope（冻结）

- **实现**：单宠物展示（`pet_id` 由后端派生，前端不选宠物）、当前动作播放、最近事件列表、基础统计。
- **不实现**：WebSocket（含 WS query —— 属 QP-5 范畴的 Phase 2）、登录、多用户、上传素材、实时推流。
- 进入任一被排除项须 Change Request 修订本文与后端契约，**不得**在前端单方面引入。

## Forbidden（汇总）

- 组件/`.gitkeep` 之外，**禁止**在本步产生任何 frontend 代码或依赖变更（本步零 frontend diff）。
- **禁止**另设并行数据面目录（第二个 api/ 或 store 实现）。
- **禁止**前端复刻后端校验/规则（事件合法性、limit 边界等以后端裁定为准）。
- **禁止**在前端写死 `pet_id`（红线 C3 同源：Phase 1 由后端 `pet_ids()` 派生下发）。

## Deferred（不在本步裁决）

| 项 | 说明 | 归属 |
|---|---|---|
| D-UB-1 | 技术选型：Vite / React 版本 / TS / 包管理器 / router / state 库 / CSS 方案 | Step 4.1-C-1 |
| D-UB-2 | 轮询节奏与「到期回落」的前端呈现细节（后端已按查询推进状态机） | Step 4.1-C-1+ |
| D-UB-3 | `tests/` 内前端测试形态（组件测试 / 契约 mock） | Step 4.1-C-1+ |

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-20 | 首次冻结。裁决 UB-1..UB-5（编号空间与 Step 4.1-B 的 UI-1..UI-6 显式分离）；记录 C-1..C-4 调查与零冲突结论。 |
