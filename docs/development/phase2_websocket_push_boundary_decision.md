# Phase 2.2-7B-0 WebSocket Outbound Push Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-7B-0 指令）
> 性质：**纯文档冻结**——零代码、零依赖、零测试改动
> （不写 `websocket.send`、不写 dispatcher、不改 `backend/app/**`、不改 `frontend/**`）。
> 输入：`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_frontend_push_channel_decision.md`（PC-*），
> 以及 Phase 2.2-7A 审计草案（本文件由其**整理并冻结**而来）。
> 编号空间声明：本文档使用 **WP-***（创建前核查：全仓 `WP-` 命中**仅** 7A 草案自身，
> 无撞车；与 WS/WM/WA/WG/PC/PB/RB 互不重叠）。

## Input

- 指令：Phase 2.2-7B-0 —— 把 Phase 2.2-7A 的 **Push Boundary Draft（v0.2）** 转为
  **正式冻结决策**，冻结出站推送（Outbound Push）的所有权 / 触发点 / 载荷 / 连接 / 失败策略 / 范围。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = **`5b6cde7`**；
  working tree 恰含 `?? docs/development/phase2_websocket_push_boundary_draft.md`；
  草案为 **v0.2**、**C-WP3 已裁决 = A**、**未修改任何既有冻结文档**。

## Step 1 已核读冻结（关键条款）

| 来源 | 与出站推送相关的冻结要点 |
|---|---|
| **WS-1 / WS-2** | WS 属**实时输入适配层**（platform websocket adapter）；唯一入口 `EventGateway.normalize()` |
| **WS-3** | 推送 ≠ refresh（pull/push 长期并存，禁 WS 内 refresh 循环） |
| **WS-4** | PlaybackState **7 字段（CR-1）冻结**；推送**不能增加** `duration`/`progress`/`current_time`/`video_state` |
| **WS-5 / WS-6** | 断线只设计三事件；重连/心跳/恢复 Deferred；scope freeze |
| **WM-1** | envelope **恰 4 字段** `event_type`/`payload`/`timestamp`/`source`；`event_type` ∈ `{comment,gift,like,system}` |
| **WM-4 / WM-6** | push channel 归属 FD 层新增通道；scope freeze |
| **WA-1 ~ WA-3** | adapter 职责**恰三项**（接收/检查/转交）；**输出只有两种**（交付 Gateway / 拒收） |
| **WA-2** | connection 生命周期属 **transport 层**；禁 session/房间/广播；连接不得携带业务状态 |
| **WG-1 / WG-3** | 唯一入口 normalize；下一跳 = `SimulationPipeline`，责任方 = transport；禁 adapter 调 pipeline |
| **WG-5 / WG-6** | **单连接独立语义**；scope freeze |
| **PC-1 ~ PC-6** | 前端 push channel：transport-only client + 唯一接线 hook；**格式 = WM-1 envelope 逐字段保持**；`applyPushEvent` = 第 4 个写出口；schema 不变 |

## Step 2 只读调查（Phase 2.2-7A 结论，本步沿用）

| 问题 | 结论（附证据） |
|---|---|
| **Q1 Runtime State 变更点** | ①`SimulationPipeline.apply_event()`（`pipeline.py:109-143`，事件驱动）；②`pipeline.snapshot()`→`_expire_if_due()`→`ActionEngine.restore_idle()`（**轮询驱动到期**，位于**读取路径**）。`PlaybackManager` 不持业务状态；生产**不注入 `on_finished`**（`runtime_factory.py:133`） |
| **Q2 完成通知点** | **不存在**（`after_apply` / `after_action` / `after_playback` / `subscribe` / `listener` / `observer` / `registry` / `asyncio` / `lifespan` / `websocket.send*` **全 0 命中**）⇒ 当前为纯拉取模型，推送**缺触发器** |
| **Q3 连接归属** | `api/ws.py` 端点协程**局部** `WebSocket`；**无注册表 / 无 ConnectionManager / 无 session**（单连接 = WG-5）；`SimulationPipeline` **无连接引用** |

## Decision（冻结总表 WP-1 ~ WP-6）

### WP-1 —— Push Ownership（冻结）

