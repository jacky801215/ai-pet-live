import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Phase 1（Step 4.1-C-1 骨架）：无 proxy、无环境变量注入、无 mock —— API 对接
// 归 Step 4.1-C-2（UB-1：HTTP 层收敛在 src/api/）。本配置刻意保持最小面。
export default defineConfig({
  plugins: [react()],
});
