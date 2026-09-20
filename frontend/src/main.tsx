/**
 * 应用入口（Step 4.1-C-1 骨架）。
 *
 * 仅负责「挂载 App 到 #root」这一件事；路由 / 全局 Provider / 状态接线
 * 均属后续 Step（FE-4：Phase 1 无 router、无全局状态库注入）。
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root 挂载点不存在（index.html 被改动？）");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
