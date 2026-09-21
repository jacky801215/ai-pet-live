# Phase 2.2-7C-3 WebSocket Lifecycle Implementation Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-7C-3 指令）
> 性质：**纯文档冻结**——零代码、零依赖、零测试改动
> （不修改 `backend/**`、`frontend/**`、`tests/**`、`package.json`，不改任何既有 FROZEN 条款）。
> 输入：`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_websocket_push_boundary_decision.md`（WP-*）、
> `phase2_websocket_commit_point_decision.md`（WC-*）、
> `phase2_websocket_connection_lifecycle_boundary_decision.md`（WL-*，v1.0 FROZEN）、
> `phase2_frontend_push_channel_decision.md`（PC-*），
> 以及 Phase 2.2-7C-2 只读审计草案（本文件由其**整理并冻结**而来）。
> 编号空间声明：本文档使用 **`LI-*`**（创建前核查：全仓 `\bLI-` **0 命中**，无撞车；
> 与 WS/WM/WA/WG/WP/WC/WL/PC/PB/RB 互不重叠）。

## Input

- 指令：Phase 2.2-7C-3 —— 把 Phase 2.2-7C-2 的 **Lifecycle Implementation Boundary Draft（v0.1）**
  转为**正式冻结决策**，保留审计证据 + LI-1 ~ LI-6 + 冲突矩阵，并新增 **Resolution Record**。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = **`5036045`**，working tree 恰含
  `?? docs/development/phase2_websocket_lifecycle_implementation_boundary_draft.md`；
  `LI-*` 于 **tracked files 0 命中**（无编号污染）；8 份既有冻结文档齐备；目标 decision 文件**不存在**。

## Step 1 只读审计记录（Phase 2.2-7C-2 结论，本步沿用）

### Q1 —— 连接对象生命周期（仍满足 WL）

| 文件 | 行数 | 最后修改 commit | sha256(12) |
|---|---|---|---|
| `backend/app/api/ws.py` | 120 | `d70f6f9`（7B-2） | `b9357e0f6c6a` |
| `backend/app/platform/websocket_dispatcher.py` | 140 | `d70f6f9`（7B-2） | `46df13ac0ea5` |
| `backend/app/platform/websocket_adapter.py` | 108 | `3e01d6c`（3B-2） | `c9eb312fbea7` |

⇒ 自 7C-1 冻结（`5036045`，纯文档）以来，**runtime 传输侧三文件零改动**。

```
await websocket.accept()                          ← 连接建立（协程局部变量）
  ↓ while True:
    raw = await websocket.receive_text()          ← 唯一接收点
    event = adapter.handle(raw)                   ← 传值（Event），不传连接
    pipeline.apply_event(event, platform=WS)      ← 传值（Event），不传连接
    await dispatcher.send_event(event, websocket) ← 连接**借用**（仅本次调用）
  ↓ WebSocketDisconnect
    logger.info("websocket disconnected: ...")    ← 只记日志
```

| WL 判据 | 复核结果 |
|---|---|
| 单连接（single active connection） | ✅ 连接 = 一次协程调用的局部变量，无第二处引用 |
| per-coroutine | ✅ 所有权边界 = 协程栈帧 |
| 无 registry | ✅ 全 `app/**` 关键字命中共 **4** 处，**全部**为 docstring/注释（`ws.py:39/66/84`、`dispatcher.py:23`） |
| 无 session | ✅ 同上；无 `client_id` / 无连接身份 |

### Q2 —— Dispatcher 与 lifecycle 边界（`websocket_dispatcher.py`，140 行）

| 断言 | 机器复核结果 |
|---|---|
| dispatcher **不持** websocket | ✅ 源码无 `self._websocket = ...`、无任何 socket 属性赋值/读取 |
| dispatcher **不持** connection state | ✅ 无 `self._conn*` / `self._state*` 赋值 |
| dispatcher **不持** failure state | ✅ 无 `self._failure*` / `self._failed*` 赋值 |
| `send_event()` 仍符合 `failure → log → False → 连接继续` | ✅ `except Exception`×1 → `logger` → `return False`×1；正常路径 `return True`×1；socket 交互仅**借参** `websocket.send_json` |

### Q3 —— Frontend lifecycle 对齐

