# Phase 2.2-4 WebSocket Runtime Integration Architecture Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-4 指令确认执行，纯架构冻结——零代码零依赖零修改）
> 输入：`phase1_completion.md`、`phase2_platform_boundary_decision.md`（PB-*）、
> `phase2_render_boundary_decision.md`（RB-*）、`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、`phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `step4_frontend_data_flow_decision.md`（FD-*）、`step4_frontend_refresh_boundary_decision.md`（RF-*）
> 编号空间声明：本文档使用 **WG-***（创建前核查：全仓 0 命中，无撞车）。

## Input

- 指令：Phase 2.2-4 —— 在 runtime integration **实现前**冻结：WS 事件进入 runtime 的唯一入口、
  gateway 所有权、runtime 下一跳、push 模型、多客户端政策、scope。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `3e01d6c`，working tree clean，
  WG-* 全仓 0 命中，全部输入文档齐备。

## Investigation（只读调查记录，2026-09-21）

### I-1 当前链路（实现现状）

```
HTTP simulate（已实现）：
  POST /api/events/simulate → api/events.py → SimulationPipeline.simulate()
  → EventGateway.normalize → InteractionEngine.evaluate → ActionEngine.execute
  → DataManager 记录（platform="simulator"）→ PlaybackSnapshot

WS（transport 已实现，链路止于 normalize）：
  WS /api/ws → api/ws.py（transport）→ platform WebSocketAdapter
  → EventGateway.normalize → 内部事件（**刻意不消费**）→ STOP
```

### I-2 EventGateway 生命周期

- 由 `runtime_factory.build_runtime()` 装配进 `Runtime`（frozen，12 字段之一），
  `SimulationPipeline` 持有 `self._runtime.gateway`，**无公开访问器**；
- **`EventGateway` 无状态**（纯转换：dict → Event，规则校验）→ **可安全共享**；
- 当前 WS 路径经 `build_websocket_adapter()` 使用 **adapter 级独立实例**
  （Phase 2.2-3B-1/2 落位决策：`services/pipeline.py` 当时不在授权范围、且 pipeline 无 gateway
  公开访问器——代码 docstring 已自述为过渡形态）。

### I-3 SimulationPipeline 外部事件入口

- 公开编排入口恰两个：`simulate(raw_event) -> PlaybackSnapshot`（完整链路 + 记录）与
  `snapshot()`（只读快照）；`simulate` 是**唯一**能驱动 ActionEngine 的公开路径；
- `simulate` 内部记录口径：`platform=PLATFORM_SIMULATOR`（常量，Phase 1 只有模拟器）。

### I-4 Runtime State 写入路径（现状）

- 唯一写出口：`pipeline._record → DataManager`（`write_event / aggregate_counter / record_action`）；
- 读取：`repositories/**`（只读）→ API stats / events/recent；
- WS 路径当前**零写库**（Phase 2.2-3B-2 测试钉死：断线前后 events/recent 一致）。

### I-5 Frontend 现状

- 数据流：`usePetRuntime()`（FD-3）→ `loadRuntimeData`（Promise.all 三路拉取）→ store 三 setter；
- 刷新：`refresh()` 唯一来源 `usePetRuntime()`（RF-1）、触发仅 button click（RF-2）、
  simulate 写路径经 `triggerEvent`（ES-2）——**全部是 pull**；
- **push channel 不存在**（FD-5 明确排除 websocket；hooks/ 内无任何订阅代码）。

## Decision（裁决总表 WG-1 ~ WG-6）

### WG-1 —— Event Entry Boundary（冻结）

- WS 事件进入系统的**唯一入口** = `EventGateway.normalize()`（与 HTTP simulate 同一扇门）；
- 完整链路：`socket message → transport（api/ws.py）→ platform adapter → EventGateway.normalize()`
  —— 与 WA-3 / WM-3 完全一致，本决策不加宽不加窄；
