# CR-5：AI 生成内容标识样式落地

> 变更请求（**第五份正式 CR**）。契约来源：`PROJECT_RULES.md` §七（CR 流程）· §十四（边界登记）。
> 前置：**CR-4**（`docs/change_request/cr-4_ai_content_labeling.md`，已交付 `fce75ef`）
> —— CR-4 只落地了**结构性标识**（文字 + `className` 钩子），**全仓无 CSS ⇒ 无实际视觉标识**。
> 前置法规：`docs/development/phase3_6_ai_live_compliance_audit.md`（**B-2** 显式标识）·
> `docs/development/phase3_6c_ai_implicit_label_research.md`（隐式标识，本 CR 不实现，见 §九）。
> 状态：**草案 · 待 owner 审阅确认**（确认前不实现、不提交）。
> 性质：本 CR **含冻结契约修订**（**FCM-4**）与 **Deferred 项部分纳入**，范围见 §五。

## 一、需求描述

《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号，**2025-09-01 生效**）与
**GB 45438-2025** 要求：显式标识须**显著可见**，并满足**位置 / 字号 / 时长**三项量化口径。

| 项 | 口径（合规文档 §一，**待 U-1 原文复核**） |
|---|---|
| 位置 | 位于**起始画面**；置于画面**边或角** |
| 字号 | **文字高度 ≥ 画面最短边的 5%** |
| 时长 | 视频形态**持续 ≥ 2 秒** |

**现状（CR-4 交付后）**：`AiContentLabel` 组件已就位（纯文字「AI生成」+ `className="ai-content-label"`），
但 `frontend/` **全仓无任何 `.css` 文件**（实测：`frontend/**/*.css` = **0**、`src/**` 内 `style=` 命中 = **0**，
`package.json` dependencies 恰 3）⇒ **`className` 仅为钩子、无样式落地** ⇒
**DOM 顺序上虽排在 `PetStage` 之前，视觉上并非真正的「画面右上角」，也无字号可言**。
即：**B-2 在「结构性存在」层面已修，在「显著可见」层面仍不满足**。

## 二、为什么需要

1. **法规要求是「显著可见」**（位置 + 字号 + 时长三者缺一不可），仅有一个无样式的 `<div>` 不构成合规标识。
2. **CR-4 的明文遗留**：CR-4 §四 第 4 条自己写明「`className` 仅为钩子 …… 本 CR **不引入**样式方案
   （样式属 FCM「Deferred」项，**另行裁决**）」⇒ 本 CR 即该「另行裁决」。
3. **冻结文档把「样式方案」列为 Deferred** ⇒ 任何 CSS 引入都**必须**经 §七 CR 纳入范围，
   不可由实现方自行判定（本项目铁律：任何引入 CSS 的决策须 owner 确认）。

## 三、影响模块

| 文件 | 变更 |
|---|---|
| `frontend/src/styles/ai-content-label.css` | **新建**（唯一样式落地文件） |
| `frontend/src/main.tsx` | **引入**该样式表（副作用 import，应用入口） |
| `frontend/src/App.tsx` | ready 分支新增定位容器 `<div className="live-stage">`，包裹 `AiContentLabel` 与 `PetStage` |
| `frontend/tests/ai-content-label-style/` | **新增**样式契约用例（约 8 例） |
| `docs/development/step4_frontend_component_decision.md` | ⛔ **冻结契约修订**：**FCM-4** + Deferred（见 §五） |
| `PROJECT_RULES.md` | §十四 `Frontend Component` 块同步（**块内就地**：版本指针 + FCM-4 条目） |

**不涉及**：后端、`api/**`、`app/platform/**`、`pipeline.py`、`database/schema.sql`、
API 契约、DTO 类型、`package.json` 依赖（**零新增依赖**）。
**不修改**：`AiContentLabel.tsx`（**保持 CR-4 交付原样** —— 组件仍只带 `className` 钩子、零样式）。

## 四、修改方案

### 4.1 落地手段：**独立样式表 + `className` 钩子**（owner q-0 裁决）

**主方案 = 独立 CSS 文件**（相对 `frontend/src/main.tsx` 的 `./styles/ai-content-label.css`）：

- 组件侧**零改动**：`AiContentLabel.tsx` 仍只输出 `className="ai-content-label"`；
- 样式集中在**一个**新文件内，由**应用入口** `src/main.tsx` 以**副作用 import**（`import "./styles/ai-content-label.css";`
  —— 无 `from`，故不进任何「App import 白名单」守卫）引入；
- **不新增依赖**（Vite 原生支持 CSS，`package.json` 保持恰 3 依赖）；
- 被否决的备选：
  - ❌ **内联样式**（`style={{…}}`）：违反 **FCM-4** 明文禁令，且**必破** CR-4 自有断言
    `expect(code).not.toContain("style=")`；
  - ❌ **CSS-in-JS 库**：触 **RB-5「新依赖」禁令** + `renderBoundary.test.tsx` Case 4 守卫（deps 恰 3）。

