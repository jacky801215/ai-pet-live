/**
 * AiContentLabel —— AI 生成内容标识（**CR-4 授权增量**；FCM-2 v1.1）。
 *
 * 依据：《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号，2025-09-01 生效）
 * 与 GB 45438-2025；指令给定口径为「办法第四条」（视频：起始画面 + 播放周边适当位置；
 * 虚拟场景：起始画面适当位置，可在持续服务过程中适当位置）。
 * ⚠️ **条款号与原文待官方复核**，见 `docs/development/phase3_6_ai_live_compliance_audit.md`
 * 未确认项 U-1；本组件只落地「显著可见的静态文字标识」这一最小合规面。
 *
 * 位置：直播间画面（`PetStage` 所在区域）右上角，随页面 ready 态**全程可见**
 * （同时覆盖「起始画面」与「持续服务过程中」两个场景）。
 *
 * 边界（UB-3 / FCM-1 / FCM-3 / FCM-4）：
 * - 纯展示组件：零 store、零 API、零 state、零副作用、零网络、零持久化、零计时器；
 * - 渲染手段 = **文本展示 + 基础 `className` / 语义属性**（FCM-4 白名单内）；
 * - **不引入样式方案**（`frontend/` 全仓无 CSS；样式属 FCM 文档的 Deferred 项，另行裁决）
 *   ⇒ `className` 仅为后续样式钩子，当前无样式落地。
 */

/** AI 生成内容标识（纯静态文本，无条件渲染）。 */
export function AiContentLabel() {
  return (
    <div className="ai-content-label" role="note" aria-label="AI生成内容标识">
      AI生成
    </div>
  );
}

export default AiContentLabel;
