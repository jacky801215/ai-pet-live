# AI Cat UI Prototype Decision v1.0

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.1-B
> **定位**：Phase 1 AI 猫 UI 第一版的**唯一契约准绳**。UI 实现步（后续）与技术选型必须对齐本文档。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step2_event_schema.md`（v1.1 FROZEN）—— 统一事件四字段
> - `docs/development/step3_interaction_engine_decision.md`（v1.0 FROZEN）—— H1–H7
> - `docs/development/step3_action_engine_decision.md`（v1.0 FROZEN）—— O1–O6
> - `docs/development/step3_playback_decision.md`（v1.0 FROZEN）—— P1–P6
> - `docs/development/step4_playback_data_decision.md`（v1.0 FROZEN）—— D1–D6
> - `PROJECT_RULES.md` §十四（`### 动作指令与动作引擎边界` / `### 播放与素材边界`）
>
> **命名勘误**：本步指令引用的 `docs/system_architecture.md` / `docs/phase1_design.md` **不存在**；
> 实际路径为 `docs/architecture/system_architecture.md`、`docs/development/phase1_design.md`。本文档按后者执行。
>
> **前端现状记录（只记录，不删除）**：`frontend/` **已存在**，为 Step 1 建立的空骨架 ——
> 仅 6 个 `.gitkeep`（`src/api`、`src/components`、`src/player`、`src/stores`、`src/types`、`tests`），
> **零组件代码、零 npm 依赖**（`package.json` / `node_modules` 均不存在）。
> `ui/`、`components/`、`web/` 均不存在。
>
> **本步边界**：只产出本文档（+ 必要的 `PROJECT_RULES.md` 新增小节）。
> **不写一行前端代码**、不建 React/Vue 工程、不接 API、不装依赖、不进入 Step 4.2。

---

## Input

| 输入 | 来源 | 契约 |
|------|------|------|
| 统一事件（4 顶层字段） | `UI → POST /api/events/simulate → Event Gateway` | `step2_event_schema.md` §2.1 |
| 事件白名单 `gift` / `comment` / `like` / `system` | 事件契约 | `step2_event_schema.md` §2.3 |
| 规则 → 动作映射 | `rules.json`（`gift_heart → heart`、`like_dance → happy`、`defaults.gift → heart`） | `step3_interaction_engine_decision.md` H1–H7 |
| 动作状态快照（`state` / `current_action` / `queue_size`） | `GET /api/actions/state` | `phase1_design.md` §4.4 |
| 播放状态快照（`state` / `action` / `asset_url` / `started_at`） | `GET /api/playback/status` | `phase1_design.md` §4.4 |
| 播放完成信号 | 前端 `<video>` `onEnded` → `POST /api/playback/complete`（后端时长超时为兜底） | `phase1_design.md` §4.2；P6 |
| 互动计数 | `GET /api/stats` | `phase1_design.md` §4.4 |
| 动作取值域 | 各宠物 `assets/pets/{pet_type}/config.json` 的 `actions` | 实测：`cat` / `dog` / `panda` 均为 `idle, heart, happy, sad, surprise` |
| 前端目录骨架 | `frontend/src/{api,components,player,stores,types}` | `phase1_design.md` §4.2 |

---

## Output

| 输出 | 消费方 | 说明 |
|------|--------|------|
| 原始互动事件 | 后端 Event Gateway | `POST /api/events/simulate`；**非**统一事件 |
| 播放完成上报 | 后端 Playback API | `POST /api/playback/complete`（`onEnded` 主动路径） |
| 轮询：动作 / 播放状态 | 后端 Action / Playback API | Phase 1 用 HTTP 轮询（**无 WebSocket**） |
| 计数展示数据 | 后端 Stats API | `GET /api/stats` |
| 渲染指令 | 前端 `<video>` | `src = asset_url`（**后端下发，UI 不拼**） |

---

## UI State

### 裁决总表（UI-1 ~ UI-6）

