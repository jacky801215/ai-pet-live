# CR-4：实现 AI 生成内容标识

> 变更请求（**第四份正式 CR**）。契约来源：`PROJECT_RULES.md` §七（CR 流程）· §十四（边界登记）。
> 前置：`docs/development/phase3_6_ai_live_compliance_audit.md` **B-2 硬阻断**（🔴 AI 生成内容标识完全未做）。
> 状态：**草案 · 待 owner 审阅确认**（确认前不实现、不提交）。
> 性质：本 CR **含冻结契约修订**（FCM-2），修订范围见 §五。

## 一、需求描述

依据《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号，**2025-09-01 生效**）与
**GB 45438-2025**《网络安全技术 人工智能生成合成内容标识方法》，**直播间需添加 AI 生成内容标识**。

**标识要求（指令给定口径，办法第四条）**：

| 场景 | 要求 |
|---|---|
| **视频** | 在**起始画面**和**播放周边适当位置**添加显著提示标识 |
| **虚拟场景** | 在**起始画面适当位置**添加显著提示标识，可在**持续服务过程中适当位置**添加 |

本项目为 **虚拟场景 + AI 生成动画**，需**同时覆盖两者**。

> ⚠️ **条款原文与条号须以官方原文复核** —— 承接 `phase3_6_ai_live_compliance_audit.md` 未确认项 **U-1**
> （GB 45438-2025 显式标识准确条文：位置 / 字号 ≥ 最短边 5% / 时长 ≥ 2s）。
> 本 CR **不新增**该未确认项，仅沿用其登记。

## 二、为什么需要

1. **法规硬性要求** —— 标识办法 + GB 45438-2025（强制性国标），生效日已过（2025-09-01）。
2. **Phase 3-6 合规审查 B-2 硬阻断**（🔴）—— 「AI 生成内容标识完全未做」。
3. 与 Phase 3-6 的 **B-1**（全自动无真人驱动）**相互独立**：B-2 可**单独**先行修复，不依赖 B-1 路径裁决。

## 三、影响模块

| 文件 | 变更 |
|---|---|
| `frontend/src/components/AiContentLabel.tsx` | **新建**（纯文字标识组件） |
| `frontend/src/App.tsx` | 渲染标识（**直播间画面右上角**） |
| `frontend/tests/` | **新增**用例（组件渲染 / 文字存在 / 页面可见） |
| `docs/development/step4_frontend_component_decision.md` | ⛔ **冻结契约修订**：FCM-2 组件集 **5 → 6**（见 §五） |

**不涉及**：后端、`api/**`、`app/platform/**`、`pipeline.py`、`database/schema.sql`、API 契约、DTO 类型、依赖。

## 四、修改方案

1. **新建 `frontend/src/components/AiContentLabel.tsx`** —— 纯展示组件，**零** store / API / state / 副作用
   （满足 **UB-3**：组件只做展示；**FCM-4**：渲染手段白名单内 = 文本展示 + 基础 `className`）。
2. **在 `App.tsx` 布局中固定位置渲染** —— **直播间画面右上角**（owner q-1 裁决），**全程可见**
   （覆盖「起始画面 + 持续服务过程中」）。
3. **标识文本 = 纯文字「AI生成」**（owner q-2 裁决）；`role="note"` + `aria-label` 提供语义。
4. **`className` 仅为钩子** —— `frontend/` 全仓**无 CSS**，本 CR **不引入**样式方案
   （样式属 FCM「Deferred」项，另行裁决）。

**App.tsx 约束核对**（不破既有冻结）：`App` 保持**零 `useState`、零 API import、零 store setter、
零 fetch、零定时器**（RF-3 / FCM Forbidden）；仅新增一个静态 import + 一处静态渲染。

## 五、契约修订（**受权增量**，owner q-0 裁决）

### K1 —— FCM-2 组件集修订（**本 CR 的唯一冻结契约变更**）

- **现状（FROZEN）**：`step4_frontend_component_decision.md` **FCM-2「Phase 1 Components（冻结）」**
  明文「最小组件集（**不得增删**）」，逐字列出：
  `components/{PetStage.tsx, EventList.tsx, StatusBar.tsx, player/PetPlayer.tsx}`。
