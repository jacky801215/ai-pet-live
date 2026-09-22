# Phase 3.2-B Frontend Pet Context Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-22）。生效后变更须经 Change Request。
> 输入：`phase2_frontend_push_channel_decision.md`（**PC-1 ~ PC-6**）、
> `step4_frontend_state_decision.md`（**FS-1 ~ FS-5**）、`step4_frontend_data_flow_decision.md`（FD-*）、
> `step4_frontend_refresh_boundary_decision.md`（RF-*）、`step4_frontend_runtime_state_decision.md`（RS-*）、
> `docs/development/phase2_websocket_event_model_decision.md`（**WM-1**，冻结不变）、
> `step4_api_contract_decision.md`（**API-1 ~ API-3**，冻结不变）。
> **本次实现的前置**：Phase 3.2-A（backend `?pet_id=` 连接级上下文，commit `150111c`）。

## 编号空间声明

本文档使用 **`MPF-1 ~ MPF-7`**（Multi-Pet Frontend）。
创建前已做全仓 0 撞车核查：`MPF-\d` / `FPC-\d` / `PCTX-\d` / `PETC-\d` 均 **0 命中**（2026-09-22）。
既有编号空间（**不重复使用**）：`UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* / RV-* / RS-* / RF-* / FP-* / PI-* / ES-*`（前端）、
`AS-*/DA-*/DB-*/QP-*`、`PB-*/RB-*`、`WS-*/WM-*/WA-*/WT-*/WG-*/PC-*/WP-*/WC-*/WL-*/LI-*/WE-*/GR-*/OB-*/PH-*/HR-*`、`MP-*`（backend 多宠物）。

## 编号裁决记录

Phase 3.2-B 指令未指定前端编号空间。经**用户裁决**采用 **`MPF-*`**（与 Phase 3.2-A 的 `MP-*` 同族、前缀可区分），
并在本文档内**显式声明对所有受影响既有冻结边界的受权增量**（见 §受权增量），旧冻结文档**本体不修改** ——
沿用 `PC-4` 对 `FS-3` 的既有先例（增量在新文档声明，旧文档零改动）。

## Step 0 前置检查（只读，2026-09-22）

| 项 | 要求 | 实测 |
|---|---|---|
| branch | `phase1-step1-foundation` | ✅ |
| HEAD | `3baa069` | ✅ `3baa06931d0aed2b3e7dcd53abbf5e9f1009c5f5` |
| working tree | clean | ✅ `git status --porcelain --untracked-files=all` 为空 |
| 冻结命名空间 | 未变化 | ✅ `git diff HEAD -- PROJECT_RULES.md docs/` 为空 |
| backend 回归 | 540 passed | ✅ 同一 clean HEAD 上实测 540 passed / 0 failed |

## Step 1 勘察结论（只读）

| 勘察项 | 事实 |
|---|---|
| WS 连接创建位置 | `src/services/websocketClient.ts::connect()`（`PUSH_PATH = "/api/ws"`、`resolvePushUrl()` 同源推导；`options.url` 在 connect 时读取） |
| 接线点 | `src/hooks/useRuntimePush.ts::startRuntimePush()`（PC-1 声明的**唯一**接线点）← `App.tsx` 以 `useEffect(…, [])` 调用 |
| push → store 写入口 | `writeEnvelope(envelope)` → `usePetStore.getState().applyPushEvent(...)`（PC-4 第 4 写出口） |
| runtime state ownership | 服务器快照 → zustand `usePetStore`（3 切片）；`loading`/`error` → `usePetRuntime` 内外部 controller（FD-3：不进 store，经 `useSyncExternalStore` 订阅） |
| 测试基础设施 | vitest **2.1.9**、**node 环境（无 jsdom）**、11 文件 / 96 用例；大量 `readFileSync` **源码静态守卫**（import 白名单、`not.toContain("useState(")`） |
| 后端 pet 列表端点 | **不存在**（仅 `POST /simulate`、`GET /state`、`GET /stats`、`GET /events/recent`、`WS /api/ws`）；`known_pet_keys()` 只在 `ws.py` 内部用于校验，**未经 HTTP 暴露** |

### 冲突清单（本步触发 STOP + 用户裁决）

| # | 冲突 | 依据 | 裁决 |
|---|---|---|---|
| 1 | `PC-6` 明文冻结「不实现 … **multi pet**」（同条并禁 reconnect） | PC-6 | 受权增量 |
| 2 | `PC-1` 冻结 push 生命周期 = mount→connect / cleanup→close | PC-1 | 受权增量 |
| 3 | `PC-4`/`PC-5`「不新增切片/字段/第二 store/派生业务状态」「前端零新增状态字段」 | PC-4 / PC-5 | 受权增量 |
| 4 | `FS-3` 单一 store 恰 3 切片、禁拆分/新建平行 store；`FS-2` 禁第二状态方案与 Context 状态总线 | FS-2 / FS-3 | 受权增量 |
| 5 | `RF-3` App 无本地 state（守卫硬断言 `not.toContain("useState(")`） | RF-3 + 守卫 | 保持（App 仍零 useState） |
| 6 | App **import 白名单**守卫为固定数组 | 守卫 | 同步扩展允许项 |
| 7 | 后端无 pet 列表端点，而 Step 3 禁改 `backend/app/*` | 实测 | **前端静态常量**（用户裁决） |

