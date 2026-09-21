# Phase 2.2-7C-1 WebSocket Connection Lifecycle Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-7C-1 指令）
> 性质：**纯文档冻结**——零代码、零依赖、零测试改动
> （不修改 `backend/**`、`frontend/**`、`tests/**`、不改任何既有 FROZEN 条款）。
> 输入：`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_frontend_push_channel_decision.md`（PC-*）、
> `phase2_websocket_push_boundary_decision.md`（WP-*）、
> `phase2_websocket_commit_point_decision.md`（WC-*），
> 以及 Phase 2.2-7C-0 只读审计草案（本文件由其**整理并冻结**而来）。
> 编号空间声明：本文档使用 **`WL-*`**（创建前核查：全仓 `\bWL-` **0 命中**，无撞车；
> 与 WS/WM/WA/WG/PC/WP/WC 互不重叠）。

## Input

- 指令：Phase 2.2-7C-1 —— 把 Phase 2.2-7C-0 的**连接生命周期边界草案**转为**正式冻结决策**，
  写入 WL-1 ~ WL-6，并附 **C-WL1 / C-WL2 Resolution Record**。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = **`d70f6f9`**，working tree 恰含
  `?? docs/development/phase2_websocket_connection_lifecycle_boundary_draft.md`；
  `WL-*` 全仓 **0 命中**；7 份既有冻结文档齐备；目标 decision 文件**不存在**。
- **用户裁决（2026-09-21）**：**C-WL1 选 A**、**C-WL2 选 A**（见 §3 Resolution Records）。

## Step 1 只读审计记录（Phase 2.2-7C-0 结论，本步沿用）

### Q1 —— 连接生命周期（`backend/app/api/ws.py`，120 行）

| 阶段 | 事实 |
|---|---|
| **connect** | 首行 `await websocket.accept()`——**无**握手鉴权 / **无** subprotocol 协商 / **无**首帧解析 |
| **receive loop** | `while True: raw = await websocket.receive_text()`——**唯一**接收点，每轮恰一条 |
| **disconnect** | `except WebSocketDisconnect:` → `logger.info("websocket disconnected: path=/api/ws")`——**只记日志**（零额外业务事件 / 零推送 / 零重连 / 零恢复） |
| **unexpected error** | **无**通用 `except Exception`；非 `WebSocketDisconnect` 异常**原样传播**出 endpoint；`WebSocketAdapterRejectError` 属**消息级**（`except` → `continue`，**连接继续**） |
| **cleanup** | **无** `finally`、**无**资源释放代码——因为**不存在**待清理的 registry / session / buffer / 后台任务 |

### Q2 —— 连接所有权（全 `backend/app/**` 只读搜索）

connection registry / active websocket store / session object / client id / room·channel / broadcast manager
——**全部不存在**（关键字搜索仅命中 6 处，全部为 docstring·注释 + 1 处无关 `sqlite3.Connection`）。
连接 = endpoint 协程**局部变量** `websocket`，作用域 = **per-connection**，无跨请求共享。
进程级共享对象仅 `_default_dispatcher` 与 `SimulationPipeline` 单例，**均不持有 socket**。

### Q3 —— dispatcher 生命周期（`backend/app/platform/websocket_dispatcher.py`，140 行）

| 问题 | 结论 |
|---|---|
| 是否保存 websocket 引用 | ❌ 否（`send_event(event, websocket)` **逐次传入**；`__dict__` 仅 `{_now, _logger}`） |
| 是否保存连接状态 | ❌ 否 |
| 是否保存失败状态 | ❌ 否（失败只 log + `return False`；无计数器 / last-error / 缓存） |
| 是否可重入 | ✅ 是（`build_envelope` 纯函数；`send_event` 不写实例状态） |
| 线程 / 协程安全 | ✅ 无共享可变态、无锁需求；实际并发度 = 1 |

### Q4 —— 失败语义

`send_json` 抛异常 → `logger.exception` + **返回 `False`**。之后：websocket **继续循环** ✅、
**不关闭连接**、**不重试**、**不缓存**。

### Q5 —— 前端生命周期（`frontend/src/**`）

connect 时机 = **App 挂载**（`App.tsx:33` → `useEffect(..., [])`）；close = **App 卸载**；
**reconnect ❌ / heartbeat ❌**；subscription **仅 `message`** 一种（无 `close`/`error`/`open`）。
（`usePetRuntime.ts::subscribe` 属 runtime controller 自持 listener 集合，**与 WS 无关**。）
**开发模式观察**：`main.tsx` 的 `<StrictMode>` 使 effect 双调用 ⇒ mount/cleanup/mount（生产单次）。

## Step 2 Decision（冻结总表 WL-1 ~ WL-6）

### WL-1 —— Connection Ownership（冻结）

- websocket 生命周期（accept / receive loop / disconnect / 关闭）**唯一所有者 = transport endpoint**
  （`app/api/ws.py::websocket_endpoint` 协程）；
