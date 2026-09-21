# Phase 2.2-2 WebSocket Adapter Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-2 指令）
> 输入：`phase2_platform_boundary_decision.md`（PB-*）、
> `phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `step2_event_schema.md`（事件契约 v1.1）
> 编号空间声明：本文档使用 **WA-***（创建前核查：docs + 源码 `WA-\d` 全仓 **0 命中**，无撞车）。
> 本步**纯架构冻结：零代码、零依赖、零 backend 修改、零 frontend 修改**——
> 不创建 websocket endpoint、不加 FastAPI websocket route、不写 connection manager /
> broadcast / client session、不修改 EventGateway 实现与 ActionEngine。

## Input

- 指令：Phase 2.2-2 Backend WebSocket Adapter Boundary Design——冻结 backend WebSocket adapter 的职责。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `e3c9838`，working tree clean。

## Step 1 已核读冻结（职责定位依据）

- **PB-1/2/3**：platform 是外部输入适配层；禁业务逻辑；产物唯一走 `EventGateway.normalize()`；
- **WS-1/2**：WS 属实时输入适配层（platform websocket adapter）；消息转事件契约 v1.1；
  禁 socket 直调引擎/Store/services；非契约消息只有拒收+日志；
- **WM-1/3**：envelope 恰 4 字段（event_type/payload/timestamp/source）；
  流转 `WS 消息 → platform adapter → normalize → 内部事件`；
- 本决策把上述边界**落到 backend adapter 的具体职责切分**，不引入新架构面。

## Decision（裁决总表 WA-1 ~ WA-6）

### WA-1 —— Adapter Position（冻结）

- backend WebSocket adapter 的位置：**platform 层**（`platform/websocket adapter`；
  落位目录在实现步裁决）；
- 职责**恰三项**：
  1. **协议接收**（WebSocket 连接上的原始消息接收）；
  2. **格式检查**（envelope 校验：恰 4 字段 / 类型 / `event_type` ∈ 契约白名单 / payload 结构，WM-1）；
  3. **转交 normalize**（合法消息交付 `EventGateway.normalize()`，WM-3）；
- **禁止业务判断**：动作选择、规则匹配、优先级、素材、播放、统计、落库——全部不在 adapter
  （PB-2 同口径）；adapter 是"门卫"，不是"裁判"。

### WA-2 —— Connection Ownership（冻结）

- connection 生命周期（accept / close / 连接表维护）**属于 transport 层**细节，
  可存在于 adapter 的传输侧；
- 本阶段**不定义**：用户 session 模型、房间、广播、多客户端管理、连接身份归属
  （与 WS-5 / WM-6 一致）；
- 连接对象**不得**携带业务状态（不得缓存 playback / 队列 / 统计）。

### WA-3 —— Message Flow（冻结）

流转固定单向（WM-3 落到 backend 侧）：

```
socket message → adapter（协议接收 + 格式检查）→ EventGateway.normalize() → internal event → 核心链路
```

- **禁止** adapter 调用：ActionEngine、PlaybackManager、Store（前端 store 亦无从谈起）、
  repositories、DataManager、任何 `services/**`；
- adapter 的输出**只有**两种：① 合法事件交付 Gateway；② 拒收（WA-4）。

### WA-4 —— Error Policy（冻结）

非法输入分类与处理：

| 非法类型 | 例子 | 处理 |
|---|---|---|
| 非法 JSON | 消息体无法解析 | reject + log |
| 非法字段 | envelope 缺字段 / 多字段 / 类型错（WM-1） | reject + log |
| 非法 event_type | 不在契约 v1.1 白名单 | reject + log |
| 非法 payload | 与契约字段约定不符 | reject + log |

- 统一口径：**reject + log**（对齐 PB-2 / WS-2 / QP-3"禁纠偏"精神）；
- **禁止自动修复业务字段**：不补默认、不改写、不"猜"合法值——修正责任在外部发送方；
- 日志按 backend 日志规范记录拒收原因（不含完整 payload 敏感内容dump 的要求归实现步）。

### WA-5 —— Security Boundary（冻结）

- **认证 / 授权留待独立设计**（后续冻结文档），本阶段完全不实现；
- 本阶段**不实现**：token 校验、user identity 绑定、permission 检查、限流；
- 因此当前 adapter 语义 = **匿名传输适配**（与 Phase 1 HTTP simulate 的匿名口径一致）；
  未来引入认证时必须新冻结文档修订 WA-5，且认证属 platform 传输侧、不进业务链路。

### WA-6 —— Scope Freeze（冻结）

本阶段**禁止**：broadcast、rooms、multi client 管理、reconnect、heartbeat、
queue（消息队列化）、AI 相关任何内容、endpoint / route / connection manager 的实现代码、
新依赖（含 ws 库引入决策——实现步裁决）、EventGateway 实现修改、ActionEngine 修改。

## Step 3 冲突检查结果（PB / WS / WM）

| 冲突项 | 结论 |
|---|---|
| **PB-1..4** | ✅ 无冲突：WA-1..3 是 PB"适配层/禁业务/唯一入口"在 WS 场景的具体化 |
| **WS-1..6** | ✅ 无冲突：WA 与 WS-1（位置）/WS-2（唯一入口+拒收）/WS-5（不实现重连心跳）/WS-6（scope）逐条一致 |
| **WM-1..6** | ✅ 无冲突：WA-1 格式检查即 WM-1 envelope 校验；WA-3 即 WM-3 流转；WA-4 拒收口径即 WM-3；无新字段、无双体系 |

**结论：本决策不需要修改任何既有冻结规则**（PB/WS/WM 均保持原样；
WA 是三者的 backend adapter 职责落位，不新增架构面）。

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| WA-* 编号空间全仓 0 撞车 | ✅ |
| WA-1 职责恰三项（接收/检查/转交） | ✅ |
| WA-2 连接归 transport，无 session/房间/广播 | ✅ |
| WA-3 流转单向、输出只有两种 | ✅ |
| WA-4 reject+log 四类非法输入，禁自动修复 | ✅ |
| WA-5 认证授权完全 Deferred（匿名口径与 HTTP simulate 一致） | ✅ |
| 落地项 | 无（架构冻结步；endpoint/adapter 实现须另行授权 + FastAPI websocket 路由设计文档） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-21 | 首版冻结（WA-1 ~ WA-6 + 冲突检查无冲突结论）；零代码变更 |
