# Phase 2.2-1 WebSocket Event Model Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-1 指令）
> 输入：`phase2_websocket_boundary_decision.md`（WS-*，v1.0）、
> `phase2_platform_boundary_decision.md`（PB-*）、`phase2_render_boundary_decision.md`（RB-*）、
> `step4_frontend_data_flow_decision.md`（FD-*）、`step2_event_schema.md`（事件契约 v1.1）
> 编号空间声明：本文档使用 **WM-***（创建前核查：docs + 源码 `WM-\d` 全仓 **0 命中**，无撞车）。
> 本步**纯数据模型与流转规则冻结：零代码、零依赖、零 backend、零 frontend**——
> 不创建 websocket server / client / endpoint / hook，不修改 store / API / PlaybackState。

## Input

- 指令：Phase 2.2-1 WebSocket Event Model Design——冻结 WS 实现前的数据模型和流转规则。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `6dbf911`，working tree clean。

## Step 1 已核读冻结（边界关系）

- **WS-1/2**：WS 属 platform 实时输入适配层；消息必须转换为事件契约 v1.1 统一事件，
  唯一入口 `EventGateway.normalize()`；
- **WS-3**：推送 ≠ refresh（pull 与 push 长期并存，禁 WS 内 refresh 循环）；
- **WS-4**：PlaybackState 6 字段冻结，推送载荷与 API-2 同构；
- **PB-2/PB-3**：platform 禁业务逻辑；产物唯一走 Gateway；
- **FD-1..5**：现状唯一写入路径 = hook 层 `loadRuntimeData()`（API pull）。

## Decision（裁决总表 WM-1 ~ WM-6）

### WM-1 —— Event Envelope（冻结）

WS 消息**外层结构（envelope）恰 4 字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_type` | `string` | ∈ 事件契约 v1.1 白名单（`comment/gift/like/system`） |
| `payload` | `object` | 与事件契约 payload 同构（按 event_type 的既有字段约定） |
| `timestamp` | `string` | 事件发生时间，**ISO 8601 字符串**（UTC；精确格式实现步定） |
| `source` | `string` | 事件来源标识（如 `"ws"`；与 HTTP 模拟器的 `"simulator"` 平级区分） |

- **字段数量冻结**：v1.0 恰 4 字段，**新增字段必须修订本文档**（版本升级），禁止实现层私自扩展；
- **禁止业务字段进入 envelope**：gift_name / like_count / 动作名 / 播放状态等业务信息
  一律只存在于 `payload`（envelope 是信封，不是业务对象）；
- **待实现步裁决项**（不在本版冻结）：用户身份（`user_id` / `user_name`）的承载方式——
  连接握手注入 vs 放入 payload；裁决前任何实现不得假设其一。

### WM-2 —— Event Source（冻结）

- 事件来源恰两个：**API（runtime pull）** 与 **WS（runtime push）**；
- 两者最终**都进入事件契约 v1.1** 的统一事件体系（同一套 Gateway / Engine / 数据链）；
- **禁止双事件体系**：不得为 WS 另建一套事件结构、第二套 Gateway、第二套规则匹配——
  来源不同、契约唯一。

### WM-3 —— Normalize Boundary（冻结）

流转规则固定单向：

```
WS 消息 → platform websocket adapter → EventGateway.normalize() → 内部事件 → 核心链路
```

- adapter 职责恰为：连接管理 + envelope 校验 + 交付 Gateway（PB-1/PB-2/WS-1/WS-2 不变）；
- **禁止** socket 直接进入 services（ActionEngine / PlaybackManager / DataManager 等）；
- 非法 envelope（缺字段 / 多字段 / 类型错 / event_type 越白名单）只有拒收 + 日志一种处理。

### WM-4 —— Frontend Consume Boundary（冻结）

- 未来 WS 推送数据进入前端的**唯一方式**：**FD 层新增 push channel**（实现步出 FD 修订文档）；
- **不改变**：`refresh` 语义与唯一来源（RF-1/RF-2 不变）、`loadRuntimeData` 的既有职责；
- **禁止** WS 调用 refresh（WS-3 重申）；
- 本决策不设计 push channel 的内部形态（hook 形状 / store 写入方式），留实现步。

### WM-5 —— Ordering（冻结）

- 本阶段**只定义**事件时间字段（envelope 的 `timestamp`，WM-1）；
- **不实现**：队列排序、重放、补偿、ack、seq 序号——全部留待后续冻结文档；
- 消费端不得假设"收到顺序 = 业务顺序"（本阶段无排序保证，避免隐式依赖）。

### WM-6 —— Scope Freeze（冻结）

本阶段**禁止**：自动重连、消息恢复、离线同步、多客户端广播、房间系统、多宠物同步、
seq/ack 机制、任何 server / client / endpoint / hook 实现代码、新依赖、
API 修改、PlaybackState 修改、store 修改。

## Step 3 冲突检查结果（WS-3 / RF-2 / FD / PlaybackState）

| 冲突项 | 结论 |
|---|---|
| **WS-3**（推送 ≠ refresh） | ✅ 无冲突：WM-4 与其完全同构（push 走 FD 新通道、禁调 refresh） |
| **RF-2**（refresh 唯一入口） | ✅ 无冲突：WM-4 明确不改变 refresh 语义与唯一来源 |
| **FD**（数据流唯一写入路径） | ✅ 无冲突：FD 文档**本体不动**；WM-4 只声明 push channel 的架构地位，FD 修订归实现步（须新文档裁决，届时须用户授权） |
| **PlaybackState**（6 字段） | ✅ 无冲突：WM-1 envelope 不含播放器派生字段；推送载荷同构沿用 WS-4 |

**结论：本决策不需要修改任何既有冻结规则**（WS/PB/RB/FD/RF 均保持原样）。

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| WM-* 编号空间全仓 0 撞车 | ✅ |
| WM-1 envelope 恰 4 字段、业务字段只进 payload | ✅ |
| WM-2 单一事件体系（无双轨） | ✅ |
| WM-3 流转单向、唯一入口 normalize | ✅ |
| WM-4 push channel 声明与 FD/RF 正交 | ✅ |
| WM-5 只定义时间字段，排序/重放/ack 全 Deferred | ✅ |
| 落地项 | 无（模型冻结步；实现须另行授权 + FD 修订文档 + 用户身份承载裁决） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-21 | 首版冻结（WM-1 ~ WM-6 + 冲突检查无冲突结论）；零代码变更 |
