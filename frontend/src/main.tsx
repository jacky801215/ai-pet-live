/**
 * 应用入口（Step 4.1-C-1 骨架）。
 *
 * 仅负责「挂载 App 到 #root」这一件事；路由 / 全局 Provider / 状态接线
 * 均属后续 Step（FE-4：Phase 1 无 router、无全局状态库注入）。
 *
 * **CR-5（受权增量，FCM-4 v1.2）**：全局样式表 `./styles/ai-content-label.css`
 * 在本入口以副作用 import 引入 —— 仅承载 **AI 生成内容标识**的最小样式
 * （字号 / 位置 / 显著可见性）；组件侧保持**零样式**（只输出 `className` 钩子）。
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles/ai-content-label.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root 挂载点不存在（index.html 被改动？）");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