### 4.2 量化取值（**owner q-1 / q-2 裁决 + 依据**）

| 项 | 取值 | 依据 |
|---|---|---|
| **位置** | `position: absolute; top: 0; right: 0`（相对定位容器） | 合规「置于画面**边或角**」；owner q-2 = **相对画面容器** |
| **字号** | `font-size: 36px` | owner **q-1** = 最短边 5%；素材固有 **720×1280** ⇒ 最短边 **720** ⇒ 5% = **36px** |
| **持续** | ready 态**全程可见**（恒 ≥ 2s） | 合规「持续 ≥ 2 秒」+ CR-4「仅 ready 态渲染」（owner 裁决） |
| **显著可见性** | `color: #fff` + `background-color: rgba(0,0,0,.5)` + `padding: 0 .2em` | 合规「显著」要求；⚠️ **配色/内边距为 BUDDY 取值**（owner 未逐项指定，如需调整请指示） |
| **定位容器** | `.live-stage { position: relative; width: fit-content; }` | owner **q-2**：`App.tsx` 用 `<div className="live-stage">` 同时包裹标识与画面；`width: fit-content` 使容器**收缩至画面固有宽度**，令 `right: 0` **锚定画面右缘**（否则会锚到父容器/app-shell 右缘） |
| **不遮挡交互** | `pointer-events: none` | 标识为纯展示，不得拦截画面交互（UB-3） |
| **引入点** | `src/main.tsx` | 保持组件「零样式」（FCM-3 / FCM-4）；避免触碰 App 的 import 白名单守卫 |

> ⚠️ **两个前提（须与 owner 共识）**：
> 1. **「画面按固有尺寸呈现」** —— 本文件**不改变**视频尺寸（不设 `max-width` / 不引入缩放），
>    故 720×1280 的固有尺寸成立、36px = 最短边 5% 成立。若后续引入响应式缩放，须**重算并另裁**（见 §九 U-2）。
> 2. **「字号 = 文字高度」的口径** —— 本 CR 按 owner q-1 直接取 `font-size: 36px`；
>    若 U-1 原文复核后「文字高度」须按**字形实测高度**（CJK 约 0.88 em）解释，36px 字号对应约 31.7px 字形高度，
>    **可能需上调**（见 §九 U-1）。

### 4.3 `App.tsx` 约束核对（不破既有冻结）

`App` 仍保持：**零 `useState`、零 API import、零 store setter、零 fetch、零定时器**（RF-3 / FCM Forbidden）；
本次仅新增**一个 `className` 容器**（`div.live-stage`）—— **不新增任何 import**，
故 `tests/runtime/runtime.integration.test.tsx` 与 `tests/hooks/usePetRuntime.test.tsx`
两处 **App import 全等断言无需改动**（实测确认）。

## 五、契约修订（**受权增量**）

### K1 —— FCM-4 渲染边界修订（**本 CR 的唯一冻结契约变更**）

- **现状（FROZEN）**：`step4_frontend_component_decision.md` **FCM-4** 白名单 = 「文本展示 / 图片 URL 展示 /
  基础 `className` / `data-*` 属性」，并明文**禁止**「动画库、canvas、视频标签自建播放器、组件内自建播放状态机、
  **内联样式系统/主题方案**」。
- **冲突**：独立 `.css` 文件**不在**白名单枚举内；且样式方案属本文 **Deferred** 项 ⇒ 必须修订。
- **修订口径**：白名单**增补**「**独立样式表（`.css`，经应用入口引入）+ `className` 钩子**」为
  **受权样式落地手段**（限 **AI 生成内容标识**的最小样式：字号 / 位置 / 显著可见性）。
  **内联样式（`style={{…}}`）/ 主题方案 / CSS-in-JS / 新依赖的禁令逐字不变**。

### K2 —— Deferred 项**部分纳入**

- **现状（Deferred）**：「样式方案 / 主题 / 布局细节（仅 `className` 骨架）」**不在本步裁决**。
- **修订口径**：由本 CR **部分纳入** —— **仅**「AI 标识的最小样式」；「主题 / 布局细节 / 其余样式」**仍 Deferred**。

### K3 —— 其他边界影响说明（**不修订，仅登记**）