- **Outbound push 属于 `platform websocket transport boundary`**（连接所在的传输侧）；
- **禁止**以下对象**直接持有 socket**：
  - `ActionEngine`、`PlaybackManager`、`EventGateway`、`SimulationPipeline`；
- **禁止** `WebSocketAdapter.send()`；
  - **理由**：保持 **WA** 冻结口径 —— adapter = **inbound only**（职责恰三项、输出恰两种，WA-1 / WA-3）。

### WP-2 —— Push Trigger Boundary（冻结）

- push 触发点**必须位于 runtime state commit point 之后**（即：状态提交完成、再发起推送）；
- **禁止**：`ActionEngine.execute()` 内直连 `websocket.send()`；
- **禁止**：`PlaybackManager` 持有 socket 引用（播放层不得持有连接）。
- commit point 的**精确定义**（`apply_event()` 受理成功 / `snapshot()` 到期推进的实际变更）
  归 **Phase 2.2-7B-1「Runtime Commit Point Design」**（须另行授权）。

### WP-3 —— Payload Contract（冻结）

出站帧**唯一形式** = **WM-1 envelope**：

```json
{"event_type": "...", "payload": {}, "timestamp": "...", "source": "..."}
```

- **冻结**：**不新增** envelope 字段（恰 4 字段，WM-1）；
- **冻结**：**不增加** PlaybackState 字段（**CR-1** 起为 **7 字段**，此后不再增加）；
- **冻结**：**不发送** `duration` / `progress` / `video_state` / `queue`。

> **受权增量（CR-6 / 2026-09-28）**：本条首句的「**唯一形式**」经 **CR-6** 授权放宽为「**两类形态**」——
> **① 事件帧**（= 上述 **WM-1 envelope**，**逐字不变**）与 **② 状态帧**（**CR-6 新增**；载荷 = API-2 的
> `PlaybackState` **7 字段原样**，仅用于 idle 到期后的**状态同步**）。
> **上述三条冻结禁止项逐字不变**；「**不新增** envelope 字段」的约束**仅适用于事件帧**。
> 详见 **§CR-6 修订记录**。

### WP-4 —— Connection Ownership（冻结）

- 当前阶段：**single active connection**（单活动连接）；
- 连接生命周期：**transport owns**（与 WA-2 / WG-5 一致）；
- **禁止**：global connection registry、room、broadcast、multi client。

### WP-5 —— Failure Policy（冻结）

- 发送失败：**只允许 log**；
- **禁止**：retry、reconnect、buffer（缓冲队列）、ack、replay。

### WP-6 —— Scope Freeze（冻结）

本阶段**明确禁止**：heartbeat、authentication、authorization、multi-user、multi-pet、
OBS、AI、Live2D。

## Step 3 C-WP3 Resolution Record（冲突澄清）

**旧描述（存在表达歧义）**：

| 出处 | 原文 | 表面形态 |
|---|---|---|
| **WS-4** | 「推送**载荷与 API-2 同构**」 | PlaybackState 6 字段快照 |
| **WG-4** | 「**载荷口径**：push 载荷与 **API-2 快照同构**（PlaybackState 6 字段）」 | PlaybackState 6 字段快照 |
| **WM-1** | envelope 恰 4 字段、`payload` = 事件 payload、`event_type` ∈ 白名单 | 事件 envelope |
| **PC-2 / PC-4** | 「消息格式 = **WM-1 envelope** 逐字段保持」；由 envelope 派生 `EventItem` | 事件 envelope |

**歧义点**：WS-4 / WG-4 的「载荷与 API-2 快照同构」被读作**线上帧 schema**，
与 WM-1 / PC 的 envelope 形态**不可同时成立**
（WM-1 的 `event_type` 限白名单、`payload` 为事件 payload ⇒ 装不下 PlaybackState 快照；
前端 `parsePushEnvelope` 只接受 envelope 形态、会**拒收**快照帧）。

**✅ 裁决（2026-09-21，用户）：Outbound WebSocket frame = `WM-1 envelope`。**

**解释**：
- **WS-4 / WG-4 的「同构」仅约束**：
  1. **禁止新增播放字段**（`duration` / `progress` / `video_state` / `queue` 一律不发送）；
  2. **不扩张 PlaybackState**（**CR-1** 起为 **7 字段**；此后不再扩张）；