- `WebSocketAdapter`（platform 类）**不管理连接生命周期**——职责恰三项 = **inbound**（WA-1）；
- `WebSocketDispatcher` **不**持有 socket——**outbound 无状态端口**（WP-1 / WP-4）；
- 组合根 `SimulationPipeline` **无**连接引用（WP-1）；
- 连接作用域 = **per-connection**（单次协程调用），**无**跨请求共享；
- **禁**：第二所有者（connection manager / registry / session store / 广播中心）。

### WL-2 —— Connect Boundary（冻结）

- `connect` = `await websocket.accept()`，**仅**建立连接；
- **禁**：握手鉴权 / token 校验 / subprotocol 协商 / 首帧解析（**WA-5 匿名口径**，认证授权 Deferred）；
- **禁**：connect 触发业务事件、写库、推送；
- 🔒 **connect 不执行 runtime 对账、不调用 `loadRuntimeData()`**（C-WL2 裁决 A，见 §3）；
- 允许链：`App mount → WebSocket connect → 收 WM-1 envelope → applyPushEvent() → store update → UI render`；
  **不允许**链：`connect → loadRuntimeData() → HTTP refresh`。

### WL-3 —— Disconnect Boundary（冻结）

- **正常断开**：`WebSocketDisconnect` → **只记日志**；**不**产生额外业务事件、**不**推送、**不**重连、**不**恢复；
- **异常断开**：非 `WebSocketDisconnect` 异常**原样传播**（既有口径，本层**不**吞掉）；
  `WebSocketAdapterRejectError` 属**消息级**（`continue`，连接继续）；
- **resource release = 无资源可释放**（无 registry / session / buffer / 后台任务）⇒ 本阶段**不新增**
  `finally` / 通用 `except` / 显式 `close()`；
- **禁**：断线缓存、断线重放、断线广播通知。

### WL-4 —— Failure Boundary（冻结）

- **send failure**（`send_json` 抛异常）→ **只 log**（`logger.exception`）+ `send_event` 返回 `False`；
- **不关闭连接**（连接**继续**服务后续消息）；**不** retry；**不** buffer/queue；**不** ack；**不** replay；
- **不**回滚已提交的 runtime mutation；**不**把异常上抛入 inbound 循环；
- **禁**：失败计数 / last-error 状态 / 自动降级为 pull / 指数退避；
- ⇒ = **WP-5 / WC-5 的逐条重申**，无新增。

### WL-5 —— Client Lifecycle Boundary（冻结）

- 前端 **connect 时机 = App 挂载**（`useRuntimePush`）；**close = App 卸载**；
- **冻结不存在**：reconnect / heartbeat / offline recovery / message replay / 订阅扩展（**仅** `message`）；
- 非法帧**拒收**（不写 store，PC-2）；写通道**必须**经 store（PC-5）；
- **禁**：`window`/`document` 级全局 socket、多 client、把 socket 句柄传入组件、组件内建 websocket；
- **记录（不裁决）**：`<StrictMode>` 开发模式双调用导致的 mount/cleanup/mount（生产单次）。

### WL-6 —— Scope Freeze（冻结）

本阶段明确**禁止**（除非后续**单独授权**）：

- ❌ multi-client / ❌ broadcast / ❌ room-channel
- ❌ auth（认证 / 授权）
- ❌ heartbeat
- ❌ reconnect
- ❌ persistence（连接状态持久化）
- ❌ replay（消息重放）
- ❌ offline recovery（离线恢复）
- ❌ 新依赖
- ❌ backend / frontend **任何实现代码**

> **性质声明**：WL-6 = **WS-6 / WA-6 / WP-6 / PC-6 的逐条重申**，**不新增**禁止项，**不扩张** scope。

## Step 3 C-WL1 / C-WL2 Resolution Record（裁决澄清）

### C-WL1 Resolution Record —— 「adapter」术语口径

**旧描述（存在表达歧义）**：

| 出处 | 原文 |
|---|---|
| **WS-1** | 「连接生命周期管理（accept/close）属传输细节，**可存在于 adapter**，不得附带业务判断」 |
| **WA-1** | adapter 职责**恰三项**（协议接收 / 格式检查 / 转交 normalize） |
| **WA-2** | 「connection 生命周期（accept/close/连接表维护）**属 transport 层**细节，**可存在于 adapter 的传输侧**」 |
| **WP-1** | **禁** `WebSocketAdapter.send()`（adapter = **inbound only**） |

**歧义点**：WS-1 的「adapter」指 **platform websocket 层整体**（含 transport endpoint），
还是指 `WebSocketAdapter` **类**（实现选择后者不管理连接 ⇒ 生命周期在 `app/api/ws.py`）。

**✅ 裁决（2026-09-21，用户）：选 A。**

- **WL-1 写明**：**websocket 生命周期归 transport endpoint**（`app/api/ws.py`）；
  **`WebSocketAdapter` 类不管理连接生命周期**；
- **解释**：WS-1 的「生命周期**可存在于 adapter**」按 **transport 层语义**理解
  （= WA-2「adapter 的**传输侧**」，即 transport endpoint），**而非** `WebSocketAdapter`
  类实例持有生命周期；
