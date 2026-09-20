# Phase 2.1 Render Boundary Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20，Phase 2.1 夜间自主工作指令确认执行）
> 输入：`phase1_completion.md`、`phase2_platform_boundary_decision.md`（PB-*）、
> `phase2_render_boundary_draft.md`（v0.1 提案稿，本版按指令裁决正式冻结）、
> `step4_frontend_component_decision.md`（FCM-*）、`step4_ui_boundary_decision.md`（UB-*）、
> `step4_frontend_player_decision.md`（FP-*）、`step4_frontend_player_interaction_decision.md`（PI-*）
> 编号空间声明：本文档使用 **RB-***（创建前核查：全仓 0 命中，无撞车）。
> 本步同时落地 **双渲染修复**（见 RB-3 实施口径），范围：PetStage 移除 `asset_url` img 消费；
  PlaybackState / API / store / runtime / backend **零触碰**。

## Input

- 指令：Phase 2.1 Autonomous Night Work——正式冻结 Render Boundary；安全条件满足时修复双媒体渲染。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = `28cc012`，working tree clean。
- 调查事实（2026-09-20 审计）：`asset_url !== null` 时 PetStage 渲染 `<img>`（pet-stage-asset）
  **且** PetPlayer 渲染 `<video>`（pet-player-media）——同一素材 URL 双媒体元素并存
  （历史遗留：Stage img 先于 E-1 video 存在）。

## Decision（裁决总表 RB-1 ~ RB-5）

### RB-1 —— Render 层职责（冻结）

- **PetStage 是舞台容器**：只负责 container / layout / 展示形态落点
  （Phase 2 后续的透明背景 / 16:9 / 9:16 适配在此层）与容器级空态；
- **PetPlayer 是唯一媒体渲染点**：`<video>`（FP-3 属性白名单内）+ playback snapshot 文本
  （pet_id / state / action）；
- StatusBar / EventList / EventSimulator 职责不变（非媒体数据展示与交互入口）；
- 页面组合与四态归 App（RS-* 不变）。

### RB-2 —— Asset 消费规则（冻结）

- `asset_url` **只能消费**（UB-4 / UI-6 沿用并强化）；
- **禁止**前端拼接素材路径；
- **禁止**前端判断素材类型（img/video 的选型不由前端猜扩展名；
  未来如需类型区分，须由后端契约提供字段——涉 C4，另行裁决）。

### RB-3 —— 全页面唯一媒体消费者（冻结）

- 全页面**只有 PetPlayer** 负责 video/image 媒体展示；
- **PetStage 不得重复消费 `asset_url`**（实施：删除其 `<img>` 分支与 `asset_url` 读取）；
- `asset_url === null` → 无媒体元素；空态由 PetPlayer 的既有空态（pet-player-empty）表达；
- 实施时同步既有守卫断言（允许 PetStage 无 img 媒体消费；不删除测试用例）。

### RB-4 —— 未来动画扩展入口（冻结）

- 未来任何媒体技术（canvas / Live2D / 动画库）的引入**必须经过 Player 边界**
  （只改 Player 内部渲染分支；PI-5 政策性冻结仍把守：引入前须修订 PI 文档）；
- **Stage 只负责布局**：展示形态（透明背景、尺寸）只在 Stage 层的 className / 布局实现，
  不侵入 Player；
- video 事件入口：PI-3 政策性冻结不变，本决策不开启任何事件监听。

### RB-5 —— Scope Freeze（冻结）

本阶段**禁止**：WebSocket、OBS、Live2D、Canvas、动画系统、AI 素材生成、新依赖、
backend 修改、API 契约修改、PlaybackState 字段修改。
上述能力引入前必须先出对应冻结文档并获授权。

## 设计验证清单

| 检查项 | 结果 |
|---|---|
| 双渲染重叠存在（调查确认） | ✅ → 本步修复 |
| 修复范围恰为 PetStage 移除 img/asset_url 消费 | ✅（PlaybackState/API/store/runtime 零触碰） |
| 既有守卫同步：允许 PetStage 无 img，不删除用例 | ✅（components.test 断言调整 + 新增 render-boundary 套件） |
| 新增 tests/render-boundary/：Case1 唯一消费者 / Case2 Stage 无媒体标签 / Case3 PlaybackState 不变 / Case4 无新依赖 | ✅ |
| FCM-2 组件集 / FP-3 / PI-* / UB-4 均无需放宽 | ✅（RB 是职责细化与收窄） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.1 | 2026-09-20 | 提案稿（Phase 2.1 审计产出，工作区） |
| v1.0 | 2026-09-20 | 正式 FROZEN（RB-1 ~ RB-5）；同批落地双渲染修复 |