- **WS-4 / WG-4 不作为线上 frame schema** —— 线上帧 schema **唯一**取 **WM-1 envelope**（WP-3）。

> **说明**：本裁决**未回改** WS-4 / WG-4 的已冻结条款（其**禁止项**继续有效；**字段数**经 **CR-1** 由 6 → 7）；
> 如需对 WS-4 / WG-4 做**正式文字澄清**，须**另出修订文档**（待授权）。

## Step 4 冲突矩阵

| 冻结 | 结果 | 说明 |
|---|---|---|
| **WS-1 ~ WS-6** | ✅ 无冲突 | WP-3 取 envelope 形态（WS-4 的禁止项不变）；WP-4/WP-6 为 WS-5/WS-6 重申 |
| **WM-1 ~ WM-6** | ✅ 无冲突 | WP-3 = WM-1 envelope 逐字；WP-6 = WM-6 一致 |
| **WA-1 ~ WA-6** | ✅ 无冲突 | WP-1 明令**禁止** `WebSocketAdapter.send()` ⇒ WA-1「恰三项」/ WA-3「输出恰两种」**保持** |
| **WG-1 ~ WG-6** | ✅ 无冲突（C-WP3 已澄清） | WP-1/2/4/5/6 与 WG-1/3/5/6 一致；WG-4 的「同构」经 C-WP3 解释为**约束**而非 frame schema |
| **PC-1 ~ PC-6** | ✅ 无冲突 | WP-3 与 PC-2/PC-4（**已冻结且已实现**）一致；PC-6 与 WP-6 逐条一致 |
| **PlaybackState（API-2）** | ✅ 不增加字段（**CR-1** 起为 7 字段） | WP-3 明确「不增加 PlaybackState 字段」；字段数经 **CR-1** 由 6 → 7 |

**结论：本次冻结不需要修改任何既有冻结规则。**

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `WP-*` 编号空间无撞车 | ✅ |
| WP-1 禁止 `WebSocketAdapter.send()`（保 WA-1/WA-3） | ✅ |
| WP-2 禁止 `ActionEngine.execute()` 直连 send / `PlaybackManager` 持 socket | ✅ |
| WP-3 出站帧唯一 = WM-1 envelope；禁新增 envelope / PlaybackState 字段 / 播放派生字段 | ✅ |
| WP-4 单连接 + transport owns + 禁 registry/room/broadcast | ✅ |
| WP-5 失败只 log（禁 retry/reconnect/buffer/ack/replay） | ✅ |
| WP-6 scope 清单完整 | ✅ |
| C-WP3 裁决记录（含「WS-4/WG-4 不作为 frame schema」的解释） | ✅ |
| 全部既有编号空间 0 修改 | ✅ |

## 落地项（归 Phase 2.2-7B-1，须另行授权）

- **Runtime Commit Point 设计**（WP-2 的精确触发面）：`Runtime State Commit → Push Dispatcher
  → WebSocket send()`；
- **Push Dispatcher 落位**（WP-1：platform websocket transport boundary；落位具体文件为 7B-1 决策项）；
- **通知路径**：commit point → transport（当前**不存在**，见 Q2）；
- **发送实现**（`websocket.send()`）+ 失败只 log（WP-5）。

## CR-6 修订记录 —— idle return push 状态帧（2026-09-28，受权增量）

> **依据（变更请求）**：`docs/change_request/cr-6_idle_return_push.md`（**CR-6**；
> owner 2026-09-28 授权 P0 修法 ①「服务端定时推进 + 推送状态快照」）。
> **程序依据**：本文件 §Step 3 C-WP3 Resolution Record 末尾的**明文条款** ——
> 「如需对 WS-4 / WG-4 做**正式文字澄清**，须**另出修订文档**（待授权）」。
> **CR-6 即该「另出修订文档」**（本文档不是绕过冻结，而是**行使其明文的修订程序**）。
> **范围**：**仅契约文字**；**零代码**、**零依赖**、**零测试改动**
> （不改 `pipeline.py` / `api/ws.py` / 前端 store / tests）。

### 一、允许项（本次授权）

