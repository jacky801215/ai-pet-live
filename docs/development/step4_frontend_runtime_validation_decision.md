# Step 4.1-D-2 Frontend Runtime Validation Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_api_client_decision.md`（FC-*）、`step4_frontend_state_decision.md`（FS-*）、
> `step4_frontend_component_decision.md`（FCM-*）、`step4_frontend_data_flow_decision.md`（FD-*）
> 编号空间声明：本文档使用 **RV-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-*
> 均不复用、不覆盖；同一事项两处均有规定时，以**更严格者**为准。
> 本步**不是新增功能**：不进入 polling / websocket / animation / router / 登录 /
> 后端接口扩展 / UI 美化。

## Input

- 指令：Step 4.1-D-2 Frontend Runtime Integration Validation —— 在**不扩展数据流边界**的前提下，
  验证 `API Client ↓ usePetRuntime() ↓ Zustand Store ↓ Components ↓ App` 完整链路可运行。
- 前置（§一 前置检查，全部通过，无 STOP 条件）：
  - branch = `phase1-step1-foundation`，HEAD = `5fab6ab`，working tree clean
  - `src/api/`、`src/hooks/usePetRuntime.ts`、`src/stores/usePetStore.ts`、`src/components/`、`src/App.tsx` 均存在
  - 禁止现状扫描（剥注释）：`src/components/**` 对 fetch( / `/api/` / axios / setInterval / WebSocket
    **0 命中**；`src/stores/**` 对 fetch( / Promise / async **0 命中**；`src/hooks/**` 无组件 import

## Investigation（只读调查记录，2026-09-20）

### 2.1 当前 Runtime 行为

- `App()` 每次挂载调用一次 `usePetRuntime()`；hook 内 controller 经 `useMemo(..., [])` 创建，
  初次加载经 `useEffect(..., [controller])` **恰执行一次**（重挂载才重新拉取，无重复触发）；
- `refresh` 仍由 hook 返回值暴露（`useCallback` 包装 controller.refresh）；
- loading 初始为 true，加载收敛后为 false；错误实例原样保存（FD-4）。

### 2.2 API Mock / 测试环境

- 现有 Vitest（v2.1.9）**没有** fetch mock / API mock 基建，**没有** MSW mock server；
- node_modules 中 **无 jsdom / happy-dom / @testing-library**；
- 指令禁止新增依赖 → 集成测试策略冻结为：**API 三模块 `vi.mock`（`vi.hoisted` 持有 mock 函数）+
  真实 zustand store + 真实 controller / loadRuntimeData + `react-dom/server` 静态渲染**；
- 已知限制（记录性，不属边界扩展）：静态渲染不执行 React effects —— 挂载触发的「那一次」加载
  在**controller 层**验证（refresh 即 hook 挂载调用的同一函数），hook 返回值接线经静态渲染 Probe 验证。

## Decision（裁决总表 RV-1 ~ RV-5）

### RV-1 —— Runtime Entry（冻结）

- 数据流**唯一入口**：`App ↓ usePetRuntime()`；
- **禁止**任何组件直接初始化数据（组件只经 store 读取 —— FCM-3 不变）。

### RV-2 —— Initial Load（冻结）

- Phase 1 允许：**mount → loadRuntimeData() 恰一次**；
- **禁止**：interval / timer / background refresh / subscription / 重试式重复加载。

### RV-3 —— Refresh（冻结）

- refresh 链路只允许：**manual caller ↓ hook ↓ API ↓ store**；
- 禁止定时自动 refresh、禁止组件绕过 hook 直接调 API 层或写 store setter。

### RV-4 —— Error Visibility（冻结）

- 错误必须保持 `ApiError` 的 **status / code / message** 三元组原样可见；
- **不可**：替换为其它异常、吞掉、转字符串覆盖、降级为布尔标志（FD-4 的验证性重申）。

### RV-5 —— Scope Freeze（冻结）

- 本阶段运行验证只覆盖：**数据加载、store 更新、组件读取**；
- **不覆盖**：动画、播放器、资源加载、后端修改（这些归各自后续步骤）。

## 验证裁决（补充）

- 集成测试位置：`frontend/tests/runtime/runtime.integration.test.tsx`；
- **测试注入缝隙**：`usePetRuntime(options?)` 增加**可选** `controller` 注入形参 ——
  仅测试在静态渲染环境（effects 不执行）中观察与被 await 的**同一** controller 实例；
  生产调用（App）**恒为零参**，默认创建路径与行为完全不变；返回值形状（FD-3）不变；
- Case 1 首次加载：mock 三个 API 函数 → 断言 loading true→false 转移（controller 订阅记录）
  与 store 三字段更新、hook 投影一致；
- Case 2 APIError：`new ApiError(...)` 拒绝 → hook.error === **同一实例**（status/code/message 原样）；
- Case 3 refresh：第一次 `stats.total = 1`，refresh 后 `stats.total = 2`（mock 实现切换），store 更新；
- Case 4 App 集成：静态渲染 App → 无 crash、子组件正常消费 store（Stage / StatusBar / EventList 均渲染数据）；
- 零新增依赖；`package.json` / `package-lock.json` 零变化；backend / database 零触碰。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（RV-1 ~ RV-5） |