- **禁止**：socket 任何形式 bypass EventGateway（直调引擎 / 直写 DataManager / 直拼内部事件对象）。

### WG-2 —— Gateway Ownership（裁决：方案 A，冻结）

**裁决 = 方案 A：WS 与 HTTP simulate 共用同一 EventGateway 生命周期。**

理由：

1. **单一事件语义**：`normalize()` 是事件契约 v1.1 的唯一解释者；两个实例 = 两份白名单与校验
   规则的副本，必然漂移（一个放宽一个收紧时无任何机制告警）；
2. **无状态 ⇒ 共享零成本**：`EventGateway` 无状态（I-2），共享无并发/顺序风险，
   不需要任何同步机制；
3. **冻结一致性**：WS-2「消息必须转换为统一事件」与 WM-2「禁止双事件体系」在逻辑上
   已经要求**同一个解释者**——两个实例即使代码相同，也在架构上构成双体系雏形；
4. **诊断单点**：事件被拒收时只有一处日志口径，排查成本最低。

**过渡形态声明**：Phase 2.2-3B-1/2 的 adapter 级独立实例是**当时授权范围约束下的过渡形态**
（代码 docstring 已自述），**不是终态**；实现步必须统一为方案 A。

**实现路径（归实现步，须授权）**：修改 `app/services/pipeline.py` 为组合根暴露 gateway
只读访问器（或等价的组合根级出口），`build_websocket_adapter` 改为消费组合根实例；
该修改**同时**要求出实现授权指令。

### WG-3 —— Runtime Integration（冻结）

- `EventGateway` 之后的下一跳 = **`SimulationPipeline` 的编排入口**（I-3 的 `simulate()`，
  或实现步裁决的等价编排方法）——runtime 集成的**唯一编排者**；
- **谁负责进入 pipeline：transport 层**（`api/ws.py` 的 websocket endpoint）。职责链：
  adapter 产出合法内部事件 → transport 将其交给 pipeline 编排入口；
- **禁止**：
  - adapter 调 pipeline（WA-3 不变：adapter 输出只有「交付 Gateway」与「拒收」两种）；
  - EventGateway 调 pipeline（网关是纯转换，无编排职责）；
  - pipeline 为 WS 新增第二条编排入口（编排入口唯一性归 DB-4/组合根唯一性原则；
    是否复用 `simulate()` 还是扩展其签名，**归实现步裁决项**，裁决时须同步明确
    WS 事件的写库 `platform` 口径——当前常量 `PLATFORM_SIMULATOR` 不适配 WS 来源）；
- **禁止** adapter / transport 绕过 pipeline 直调 ActionEngine / PlaybackManager / DataManager。

### WG-4 —— Runtime Push Model（冻结）

- **允许** backend → frontend push（架构地位），但 push 的**性质**冻结为：
  **FD 层新增 push channel**（hook → store 的第二条写入路径），**不是 refresh 的替代品**；
- **RF-1 refresh 唯一来源不变**：`refresh` 仍只有 `usePetRuntime()` 一个来源、
  触发仍仅人工（RF-2）；push channel **不复用、不调用、不替代** `refresh`（WS-3 重申）；
- **载荷口径**：push 载荷与 API-2 快照**同构**（PlaybackState 6 字段冻结，WS-4 重申）；
  禁止 push 携带 duration / progress / current_time / video_state 等派生字段；
- FD 文档**本体不动**；push channel 的内部形态（hook 形状 / store 写入方式 / 订阅生命周期）
  归实现步，且**须 FD 修订文档 + 用户授权**后方可实现；
- **禁止**：WS 内部调用 refresh 循环、以推送之名行轮询之实、绕过 store 直接写组件状态。

### WG-5 —— Multi Client Policy（冻结）

- 当前 Phase 2.2：**单连接独立语义**——每个 websocket 连接独立处理，服务端不持有连接集合、
  不向其他连接发送数据；