**允许**：

1. **服务端在 idle 到期检测后发送「状态帧」** —— 定时观察发现**状态发生变化**时，由 transport 侧
   出站推送**一次**状态帧（触发时机见 CR-6 §4.2）；
2. **状态帧字段复用 API-2 已存在字段** —— 载荷**原样**取 `PlaybackState` 的 **7 字段**
   （`pet_id` / `state` / `action` / `asset_url` / `queue_size` / `last_event` / `loop`）；
   **不新增、不改名、不裁剪、不派生**；
3. **推送用于同步客户端展示状态** —— 前端将状态帧**整份写入** `playback` 切片，**仅**用于展示同步。

**由此，出站帧有且仅有两类**：

| 类型 | 形态 | 载荷 | 相对 v1.0 |
|---|---|---|---|
| **事件帧** | **WM-1 envelope**（恰 4 字段） | 事件 `payload` | ⛔ **逐字不变** |
| **状态帧**（**CR-6 新增**） | 含 `type` 标记 + `snapshot` | `PlaybackState` **7 字段原样** | ✅ **新增** |

**两类帧的判别**：帧内出现 `type` 字段（取值 `"playback_state"`）即为**状态帧**；
**不含** `type` 者**一律**按 **WM-1 事件帧**处理（⇒ 两类**互斥可判**，事件帧校验口径不变）。

### 二、禁止项（**保持冻结**）

**禁止**：

1. **新增播放字段** —— `duration` / `progress` / `current_time` / `video_state` / `queue`
   及任何播放派生字段**一律不发送**（WP-3 存活禁止项，**逐字不变**）；
2. **新增 PlaybackState 枚举** —— `state` 的取值集合**不扩张**（仍 `idle` / `playing`；
   `action` 名来自素材/规则描述，**不构成**枚举扩张）；
3. **新增独立 runtime registry** —— **不建** connection registry / room / broadcast / multi client
   （**WP-4 逐字不变**）；连接生命周期仍归 **transport**（WA-2 / WG-5）；
4. **修改 `pet_id` 读取策略** —— **MP-1 / MP-2 / MP-3 逐字不变**：仅**显式** `?pet_id=` 连接按 pet 写，
   默认 / 旧路径仍写 `NULL`；**不新增**宠物投影、**不新增**读侧作用域规则；
5. **将 WS 推送变成播放控制通道** —— 推送**只出站**，**不构成**对 runtime 的指令：
   前端**禁止**由推送帧反推业务（**PC-3 逐字不变**）；**禁止** `WebSocketAdapter.send()`
   （**WA-1 / WA-3 / WP-1 不变**）；**禁止**由推送触发 `apply_event` / `ActionEngine.execute()` /
   队列变更。

### 三、状态帧边界（**性质定义**）

**WS idle return push：**

> 是**状态同步机制**，**不是**播放驱动机制。

**状态来源**：

```
pipeline.snapshot()
```

**而不是**：

```
new playback state machine
```

**展开说明**：

- 状态帧的载荷**只来自** `pipeline.snapshot()` 的返回值（其内部已含**既有**的到期推进 `_expire_if_due()`）；
- ⛔ **不新增**状态机、**不新增**推进实现、**不新增**通知路径 —— 定时观察仅是对**既有读路径**的**再调用**；
- ⇒ **WC-3**（v1.1：到期推进 = **读路径 + 事件受理路径**）**语义不变**：本增量**不构成**第三类推进路径，
  只是新增「服务端**何时**去读」的触发时机。**故本笔不修订 WC-3**（登记于此，供后续实现核对）。

### 四、WS-4 / WG-4 口径重申（**禁止项不变**）

