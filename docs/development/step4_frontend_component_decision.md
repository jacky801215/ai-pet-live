# Step 4.1-C-4 Frontend Component Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_ui_boundary_decision.md`（UB-*）、`step4_frontend_skeleton_decision.md`（FE-*）、
> `step4_frontend_api_client_decision.md`（FC-*）、`step4_frontend_state_decision.md`（FS-*）
> 编号空间声明：本文档使用 **FCM-***。已有编号空间 UI-*（Step 4.1-B 早期原型决策）、
> UB-*（UI 边界冻结）、FE-*（工程骨架）、FC-*（API Client）、FS-*（状态层）均**不复用、不覆盖**；
> 同一事项两处均有规定时，以**更严格者**为准。

## Input

- 指令：Step 4.1-C-4 Frontend Component Boundary Implementation —— 只实现展示组件层并接线 App，
  不做动画、不做真实播放、不做后端联调、不新增依赖。
- 前置（§一 前置检查，全部通过）：
  - branch = `phase1-step1-foundation`，HEAD = `48b2317`，`git status --porcelain` 为空
  - 四份上游冻结文档齐备（UI / Skeleton / API Client / State）
  - `src/{api,types,stores,components}`、`src/components/player` 均存在；`src/stores/usePetStore.ts` 已就位
  - 禁止现状扫描（react-router / UI framework / animation / canvas / WebSocket / 轮询计时器）：
    全 frontend 实现代码 **0 命中**（唯二命中为既有 store 测试文件中的静态断言字符串，属守卫文本非实现）

## Investigation（只读调查记录，2026-09-20）

### I-1 Store 消费方式

- `src/stores/usePetStore.ts` 具名导出 **`usePetStore`**（`create<PetStoreState>()`，Zustand v5）与类型 `PetStoreState`。
- 三切片：`playback: PlaybackState | null`、`recentEvents: EventItem[]`、`stats: StatsResponse | null`；
  三个 setter：`setPlayback` / `setRecentEvents` / `setStats`（整份替换，无业务 action —— FS-3）。
- 组件消费方式：`usePetStore((s) => s.切片)` 只读取。

### I-2 API Client 可用接口（组件**不得** import）

| 模块 | 导出 |
|---|---|
| `src/api/events.ts` | `simulateEvent(body)`、`getRecentEvents(limit?)` |
| `src/api/playback.ts` | `getPlaybackState()` |
| `src/api/stats.ts` | `getStats()` |
| `src/api/client.ts` | `ApiError`、`request<T>()`（传输细节，更不得外泄） |

数据获取归调用方（后续步骤的联调层）喂给 store setter；组件只读 store（FS-4 / FCM-3）。

### I-3 UI Boundary 对照（UB-3 / UB-4）

- 组件**只能**：接收 store 数据、渲染展示、触发 UI action；
- **禁止**：自行发起网络请求、拼 URL、状态持久化、播放计时器（UB-3 Forbidden 表逐项继承）；
- 素材**只消费** `playback.asset_url`（后端已解析的对外地址），前端不生成任何素材路径（UB-4）。

### I-4 DTO 字段与指令表述的映射（以冻结契约为准）

- 指令中 PetPlayer「pet_id / action_name / status」对应 `PlaybackState` 实际字段：
  **`pet_id` / `action`（可空）/ `state`（仅 "idle" | "playing"）** —— 契约（API-2）无 `action_name` 字段，
  该字段名属于 `EventItem`（API-3），两者不得混用。
- EventList 展示 `event_type` / `action_name` / `created_at`（均来自 `EventItem`，后两者可空）。
- StatusBar 展示 `stats.events` / `stats.actions` / `stats.total`（API-4）。

## Decision（裁决总表 FCM-1 ~ FCM-5）

### FCM-1 —— Component Location（冻结）

- 展示组件**唯一**位置 `src/components/`（播放区子组件归 `src/components/player/`）；
- 职责只有「展示 UI」；
- **禁止**：传输层职责（HTTP 请求归 `src/api/`，经 store 供给）、创建第二个 store、数据持久化
  （localStorage 等浏览器存储一律禁止）。

### FCM-2 —— Phase 1 Components（冻结）

最小组件集（不得增删）：

```
components/
├── PetStage.tsx
├── EventList.tsx
├── StatusBar.tsx
└── player/
    └── PetPlayer.tsx
```

| 组件 | 职责 |
|---|---|
| `PetStage` | 宠物展示区域（内嵌 `PetPlayer`；有 `asset_url` 时展示素材，否则空态） |
| `PetPlayer` | 当前动作展示（`pet_id` / `state` / `action`；无快照时空态） |
| `EventList` | 最近事件列表（每项展示 `event_type` / `action_name` / `created_at`；空列表空态） |
| `StatusBar` | 统计展示（`events` / `actions` / `total`；无数据时空态） |

### FCM-3 —— Data Flow（冻结）

- 数据流固定：`Store ↓ Component`（FS-4 的组件侧落地）；
- 组件**只能**通过 `usePetStore()`（可带只读 selector）读取数据；
- **禁止**：Component → `src/api/*`、Component → 原生传输调用、Store → 网络请求。

### FCM-4 —— Rendering Boundary（冻结）

Phase 1 渲染手段白名单：**文本展示、图片 URL 展示（`<img src={asset_url}>`）、基础 className / data-\* 属性**。
**禁止**：动画库、canvas、视频标签自建播放器、组件内自建播放状态机、内联样式系统/主题方案（属后续步骤）。

### FCM-5 —— Scope（冻结）

- 本步实现：静态页面骨架、store 数据消费、空态展示、App 组合接线；
- **不实现**：自动刷新（polling）、WebSocket、动画播放、后端联调流程（数据获取接线归后续步骤）。

## Forbidden（汇总）

- 组件目录出现任何网络请求调用、API 模块 import、`/api/` 路径字面量；
- 组件创建 / 修改 store 形状、持久化、定时器、动画、canvas、WebSocket；
- 组件自行拼接素材或接口地址（UB-4：只消费 `asset_url`）；
- App 出现 store 逻辑 / 网络请求 / 定时器（只允许组合子组件）；
- `package.json` 新增任何依赖（本步零依赖变化）。

## Deferred（不在本步裁决）

- 数据获取接线与轮询节奏（谁调用 API 层并喂 store）；
- 样式方案 / 主题 / 布局细节（仅 className 骨架）；
- 动画播放实现（`asset_url` 为素材地址的后续播放方案）。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（FCM-1 ~ FCM-5） |