| 文件 | 行数 | 最后修改 commit |
|---|---|---|
| `frontend/src/hooks/useRuntimePush.ts` | 44 | `5b6cde7` |
| `frontend/src/services/websocketClient.ts` | 171 | `5b6cde7` |
| `frontend/src/App.tsx` | 91 | `5b6cde7` |

| 判据 | 结果 |
|---|---|
| mount → connect | ✅ `App.tsx:33` 顶部无条件 `useRuntimePush()` → `useEffect(() => startRuntimePush(), [])` |
| unmount → close | ✅ cleanup → `startRuntimePush` 返回的 stop 函数 → `client.close()` |
| no reconnect | ✅ 全 `src/**` 仅命中**禁止项注释**（`websocketClient.ts:9`）；无退避/jitter |
| no heartbeat | ✅ 无 `setInterval` / `ping` / `pong` / 定时器 |
| no refresh（socket 路径） | ✅ `useRuntimePush.ts` / `websocketClient.ts` **不 import** `src/api/**`、**不调用** `loadRuntimeData()`；`loadRuntimeData()` 仅存在于 `usePetRuntime.ts`（**HTTP pull 路径**，RF-1/ES-2 人工触发——**与 socket 无关**，未违反 PC-3） |

## Step 2 Decision（冻结总表 LI-1 ~ LI-6）

> **定位**：WL-* 冻结「连接生命周期**归谁**」；**LI-*** 只做「**实现预备**」——
> 把 WL 的所有权/边界翻译成**可逐条对照的实现约束清单**，**不新增**任何边界、**不扩张**任何 scope。

### LI-1 —— Connection object ownership（冻结）

- 连接对象（`fastapi.WebSocket`）**唯一所有者 = transport endpoint 协程**
  （`app/api/ws.py::websocket_endpoint`），经 FastAPI 依赖注入取得，**生命周期 = 协程栈帧**；
- 跨模块**只传值**：`adapter.handle(raw) → Event`、`pipeline.apply_event(event)` 均**不携带**连接；
- `dispatcher.send_event(event, websocket)` 中的 `websocket` 为**借用参数**——**仅在本次调用期间有效**，
  调用返回即释放（WP-4）；
- **冻结**：任何模块**不得**把连接对象提升为 字段 / 属性 / 单例 / 集合成员 / 闭包捕获；
  **不得**跨消息复用连接引用（每消息重新从协程局部取得）。

### LI-2 —— Client / server lifecycle symmetry（冻结）

| 侧 | 建立 | 销毁 |
|---|---|---|
| **Server** | `await websocket.accept()` | 协程退出（`WebSocketDisconnect` / 异常传播） |
| **Client** | App 挂载 → `startRuntimePush()` → `connect()` | App 卸载 → cleanup → `close()` |

- **冻结的对称性**：
  1. **每个 client 实例**：`connect()` **幂等**（已有句柄 ⇒ no-op；**不**重连、**不**退避）；
  2. `close()` → 清空句柄并 `socket.close()`，**不**监听 `close`/`error` ⇒ **无**自动重建；
  3. 服务端**不**因发送失败主动关闭连接（LI-4）；客户端**不**对关闭/错误事件作反应；
  4. **无** lifecycle 握手（无 subprotocol 协商 / 无 ping-pong / 无 session 建立）；
  5. **connect 不做对账**（继承 **WL-2 / C-WL2 裁决 A**）：**不**调用 `loadRuntimeData()`、**不**触发 refresh。
- **记录（环境观察，不裁决）**：开发模式 `<StrictMode>`（`main.tsx:18`）会使 effect 双调用
  ⇒ 客户端出现 **connect→close→connect**（两个 client 实例），服务端对应**两个先后独立的** per-connection
  生命周期；生产构建为单次。因无重连逻辑，**不产生**额外语义。

### LI-3 —— Dispatcher lifecycle neutrality（冻结）

- dispatcher **无状态**：`__dict__ == {_now, _logger}`（已有测试断言）；
- 连接以**借用参数**传入 `send_event(event, websocket)`，**不缓存**、**不持有**；
- **不持** connection state / failure state / 计数器 / last-error；
- **可重入**、**无共享可变态** ⇒ 并发调用互不干扰；实际并发度 = 1（单连接）；
- **冻结**：dispatcher 行为**跨调用无记忆**——不因调用次数、失败次数改变任何行为；
- **推论（冻结）**：dispatcher **不参与**连接生命周期决策（**不** accept / **不** close / **不** reconnect）。