| 条款 | 口径 | 本增量后 |
|---|---|---|
| **WS-4** | `PlaybackState` **7 字段（CR-1）冻结**；推送**不能增加** `duration` / `progress` / `current_time` / `video_state` | ✅ **重申，逐字不变** |
| **WG-4** | 「**载荷口径**：push 载荷与 **API-2 快照同构**」 | ✅ **不变**；状态帧**首次让该口径在线上帧落地**（事件帧不受影响） |
| **WP-3** | 出站帧形态 | ⚠️ **本增量唯一修订点**：「**唯一形式**」→「**两类形态**」（见 §一）；三条**冻结禁止项**逐字不变 |
| **WP-1 / WP-2 / WP-4 / WP-5 / WP-6** | 所有权 / 触发点 / 连接 / 失败策略 / 范围 | ✅ **逐字不变** |
| **WM-1** | envelope **恰 4 字段**、`event_type` ∈ 白名单 | ✅ **不变**（该约束**仅约束事件帧**） |
| **PC-2 / PC-4** | 前端格式 = WM-1 envelope；`applyPushEvent` = 第 4 写出口 | ⚠️ 归 **CR-6 后续笔**修订（**本笔不含**，见 §五） |

### 五、本笔**未触及**（登记，供后续笔核对）

| 项 | 状态 |
|---|---|
| **WC-3**（到期推进时机） | **无需修订** —— 设计**复用既有读路径**（§三） |
| **PC-2 / PC-4**（前端推送通道：按帧型分流 + 状态写出口） | **未修订** —— 归 CR-6 后续（前端实现）笔 |
| **`PROJECT_RULES.md` §十四 摘要** | **未修改**（本笔指令明确要求保持不变）⇒ 摘要仍为**修订前**口径，**须在后续授权笔同步** |
| `phase2_websocket_boundary_decision.md` / `phase2_websocket_event_model_decision.md` 中的 **WS-4 重申行** | **未修改** —— 二者只约束**字段数**与「推送载荷与 API-2 同构」，与本增量**一致**，无需改动 |

### 六、变更记录

| 项 | 内容 |
|---|---|
| **原冻结约束** | ① **WP-3**：出站帧**唯一形式** = WM-1 envelope（恰 4 字段）；② **C-WP3 裁决（2026-09-21）**：WS-4 / WG-4 的「载荷与 API-2 快照同构」**不作为线上 frame schema**，**仅约束**「禁新增播放字段」+「不扩张 PlaybackState」；③ **WS-4**：`PlaybackState` **7 字段**冻结；④ **WP-4**：单连接 / transport owns / 禁 registry、room、broadcast、multi client；⑤ **WP-6**：禁 heartbeat / multi-pet / OBS / AI / Live2D |
| **本次授权范围** | **仅**：① 允许服务端在 idle 到期后推送**状态帧**（**第二类**出站帧）；② 状态帧载荷**原样复用** API-2 的 **7 字段**；③ 明确「idle return push = **状态同步**，非播放驱动」且状态来源**恒为** `pipeline.snapshot()`。**修订落点 = WP-3 一条**（「唯一形式」→「两类形态」）+ 本 §CR-6 记录。**零代码** |
| **不受影响范围** | **WP-1 / WP-2 / WP-4 / WP-5 / WP-6** 逐字不变；**WM-1**（事件帧恰 4 字段）不变；**WS-4 / WG-4 的禁止项**逐字不变；**PlaybackState 仍 7 字段**（不扩张）；**MP-1 / MP-2 / MP-3**（`pet_id` 读取策略）不变；**WC-3** 语义不变；**PC-1 ~ PC-6** 本笔未触碰；**`PROJECT_RULES.md`** 未修改；**组合根预算**未触碰 |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 Phase 2.2-7A 草案（v0.2）整理冻结：WP-1 ~ WP-6 + C-WP3 Resolution Record；零代码变更 |
| —（**CR-1** 登记） | 2026-09-24 | WP-3 / C-WP3 的 `PlaybackState` 字段数 6 → 7（+ `loop`）；WP-1/2/4/5/6 **逐字不变**。见 `docs/change_request/cr-1_idle_loop.md` |
| —（**CR-6** 登记） | 2026-09-28 | **WP-3** 出站帧形态「**唯一形式**」→「**两类形态**」（事件帧逐字不变 + **新增状态帧**，载荷原样复用 API-2 的 7 字段）；新增 **§CR-6 修订记录**（允许项 / 禁止项 / 状态帧边界 / WS-4·WG-4 重申 / 变更记录）。**WP-1/2/4/5/6 与 WS-4/WG-4 禁止项逐字不变**；WC-3 语义不变。见 `docs/change_request/cr-6_idle_return_push.md` |
