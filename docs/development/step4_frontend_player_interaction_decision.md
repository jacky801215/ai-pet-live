# Step 4.1-E-3 Frontend Player Interaction Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-20）
> 输入：`step4_frontend_player_decision.md`（FP-*，v1.1）、`step4_frontend_data_flow_decision.md`（FD-*）、
> `step4_frontend_runtime_state_decision.md`（RS-*）、`step4_frontend_refresh_boundary_decision.md`（RF-*）、
> `docs/development/step4_api_contract_decision.md`（API-2 / `PlaybackState` 冻结契约）
> 编号空间声明：本文档使用 **PI-***。已有编号空间 UI-* / UB-* / FE-* / FC-* / FS-* / FCM-* / FD-* /
> RV-* / RS-* / RF-* / FP-* 均不复用、不覆盖。
> 本步**只做播放器交互能力调查与边界冻结，不实现任何新播放行为**（video event / 队列 /
> websocket / animation / 音频 / 全屏 / 控制条全部禁止，落地与否归后续授权步骤）。

## Input

- 指令：Step 4.1-E-3 Frontend Player Interaction Decision —— 进入播放器下一阶段前，
  只完成：播放器交互能力**调查** + 边界**冻结**文档。
- 前置（§一 前置检查，全部通过，无 STOP 条件）：
  - branch = `phase1-step1-foundation`，HEAD = `eb16906`，working tree clean
  - `frontend/src/components/player/PetPlayer.tsx` 存在
  - `frontend/tests/player-runtime/` 存在
  - `docs/development/` 存在
  - 待创建文档 `docs/development/step4_frontend_player_interaction_decision.md` 不存在（无撞车）

## Investigation（只读调查记录，2026-09-20）

### I-1 当前播放器实现（`src/components/player/PetPlayer.tsx`）

当前能力（**允许且仅有**）：`Store playback ↓ PetPlayer ↓ video/text render`：

- 数据来源：`usePetStore((s) => s.playback)` 单切片只读；空态 `playback === null` →
  「暂无播放内容」（`data-testid="pet-player-empty"`）；
- 渲染内容：`asset_url !== null` → 原生 `<video>`（FP-3 属性白名单：src / autoPlay / muted /
  playsInline / controls={false} / **loop**（**CR-1**），`data-testid="pet-player-media"`）+ 三行文本
  （pet_id / state / action，可空显示「—」）；
- **确认不存在**（剥注释全文扫描）：
  - video 事件回调：`onPlay` / `onPause` / `onEnded` / `onTimeUpdate` / `onError` —— **0 命中**
  - 命令式句柄：`ref` / `useRef` —— **0 命中**
  - 本地状态：`useState` / `useEffect` —— **0 命中**
  - 反向写入：`setState` / `refresh` 调用 / API import —— **0 命中**

### I-2 当前 PlaybackState（冻结契约，禁止新增字段）

`src/types/api.ts` → `PlaybackState`（API-2；**CR-1** 起为 **7 字段**，逐字段与后端一致）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `pet_id` | `string` | 宠物标识 |
| `state` | `string`（仅 "idle" \| "playing"） | 播放状态 |
| `action` | `string \| null` | 当前动作 |
| `asset_url` | `string \| null` | 已解析的对外素材 URL；无动作时 null |
| `queue_size` | `number` | 动作队列长度 |
| `last_event` | `string \| null` | 最近事件 |
| `loop` | `boolean` | **CR-1**：当前媒体是否循环（待机 `true`、其余 `false`；只消费、不判断） |

**禁止新增**：`duration` / `progress` / `playingTime` / `videoState` 等任何播放器派生字段
（DTO 归后端契约所有，前端不得「顺手」扩展）。

### I-3 当前数据流（单向，禁止反向）

```
API Client ↓ usePetRuntime(controller) ↓ Zustand Store ↓ PetPlayer ↓ native <video>
```

- 正向链路：`getPlaybackState()` → store setter → `usePetStore((s) => s.playback)` → 渲染
  （FD-1 / FS-* / FCM-3 / FP-4 全部一致）；
- **确认不存在反向流**：`video → store`（无事件回调回写、无 ref 命令式驱动、无组件内 fetch）；
- I-1 扫描结论即反向流的静态证据：0 个事件回调 + 0 个 ref + 0 个 store 写入。

## Decision（裁决总表 PI-1 ~ PI-5）

### PI-1 —— Player Event Boundary（冻结）

第一版播放器**只负责**：

- render media（`<video>` 展示 `asset_url`）；
- render snapshot（pet_id / state / action 文本展示）。

**禁止**：

- 监听 video 生命周期事件（onPlay / onPause / onEnded / onTimeUpdate / onError 等）；
- 修改 store（任何形式的写入，包括播放结束回写）；
- 调用 `refresh()`（刷新归 RF-1 唯一来源 `usePetRuntime()`）；
- 调用 API（组件层零网络请求，FCM-3 / UB-1 不变）。

### PI-2 —— Playback Ownership（冻结）

播放状态**唯一来源**：`PlaybackState`（经 `Store ↓ PetPlayer` 读取，API-2 契约 **7 字段（CR-1）**）。

**禁止新增任何 player state**，包括但不限于：

- `const [playing, setPlaying] = ...`
- `const [progress, setProgress] = ...`
- `duration` / `currentTime` / `playingTime` / `videoState` 等一切派生 UI state
  （FP-4 重申并升级为 PI 命名空间下的硬约束）。

### PI-3 —— Video Event Policy（冻结）

- 当前阶段**不处理**：`onPlay` / `onPause` / `onEnded` / `onError` / `onTimeUpdate`；
- **原因**：等待后续播放模型设计（事件消费方、回写口径、队列驱动方式均未裁决；
  在播放模型冻结前监听事件必然诱发 PI-1/PI-2 禁止的反向写入或影子状态）；
- 本条为**政策性冻结**：不是「永久不做」，而是「播放模型设计完成前不做」；
  后续如需引入，必须先出新的冻结文档修订本条。

### PI-4 —— Control Surface（冻结）

第一版**无任何控制面板**：

- **禁止**：暂停按钮、播放按钮、进度条、音量、全屏、倍速；
- **只展示**：`<video>`（`controls={false}`，FP-3 白名单不变）+ snapshot 文本；
- 浏览器原生 `controls` 属性保持 `false`，不因控制需求回退为 `true`。

### PI-5 —— Scope Freeze（冻结）

本阶段**不实现**：

- websocket、polling、animation、Live2D；
- queue consumer（动作队列消费）、播放结束回写；
- audio（音频）、fullscreen（全屏）、media controller（自定义控制条）。

任何上述能力的引入都必须走新的授权步骤 + 新的冻结文档，禁止「顺手实现」。

## 设计验证清单（本步零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `PlaybackState` 仍为 6 字段，无 duration / progress / playingTime / videoState | ✅ |
| `PetPlayer` 无 video 事件回调 / ref / useState / useEffect（I-1 扫描 0 命中） | ✅ |
| 数据流单向 `API ↓ hook ↓ store ↓ PetPlayer`，无 `video ↓ store` 反向流 | ✅ |
| 现状即满足 PI-1 ~ PI-4（本步无需改代码，只冻结边界） | ✅ |
| 落地项 | 无（边界冻结步；后续步骤若扩展交互，须先修订 PI-1/PI-3） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-20 | 首版冻结（PI-1 ~ PI-5）；调查确认现状即合规，零代码变更 |
