# Step 4.1-F-0 Frontend Event Simulator Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_component_decision.md`（FCM-*）、`step4_frontend_data_flow_decision.md`（FD-*）、
> `step4_frontend_refresh_boundary_decision.md`（RF-*）、`step4_frontend_runtime_state_decision.md`（RS-*）、
> `step4_frontend_player_interaction_decision.md`（PI-*）、`step4_api_contract_decision.md`（API-1 契约）、
> `docs/development/development_plan.md` v0.2（任务 **1-16**：前端事件模拟器面板，P0）
> 编号空间声明：本文档使用 **ES-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* /
> RV-* / RS-* / RF-* / FP-* / PI-* 均不复用、不覆盖。
> **与 FCM-2 的关系（必读，经用户裁决）**：FCM-2 曾冻结「最小组件集（不得增删）= PetStage / EventList /
> StatusBar / PetPlayer 四件」。本决策**局部修订**该条：组件集**增补第五件 `EventSimulator`**；
> 原四件的位置与职责**零改动**。两处冲突以本文档（更具体的模拟器决策）为准。
> 本步**只冻结边界，不实现任何代码**（实现归 Step 4.1-F-1，待下一条授权）。

## Input

- 指令：Phase 1 自主推进授权（2026-09-20）—— 完成前端基础闭环剩余工作，不进 Phase 2。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `8aea251`，working tree clean。
- 用户裁决（AskUserQuestion，2026-09-20）：
  1. FCM-2 冲突 → **按 FP-1 修订 FCM-4 的先例做局部修订**；
  2. 推进节奏 → **F-0 冻结完成后 STOP**，F-1 实现另待授权。

## Investigation（只读调查记录，2026-09-20）

### I-1 Phase 1 前端闭环缺口（任务对照 development_plan.md v0.2）

| 任务 | 状态 |
|---|---|
| 1-15 前端展示端（宠物画面 + 待机） | ✅（PetStage + PetPlayer） |
| **1-16 前端事件模拟器面板（gift/comment/follow）** | ❌ **唯一缺失的 P0 闭环项** |
| 1-17 前端状态栏（播放状态 + 互动计数） | ✅（StatusBar） |
| 1-19 / 1-20 单元 / 集成测试 | ✅（backend 467 passed / frontend 64 passed） |
| 1-21 音效 / 1-22 队列增强 | P1；1-21 与 PI-5（禁 audio）冲突，不在本轮 |

### I-2 `simulateEvent` 现状（API 层已就绪，UI 零消费）

- `src/api/events.ts` 已有 `simulateEvent(body: SimulateEventRequest): Promise<PlaybackState>`
  （FC-4，API-1 薄封装，`POST /api/events/simulate`）；
- 全仓 grep：`simulateEvent` 仅出现在 api 层定义与 5 个测试文件的 `vi.mock` 中，
  **无任何 hook / 组件消费** —— 前端目前是「只读展示端」，页面无法触发事件；
- `SimulateEventRequest` 允许键恰 4 个：`event_type`（必填）/ `user_id` / `user_name` / `payload`
  （后三位可选，后端有补默认规则；显式 `payload: null` 会被后端 400 拒绝）。

### I-3 既有状态通道（复用基础）

- `RuntimeStatus = { loading: boolean; error: Error | null }`（hook 自持，不进 store，FD-3）；
- `refresh()`：loading 置位 → `loadRuntimeData()` → 成功清位 / 失败 `ApiError` 原样进 `error`
  （FD-4 / RF-4，单一错误通道，页面级四态由 RS-* 表达）；
- store 公开 setter 恰 3 个（`setPlayback` / `setRecentEvents` / `setStats`，FS-3），写出口唯一。

## Decision（裁决总表 ES-1 ~ ES-5）

### ES-1 —— Component Location（冻结，含 FCM-2 局部修订）

- 模拟器面板**唯一位置**：`src/components/EventSimulator.tsx`；
- **局部修订 FCM-2**：Phase 1 组件集由四件增补为五件（新增 `EventSimulator`）；
  原四件（PetStage / EventList / StatusBar / PetPlayer）位置与职责**零改动**；
- 组件职责：**只渲染三个按钮并把点击转交 hook**；禁止 API import（FCM-3 / UB-1）、
  禁止 store 写入、禁止自建网络调用、禁止持久化。

### ES-2 —— Trigger Data Flow（冻结）

触发链路固定单向：

```
按钮 click → usePetRuntime().triggerEvent(event_type)   [hook 层编排]
          → simulateEvent({ event_type, payload: {} })  [既有 FC-4 API，零新增 API 代码]
          → 成功 → loadRuntimeData()（回读三端点、整份写 store，既有路径复用）
          → Store ↓ 组件（展示侧零改动）
```

- `triggerEvent` 是**事件提交 + 回读**编排，与 `refresh`（纯重拉）语义不同；
  RF-1「refresh 唯一来源」**不变**——`refresh` 仍只有 `usePetRuntime()` 一个来源，
  `triggerEvent` 不复用、不替代 `refresh`；
- 失败路径：`ApiError` **原样**进既有 `error` 通道（FD-4 / RF-4 同一口径），
  不新增错误类型、不静默失败、不自动重试；
- store 写入仍**只**经既有 3 个 setter（loadRuntimeData 内部路径），零新增写出口。

### ES-3 —— Event Input Surface（冻结）

- 恰好**三个按钮**：`gift` / `comment` / `follow`（与后端模拟器支持的事件类型一致）；
- 请求体固定：`{ event_type, payload: {} }`；`user_id` / `user_name` 省略（后端补默认）；
- **禁止**：自由文本事件输入、payload 编辑器、事件类型下拉/自定义、批量触发、
  连点去抖/节流策略（浏览器原生行为即可；事件合法性由**后端**裁定，客户端不复刻校验）。

### ES-4 —— Trigger Status Expression（冻结）

- 触发进行中：**复用** hook 既有 `loading`（RS-3「不设第二套 loading」同一原则）；
  `RuntimeStatus` 形状**零改动**（仍恰 `loading` / `error` 两字段）；
- 触发失败：**复用**既有 `error` 通道与页面级 RS-3 错误态表达；
- 允许的表达层细节：触发进行中禁用按钮（`disabled`）；**禁止**第二套状态字段、
  toast、行内错误文案、spinner 库。

### ES-5 —— Scope Freeze（冻结）

本阶段（F-0 / F-1）**不实现**：

- websocket、polling、自动触发、定时触发；
- 自定义 payload / 事件编辑器 / 事件历史回放；
- 动作队列消费、播放结束回写（PI-5 重申）；
- video 事件监听（PI-3 不受本步影响）；
- UI 美化 / 样式系统 / 组件库引入。

任何上述能力的引入都必须走新的授权步骤 + 新的冻结文档。

## 设计验证清单（本步零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `simulateEvent` 已就绪且签名满足 ES-2（无需改 API 层） | ✅ |
| `RuntimeStatus` / store setter 均可零改动复用（I-3） | ✅ |
| FCM-2 局部修订已显式声明（用户裁决，FP-1 先例） | ✅ |
| RF-1 / FD-4 / RS-3 / UB-1 与 ES-2/ES-4 无冲突 | ✅ |
| 落地项（归 F-1） | 新增 `EventSimulator.tsx`；`usePetRuntime` 增 `triggerEvent`；App 挂载；`tests/event-simulator/` 新增测试 |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（ES-1 ~ ES-5）；局部修订 FCM-2 组件集增补第五件 |