| ID | 问题 | 候选 | **裁决** |
|----|------|------|----------|
| **UI-1** | 猫窗口形态 | A 单窗口桌宠 / B 聊天窗口 + 头像 / C 桌面 Widget | **A：单窗口（猫舞台主视觉 + 状态条 + 互动按钮）** |
| **UI-2** | 第一版组件边界 | 新造 `CatView`/`ChatInput`/`EventDispatcher` / 沿用 `phase1_design` §4.2 | **沿用 `phase1_design.md` §4.2 已冻结组件名**（`PetStage` / `EventSimulator` / `StatusBar` + `player`/`api`/`stores`/`types`） |
| **UI-3** | UI 状态模型 | `{state: idle\|playing\|thinking, action: 枚举, mood}` | **`{state: "idle"\|"playing", action: string\|null, queue_size, counts, last_event}`**；删 `thinking`、删 `mood`、**动作不内建枚举** |
| **UI-4** | 事件产生位置 | UI 直接 `evaluate()` / `execute()` / 经网关 | **经 Event Gateway**：UI 只提交**原始事件**，不构造 `Event` |
| **UI-5** | 动作消费方式 | UI 接收 `PlaybackCommand` / 接收状态快照 | **接收 `PlaybackState` 快照**；UI **不知道** ActionEngine，也不接收进程内指令对象 |
| **UI-6** | 动画资源责任 | UI 自拼 `assets/pets/...` / 后端下发地址 | **`AssetManager → PlaybackManager → 后端 API → UI`**；UI 只消费 `asset_url` |

### UI-1 —— 窗口形态：A 单窗口

**裁决：A —— 单窗口：猫舞台占主视觉，状态与互动按钮同页。**

| 候选 | 排除理由 |
|------|----------|
| **B 聊天窗口 + 猫头像** | Phase 1 验证命题是「一个标准事件能否驱动**完整宠物反馈**」（`step2_event_schema.md` §2.3）。B 把**文本**抬为主视觉、猫降为头像框 ⇒ 动作差异（`heart` / `happy` / `sad`）在小尺寸头像里**不可辨识**，验证命题失效 |
| **C 桌面 Widget 悬浮猫** | 需透明窗口 / 置顶 / 点击穿透等桌面级能力，属**展示形态验证**；`phase1_design.md` §三 明确「OBS 透明背景 / 尺寸适配 → Phase 2」，「多宠物切换 → Phase 2」。Widget 同类，Phase 1 禁止 |

- A 与 `phase1_design.md` §4.2 的既有组件划分（`PetStage` / `EventSimulator` / `StatusBar`）**一一对应**，无需新增组件。
- **澄清**：A 的「桌宠模式」指**单页单窗口**的信息结构（猫为绝对主体），Phase 1 **不**要求窗口置顶 / 透明 / 常驻桌面。
- 红线 **C6**（直播展示须标注 AI 生成内容）在 A 下由 `PetStage` 常驻标识承载（见 Components）。

### UI-3 —— UI 状态模型（冻结）

```ts
type UIState = {
  state: "idle" | "playing";          // 与 ActionEngine 状态机同域，UI 不得自增状态
  action: string | null;             // 当前动作名（取值域来自后端，UI 不内建枚举）
  queue_size: number;                // 来自 GET /api/actions/state
  counts: { events: Record<string, number>; actions: Record<string, number> };  // 来自 GET /api/stats
  last_event: { event_type: string; user_name: string | null } | null;          // 来自 POST /api/events/simulate 响应
};
```

| 建议字段 | 裁决 | 理由 |
|----------|------|------|
| `state: idle \| playing \| **thinking**` | **删除 `thinking`** | 后端状态机**只有** `idle` / `playing`（`step3_action_command_decision.md` C3、P6 冻结，Owner 是 ActionEngine）。UI 发明第三个状态 ⇒ 状态集分裂为两套。「请求中」属**请求态**（`pending` 布尔），与**业务态**分离，**不得**并入 `state` |
| `action: idle \| heart \| happy \| sad \| surprise`（字面枚举） | **改为 `string \| null`，不内建枚举** | 与 `PROJECT_RULES.md` §十四「动作名取值域唯一来源为各宠物 `config.json` 的 `actions` 数组；**禁止**在代码中内建全局动作枚举」同一条原则。UI 侧硬编码 5 个动作 ⇒ 新增动作要改前端（违反验收 A3「新增动作无需改代码」） |
| `mood: number` | **不入第一版** | 后端**无 mood 概念**：无生产者、无契约、无存储（`events` / `interactions` 均无该列）。空字段会被误读为"已实现" |
| （建议未含）`queue_size` / `counts` / `last_event` | **补入** | 三者**后端已冻结提供**（`/api/actions/state`、`/api/stats`、`/api/events/simulate` 响应）。不补则 StatusBar 无数据来源 |

**不变量**：UIState 是**后端状态的投影**，不是独立状态源。任何 UIState 字段必须能在既有 API 响应中找到来源。

---

## Components

### UI-2 —— 组件边界（冻结）