| 契约 | 是否冲突 | 说明 |
|---|---|---|
| **FCM-2（组件集）** | ✅ 不冲突 | **不增删组件**（`AiContentLabel` 已由 CR-4 增补）；本次只改 `App.tsx` 的容器 DOM |
| **FCM-3（数据流）** | ✅ 不冲突 | 样式表无数据消费；组件仍零 store 消费 |
| **UB-3（组件只做展示）** | ✅ 不冲突 | 标识仍零 API / 零 store / 零持久化；新增 `pointer-events: none` 反而**避免**拦截交互 |
| **UB-4（只消费 `asset_url`）** | ✅ 不冲突 | 样式表与素材地址无关 |
| **RB-3（唯一媒体消费者）** | ✅ 不冲突 | 未新增任何媒体元素（无 `<img>` / `<video>`，`div.live-stage` 为普通容器） |
| **RB-5（Scope Freeze）** | ⚠️ 需登记 | RB-5 禁「Canvas / 动画系统 / **新依赖** / backend / API 契约 / PlaybackState 字段」——CSS 独立文件**不在禁止清单**（且零新依赖）；属**新增样式落地**，按「引入前须先出对应冻结文档并获授权」的同口径处理：**本 CR 即该授权文档** |
| **UB-5（Phase 1 Scope）** | ⚠️ 需登记 | UB-5 未含合规标识样式 ⇒ 属**受权增量**，由本 CR（承接 CR-4）授权 |
| **FP-3 / PI-\*** | ✅ 不冲突 | 不触播放器属性与事件边界 |
| **AS-1 / API-2 / QP-\*** | ✅ 不冲突 | 不触后端与 API 契约 |

## 六、是否影响 MVP

**是** —— **合规硬前置**的**完成项**。B-2 在「显著可见」层面闭环后，方可进入上线条件评估
（B-1「全自动无真人驱动」仍为独立阻断，见 `phase3_6_ai_live_compliance_audit.md` §七）。

## 七、回滚

```bash
git revert <CR 提交> <契约修订提交> <前端提交> <测试提交>
```

## 八、落地授权记录（owner 裁决，2026-09-24）

| # | 裁决点 | 结论 |
|---|---|---|
| **q-0** | CSS 落地手段（指令建议的内联样式与 FCM-4 冲突） | **独立 CSS 文件**（本 CR 即该授权载体） |
| **q-1** | 字号量化口径（指令示例 64px = 长边 5%，与「最短边」定义矛盾） | **最短边 5% = 36px**（720×1280 ⇒ 720 × 5%） |
| **q-2** | 定位参照系 | **相对画面容器**（`PetStage` 所在区域），非 `position: fixed` 视口定位 |
| **q-3** | 测试改动范围 | **允许新增用例 + 允许同步既有断言/守卫清单** |

## 九、附：待裁 / 未确认项（**本 CR 不解决**）

| # | 项 | 说明 |
|---|---|---|
| **U-1** | GB 45438-2025 显式标识**准确条文** | 承接 `phase3_6_ai_live_compliance_audit.md` U-1（位置 / 字号 / 时长口径原文）。若「文字高度」须按字形实测解释，36px 字号可能需上调（见 §4.2） |
| **U-2** | 「画面最短边 5%」在**响应式缩放**下的重算 | 本 CR 前提 = **画面按固有尺寸（720×1280）呈现**；引入缩放须重算 36px 并另裁 |
| **U-3** | **隐式标识**（文件元数据 `AIGC` 字段） | 承接 `phase3_6c_ai_implicit_label_research.md`；需后端/文件层能力，**本 CR 不实现**（本轮禁止触碰后端） |
| **U-4** | 显著可见性的**配色/内边距** | 本 CR 采用 BUDDY 取值（白字 + 半透明黑底），owner 未逐项指定；如需统一视觉规范请指示 |

## 十、建议提交拆分（**待 owner 确认**）

| # | subject（逐字） | 文件 |
|---|---|---|
| 1 | `docs: add CR-5 for AI content label styling` | `docs/change_request/cr-5_ai_label_style.md` |
| 2 | `docs: revise FCM-4 for AI label styling` | `docs/development/step4_frontend_component_decision.md`（+ `PROJECT_RULES.md` §十四 同步） |
| 3 | `feat: add AI content label stylesheet` | `frontend/src/styles/ai-content-label.css` · `frontend/src/main.tsx` · `frontend/src/App.tsx` |
| 4 | `test: cover AI content label styling` | `frontend/tests/ai-content-label-style/` |

> 说明：**4 笔**与 CR-4 同构（CR / 契约修订 / 实现 / 测试）；冻结契约修订**独立可回滚**（§七）。
> 本次**无需**第 5 笔「同步守卫清单」—— 实测 `App.tsx` **未新增 import**，
> 两处 App import 全等断言与 `components.test.tsx` 的 `COMPONENT_FILES` 均不受影响。

## 十一、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-24 | 首次提出（CR-5 立项；含 FCM-4 修订与 Deferred 部分纳入范围；owner 4 项裁决落地） |