**用户裁决（2026-09-22）**：① 新写决策文档声明**受权增量**（旧文档本体不改）；② 可用 pet 列表用**前端静态常量**；
③ 本步**实现选择器 UI**。

## Decision（裁决总表 MPF-1 ~ MPF-7）

### MPF-1 —— Pet Catalog（冻结）

- 新增 `src/config/pets.ts`：静态常量 `AVAILABLE_PETS`（`readonly PetOption[]`，字段 `pet_id` / `label`）与 `DEFAULT_PET_ID`。
- 列表口径**必须与后端合法键一致**（MP-1：「pet_id 或 pet_type 均合法」）：本项目取各宠物 `config.json` 的 `pet_id`
  （`cat_001` / `dog_001` / `panda_001`），即后端 `AssetManager.pet_ids()` 的**子集**，保证 `?pet_id=` 一律被接受。
- **禁止**：从后端新增端点取列表（Step 3 禁改 backend）；**禁止**运行时扫描 `assets/`（前端无文件系统访问）。

### MPF-2 —— Pet Context State（冻结；受权增量）

- `usePetStore` **新增切片** `petContext: { selectedPetId: string | null }` 与**第 5 个写出口**
  `setSelectedPet(petId: string | null)`。
- **默认值 `null`** = 「默认宠物」：WS 连接**不携带** `pet_id`，与 3.2-B 之前**逐字一致**（默认行为零变更）。
  理由：backend MP-3 裁决为「**仅显式 pet 连接按 pet 写**」——若前端默认也携带 `?pet_id=cat_001`，
  默认路径的聚合计数会从 `NULL` 作用域迁到 pet 作用域，导致 `/api/stats`（前端 StatusBar 所读）读空，属**越权行为变更**。
- **禁止**：新增第二 store / 第二状态库 / React Context 状态总线（FS-2）；**禁止**改变
  `playback` / `recentEvents` / `stats` 三切片的 schema（PC-4）；**禁止**派生业务状态。

### MPF-3 —— WS Pet Context URL（冻结）

- `resolvePushUrl(petId?)`：`petId` 为空/未给 → 返回 `…/api/ws`（**逐字不变**）；
  非空 → 返回 `…/api/ws?pet_id=<encodeURIComponent(petId)>`。
- `createWebSocketClient({ petId })` 透传；`connect()` 仍**幂等**（同实例不重建，PC-6）。
- **禁止**：`payload` / 事件体中携带 pet 信息（envelope 恒 WM-1 恰 4 字段）；**禁止**自建第二条 URL 拼接路径（UB-1 配置收敛）。

### MPF-4 —— Connection Re-establishment on Pet Switch（冻结；受权增量）

- `useRuntimePush(petId)` 的 effect **依赖 `petId`**：`petId` 变化 → 旧 effect cleanup `close()` → 新 effect `connect()`。
- 这是**用户主动切换**驱动的一次性重建，**不是**自动重连：
  - **禁止** `close`/`error` 事件监听、退避、重试、心跳、消息重放、多连接并存（PC-6 / PH-6 原样有效）；
  - 切换语义 = `close → connect`，任一时刻**至多一条**连接。
- **禁止**：把 pet 写入 `applyPushEvent` 或任何 push 解析路径。

### MPF-5 —— Selector UI（冻结）

- 新增 `src/components/PetSelector.tsx`：只读 store 的 `petContext.selectedPetId` + `MPF-1` 目录渲染选项；
  切换经 **prop 注入** 的 `onSelect(petId)` 回调（与 ES-1 `onTrigger` 同构），组件**不**直写 store setter。
- 新增 `src/hooks/usePetContext.ts`：暴露 `{ selectedPetId, availablePets, selectPet }`，内部经 `setSelectedPet` 写入 store。
- `App.tsx`：`usePetContext()` 取 `selectedPetId` / `selectPet` → 传给 `useRuntimePush(selectedPetId)` 与 `<PetSelector onSelect={selectPet} />`；
  App **仍保持**：零 `useState`、零 API import、零 store setter、零 fetch（RF-3 / PC-1 原样有效）。

### MPF-6 —— Schema Invariance（冻结）

本步**零变更**：WM-1 envelope（恰 4 字段）、Event schema、`PushEnvelope` 类型、`parsePushEnvelope()` 形状校验、
`applyPushEvent()` 写入语义、`PlaybackState` 6 字段、backend API 契约、backend 任何文件。

### MPF-7 —— Scope Freeze（冻结）

本步**不实现**：自动重连 / 退避 / 重试 / 心跳 / 消息重放 / 多连接 / 离线恢复、pet 级 HTTP 端点、
pet 级统计读路径（`/api/stats` 仍读 `pet_id IS NULL`）、pet 级 `events/recent` 过滤、
新依赖（`package.json` dependencies 仍恰 3 个）、backend 任何修改、pipeline 构造清理、Live2D、OBS、AI 内容生成。