**裁决：沿用 `phase1_design.md` §4.2 已冻结的组件名与目录，不另立新名。**

> 理由：`frontend/src/` 骨架（`api` / `components` / `player` / `stores` / `types`）与 §4.2 的组件划分**已在 Step 1 冻结**。
> 再引入 `CatView` / `StatePanel` / `InteractionBar` 等第二套命名，会让同一职责出现两个名字 —— 与
> 「禁止两套方言」（H2/H3、§十四「禁止引入 `==` / `>=` 等第二套语法」）同类，故**不采纳**。

| 组件 | 目标路径 | 唯一职责 | **禁止** |
|------|----------|----------|----------|
| `PetStage` | `frontend/src/components/PetStage/` | 渲染 `<video>`、消费后端 `asset_url`、上报 `onEnded`、常驻 **AI 生成内容标识**（红线 C6） | 不含业务规则；不拼素材路径；不决定播什么 |
| `EventSimulator` | `frontend/src/components/EventSimulator/` | 产生三类原始事件（礼物 / 评论 / 点赞），**只**调事件 API | **不知道规则与动作**；不含任何阈值判断；不调播放接口 |
| `StatusBar` | `frontend/src/components/StatusBar/` | 展示 `state` / 当前动作 / 计数 | **不修改**状态；不发起事件 |
| `VideoLayer` | `frontend/src/player/` | 视频渲染与播放事件（`onEnded` / `onError`） | 不含业务规则 |
| `api 封装` | `frontend/src/api/` | 统一请求、类型、错误处理（**唯一**知道 HTTP 细节的地方） | 不含 UI 逻辑 |
| `petStore` | `frontend/src/stores/` | 持有 `UIState`（Zustand） | 不判定业务；不内建动作枚举 |
| `types` | `frontend/src/types/` | TS 类型定义 | — |

### 与建议命名的对照（避免歧义）

| 建议名 | 采纳 | 说明 |
|--------|------|------|
| `CatView` | → `PetStage` | 同一职责，采用 §4.2 既有名 |
| `StatePanel` | → `StatusBar` | 同上 |
| `InteractionBar` | → `EventSimulator` | 同上 |
| `ChatInput` | **不采纳** | 属 UI-1 候选 B（聊天形态），已排除。评论内容输入框作为 `EventSimulator` 内部元素存在，**不独立成组件** |
| `EventDispatcher` | **不采纳** | 「怎么发事件」属 `api/` 层职责。再包一层组件会出现**两个地方知道事件怎么发**；`EventSimulator` 直接调用 `api/events` |

**组件边界不变量**：组件**不得**直接调用 `ActionEngine` / `AssetManager` / `Database` / `PlaybackManager`，
也不得直接访问后端 service —— 组件只与 `api/` 层交互。

---

## Event Mapping

### UI-4 —— 事件产生位置（冻结）

```
用户行为（点击 / 输入）
        ↓  UI 本地构造「原始事件」
POST /api/events/simulate
        ↓
Event Gateway.normalize()
        ↓  统一事件（4 顶层字段）
InteractionEngine.evaluate() → ActionCommand
        ↓
ActionEngine.execute() → PlaybackCommand → PlaybackManager
```

**UI 不得直接调用 `evaluate()` / `execute()`。** 事件进入核心业务**只有一条通道**：Event Gateway（`PROJECT_RULES.md` §十四「事件入口边界」）。

### 三类用户行为的请求形态（冻结）

| 用户行为 | `event_type` | 请求 payload（原始事件，允许缺字段） |
|----------|--------------|--------------------------------------|
| 点「送小心心」 | `gift` | `{ "gift_name": "小心心", "gift_count": 1, "platform": "simulator" }` |
| 点「点赞」 | `like` | `{ "like_count": <数量输入>, "platform": "simulator" }` |
| 发送评论 | `comment` | `{ "content": "<输入文本>", "platform": "simulator" }` |

**关键裁决 —— UI 不知道阈值**：点赞数量由**用户输入**决定，UI **不得**预置 `3`、**不得**标注任何阈值提示。
理由：`rules.json` 的 `like_dance` 阈值为 `payload.like_count >= 3`（H7 裁决），这是**规则层知识**。
UI 若内建 `3`，等于把规则搬进前端 —— 违反 UI-4 与 `EventSimulator` 的职责约束（§4.2「不知道规则与动作」）。
**Demo 影响（已知并接受）**：默认单次点赞不触发动作，演示时需输入 `3` 及以上。

### 事件字段的构造边界