- **依据**：保持既有冻结边界 —— WA-1（adapter 三项职责**不扩张**）/ WA-2（transport boundary ownership）/
  WP-1（push ownership 属 platform websocket **transport**）；
- **不回改** WS / WA / WP 任何已冻结文档（本记录即为澄清，**不产生**修订文档）。

### C-WL2 Resolution Record —— connect-time 对账（pull）归属

**旧描述（存在表达歧义）**：

| 出处 | 原文 |
|---|---|
| **WS-5** | 「`connect`：链路建立，**可触发一次全量对账（pull 一次 runtime 数据，语义 = 既有 loadRuntimeData）**」（同节又称本阶段**不实现**） |
| **PC-3** | 「**禁止** `socket → loadRuntimeData()`；**禁止** push 触发 refresh、或 refresh 伪装成 push」 |
| 现状 | `useRuntimePush` 挂载**只** `connect()`，**未做**任何对账 —— 两侧均未实现 |

**歧义点**：connect-time 的一次性对账属「**connect 事件的合法拉取**（WS-5）」还是
「**socket → `loadRuntimeData()`（PC-3 禁止）**」——同一动作结论相反。

**✅ 裁决（2026-09-21，用户）：选 A。**

- **WL-2 冻结为**：**connect 仅负责建立连接**，**不执行 runtime 对账**、**不调用 `loadRuntimeData()`**；
- **依据**：保持与既有前端边界一致 —— **PC-3**：push ≠ refresh，socket 路径**禁止**触发 `loadRuntimeData()`；
- **允许链**：`App mount → WebSocket connect → 收 WM-1 envelope → applyPushEvent() → store update → UI render`；
  **不允许**：`connect → loadRuntimeData() → HTTP refresh`；
- **WS-5 原「connect 可触发一次全量对账」**：登记为 **historical design option / Deferred / 未实现**，
  **不进入** WL-2 当前冻结语义；
- **不回改** PC-3。

## Step 4 冲突矩阵

| 检查项 | 结果 | 说明 |
|---|---|---|
| **编号冲突（`WL-*`）** | ✅ **无** | 全仓 `\bWL-` 0 命中（创建前核查） |
| **WS-1 ~ WS-6** | ✅ **无冲突** | WL-1（生命周期归属）经 C-WL1 澄清为 transport 语义；WL-5 与 WS-5 的不实现项逐条一致 |
| **WM-1 ~ WM-6** | ✅ **无冲突** | 本决策不触碰 envelope / 事件模型 |
| **WA-1 ~ WA-6** | ✅ **无冲突** | WL-1 明令 `WebSocketAdapter` **类**不管理连接 ⇒ WA-1「恰三项」/ WA-3「输出恰两种」保持 |
| **WG-1 ~ WG-6** | ✅ **无冲突** | WL-1/WL-3/WL-5 与 WG-5/WG-6 单连接语义一致 |
| **WP-1 ~ WP-6** | ✅ **无冲突** | WL-1 = WP-1/WP-4 重申；WL-4 = WP-5 重申；WL-6 = WP-6 重申 |
| **WC-1 ~ WC-6** | ✅ **无冲突** | WL-3/WL-4 与 per-message 生命周期、失败隔离（WC-4/WC-5）一致 |
| **PC-1 ~ PC-6** | ✅ **无冲突** | WL-2（C-WL2 裁决）与 PC-3 一致；WL-5 与 PC-1/PC-5/PC-6 一致 |
| **PlaybackState（API-2 / WS-4）** | ✅ **无冲突** | 不触碰状态字段 |
| 是否修改既有冻结 | **否** | WS / WM / WA / WG / PC / WP / WC 全部保持原样 |
| 是否 scope 扩张 | **否** | WL-6 零新增禁止项；不引入任何机制 |

**结论：本次冻结不需要修改任何既有冻结规则。**

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `WL-*` 编号空间全仓 0 撞车 | ✅ |
| WL-1 生命周期唯一所有者 = transport endpoint；`WebSocketAdapter` 类不管理连接 | ✅ |
| WL-2 connect 仅建连（不对账 / 不 `loadRuntimeData()`），与 PC-3 一致 | ✅ |
| WL-3 断线只记日志 + 无资源可释放（不新增错误处理分支） | ✅ |
| WL-4 = WP-5 / WC-5 逐条重申 | ✅ |
| WL-5 reconnect / heartbeat / recovery / replay 冻结不存在 | ✅ |
| WL-6 scope 清单完整，零新增禁止项 | ✅ |
| C-WL1 / C-WL2 Resolution Record 齐备（含「不回改」声明） | ✅ |
| 全部既有编号空间 0 修改 | ✅ |

## 落地项（须另行授权）

- **无**（本步为边界冻结；WL-6 明令禁止 backend / frontend 实现改动）；
- 后续若需 reconnect / heartbeat / multi-client / auth / offline recovery / persistence，
  须**另立冻结文档**并单独授权。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 Phase 2.2-7C-0 草案整理冻结：WL-1 ~ WL-6 + **C-WL1 裁决 A** + **C-WL2 裁决 A**；零代码变更 |
