# Step 4.1-D-1 Frontend Data Flow Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_ui_boundary_decision.md`（UB-*）、`step4_frontend_api_client_decision.md`（FC-*）、
> `step4_frontend_state_decision.md`（FS-*）、`step4_frontend_component_decision.md`（FCM-*）
> 编号空间声明：本文档使用 **FD-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-*
> 均不复用、不覆盖；同一事项两处均有规定时，以**更严格者**为准。

## Input

- 指令：Step 4.1-D-1 Frontend Data Flow Integration —— 把已存在的
  `API Client ↓ Store ↓ Component` 三层**连接**起来；保持
  Component 不知道 API、Store 不主动发起网络请求、API Client 不持有状态。
- 前置（§一 前置检查，全部通过）：
  - branch = `phase1-step1-foundation`，HEAD = `ab9ed9f`，`git status --porcelain` 为空
  - `src/{api,stores,components,types}` 存在；`src/hooks/`、`src/services/`、`src/providers/` **均不存在**
  - `usePetStore.ts` 无网络请求 / 生命周期钩子 / 拉取类方法字样（三切片 + 三 setter 冻结态原样）

## Investigation（只读调查记录，2026-09-20）

### I-1 API Client 返回值

| 函数 | 返回类型 | 错误传播 |
|---|---|---|
| `getPlaybackState()` | `Promise<PlaybackState>` | 非 2xx 抛 `ApiError {status, code, message}`；网络层异常原样上抛（FC-5） |
| `getRecentEvents(limit?)` | `Promise<RecentEventsResponse>` | 同上 |
| `getStats()` | `Promise<StatsResponse>` | 同上 |
| `simulateEvent(body)` | `Promise<PlaybackState>` | 同上（本步不消费） |

### I-2 Store 当前职责（保持不变）

`usePetStore.ts` 只有 `playback` / `recentEvents` / `stats` 与 `setPlayback` / `setRecentEvents` /
`setStats`。本步**零改动**该文件；不得新增任何拉取类方法（fetch*/load*/refresh* 字样均不存在）。

### I-3 React 生命周期位置

- `App.tsx` 当前只做组件组合（FCM-2 / FCM-5：数据获取接线归「后续步骤」——即本步）。
- 裁决：新增 `src/hooks/` 作为 **orchestration layer**（编排层），App 只调用 `usePetRuntime()` 初始化数据流。

## Decision（裁决总表 FD-1 ~ FD-5）

### FD-1 —— Data Flow Boundary（冻结）

数据流固定：`Hook → API Client`、`Hook → Store`、`Store ↓ Component`。

- Hook 负责：调用 API 层函数、把结果**整份**写入 store（setPlayback / setRecentEvents / setStats）；
- Component 不知道 API（FCM-3 维持）；Store 不主动发起网络请求（FS-1 维持）；API Client 不持有状态（FC-2 维持）。

### FD-2 —— Hook Location（冻结）

- 编排逻辑**唯一**位置 `src/hooks/`；
- **禁止**：component 内生命周期钩子调 API 层、store 内任何请求、组件props 钻取绕过 store。

### FD-3 —— Phase 1 Hooks（冻结）

- 只实现 **`usePetRuntime()`**；
- 返回 `{ playback, recentEvents, stats, loading, error, refresh }`；
- 前三项为 store 三切片的只读投影；`loading` / `error` 为 hook 自身的运行状态（**不进 store**，
  store 形状维持 FS-3 冻结不变）；`refresh` 为手动重拉方法。

### FD-4 —— Error Boundary（冻结）

- Hook **不得吞错误**：API 抛出的错误实例（含 `ApiError` 的 `status` / `code` / `message`）
  **原样**保存进 `error` 并暴露，不改写、不降级、不 fallback；
- **禁止**自动重试、静默失败、吞掉异常后继续；`refresh()` 失败以 `error` 状态呈现（不额外抛出
  未处理 rejection —— 错误已通过返回值可见，这**不是**吞错，是「呈现方式」裁决）。

### FD-5 —— Scope（冻结）

- 本步实现：**初次加载**（App 挂载触发一次）+ **手动 refresh 方法**；
- **不实现**：polling、websocket、timer、background sync、错误重试策略、写操作（simulate）接线。

## 实现裁决（补充）

- 三块数据为**互不依赖的只读拉取**，`loadRuntimeData` 用 `Promise.all` 并行获取后按序写入 store
  （与指令的顺序 await 语义等价，仅省时延；写入顺序固定为 playback → recentEvents → stats）。
- 加载/错误状态放在一个**纯 JS 可观察 controller**（`createPetRuntimeController`）里，
  hook 经 `useSyncExternalStore` 订阅 —— 目的：**零新增依赖**下可完整测试
  成功/失败/重拉路径（vitest 无 jsdom，React effects 不会在静态渲染中执行）。
- 初次加载 = 挂载时调用一次 `refresh`（`useEffect` + 空依赖数组）；`refresh` 幂等、可重复调用。

## Forbidden（汇总）

- 组件 / App 直接 import API 层或调用 store setter；
- store 内出现网络请求、生命周期钩子、拉取方法；
- hook 内出现 UI 生成、DOM 操作、组件状态修改、对 API Client 的修改；
- 自动重试 / fallback / 改写错误 / 静默失败；
- `package.json` 新增依赖（react-query / axios / swr / socket.io 等一律禁止）。

## Deferred（不在本步裁决）

- 自动刷新节奏（polling 间隔）、写操作（simulate）触发点、错误呈现 UI；
- 动画播放、WebSocket、生产部署。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（FD-1 ~ FD-5） |