| 字段 | 谁负责 | 说明 |
|------|--------|------|
| `event_type` / `payload.*` | **UI（原始事件）** | UI 只提供它知道的 |
| `user_id` | UI 可省 | 缺口由归一化补 `null`（**禁止**补 `"anonymous"` 常量） |
| `user_name` | UI 可省 | 缺口补 `""`；显式 `null` 保留 |
| 顶层 4 字段完整性 | **Event Gateway（唯一构造点）** | **UI 不得**自行拼装统一事件 |

---

## Action Rendering

### UI-5 —— 动作消费方式（冻结）

**裁决：UI 接收「`PlaybackState` 状态快照」，不接收 `PlaybackCommand`。UI 不知道 ActionEngine 的存在。**

```
ActionEngine ──PlaybackCommand──▶ PlaybackManager ──已解析素材──▶ 后端 API ──JSON──▶ UI
                                                                  （asset_url）
UI ──onEnded──▶ POST /api/playback/complete ──▶ PlaybackManager ──▶ ActionEngine.restore_idle(pet_id)
```

**为何不能下发 `PlaybackCommand`（关键）**：
`PlaybackCommand{pet_id, action_type}` 是**进程内指令对象**（P1/D1 冻结），**不含素材地址**。
若把它下发到 UI，UI 就必须自己把 `action_type` 解析成文件路径 ⇒ **直接违反 P3**
（「全项目只有一个路径解析点 = AssetManager」）与 UI-6。
⇒ 跨进程传输形态**必须**是**已解析的状态快照**（含 `asset_url`）。

| 项 | 裁决 |
|----|------|
| UI 读取的状态源 | `GET /api/playback/status`（`{state, action, asset_url, started_at}`）+ `GET /api/actions/state`（`{pet_id, state, current_action, queue_size}`） |
| 状态更新时机 | ① 事件响应即时更新；② 轮询兜底（**≤1s**） |
| 通信方式 | **仅 HTTP REST**（Phase 1）；WebSocket 属 Phase 2，**禁止**提前引入 |
| 播放完成上报 | 前端 `<video>` `onEnded` → `POST /api/playback/complete`（主动路径）；后端时长超时为**兜底**路径 |
| UI 是否判定「该播什么」 | **否** —— 完全由后端规则链决定 |
| UI 是否拥有 `idle`/`playing` | **否** —— 状态 Owner 是 ActionEngine（P6）；UI 只做**投影展示**，收到 `idle` 即停播回落 |

**降级渲染（对齐 P4 / D4 / 红线 C4）**：播放失败 / 素材缺失 / `onError` ⇒ UI 不弹错误阻塞，
回落 standby 画面并保持可交互（"播放失败不得中断系统"）。

### UI-6 —— 动画资源责任（冻结）

**唯一方向（不可逆）**：

```
assets/pets/{pet_type}/actions/{action}/{action}.mp4
        ↑ 唯一解析者
   AssetManager  ──▶  PlaybackManager  ──▶  后端 API（转 asset_url）  ──▶  UI
```

| 项 | 裁决 |
|----|------|
| UI 是否拼路径 | **禁止**。UI 不得出现 `assets/pets/...` 字面量、不得用 `pet_type`/`action` 拼接 URL |
| UI 素材来源 | **只**消费后端下发的 `asset_url` |
| UI 渲染方式 | `<video src={asset_url} />`；不做路径推导、不做存在性判断 |
| 角色名 | UI **不得**硬编码 `cat` / `cat_001`（红线 C3）；宠物信息经 API 获取 |
| 动作列表 | UI **不得**内建枚举；需要时取 `GET /api/actions` |

---

## Boundary

```
┌──────────────────────── 前端（浏览器，TS）────────────────────────┐
│  PetStage / EventSimulator / StatusBar / VideoLayer / petStore   │
│                              │ api/ 层（唯一 HTTP 出口）           │
└──────────────────────────────┼───────────────────────────────────┘
                               │  HTTP + JSON（Phase 1 唯一通道）
┌──────────────────────────────▼───────────────────────────────────┐
│                        后端 API 层（FastAPI）                     │
│  /api/events/simulate   /api/playback/{status,complete,stop}     │
│  /api/actions{,/state}  /api/stats        /assets/* (静态)        │
└──────────────────────────────┬───────────────────────────────────┘
                               │ 进程内调用（UI 不参与）
   EventGateway → InteractionEngine → ActionEngine → PlaybackManager → AssetManager
```

