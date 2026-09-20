# Step 4.2-P / Phase 2.0 Platform Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`docs/development/development_plan.md` v0.3（Phase 2 任务 2-4 / 2-5、Phase 3 任务 3-4/3-5）、
> `step2_event_schema.md`（事件契约 v1.1）、`step4_frontend_event_simulator_decision.md`（ES-*）、
> `phase1_completion.md`（架构注记：backend 无独立 platform 模块层）
> 编号空间声明：本文档使用 **PB-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* /
> RV-* / RS-* / RF-* / FP-* / PI-* / ES-* / AS-* / DA-* / DB-* / QP-* 均不复用、不覆盖
>（创建前已核查：`PB-\d` 全仓 0 命中，无撞车）。
> 本步**只冻结平台层架构边界，不实现任何代码**（WebSocket / OBS / Adapter 实现均归后续授权步骤）。

## Input

- 指令：Phase 2.0 基础收口 —— 完成开发前基础收口（文档新增 + 架构边界设计）。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `3232005`，working tree clean；
  `phase1_completion.md` 与本文档均为待创建（无撞车）。

## Investigation（只读事实，2026-09-20）

- Phase 1 的平台可替换性（G2）由**事件契约（`normalize(dict)` 唯一入口）+ HTTP simulate 端点**承担；
  `backend/app/` 无 platform/adapter/simulator 模块——Simulator 在架构上是 **HTTP 事件源**；
- Phase 2/3 即将引入的事件源：WebSocket 推送（2-4）、OBS 浏览器源（2-3，展示侧）、
  Douyin / YY / Bilibili Adapter 骨架（3-4/3-5）；
- EventGateway `normalize(dict)` 对**来源无感知**：只认事件契约字段（event_type / user_id /
  user_name / payload）——这是 platform 层可以薄化的结构基础。

## Decision（裁决总表 PB-1 ~ PB-4）

### PB-1 —— Platform 是外部输入适配层（冻结）

- platform 层**唯一职责**：把**外部输入**（WebSocket 连接消息、直播平台回调、本地调试信号等）
  适配为**内部可处理的输入**；
- platform 是系统的**最外圈**：它只接触外部世界，不接触任何业务对象
  （InteractionEngine / ActionEngine / PlaybackManager / DataManager 均不可见）；
- platform 不持有业务状态、不做缓存决策、不重试业务（连接级重连属传输细节，可存在于 platform，
  但**不得**附带业务判断）。

### PB-2 —— 禁止业务逻辑进入 platform（冻结）

- **禁止**在 platform 层出现：规则匹配、动作选择、优先级判断、数据落库、统计聚合、
  素材解析、播放控制、任何 `services/**` 的 import；
- platform 对非法输入的处理**只有一种**：拒收/丢弃并记录日志（错误口径与事件契约一致），
  **不得**自行业务纠偏（对齐 QP-3「禁纠偏」精神）；
- 违反本条的代码不得进入 `backend/app/platform/**`（未来落位目录）或任何命名为 platform 的层。

### PB-3 —— platform 输出统一内部事件（冻结）

- platform 适配产物**只有一种**：符合**事件契约 v1.1** 的统一内部事件
  （`event_type` ∈ 白名单 / `user_id` / `user_name` / `payload`）；
- 事件进入核心的唯一通道：**`EventGateway.normalize(dict)`**（Step 2 冻结不变）；
- **禁止** platform 旁路 Gateway 直调 Engine / ActionEngine / PlaybackManager / DataManager；
- 新事件源接入 = 新 adapter 产出同构事件；**白名单扩展必须走事件契约修订**，禁止 adapter 私自放宽。

### PB-4 —— WebSocket / OBS / 外部平台必须经过 adapter（冻结）

- 任何外部通道（WebSocket、OBS 集成、抖音/YY/Bilibili、本地调试工具）接入本系统，
  **必须**以 adapter 形态落在 platform 层，**禁止**在 `api/**`、`services/**`、前端业务组件中
  直连外部协议；
- adapter 骨架（Phase 3 任务 3-4/3-5）与本冻结一致：可编译、可 mock 单测、核心业务零修改；
- 展示侧（OBS 浏览器源）不产生事件，属**输出/展示通道**，不适用本条事件路径；
  其接入形态（部署形态）在 2-3 授权时单独裁决。

## Scope Freeze（本决策不含实现）

本阶段（Phase 2.0）**不实现**：WebSocket 端点、OBS 集成、任何 adapter 代码、
多宠物切换、AI 生成内容管线、音效、运行时优先级抢占。
上述能力引入前必须先出对应冻结文档（含 C1~C8 冲突清单中相关项的修订裁决）。

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `normalize(dict)` 对来源无感知（platform 可薄化的结构基础） | ✅ |
| PB-2 与既有"错误不纠偏"口径（QP-3 / 事件契约）一致 | ✅ |
| PB-3 与 FD-1 单向数据流、RF-1 语义不冲突（WS 推送写入路径归 FD 修订，另立文档） | ✅ |
| PB-4 与 Phase 3 风险闸门（Go/No-Go）兼容：adapter 骨架可先行 | ✅ |
| 落地项 | 无（架构冻结步；后续 WS / adapter 步须先出对应冻结文档） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（PB-1 ~ PB-4 + Scope Freeze）；零代码变更 |
