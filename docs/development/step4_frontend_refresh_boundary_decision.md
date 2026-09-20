# Step 4.1-D-4 Frontend Refresh Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_data_flow_decision.md`（FD-*）、`step4_frontend_runtime_validation_decision.md`（RV-*）、
> `step4_frontend_runtime_state_decision.md`（RS-*）
> 编号空间声明：本文档使用 **RF-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* / RV-* / RS-*
> 均不复用、不覆盖；同一事项两处均有规定时，以**更严格者**为准。
> 本步不实现：自动刷新、定时器、websocket、notification、播放控制、后端修改。

## Input

- 指令：Step 4.1-D-4 Frontend Manual Refresh Boundary —— 在不破坏 FD / RS 边界的前提下，
  引入**人工触发**刷新入口；验证链路
  `用户操作 ↓ App/UI ↓ usePetRuntime.refresh() ↓ API Client ↓ Store ↓ Components`。
- 前置（§一 前置检查，全部通过，无 STOP 条件）：
  - HEAD = `b9de7a7`，working tree clean；五处目标文件/目录均存在
  - STOP 扫描（剥注释）：`src/components/**` 无 API / hooks import；`src/stores/**` 无 async / fetch / Promise；
    `src/hooks/**` 无 timer / interval / websocket

## Investigation（只读调查记录，2026-09-20）

### 2.1 refresh 当前暴露情况

- `usePetRuntime()` 返回值含 `refresh`（FD-3），实现为 `useCallback(() => controller.refresh(), [controller])`
  —— **引用稳定**，可作为按钮事件处理器直接绑定，不因重渲染变化；
- 当前**无任何 UI 使用** refresh（按钮尚未存在）。

### 2.2 当前页面入口

- App ready 分支结构：`PetStage / StatusBar / EventList`；
- 刷新按钮插入位置裁决：**ready 分支顶部新增一个工具条**（`data-testid="app-toolbar"`）容纳按钮
  （`data-testid="app-refresh"`，文本「刷新」），三组件顺序不变。

## Decision（裁决总表 RF-1 ~ RF-5）

### RF-1 —— Refresh Ownership（冻结）

- refresh **唯一来源**：`usePetRuntime()` 返回值；
- **禁止**：API module 暴露 UI handler、component 自建 reload、绕过 hook 直接调 API 层。

### RF-2 —— Trigger（冻结）

- Phase 1 允许的触发方式：**button click ↓ refresh()**（人工触发，恰好一次调用由浏览器语义保证）；
- **禁止**：interval、effect loop、timer、任何自动触发。

### RF-3 —— Loading During Refresh（冻结）

- refresh 进行中**复用** hook 的 `loading`（RS-2 统一加载区随之呈现）；
- **禁止**：第二套 loading state、component local state（`useState` 计数/标志一律不允许）。

### RF-4 —— Error（冻结）

- refresh 失败：`ApiError` **原样**进入 `error`（FD-4 链路不变）；
- 页面按 RS 优先级（error ↓ loading ↓ ready）切换到错误区，完整展示 status / code / message。

### RF-5 —— Scope（冻结）

- 只实现：**一个**刷新入口（ready 分支工具条按钮）+ refresh 调用 + 测试覆盖；
- **不实现**：自动刷新、toast、retry strategy、按钮禁用态/防抖策略（后续步骤）。

## 实现裁决（补充）

- 按钮处理器：`onClick={() => { void runtime.refresh(); }}` —— `void` 明确吞掉的是
  「Promise 对象本身」而非错误（错误已由 controller 原样写入 error，FD-4 / RF-4），
  不会产生未处理 rejection；
- 按钮位置在 App ready 分支内联（不新建组件文件，FCM-2 组件集维持不变）；
- App 内**禁止出现 `useState`**（RF-3 的可静态断言表达）。

### 测试裁决（记录性，与 RV / RS 一致的已知限制）

- 静态渲染（无 jsdom、零新增依赖）无法派发 DOM 点击事件 —— 「点击」以
  **调用按钮 onClick 所绑定的同一函数引用**（hook 返回的 `refresh`，注入同一 controller 后经
  probe 捕获）等价模拟；按钮的存在性、位置、文案由 ready 分支 markup 断言。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（RF-1 ~ RF-5） |