### 跨进程契约清单（UI 可用的全部接口）

| 方法 | 路径 | UI 用途 |
|------|------|---------|
| `POST` | `/api/events/simulate` | 产生原始事件（**唯一**事件入口） |
| `GET` | `/api/playback/status` | 取播放状态 + `asset_url` |
| `POST` | `/api/playback/complete` | 上报播放完成（`onEnded`） |
| `GET` | `/api/actions/state` | 取动作状态（`state` / `current_action` / `queue_size`） |
| `GET` | `/api/actions` | 取动作列表（**不硬编码**） |
| `GET` | `/api/stats` | 取互动计数 |
| `GET` | `/health` | 连通性检查 |

### 边界不变量（冻结）

1. **唯一通道**：UI ⇄ 后端只经 **HTTP + JSON**；Phase 1 **无** WebSocket / SSE。
2. **UI 只发原始事件**：不构造统一事件、不跳过 Event Gateway。
3. **UI 只收状态快照**：不接收 `Event` / `ActionCommand` / `PlaybackCommand` 等**进程内对象**。
4. **UI 不解析素材**：路径解析唯一属 AssetManager（P3）；UI 只消费 `asset_url`。
5. **UI 不拥有业务状态**：`idle` / `playing` Owner 是 ActionEngine（P6）；UI 只投影。
6. **UI 不含规则**：不匹配规则、不判阈值、不决定播什么。

---

## Forbidden

**本 Step（4.1-B）不得**：

- ❌ 创建 React / Vue 工程（不建 `package.json`、不装 npm 依赖）
- ❌ 写组件代码 / CSS / 动画逻辑
- ❌ 接 API、起前端 dev server
- ❌ 创建 `ui/` / `web/` 目录；**不得删除**已存在的 `frontend/` 骨架
- ❌ 修改 `backend/**` / `tests/**` / `database/**` / `rules.json` / 任何既有冻结文档
- ❌ 进入 Step 4.2（DataManager / `events` 表 / `interactions` 表 / DB migration）

**UI 实现步（后续）不得**：

- ❌ 组件直接调用 `ActionEngine` / `AssetManager` / `Database`（须经 `api/` 层）
- ❌ UI 内出现 `assets/pets/...` 路径字面量或拼接（P3 不变量）
- ❌ UI 内硬编码角色名（红线 C3）或动作枚举（§十四）
- ❌ UI 自行构造统一事件 / 绕过 Event Gateway
- ❌ UI 内建规则或阈值判断（如点赞阈值 `3`）
- ❌ UI 自行把动作状态置为 `idle`（状态 Owner 是 ActionEngine）
- ❌ 引入 WebSocket / SSE（Phase 2）
- ❌ 引入 `thinking` / `mood` 等后端不存在的状态字段
- ❌ 播放失败时弹阻塞式错误（红线 C4）

---

## Deferred

| # | 事项 | 挂起原因 | 处理 |
|---|------|----------|------|
| **U1** | `mood`（情绪值） | 后端无生产者 / 无契约 / 无存储 | 需求变更后 |
| **U2** | `thinking` 状态（AI 生成中） | AI 实时生成视频「技术路线未验证」（`phase1_design.md` §三） | 未定 |
| **U3** | 对话式 UI（聊天窗口 + 头像，UI-1 候选 B） | Phase 1 验证命题是宠物反馈可辨识 | Phase 2+ |
| **U4** | 桌面 Widget / 置顶 / 透明背景 | 属展示形态验证 | Phase 2 |
| **U5** | WebSocket / SSE 实时推送 | `phase1_design.md` §三 明确 Phase 2 | Phase 2 |
| **U6** | 多宠物切换 UI | 架构已支持，UI 延后 | Phase 2 |
| **U7** | 音效播放 | Phase 1 明确不实现 | P1 |
| **U8** | 前端类型自动生成（OpenAPI → TS） | Phase 1 接口少，手写成本更低 | Phase 2+ |
| **U9** | `interactions` 统计的 UI 明细视图 | 依赖 Step 4.2 数据层 | Step 4.2 后 |
| **E29** | AssetManager 的 `pet_type` 兼容路径（Step 4.1-A 引入） | 存量测试未迁移到 `pet_id` | 独立清理 Step |
| **C6** | 「AI 生成内容」标识的**具体文案与样式** | 本步只冻结「必须常驻」，形态未定 | UI 实现步 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 UI-1 ~ UI-6；冻结前端组件边界、事件构造边界、动作消费方式与素材地址单向流。 |
