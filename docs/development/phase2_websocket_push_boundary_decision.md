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
| **WS-4** | PlaybackState **6 字段冻结**；推送**不能增加** `duration`/`progress`/`current_time`/`video_state` |
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
- **冻结**：**不增加** PlaybackState 字段（6 字段不变）；
- **冻结**：**不发送** `duration` / `progress` / `video_state` / `queue`。

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
  2. **不扩张 PlaybackState**（6 字段冻结不变）；
- **WS-4 / WG-4 不作为线上 frame schema** —— 线上帧 schema **唯一**取 **WM-1 envelope**（WP-3）。

> **说明**：本裁决**未回改** WS-4 / WG-4 的已冻结条款（其**禁止项**与 **6 字段冻结**继续有效）；
> 如需对 WS-4 / WG-4 做**正式文字澄清**，须**另出修订文档**（待授权）。

## Step 4 冲突矩阵

| 冻结 | 结果 | 说明 |
|---|---|---|
| **WS-1 ~ WS-6** | ✅ 无冲突 | WP-3 取 envelope 形态（WS-4 的禁止项不变）；WP-4/WP-6 为 WS-5/WS-6 重申 |
| **WM-1 ~ WM-6** | ✅ 无冲突 | WP-3 = WM-1 envelope 逐字；WP-6 = WM-6 一致 |
| **WA-1 ~ WA-6** | ✅ 无冲突 | WP-1 明令**禁止** `WebSocketAdapter.send()` ⇒ WA-1「恰三项」/ WA-3「输出恰两种」**保持** |
| **WG-1 ~ WG-6** | ✅ 无冲突（C-WP3 已澄清） | WP-1/2/4/5/6 与 WG-1/3/5/6 一致；WG-4 的「同构」经 C-WP3 解释为**约束**而非 frame schema |
| **PC-1 ~ PC-6** | ✅ 无冲突 | WP-3 与 PC-2/PC-4（**已冻结且已实现**）一致；PC-6 与 WP-6 逐条一致 |
| **PlaybackState（API-2）** | ✅ 不增加字段 | WP-3 明确「不增加 PlaybackState 字段」 |

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

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 由 Phase 2.2-7A 草案（v0.2）整理冻结：WP-1 ~ WP-6 + C-WP3 Resolution Record；零代码变更 |