### LI-4 —— Failure continuity（冻结）

- `send_json` 失败 → `logger.exception` + `return False`；
- **连接继续**（**不**关闭）；**不** retry / **不** buffer / **不** ack / **不** replay；
- **不**回滚已提交的 runtime mutation；**不**把异常上抛入 inbound 循环；
- **冻结**：**失败不改变连接生命周期**——连接存活与 dispatcher 的成败**无耦合**；
- **推论**：连续失败**零累积**（无退避 / 无熔断 / 无降级）；恒为 **per-message 独立尝试**；
- 唯一例外（已冻结）：连接被**对端/传输层**关闭 ⇒ endpoint 收 `WebSocketDisconnect` ⇒ 走 **WL-3** 只记日志。

### LI-5 —— Forbidden lifecycle expansion（冻结：**汇总重申**，零新增禁止项）

实现预备阶段即冻结，防止「顺手加」：

- ❌ 连接注册表 / ConnectionManager / active-set / room / broadcast；
- ❌ 连接身份（`client_id` / `session_id`）与认证授权（auth / token / 角色）；
- ❌ 服务端主动 `close()`（既有 ASGI 收尾除外）/ 服务端主动心跳（ping-pong frame）；
- ❌ 重连（任一侧）/ 退避 / jitter；
- ❌ 消息缓存 / 重放 / 断线补发 / ack / 序号；
- ❌ 生命周期回调注册体系（`onConnect` / `onDisconnect` / `onError` 订阅）；
- ❌ 定时器 / 后台任务 / asyncio task；
- ❌ 多连接 / 多客户端 / 多宠物广播；
- ❌ 把连接对象或 socket 句柄写入模块级状态 / store / 组件 props。

> **性质**：本清单 = **WS-6 / WA-6 / WP-6 / PC-6 / WL-6 的汇总重申**，**不新增**禁止项。

### LI-6 —— Scope freeze（冻结）

- 本阶段**禁止**：`backend/**` / `frontend/**` / `tests/**` / `package.json` 任何代码改动、
  新依赖、未核查通过的新编号空间；
- **明确 Deferred（重申）**：reconnect / heartbeat / auth / multi-client / persistence / replay /
  offline recovery / lifecycle callback implementation；
- 本阶段产出**仅限**：只读调查 + 边界文档。

## Step 3 Resolution Record

> 本节为 Phase 2.2-7C-3 新增的**显式声明**，用于封住「LI 是否等于新功能」的解读空间。

**R-LI-1 —— LI 不新增 lifecycle feature（冻结声明）**

- `LI-1 ~ LI-6` **不引入**任何新的连接生命周期功能、机制、字段或事件；
- 全部条目均为 **WL / WS / WA / WG / WP / WC / PC 既有冻结条款的「实现层面展开 / 重申」**；
- 逐条映射：`LI-1 ← WL-1`；`LI-2 ← WL-2（含 C-WL2）/ WL-5 / PC-1 / PC-6`；
  `LI-3 ← WL-1 / WL-4 / WP-1 / WP-4`；`LI-4 ← WL-4 / WP-5 / WC-5`；`LI-5 ← WL-6（= WS-6/WA-6/WP-6/PC-6 汇总）`；
  `LI-6 ← WL-6 / 本阶段授权范围`；
- **禁**：以 LI 之名新增任何 lifecycle 行为（registry / reconnect / heartbeat / auth / callback / buffer …）。

**R-LI-2 —— LI 不修改 WL / WS / WP / WC / PC（冻结声明）**

- 本次冻结**零修改**任何既有 FROZEN 文档条款（WS / WM / WA / WG / WP / WC / **WL** / PC 全部保持原样）；
- 本文件与 `PROJECT_RULES` 的追加内容均为**纯追加**，不删除、不重排既有 H2 顺序；
- 若未来发现 LI 与既有冻结存在实质冲突，须**另出修订文档**，不得在本文件内回改。

**R-LI-3 —— LI 只是 implementation boundary（冻结声明）**

- 本文件的**唯一性质** = **implementation boundary**（实现边界清单），用于后续（若获授权的）
  实现步**逐条对照**；
