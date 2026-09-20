# Step 4.1-C Frontend Skeleton Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-20）。本文裁决 Step 4.1-Boundary 决策（`step4_ui_boundary_decision.md`）
> 遗留的 **D-UB-1 技术选型**，并冻结前端工程骨架；生效后变更须经 Change Request。

## Input

- 指令：Step 4.1-C-1（只做工程骨架与技术选型落地；不做页面 / 不接 API / 不做状态管理）
- 上游冻结：`step4_ui_boundary_decision.md`（UB-1..UB-5）、`step4_api_contract_decision.md`（API-1..4）、
  `step4_api_runtime_decision.md`（DB-*）、`step4_ui_prototype_decision.md`（UI-1..UI-6）
- 后端基线：`5e9a37d`，后端零改动

## Investigation（只读调查，2026-09-20）

| 项 | 结论 |
|---|---|
| frontend 现状 | 仅 6 个 0 字节 `.gitkeep` 占位（src/{api,components,player,stores,types} + tests/），**零代码、零污染** |
| 根级工具约束 | 无根 `package.json` / `.npmrc` / `.nvmrc` / `.node-version`；`.github/workflows/` 不存在 ⇒ **无 CI / 无既有工具链约束** |
| node / npm 可用性 | node v22.22.2（managed，npm 10.9.7）与 v24.18.0（system，npm 11.16.0）均可用；本步以 **22 LTS** 为准 |
| .gitignore | 仓库根已覆盖 `node_modules` 与 `dist` ⇒ 无需新增 frontend/.gitignore |

## Decision（裁决总表 FE-1 ~ FE-4）

| 编号 | 冻结项 | 裁决 |
|---|---|---|
| **FE-1** | 工程框架 | **React 18 + TypeScript + Vite 5**（`jsx: react-jsx`，TS `strict` 全开，`noEmit` + `tsc --noEmit` 参与构建） |
| **FE-2** | 包管理器 | **npm**（依据：仓库无既有工具链 / 无 CI / 无 lockfile 传统；系统自带、不引入第二套工具；`package-lock.json` 入库） |
| **FE-3** | 目录骨架 | 对应 UB-1/2/3（见下）；`src/player/` 占位迁移为 `src/components/player/`（对齐 UB-3 与本表） |
| **FE-4** | Phase 1 禁止项 | 见 Forbidden |

### FE-3 —— 目录骨架（冻结）

```
frontend/
├── index.html            # Vite 入口（FE-3 补充：Vite 必需，指令骨架图的隐含项）
├── package.json
├── package-lock.json     # npm install 产物，必须入库（可复现构建）
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── api/              # UB-1（本步仍为 .gitkeep 占位）
│   ├── components/
│   │   └── player/       # 播放区组件归组（原 src/player/ 迁入）
│   ├── stores/           # UB-2（占位）
│   ├── types/            # DTO 类型归 C-2 落地（占位）
│   ├── App.tsx           # 最小外壳占位（data-phase="skeleton"）
│   ├── main.tsx          # 唯一入口：挂载 App 到 #root
│   └── vite-env.d.ts
└── tests/                # 前端测试归后续 Step（D-UB-3）
```

- 入口文件只含**挂载**与**空外壳**（`App.tsx` 零 UI 结构、零样式方案、零 API / store 接线）。
- `tsconfig.json` 不含项目引用（单文件配置）；`vite.config.ts` 不配 proxy / 环境变量 / mock。

### FE-4 —— Phase 1 禁止项（冻结）

以下内容在 Phase 1 的前端**不得引入**（进入须 Change Request）：

- **axios / fetch 散落在组件或 store**：HTTP 只能收敛在 `src/api/`（UB-1；api 层内部选 fetch 还是
  axios 属 Step 4.1-C-2 裁决，本表禁的是「散落」而非 api 层实现本身）
- **WebSocket**（含 WS 客户端库；对应 UB-5 排除项与 QP-5 的 Phase 2 范畴）
- **router**（单窗口单页，UI-1 = A：无多路由需求）
- **UI framework**（antd / MUI / Bootstrap 等；视觉方案归后续 Step）
- **animation library**（framer-motion / gsap 等；播放由 `<video>` + 后端状态驱动）
- **状态库重复实现**（引入一个状态库后**禁止**再引入第二个，或绕过 store 直连组件）
- **mock server / msw 等**（后端 API 已真实存在，禁止在前端再造假数据层）

## Verification（本步验收记录）

- `npm install` + `npm run build`（`tsc --noEmit && vite build`）→ **exit code 0**（node v22.22.2 / npm 10.9.7）
- 边界检查：`src/**` 与工程配置中 **无** `fetch(` / `axios` / `websocket`（大小写不敏感）/ `/api/` 字符串拼接
- 结构检查：`src/{api,components/{player},stores,types}` 存在；入口仅 `main.tsx` + `App.tsx`
- 后端 / 数据库 / docs 既有冻结文件：**零触碰**

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-09-20 | 首次冻结。裁决 FE-1..FE-4（关闭 D-UB-1）；落地可构建骨架并记录验收。 |
