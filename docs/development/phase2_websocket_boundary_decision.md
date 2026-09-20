# Phase 2.2-0 WebSocket Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20，Phase 2.2-0 指令）
> 输入：`phase1_completion.md`、`phase2_platform_boundary_decision.md`（PB-*）、
> `phase2_render_boundary_decision.md`（RB-*）、
> `step4_frontend_data_flow_decision.md`（FD-*）、`step4_frontend_runtime_state_decision.md`（RS-*）、
> `step4_frontend_refresh_boundary_decision.md`（RF-*）
> 编号空间声明：本文档使用 **WS-***（创建前核查：docs + 源码 `WS-\d` 全仓 **0 命中**，无撞车）。
> 本步**纯架构设计冻结：零代码、零依赖、零 backend 修改**——
> 不创建 websocket server、不改 routes、不改 PlaybackState / Store / Runtime hook、
> 不写前端 websocket client、不做自动刷新逻辑。

## Input

- 指令：Phase 2.2-0 WebSocket Boundary Design。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `2d3b8ae`，working tree clean。

## Step 1 现有边界关系（只读输出）

| 既有边界 | 与 WebSocket 的关系 |
|---|---|
| **PB-1..4**（platform） | WS 属"外部输入适配层"的具体形态之一：连接消息 → 统一事件，禁业务逻辑；外部通道必经 adapter |
| **事件契约 v1.1 + Gateway** | platform 产物只有统一内部事件，唯一入口 `EventGateway.normalize(dict)`；WS 不得旁路 |
| **FD-1..5**（数据流） | 现状唯一写入路径 = hook 层 `loadRuntimeData()`（API pull → store 整份写）；WS 推送是**未来新增的第二写入路径**，归 FD 修订裁决（本决策只冻结其架构地位，不实现） |
| **RF-1..5**（人工刷新） | refresh 唯一来源 `usePetRuntime()`、仅 button click；WS 推送**不是** refresh 的替代或补充（WS-3） |
| **RS-1..5**（四态） | loading/error 归 hook 自持；WS 断线态的表达归后续 RS 修订（本决策不引入第五态） |
| **RB-1..5**（渲染） | WS 不触碰渲染层；媒体仍由 Player 唯一渲染 |
| **API-2 PlaybackState** | 6 字段冻结（WS-4 重申） |

## Decision（裁决总表 WS-1 ~ WS-6）

### WS-1 —— WebSocket 职责边界（冻结）

- WebSocket 属**实时输入适配层**：实现位置为 **platform 层的 websocket adapter**
  （`platform/websocket adapter`，落位目录在实现步裁决；遵循 PB-1/ PB-2）；
- **禁止**任何业务逻辑进入 websocket 层：规则匹配、动作选择、落库、统计、素材解析、
  播放控制、`services/**` import 一律禁止（与 PB-2 同口径）；
- 连接生命周期管理（accept/close）属传输细节，可存在于 adapter，不得附带业务判断。

### WS-2 —— 消息转换与唯一入口（冻结）

- WebSocket 消息**必须**转换为**事件契约 v1.1** 的统一内部事件；
- 进入核心的**唯一入口**：`EventGateway.normalize()`（Step 2 冻结不变）；
- **禁止** socket 直接调用：ActionEngine、PlaybackManager、Store（前端 Zustand store）、
  DataManager 或任何 `services/**`；
- 非契约消息（未知 event_type / 非法 payload）处理只有一种：拒收 + 日志（禁业务纠偏，PB-2/ES 同口径）。

### WS-3 —— 推送与 refresh 的关系（冻结）

- **推送不是 refresh 的替代品**，二者职责不同、长期并存：
  - **当前（API pull）**：runtime `refresh()`——用户显式动作触发的一次性重拉（RF-1/RF-2 不变）；
  - **未来（WS push）**：runtime event update——服务器主动推送驱动的 store 更新，
    走 FD 层新写入通道（实现前须 FD 修订裁决）；
- **禁止** WS 内部调用 refresh 循环（禁止以推送之名行轮询之实）；
- RF-1「refresh 唯一来源」**不变**：refresh 仍只有 `usePetRuntime()` 一个来源，WS 不复用、不替代。

### WS-4 —— PlaybackState 冻结重申（冻结）

- `PlaybackState` 保持 **6 字段冻结**（pet_id / state / action / asset_url / queue_size / last_event）；
- WebSocket 推送**不能增加**：`duration` / `progress` / `current_time` / `video_state`
  或任何播放器派生字段（C4 冻结延续；推送载荷与 API-2 同构）。

### WS-5 —— 断线策略（冻结：只设计，不实现）

- 本阶段**只设计**三种连接事件语义：`connect` / `disconnect` / `error`；
  - `connect`：链路建立，可触发一次全量对账（pull 一次 runtime 数据，语义 = 既有 loadRuntimeData）；
  - `disconnect`：链路断开；UI 表达归 RS 修订（后续裁决），本阶段**不**实现自动降级逻辑；
  - `error`：链路错误原样进入既有 error 通道口径（FD-4 同构），不新增错误体系；
- **不实现**：自动重连、心跳、消息恢复、指数退避、断线缓存重放——全部留待后续冻结文档；
- 前端 hook 侧的订阅/清理生命周期（挂载/卸载）在实现步设计，本决策不预写。

### WS-6 —— Scope Freeze（冻结）

本阶段**禁止**：多人房间、多宠物同步、动作队列消费、播放控制、音频、
自动重连/心跳/消息恢复（WS-5）、websocket server 与 client 的任何实现代码、
OpenAPI 文档开启、新依赖（含 ws / socket.io 等）。

## Step 3 冲突检查结果（C2 / C4 / C6）

| 冲突项 | 结论 | 依据 |
|---|---|---|
| **C2**（RF-2 refresh 唯一入口） | ✅ **无冲突，无需修订** | WS-3 明确推送 ≠ refresh：refresh 语义/唯一来源不变；推送走 FD 层新通道，**不是** refresh 的调用者 |
| **C4**（PlaybackState 6 字段） | ✅ **无冲突，无需修订** | WS-4 重申 6 字段冻结，推送载荷同构，零新增字段 |
| **C6**（PI-3/PI-5 video 事件与队列消费） | ✅ **无冲突，无需修订** | 本决策不触碰渲染层与 video 事件；WS 只推后端状态，绕开 onEnded 依赖（推荐路线维持） |

**结论：本次冻结不需要修改任何既有冻结规则**（PB/RB/FD/RF/RS/PI 均保持原样；
FD 的"推送写入路径"修订留到实现步，届时须新文档裁决）。

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| WS-* 编号空间全仓 0 撞车 | ✅ |
| WS-1/WS-2 与 PB-1..4 同口径（适配层/禁业务/唯一入口） | ✅ |
| WS-3 与 RF-1/RF-2 正交（推送 ≠ refresh） | ✅ |
| WS-4 与 API-2/C4 冻结一致 | ✅ |
| WS-5 断线语义三事件最小集，重连/心跳明确 Deferred | ✅ |
| 落地项 | 无（架构冻结步；WS 实现须另行授权 + FD 修订文档） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（WS-1 ~ WS-6 + 冲突检查 C2/C4/C6 无冲突结论）；零代码变更 |