- **不是** feature spec、**不是**授权文件：**不授权**任何实现；
- 任何实现（reconnect / heartbeat / auth / multi-client / persistence / replay / offline recovery /
  lifecycle callback）**必须另立冻结文档 + 单独授权**。

## Step 4 冲突检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| **编号冲突（`LI-*`）** | ✅ **无** | 全仓 `\bLI-` 0 命中（创建前核查）；与 WS/WM/WA/WG/WP/WC/WL/PC/PB/RB 不重叠 |
| **LI ↔ WS** | ✅ **无冲突** | LI-2/LI-4 与 **WS-5**（只设计 connect/disconnect/error 三语义、**不实现**重连/心跳/恢复）一致；LI-5/LI-6 与 WS-6 一致 |
| **LI ↔ WP** | ✅ **无冲突** | LI-1/LI-3 = WP-1（transport owns push）+ WP-4（无 registry）；LI-4 = WP-5；LI-5/LI-6 = WP-6 |
| **LI ↔ WC** | ✅ **无冲突** | LI-4 = WC-5（失败隔离）；LI-3 明令 dispatcher 不参与 commit point（WC-1 不受影响） |
| **LI ↔ WL** | ✅ **无冲突** | LI-1 = WL-1 展开；LI-2 = WL-5 展开（+ 继承 WL-2 / C-WL2）；LI-3 = WL-1/WL-4 展开；LI-4 = WL-4 展开；LI-5/LI-6 = WL-6 重申 |
| **LI ↔ PC** | ✅ **无冲突** | LI-2 = PC-1（mount/cleanup 唯一接线点）+ PC-3（connect 不对账）+ PC-6（不重连/心跳）；LI-4 不触碰 push≠refresh |
| **LI ↔ WA / WG** | ✅ **无冲突** | LI-1 与 WA-1（adapter 恰三项）/ WA-2（连接归 transport）/ WG-5（单连接）一致 |
| **PlaybackState（API-2 / WS-4）** | ✅ **无冲突** | 本决策不触碰状态字段 |
| **scope 扩张** | ❌ **无** | LI-5 为汇总重申；LI-1~LI-4 为实现层面展开，均不引入机制（R-LI-1 已显式声明） |
| 是否修改既有冻结 | **否** | R-LI-2 已显式声明 |

**结论：本次冻结不需要修改任何既有冻结规则。**

### 口径说明（已考虑，无需裁决）

- **WS-5 的三连接事件语义**（`connect` / `disconnect` / `error`）在 WS-5 中为**「只设计、不实现」**；
  本决策 **LI-5** 禁止的是实现其**回调/订阅机制**，与该「设计但未实现」状态**一致**（设计 ≠ 实现）。
- **`loadRuntimeData()` 的存在位置**：仅在 `usePetRuntime.ts`（**HTTP pull**，RF-1/ES-2 人工触发）；
  **socket 路径**（`useRuntimePush.ts` / `websocketClient.ts`）**零引用** ⇒ 未违反 PC-3 / WL-2。

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `LI-*` 编号空间全仓 0 撞车 | ✅ |
| Step 1 审计证据（Q1/Q2/Q3 + provenance）保留 | ✅ |
| LI-1 ~ LI-6 与 WL/WS/WA/WG/WP/WC/PC 逐条映射 | ✅ |
| **R-LI-1** LI 不新增 lifecycle feature | ✅ |
| **R-LI-2** LI 不修改 WL/WS/WP/WC/PC | ✅ |
| **R-LI-3** LI 只是 implementation boundary（不授权实现） | ✅ |
| 冲突矩阵 LI ↔ WS/WP/WC/WL/PC（+WA/WG）全 ✅ | ✅ |
| 全部既有编号空间 0 修改 | ✅ |

## 落地项（须另行授权）

- **无**（本步为边界冻结；LI-6 明令禁止 backend / frontend / tests / package.json 改动）；
- 后续若需 reconnect / heartbeat / auth / multi-client / persistence / replay / offline recovery /
  lifecycle callback，须**另立冻结文档 + 单独授权**。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 Phase 2.2-7C-2 草案整理冻结：Step 1 审计证据 + LI-1 ~ LI-6 + 冲突矩阵 + **Resolution Record（R-LI-1/R-LI-2/R-LI-3）**；零代码变更 |
