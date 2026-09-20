# Step 4.1-D-3 Frontend Runtime State Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_component_decision.md`（FCM-*）、`step4_frontend_data_flow_decision.md`（FD-*）、
> `step4_frontend_runtime_validation_decision.md`（RV-*）
> 编号空间声明：本文档使用 **RS-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* / RV-*
> 均不复用、不覆盖；同一事项两处均有规定时，以**更严格者**为准。
> 本步不进入：UI 美化、动画、播放器增强、自动刷新。

## Input

- 指令：Step 4.1-D-3 Frontend Runtime UX State Boundary —— 补齐页面级 runtime 状态表达边界：
  **loading / error / empty / ready** 四态。成功路径、hook 内部 loading/error、store 数据消费均已存在；
  缺失的只是「页面如何表达」。
- 前置（§一 前置检查，全部通过，无 STOP 条件）：
  - branch = `phase1-step1-foundation`，HEAD = `155fc35`，working tree clean
  - `src/hooks/usePetRuntime.ts`、`src/stores/usePetStore.ts`、`src/components/`、`src/App.tsx` 均存在
  - 禁止现状扫描（剥注释）：`src/components/**` 对 fetch( / `/api/` / axios / setInterval / WebSocket
    **0 命中**；`src/hooks/**` 无组件 import

## Investigation（只读调查记录，2026-09-20）

### 2.1 App 数据状态

- `App()` 当前**只调用** `usePetRuntime()` 做初始化（触发挂载加载），**不读取**返回值
  （`{playback, recentEvents, stats, loading, error}` 全部未消费）——页面因此无法表达加载/失败。

### 2.2 Component 空态能力（已具备，本步不动组件）

| 组件 | 空态 | 触发条件 |
|---|---|---|
| `PetStage` | 「暂无宠物画面」 | `playback?.asset_url == null` |
| `PetPlayer` | 「暂无播放内容」 | `playback == null` |
| `EventList` | 「暂无最近事件」 | `recentEvents.length === 0` |
| `StatusBar` | 「暂无统计数据」 | `stats == null` |

即 **empty 态已由组件层自足表达**（RS-4 只需保证 ready 布局下渲染组件即可）。

### 2.3 错误展示位置

- `ApiError`（status / code / message）目前**只存在于 hook**（FD-4：原样保存在 `error`），
  从未进入组件或页面 —— 页面级错误表达缺失，由本步补齐。

## Decision（裁决总表 RS-1 ~ RS-5）

### RS-1 —— Runtime State（冻结）

- 页面状态**唯一来源**：`usePetRuntime()` 返回的 `loading` / `error`（数据切片已有；
  组件**禁止**自建 loading / 自建 error，App 是唯一消费点）。

### RS-2 —— Loading（冻结）

- `loading === true` 时页面展示**统一 loading 区域**（单块文本区域，含 `data-testid="app-loading"`）；
- **禁止**：skeleton library、animation、timer、分组件散落的加载态。

### RS-3 —— Error（冻结）

- error 态页面**必须完整保留** `status` / `code` / `message` 三元组原样展示（RS 与 FD-4 一致）；
- **禁止**：自定义错误分类、fallback 文案覆盖、把错误折叠成布尔或通用文案；
- 实现注记：App 以鸭子类型读取 `status` / `code`（**不 import** `src/api/**`，维持 App import 白名单）；
  非 ApiError 的 Error（理论不出现）status/code 显示占位符，message 仍原样。

### RS-4 —— Empty（冻结）

- ready 态下数据为空时，由**既有组件空态**表达（暂无宠物画面 / 暂无最近事件 / 暂无统计数据）；
- **不得**：修改 DTO、修改 store shape、在 App 重复造空态组件。

### RS-5 —— Scope（冻结）

- 只实现 runtime 状态展示（error ↓ loading ↓ ready 三级优先组合，empty 属 ready 的组件内表达）；
- **不实现**：retry button、refresh UI、polling、notification、错误重试流程。

## 实现裁决（补充）

- 状态组合优先级固定：**error → loading → ready**（error 优先级最高：失败时页面只展示错误，
  不展示半成品数据）。
- loading / error 页面区**内联在 App.tsx**（不新建组件文件）—— FCM-2 最小组件集维持不变
  （PetStage / EventList / StatusBar / player/PetPlayer 四个，不增删）。
- App 增加可选 `controller` 注入 prop（**仅测试用**，与 hook 的 RV 注入缝隙同构；
  生产 `<App />` 零参渲染，行为不变）。
- 组件四件零改动；`src/api/**`、`src/stores/**`、`package.json` 零触碰。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（RS-1 ~ RS-5） |