- **冲突**：新建 `AiContentLabel.tsx` = **增删组件集** ⇒ **必须**修订 FCM-2。
- **修订口径**：在 FCM-2 清单中**追加** `AiContentLabel.tsx`（组件集 **4 → 5 个文件**，
  含既有受权增量 `EventSimulator.tsx` / `PetSelector.tsx` 则全量为 **`components/` 6 个文件**），
  并补一行职责说明：「AI 生成内容标识（合规展示，纯静态）」。
- **同时登记**：`PROJECT_RULES.md` §十四 **FCM 块内追加 bullet**（**不新增 H3 块**，H2 恒 16 不变）。

### K2 —— 其他边界的影响说明（**不修订，仅登记**）

| 契约 | 是否冲突 | 说明 |
|---|---|---|
| **UB-3（组件只做展示）** | ✅ 不冲突 | 标识组件零 API / 零 store / 零持久化 |
| **UB-4（只消费 `asset_url`）** | ✅ 不冲突 | 标识不使用任何素材地址 |
| **FCM-4（渲染白名单）** | ✅ 不冲突 | 纯文字 + 基础 `className` 在白名单内 |
| **FCM-3（数据流 Store ↓ Component）** | ✅ 不冲突 | 标识无数据消费 |
| **RB-3（全页面唯一媒体消费者）** | ✅ 不冲突 | 标识**不是**媒体元素（非 `<img>` / `<video>`） |
| **RB-5（Scope Freeze）** | ⚠️ 需登记 | RB-5 禁「WebSocket / OBS / Live2D / Canvas / 动画系统 / **AI 素材生成** / 新依赖 / backend / API 契约 / PlaybackState」——**标识不在禁止清单内**；但属**新增展示元素**，按「上述能力引入前须先出对应冻结文档并获授权」的**同口径**处理：**本 CR 即该授权文档** |
| **UB-5（Phase 1 Scope）** | ⚠️ 需登记 | UB-5 列举的实现项未含合规标识 ⇒ 属**受权增量**，由本 CR 授权 |
| **PI-*** | ✅ 不冲突 | 不触播放器事件边界 |

## 六、是否影响 MVP

**是** —— **合规硬前置**。在标识落地前，本项目不具备对外上线条件。

## 七、回滚

```bash
git revert <CR 提交> <契约修订提交> <前端提交> <测试提交>
```

## 八、落地授权记录（owner 裁决）

| # | 裁决点 | 结论 |
|---|---|---|
| **q-0** | 新建组件与冻结 FCM-2 冲突 | **立 CR 修订 FCM-2 后实现**（本 CR 即该修订载体） |
| **q-1** | 标识位置 | **直播间画面角标（右上角）** |
| **q-2** | 标识样式 | **纯文字「AI生成」** |
| **q-3** | 「禁止修改测试」vs「新增用例」 | **允许新增用例**（「禁止修改测试」理解为禁止改动既有用例；新用例为指令第 3 步明文要求） |

## 九、附：隐式标识（**暂不实现，登记待裁**）

文件元数据中的**隐式标识**（`GB 45438-2025`）**本 CR 不实现**，登记为待裁项。
理由：需后端/文件层能力（本轮禁止触碰后端），且属独立技术面。

## 十、建议提交拆分（**待 owner 确认**）

> ⚠️ 指令原定 **3 笔**（CR / 前端 / 测试）；因 **q-0** 已裁决「立 CR **修订 FCM-2**」，
> 冻结契约修订**需要独立可回滚** ⇒ 建议调整为 **4 笔**：

| # | subject（逐字） | 文件 |
|---|---|---|
| 1 | `docs: add CR-4 for AI content labeling` | `docs/change_request/cr-4_ai_content_labeling.md` |
| 2 | `docs: revise FCM-2 for AI content label` | `docs/development/step4_frontend_component_decision.md`（+ `PROJECT_RULES.md` §十四 登记） |
| 3 | `feat: add AI content label for compliance` | `frontend/src/components/AiContentLabel.tsx` · `frontend/src/App.tsx` |
| 4 | `test: cover AI content label` | `frontend/tests/` |

## 十一、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-24 | 首次提出（CR-4 立项；含 FCM-2 修订范围；owner 4 项裁决落地） |