## 受权增量声明（对既有冻结边界的显式扩展）

| 既有冻结项 | 增量 | 本体是否修改 |
|---|---|---|
| **PC-6**「不实现 multi pet / reconnect」 | 解禁 **multi pet 的「前端 pet 上下文」子集**（MPF-1~MPF-5）；`reconnect`（自动重连）、退避、重试、心跳**仍禁** | ❌ 不修改 |
| **PC-1** 生命周期 = mount→connect / cleanup→close | 生命周期**增补**一个依赖维度：`petId` 变化时 cleanup+重新 connect（MPF-4）；「唯一接线点」归属不变（仍在 `useRuntimePush`） | ❌ 不修改 |
| **PC-4 / PC-5** 不新增切片/字段/第二 store · 前端零新增状态字段 | 增补**独立于 runtime schema 的** `petContext` 切片（MPF-2）；`playback`/`recentEvents`/`stats` 三切片与 push 写入语义**零变化** | ❌ 不修改 |
| **FS-3** 单一 store 恰 3 切片 · 禁新建平行 store | 切片数 **3 → 4**（同一 `usePetStore`，**不新建** store）；三个 setter 与 `applyPushEvent` 语义不变 | ❌ 不修改 |
| **FS-2** 禁第二状态方案 / Context 状态总线 | 未引入新状态库、未引入 Context 状态总线 —— 增量**不触碰** FS-2 | ❌ 不修改 |
| **RF-3** App 无本地 state | **不增量**：App 仍零 `useState`（pet 状态全在 store，经 hook 读取） | ❌ 不修改 |

## 冲突检查结果

| 冲突项 | 结论 |
|---|---|
| **WM-1 / WM-* 全部** | ✅ 无冲突：envelope 逐字段沿用，前端 `parsePushEnvelope` 与 `applyPushEvent` **零改动** |
| **WS-* / WA-* / WG-* / WP-* / WC-* / WL-* / LI-* / WE-* / GR-* / OB-* / PH-* / HR-*（backend）** | ✅ 无冲突：本步**不修改任何 backend 文件** |
| **API-1 ~ API-3** | ✅ 无冲突：不新增/不修改任何 HTTP 端点与 DTO |
| **FS-1** Store Boundary（只放服务器快照的消费态） | ⚠️ **受权增量**：`petContext` 含「用户选择」（非服务器快照）。按用户裁决纳入**唯一** store，以维持 FS-1「唯一状态容器」；**不**新建 `src/stores/` 之外的状态容器 |
| **FS-4** 单向数据流 | ✅ 无冲突：`Component → Store ← Hook`；新组件不触 API、不 fetch |
| **RF-1 / RF-2 / RF-4** | ✅ 无冲突：refresh 唯一来源 / 人工触发 / 错误通道全不变 |
| **FD-1 / FD-3 / FD-5** | ✅ 无冲突：`loadRuntimeData()` 与三 setter 零删除零修改 |
| **RB-1 / RB-3** | ✅ 无冲突：PetStage / PetPlayer 零改动 |
| **FCM-2 / FCM-3** | ⚠️ **受权增量**：组件集**增补第 6 件** `PetSelector`（FCM-2 曾以 F-1 先例增补 EventSimulator 为第 5 件）；App import 白名单守卫同步扩展两处 |

## 设计验证清单

| 检查项 | 结果 |
|---|---|
| 编号空间 `MPF-*` 全仓 0 命中（创建前核查） | ✅ |
| 受权增量逐条显式声明，旧冻结文档本体零修改 | ✅ |
| WM-1 envelope / Event schema / push parsing 零变更 | ✅（MPF-6） |
| backend 零修改（`backend/app/*` 未触碰） | ✅（MPF-7） |
| 默认路径行为零变更（默认 `selectedPetId = null` ⇒ URL 逐字不变） | ✅（MPF-2 / MPF-3） |
| App 仍零 `useState` / 零 API import / 零 store setter | ✅（MPF-5） |
| 零新依赖（dependencies 恰 `react` / `react-dom` / `zustand`） | ✅（MPF-7） |
| 无自动重连 / 退避 / 重试 / 心跳 / 多连接 | ✅（MPF-4 / MPF-7） |

## 落地项（归后续授权步）

- **`PROJECT_RULES.md` §十四 登记**：本步 Step 3 明令**禁止修改 `PROJECT_RULES.md`**，
  故本文档**未**在 §十四 增补 H3 小节 —— 登记**待后续授权**（不因此阻碍本步落地）。
- pet 级统计读路径（`/api/stats` 支持 `pet_id`）——须修改 backend，另行授权。
- `events/recent` 按 pet 过滤 ——须修改 backend，另行授权。
- 断线可见性（RS 第五态「离线」表达）——**仍 Deferred**（PC 已声明）。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-22 | 首次冻结（MPF-1 ~ MPF-7）。编号空间 MPF-*；显式声明对 PC-1/PC-4/PC-5/PC-6/FS-1/FS-3/FCM-2 的受权增量；旧冻结文档本体零修改。 |
