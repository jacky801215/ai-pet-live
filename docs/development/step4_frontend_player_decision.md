# Step 4.1-E-0 Frontend Player Decision v1.1（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_component_decision.md`（FCM-*）、`step4_frontend_data_flow_decision.md`（FD-*）、
> `step4_frontend_api_client_decision.md`（FC-*）、`step4_frontend_state_decision.md`（FS-*）、
> `docs/development/step4_api_contract_decision.md`（API-2 / `PlaybackState` 冻结契约）
> 编号空间声明：本文档使用 **FP-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* /
> RV-* / RS-* / RF-* 均不复用、不覆盖。
> **与 FCM-4 的关系（必读）**：FCM-4 曾冻结「渲染白名单 = 文本 / 图片 URL / className，
> 禁止视频自建播放器」。本决策在**且仅在** `src/components/player/` 职责范围内**局部修订**该条：
> 允许原生 `<video>`（FP-3）。FCM-4 对其余所有组件（PetStage / EventList / StatusBar / App）继续生效；
> 两处冲突以本文档（更具体的播放器决策）为准。
> 本步**不实现视频播放代码**（实现归 Step 4.1-E-1，待下一条授权）。

## Input

- 指令：Step 4.1-E-0 Frontend Player Boundary Design —— 进入播放器阶段前，只完成播放器边界**设计与冻结**。
- 前置（§一 前置检查，全部通过，无 STOP 条件）：
  - branch = `phase1-step1-foundation`，HEAD = `3608997`，working tree clean
  - `src/components/player/PetPlayer.tsx` 存在
  - 已有播放器实现扫描（剥注释，全 `src/**`）：`<video>` / `<audio>` / `<canvas>` / animation /
    framer-motion / react-player / video.js / three / WebSocket / socket.io —— **全部 0 命中**
  - 依赖核验：package.json 无 framer-motion / react-player / video.js / three / socket.io（禁新增项确认）

## Investigation（只读调查记录，2026-09-20）

### I-1 Playback DTO（冻结契约，禁止新增字段）

`src/types/api.ts` → `PlaybackState`（API-2，6 字段，逐字段与后端一致）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `pet_id` | `string` | 宠物标识 |
| `state` | `string`（仅 "idle" \| "playing"） | 播放状态 |
| `action` | `string \| null` | 当前动作 |
| `asset_url` | `string \| null` | **已解析的对外素材 URL**；无动作时 null |
| `queue_size` | `number` | 动作队列长度 |
| `last_event` | `string \| null` | 最近事件 |

### I-2 当前 PetPlayer（实现现状）

- 位置：`src/components/player/PetPlayer.tsx`；数据来源：`usePetStore((s) => s.playback)` 单切片只读；
- 渲染内容：**纯文本**三行 —— `pet_id` / `state` / `action`（可空显示占位符「—」）；
- 空态：`playback === null` → 「暂无播放内容」（`data-testid="pet-player-empty"`）；
- **缺失**：媒体资源展示区（无 `<video>` / `<img>`）；`asset_url` 目前只被 `PetStage` 以 `<img>` 消费
  （RS-4 / FCM-4 白名单内）。

### I-3 后端 asset_url 实际形态（只记录，不修改 backend）

- 契约示例：`/assets/pets/cat/actions/happy/happy.mp4`
  （即 `/{资源根}/pets/{pet_id}/actions/{action}/{action}.mp4`，由后端解析生成）；
- `asset_url: str | null`，无动作时为 `null`；UI **只消费**、绝不自行拼接素材路径（P3 / UI-6 一致）。

## Decision（裁决总表 FP-1 ~ FP-5）

### FP-1 —— Player Boundary（冻结）

- 播放器**唯一位置**：`src/components/player/PetPlayer.tsx`；
- 职责：**消费 playback snapshot、展示媒体资源、展示状态文本**（pet_id / state / action 沿用现状）；
- **禁止**：API 请求、store 写入、数据转换、业务判断（数据流仍为 `Store ↓ Component`，FCM-3 不变）。

### FP-2 —— Media Source（冻结）

- 媒体输入**唯一**来源：`PlaybackState.asset_url`；
- 规则：`asset_url != null` → 渲染 `<video>`（FP-3）；
- `asset_url === null`：**仅表示无媒体资源；不渲染媒体区域**；保留已有 playback snapshot 文本展示
  （pet_id / state / action）以及既有空态体系；
- **禁止**：自建资源路径、拼接 URL、修改 `asset_url`（UB-4 / P3 不变，只消费）。

### FP-3 —— Playback Technology（冻结）

- 第一版**只使用原生 HTML `<video>`**；
- 允许属性白名单：`src` / `autoplay` / `muted` / `playsInline` / `controls={false}` / `preload`；
  其中 `preload` **仅作为浏览器原生媒体加载属性允许存在**；不代表引入播放器状态管理，
  不允许基于 `preload` 增加业务逻辑；
- **禁止**：第三方播放器（react-player / video.js 等）、canvas、Live2D、动画库、自建播放器状态机
  （配合 FP-4）。

### FP-4 —— State Ownership（冻结）

- 播放器状态来源：**`Store ↓ PetPlayer`**（唯一）；
- **禁止**播放器内部：`useState(playback)`（snapshot 一律来自 store，不得复制进本地 state）、
  新增 `isPlaying` / `currentTime` / `progress` 等 UI state、播放结束回写 store；
- 播放器**不引入**新的事件回调向 store / hook 反向写数据（FD-1 单向流不变）。

### FP-5 —— Scope Freeze（冻结）

本阶段（E-0 / E-1）**不实现**：websocket、polling、自动刷新、播放结束回写、动作队列消费、
Live2D / 动画系统、音量/进度/清晰度控制、全屏。

## 设计验证清单（§五：只做设计验证，不写播放器测试；实现归 E-1）

| 检查项 | 结果 |
|---|---|
| `PlaybackState` 6 字段与契约一致，无新增字段 | ✅ |
| `PetPlayer` 当前无媒体区、无本地 state、无 API 依赖 | ✅（现状即满足 FP-1/FP-4） |
| `asset_url` 可空性与空态路径已定义（FP-2） | ✅ |
| 技术选型无第三方依赖（FP-3 白名单内零新增包） | ✅ |
| E-1 落地项 | PetPlayer 增加媒体区：`asset_url != null` → `<video src autoplay muted playsInline controls={false}>`；保留三行状态文本与空态；`tests/player/` 随实现建立 |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（FP-1 ~ FP-5）；局部修订 FCM-4 于 player 职责范围 |
| v1.1 | 2026-09-20 | 明确媒体区域空态边界；补充 preload 原生属性白名单 |