- **禁止**：broadcast / room / multi user sync（与 WA-2 / WA-6 / WS-6 完全一致，不放宽）；
- **未来扩展入口**：如需多客户端能力，必须**先出独立决策文档**（新编号空间，不得复用 WG）
  并获用户授权，且不得回口修改本决策的已冻结条款。

### WG-6 —— Scope Freeze（冻结）

本阶段**不实现**：

- ❌ frontend websocket hook / subscription
- ❌ reconnect（自动重连）
- ❌ heartbeat（心跳）
- ❌ message replay（消息重放）
- ❌ queue sync（队列同步）
- ❌ playback control（播放控制）
- ❌ multi pet（多宠物）
- ❌ runtime integration 的任何实现代码（pipeline.py / adapter / transport 修改须实现授权指令）

## Step 3 冲突检查结果（WS / WM / WA / PB / RB / RF / FD / PlaybackState）

| 冲突项 | 结论 |
|---|---|
| **WS-1 ~ WS-6** | ✅ 无冲突：WG-1/3 与 WS-1/2 同构；WG-4 即 WS-3 的 runtime 集成落位；WG-5 即 WS-6 重申 |
| **WM-1 ~ WM-6** | ✅ 无冲突：WG-1 沿用 WM-3 流转；WG-4 沿用 WM-4「FD 新通道、不改 refresh」 |
| **WA-1 ~ WA-6** | ✅ 无冲突：WG-2 方案 A 只统一 gateway **实例来源**，WA-3 依赖面（恰 gateway）不变；WG-3 明确 adapter 不调 pipeline（WA-3 重申） |
| **PB-1 ~ PB-4** | ✅ 无冲突：WG 是 PB-3（唯一通道 normalize）在 runtime 集成维度的具体化 |
| **RB-1 ~ RB-5** | ✅ 无冲突：WG 不触碰渲染层；push 载荷 6 字段同构（WS-4/RB 一致） |
| **RF-1 ~ RF-5** | ✅ 无冲突：WG-4 明确 refresh 唯一来源/人工触发**不变**，push 不复用不调用不替代 |
| **FD-1 ~ FD-5** | ✅ 无冲突：FD 文档本体不动；WG-4 只声明 push channel 的架构地位，FD 修订归实现步（须授权） |
| **PlaybackState（API-2/C4）** | ✅ 无冲突：push 载荷同构 6 字段，零新增字段 |

**过渡形态定性说明**：WG-2 把 3B-1/3B-2 的 adapter 级 gateway 实例定性为「过渡形态、非终态」——
这是对**实现细节**的方向裁决，不修改任何已冻结条款（该形态从未被冻结为终态，
其代码 docstring 自述即为过渡）。实现步统一时按本决策执行即可，无需回改 WS/WA/WM 文档。

**结论：本次冻结不需要修改任何既有冻结规则**（WS/WM/WA/PB/RB/RF/FD 均保持原样）。

## 设计验证清单

| 检查项 | 结果 |
|---|---|
| WG-1 唯一入口与 WS-2/WA-3/WM-3 三方一致 | ✅ |
| WG-2 裁决附完整理由（4 条）+ 过渡形态定性 + 实现路径 | ✅ |
| WG-3 下一跳明确、责任方明确、三重禁止明确 | ✅ |
| WG-4 push = FD 新通道，RF-1 不破坏，载荷同构 | ✅ |
| WG-5 单连接语义 + 未来扩展入口（独立文档） | ✅ |
| WG-6 scope 清单完整（7 项不实现） | ✅ |
| 全部既有编号空间 0 修改 | ✅ |
| 落地项 | 归实现步（pipeline.py gateway 访问器 + WS→simulate 接线 + FD push channel 修订），均须授权 |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-21 | 首版冻结（WG-1 ~ WG-6；gateway 所有权裁决 = 方案 A） |
