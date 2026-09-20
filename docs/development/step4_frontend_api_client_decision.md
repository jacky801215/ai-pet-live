# Step 4.1-C Frontend API Client Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-20）。本文冻结 UB-1「API Client 层」的**实现边界**；
> 生效后变更须经 Change Request。

## 编号空间声明

本文使用 **`FC-1..FC-5`**（Frontend Client）。**不**使用 `API-*`（后端契约文档已占用）、
`UI-*`（Step 4.1-B 原型决策已占用）、`UB-*`（Step 4.1-C-0 边界决策已占用）、`FE-*`（骨架决策已占用）。

## Input 与 DTO 调查表（§二，来源：`step4_api_contract_decision.md` v1.0 FROZEN）

| API | Request | Response | Error |
|---|---|---|---|
| `POST /api/events/simulate` | `{event_type, user_id?, user_name?, payload?}`（未知顶层字段 400，DA-7；`payload` 显式 `null` 400；`pet_id`/时间戳后端补齐，UI 不发） | `PlaybackState`（6 字段） | `400 INVALID_REQUEST` |
| `GET /api/playback/state` | 无 query（QP-1：未知 query 400） | `PlaybackState`（6 字段） | `400 INVALID_REQUEST` |
| `GET /api/events/recent?limit=` | `limit` 可选，1..200，越界/非整数 400、禁纠偏（QP-3） | `{items: EventItem[], count}`（EventItem 恰 9 字段） | `400 INVALID_REQUEST` |
| `GET /api/stats` | 无 query | `{events: {…:int}, actions: {…:int}, total: int}` | `400 INVALID_REQUEST` |
| （所有端点）错误体 | — | — | `{code, message}`；码恰 3 个：`INVALID_REQUEST` / `ASSET_NOT_FOUND` / `INTERNAL_ERROR` |

`PlaybackState` 6 字段：`pet_id / state / action|null / asset_url|null / queue_size / last_event|null`。
`EventItem` 9 字段：`id / event_type / user_id|n / user_name|n / pet_id|n / action_name|n / platform|n / payload(object) / created_at|n`。

## Decision（裁决总表 FC-1 ~ FC-5）

| 编号 | 冻结项 | 裁决 |
|---|---|---|
| **FC-1** | Client 唯一出口 | 所有 HTTP 请求**只能**发生在 `src/api/`；组件 / store / 页面直接 `fetch` 一律禁止 |
| **FC-2** | Transport Boundary | 传输用**原生 `fetch`**，且只允许存在于 `src/api/client.ts`；**禁止** axios 及任何第三方 HTTP 库 |
| **FC-3** | DTO | DTO 只存于 `src/types/api.ts`；**只**含 API request / response / 错误体类型；**禁止** UI state / React 类型 |
| **FC-4** | API Modules | `src/api/events.ts`（`simulateEvent()` / `getRecentEvents()`）、`src/api/playback.ts`（`getPlaybackState()`）、`src/api/stats.ts`（`getStats()`）；**禁止** React import / store / localStorage |
| **FC-5** | Error Boundary | 客户端错误类型 `ApiError`（`status` + `code` + `message`）**只**由 HTTP 非 2xx 转换而来；**禁止**业务错误判断、**禁止**改写后端 `code`、**禁止**吞错误 |

### FC-1 —— Client 唯一出口（冻结）

- 任何 HTTP 请求必须经 `src/api/` 暴露的函数；组件 / store / 页面**不得**直接 `fetch`、
  不得自行拼 `/api/...` 路径、不得绕过 DTO 直接处理原始响应。

### FC-2 —— Transport Boundary（冻结）

- 传输实现 = 原生 `fetch`，**唯一**位置 `src/api/client.ts`（`request<TResponse>()` 私有通用入口）。
- 基地址：默认**同源**（`""`），可用 `VITE_API_BASE` 覆盖（开发期指向后端；CORS 白名单见 DB-6）。
- **禁止** axios / ky / react-query 等第三方 HTTP 或数据获取库（`package.json` 不得新增）。

### FC-3 —— DTO（冻结）

- `src/types/api.ts` 与后端契约**逐字段一致**（含可空性）；**禁止**前端「顺手」归一化字段名。
- DTO 上**禁止**出现 UI state、组件 props 形状、store 形状；`counts` 等合并逻辑属 store（UB-2）。

### FC-4 —— API Modules（冻结）

- 三个模块各自薄封装「路径 + 方法 + DTO」；`limit` 边界（1..200）由**后端**裁定，
  客户端**不复刻**校验（避免两份规则漂移；越界收 400 即契约行为）。
- **禁止**：React import、store 依赖、`localStorage` 等持久化、业务判断、重试逻辑。

### FC-5 —— Error Boundary（冻结）

- `ApiError { status, code, message }` **只**由 HTTP 非 2xx 转换：`code` / `message` 原样取自
  后端统一错误体；错误体非 JSON 时保留状态码与 `statusText`（**不吞错**）。
- **禁止**：解读 `code` 的业务含义、给 `code` 改名/翻译、吞掉或折叠错误、自动重试。
- 网络层异常（fetch reject）**原样上抛**，不包装、不重试。

## Verification（本步验收记录）

- `npm run build`（`tsc --noEmit && vite build`）→ **exit code 0**。
- 边界扫描：`fetch(` 仅命中 `src/api/client.ts`；`src/components/**` / `src/stores/**` / `src/App.tsx`
  **零** `fetch(` / `axios` / `/api/`。
- 依赖检查：`package.json` 无 axios / zustand / react-query / socket.io（依赖集与骨架步一致）。
- `src/api/.gitkeep` / `src/types/.gitkeep` 移除（实体文件已就位）；`src/stores/`、`src/components/` 保持占位不动。

## Deferred

| 项 | 说明 | 归属 |
|---|---|---|
| D-FC-1 | `ApiError` 的 UI 呈现（错误提示组件） | Step 4.1-C-3+ |
| D-FC-2 | 轮询节奏 / store 接线（消费本层函数） | Step 4.1-C-3+ |

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-20 | 首次冻结。裁决 FC-1..FC-5；落地 client / 三个 API module / DTO 类型；记录 DTO 调查表与验收。 |
