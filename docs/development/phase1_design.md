# AI Pet Live — Phase 1 设计文档

**版本**: v0.1  
**日期**: 2026-09-19  
**作者**: Q仔  
**阶段**: Phase 1 本地互动 Demo（设计阶段，未编码）  
**上游文档**: `docs/architecture/system_architecture.md` v0.2 · `docs/development/development_plan.md` v0.2

---

## 一、Phase 1 目标

### 核心验证命题

> **一个标准事件，是否可以驱动一次完整的宠物反馈。**

这是整个项目最小、最关键的假设。若此假设不成立，后续的平台接入、商业化均无从谈起。

### 最终 Demo 效果

```
点击模拟礼物
    ↓
生成标准事件
    ↓
规则匹配
    ↓
选择动作
    ↓
播放 MP4 动画
    ↓
恢复 idle
```

### 本阶段不验证的内容

| 不验证 | 原因 |
|--------|------|
| 真实平台事件 | 属 Phase 3/4 |
| 直播画面输出 | 属 Phase 2 |
| 多人并发 | 无真实流量 |
| 玩法趣味性 | 需真人主观评价，属 Phase 1 尾部 |

### 完成态定义

一个能在本地运行、可点击三类事件按钮、能看到宠物响应动画、能查看互动计数的完整闭环。

---

## 二、模块实现范围

### 设计缺口说明（重要）

原始需求列出 6 个模块，**缺少 Asset Manager**。

但 Playback Manager 需要将 `action: heart` 解析为 `assets/pets/cat/actions/heart/heart.mp4`。若由播放层自行拼路径，则需要知道 `pet_type`，直接违反红线 **C3（禁止硬编码角色名）**。

> **决策**：将 Asset Manager 作为 Phase 1 **支撑模块**纳入实现范围，但不作为主链路的一环（无独立业务规则，仅提供路径解析与配置加载）。

---

### 2.1 Event Simulator

| 项 | 内容 |
|----|------|
| **职责** | 模拟 gift / comment / like 三类用户行为，输出标准事件 |
| **边界** | 只产生事件，不关心规则，不碰播放 |
| **输入** | 前端请求参数（event_type、可选 payload） |
| **输出** | 标准事件对象（符合统一格式） |
| **依赖** | PlatformAdapter 抽象接口 |

**模拟事件类型**：

| event_type | payload 字段 | 示例值 |
|------------|--------------|--------|
| `gift` | gift_name, gift_count | 小心心 × 1 |
| `comment` | content | "好可爱" |
| `like` | like_count | 5 |

**实现要点**：
- 实现 `PlatformAdapter` 接口（与未来抖音适配器平级）
- `get_platform_name()` 返回 `"simulator"`
- 不产生随机性行为（可复现，便于测试）

---

### 2.2 Event Gateway

| 项 | 内容 |
|----|------|
| **职责** | 接收事件 → 校验格式 → 转发事件 |
| **边界** | 只做格式归一化与校验，不做业务判断 |
| **输入** | 原始事件（各来源可能有差异） |
| **输出** | 统一格式事件，转发给 Interaction Engine |
| **依赖** | 无 |

**统一事件格式**：

```json
{
    "event_type": "gift",
    "user_id": "sim_user_001",
    "user_name": "模拟观众",
    "payload": {
        "gift_name": "小心心",
        "gift_count": 1,
        "platform": "simulator"
    },
    "timestamp": "2026-09-19T12:00:00Z"
}
```

**校验规则**：

| 校验项 | 规则 | 校验失败处理 |
|--------|------|--------------|
| event_type 存在 | 必填，且在白名单内 | 拒绝 + 记录日志 |
| user_id | 可空，默认 `anonymous` | 补默认值 |
| payload | 可空，默认 `{}` | 补默认值 |
| timestamp | 缺失则补当前时间 | 自动补全 |

**白名单**：`gift` / `comment` / `like`（Phase 1 不含 follow）

**设计要点**：
- 网关是平台层与业务层的**唯一通道**
- 核心业务只认识统一格式，不认识任何平台

---

### 2.3 Interaction Engine

| 项 | 内容 |
|----|------|
| **职责** | 事件规则匹配，输出目标动作 |
| **边界** | 只决定"该播什么"，不负责"怎么播" |
| **输入** | 统一事件 |
| **输出** | 动作指令（action_command）或 None |
| **依赖** | rules.json 规则配置 |

**规则映射（Phase 1 初始规则）**：

| 事件 | 匹配条件 | 目标动作 |
|------|----------|----------|
| gift | gift_name = "小心心" | `heart` |
| gift | gift_name = "火箭" | `special` |
| gift | 其他礼物 | `heart`（默认礼物动作） |
| comment | content 含 "跳舞" | `dance` |
| comment | content 含 "生气" | `angry` |
| comment | 其他评论 | 不触发（返回 None） |
| like | like_count >= 3 | `dance` |
| like | like_count < 3 | 不触发（返回 None） |

**规则配置格式（rules.json）**：

```json
{
    "version": "1.0",
    "rules": [
        {
            "id": "gift_heart",
            "event_type": "gift",
            "match": { "field": "payload.gift_name", "op": "eq", "value": "小心心" },
            "action": "heart",
            "priority": 50
        },
        {
            "id": "comment_dance",
            "event_type": "comment",
            "match": { "field": "payload.content", "op": "contains", "value": "跳舞" },
            "action": "dance",
            "priority": 50
        }
    ],
    "defaults": {
        "gift": "heart"
    }
}
```

**支持的操作符**：`eq` / `contains` / `gte` / `lte`

**动作优先级**：

| 优先级 | 动作 | 说明 |
|--------|------|------|
| 90 | special | 大额礼物，可抢占 |
| 50 | heart / dance / angry | 常规互动 |
| 10 | idle | 默认状态 |

**设计要点**：
- 规则全部来自配置文件，**禁止在代码中硬编码匹配逻辑**
- 未命中规则返回 `None`，不抛异常
- rules.json 解析失败时使用内置空规则 + 告警日志，**不影响启动**

---

### 2.4 Action Engine

| 项 | 内容 |
|----|------|
| **职责** | 动作状态管理（idle / playing / return_idle） |
| **边界** | 管理状态与队列，不直接操作视频 |
| **输入** | 动作指令 |
| **输出** | 状态变更 + 播放请求 |
| **依赖** | Asset Manager（校验动作存在性） |

**状态机**：

```
        触发动作
   [idle] ─────────→ [playing]
     ▲                   │
     │                   │ 播放完成
     │                   ▼
     └──────────── [return_idle]
                       │
                       └──→ 回到 [idle]
```

**状态定义**：

| 状态 | 含义 | 允许的转移 |
|------|------|------------|
| `idle` | 待机中，可接受新动作 | → playing |
| `playing` | 动作播放中 | → return_idle（完成） / → playing（高优先级抢占） |
| `return_idle` | 正在恢复待机 | → idle |

**抢占规则（Phase 1 简化）**：

| 场景 | 处理 |
|------|------|
| 当前 idle，新动作到达 | 直接播放 |
| 当前 playing，新动作优先级更高 | 停止当前，播放新动作 |
| 当前 playing，新动作优先级相同或更低 | 入队（队列上限 3，满则丢弃） |
| 队列中有动作，当前播放完成 | 取队首播放 |
| 队列为空，播放完成 | 回 idle |

**动作存在性校验**：
- 触发前向 Asset Manager 校验动作素材是否存在
- 不存在 → 降级为 `idle`，记录 warn 日志，**不抛异常**

---

### 2.5 Playback Manager

| 项 | 内容 |
|----|------|
| **职责** | 播放 MP4 动画，管理播放状态 |
| **边界** | 只负责播放与回调，不决定播什么 |
| **输入** | 素材路径 + 播放指令 |
| **输出** | 播放状态 + 完成回调 |
| **依赖** | Asset Manager |

**播放流程**：

```
收到播放指令
    ↓
向 Asset Manager 请求素材路径
    ↓
路径为空？──是──→ 记录 error 日志 → 回调返回 idle
    │否
    ▼
下发播放命令（前端执行）
    ↓
等待播放完成（前端上报 或 时长超时）
    ↓
触发完成回调 → Action Engine 回 idle
```

**异常处理矩阵**：

| 异常 | 处理 | 影响主流程 |
|------|------|------------|
| 素材文件不存在 | 记 error 日志，降级 idle | 否 |
| 素材路径非法 | 记 error 日志，降级 idle | 否 |
| 前端播放失败 | 前端上报，降级 idle | 否 |
| 播放超时（超过视频时长 + 3s） | 强制结束，回 idle | 否 |
| 音效加载失败（Phase 1 无音效） | 忽略 | 否 |

> **核心原则**：播放失败**不能导致系统停止**（红线 C4）。

---

### 2.6 Data Manager

| 项 | 内容 |
|----|------|
| **职责** | 记录事件次数、动作次数 |
| **边界** | 只写不管播放，异步非阻塞 |
| **输入** | 事件 / 动作记录请求 |
| **输出** | 统计数据查询结果 |
| **依赖** | SQLite |

**记录内容**：

| 记录项 | 时机 | 维度 |
|--------|------|------|
| 事件记录 | 网关接收事件后 | 明细（每次一条） |
| 事件计数 | 同上 | 聚合（按 event_type） |
| 动作计数 | 动作成功触发后 | 聚合（按 action_name） |

**设计要点**：
- 写库失败**不影响播放主流程**（try/except 包裹 + error 日志）
- 统计查询走聚合表，避免全表扫描

---

### 2.7 Asset Manager（支撑模块）

| 项 | 内容 |
|----|------|
| **职责** | 素材路径解析、宠物配置加载、存在性校验 |
| **边界** | 只读，不产生副作用 |
| **输入** | pet_type / action / resource_type |
| **输出** | 素材相对路径 或 None |
| **依赖** | 文件系统 + config.json |

**路径解析规则**：

```
assets/pets/{pet_type}/actions/{action}/{action}.mp4
assets/pets/{pet_type}/sounds/{name}.mp3
assets/pets/{pet_type}/images/{name}.png
```

**配置加载**：
- 扫描 `assets/pets/*/config.json`
- 缓存于内存，启动时加载一次
- 提供按 `pet_id` / `pet_type` 查询

**硬约束**：
- **禁止**任何模块出现 `"cat"` 字面量（红线 C3）
- 所有角色信息通过 config.json 或 API 参数传入

---

## 三、暂不实现列表

以下内容在 Phase 1 **明确禁止实现**：

| 项 | 归属阶段 | 禁止原因 |
|----|----------|----------|
| 抖音 SDK 接入 | Phase 4 | 需授权，Phase 3 才调研 |
| YY / Bilibili 接入 | Phase 4 | 同上 |
| WebSocket | Phase 2 | Phase 1 用 HTTP 轮询足够 |
| OBS 透明背景 / 尺寸适配 | Phase 2 | 属展示形态验证 |
| AI 实时生成视频 | 未定 | 技术路线未验证 |
| 用户系统 / 登录 | 未定 | 与核心假设无关 |
| 商城 / 打赏 | 未定 | 商业化属 Phase 3 |
| 音效播放 | P1 | 非核心验证项 |
| 多宠物切换 | Phase 2 | 架构已支持，UI 延后 |
| 数据统计后台 | 未定 | 无数据量 |

**执行纪律**：Phase 1 编码期间，任何上述功能的实现请求都应拒绝并记录为待办。

---

## 四、技术实现方案

> **结构修订说明（Step 1 实施后）**
>
> 本节原设计采用「按架构层划分」（platform / gateway / engine / playback / assets / data）。
> Step 1 实施时调整为**按职责分层**：`core` / `models` / `repositories` / `services` / `api` / `config`。
>
> 调整理由：
> 1. 符合本项目实际规模，避免 Step 1 就建立 6 个空目录
> 2. 架构层语义保留在**类名与模块名**中（如 `event_gateway.py` 仍归 `services/`）
> 3. 与后续 Step 2~5 的模块归属清晰：所有业务逻辑进 `services/`，数据访问进 `repositories/`
>
> 实际文件清单以 `docs/development/step1_completion.md` 为准。

### 4.1 Backend 模块划分（Step 1 实施结构）

```
backend/
├── requirements.txt                 # 依赖声明
├── pytest.ini                       # pytest 配置
├── scripts/
│   └── init_assets.py               # 资产元数据初始化脚本
└── app/
    ├── core/                        # 基础设施（无业务逻辑）
    │   ├── constants.py             # 全局常量（路径 / 动作 / 错误码）
    │   ├── exceptions.py            # 业务异常（4 类，带稳定 code）
    │   └── logging_config.py        # 统一日志（禁止 print）
    ├── config/
    │   └── settings.py              # 运行时配置（读 .env）
    ├── models/                      # 数据结构（无 IO）
    │   └── asset.py                 # AssetRecord / AssetMetadata
    ├── repositories/                # 数据访问层
    │   ├── db.py                    # SQLite 连接与初始化
    │   └── asset_repository.py      # assets 表 DAO
    ├── services/                    # 业务逻辑层
    │   └── asset_manager.py         # 【Step1】Asset Manager
    └── api/                         # API 路由（Step 4 填充，当前为空）
```

**后续 Step 的模块归属**（统一放入 `services/`）：

| Step | 模块 | 归属路径 | 架构层语义 |
|------|------|----------|------------|
| 2 | EventGateway | `services/event_gateway.py` | 【2】事件网关层 |
| 2 | SimulatorAdapter | `services/platform/simulator_adapter.py` | 【1】平台接入层 |
| 3 | InteractionEngine | `services/interaction_engine.py` | 【3】互动引擎 |
| 3 | ActionEngine | `services/action_engine.py` | 【4】动作系统 |
| 4 | PlaybackManager | `services/playback_manager.py` | 【5】播放控制层 |
| 4 | DataManager | `services/data_manager.py` | 【7】数据层 |
| 4 | API 路由 | `api/*.py` | — |
| 4 | 规则配置 | `services/rules.json` | — |

**模块装配顺序（main.py 启动时）**：

```
加载配置 → 初始化日志 → 初始化 DB → 加载 AssetManager
   → 加载 rules.json → 实例化各 Manager → 注册 SimulatorAdapter
   → 装配 EventGateway → 挂载 API 路由
```

**约束**：
- 单文件 ≤ 300 行（PROJECT_RULES 第一条）
- 所有日志走 `logging`，禁止 `print`
- 敏感配置走 `.env`，禁止硬编码

---

### 4.2 Frontend 组件划分（Step 1 实施结构）

> Step 1 只建目录骨架，**不含任何组件代码**（指令明确禁止前端动画逻辑）。
> 目录划分与设计一致，仅 `hooks/` 与 `services/` 合并进 `api/`。

```
frontend/
├── src/
│   ├── api/                       # API 封装（Step 5 填充）
│   ├── components/                # UI 组件（Step 5 填充）
│   ├── player/                    # 播放器（Step 5 填充）
│   ├── stores/                    # 状态管理（Step 5 填充）
│   └── types/                     # TS 类型定义（Step 5 填充）
└── tests/                         # 前端测试（Step 5 填充）
```

**Step 5 填充计划**：

| 组件 | 目标路径 | 职责 |
|------|----------|------|
| PetStage | `components/PetStage/` | 宠物展示容器 + MP4 渲染 + 播放完成上报 |
| EventSimulator | `components/EventSimulator/` | 三类事件按钮（只调 Event API） |
| StatusBar | `components/StatusBar/` | 状态 + 计数展示 |
| api 封装 | `api/index.ts` | 统一请求与错误处理 |
| 状态管理 | `stores/petStore.ts` | Zustand：当前状态 / 计数 |
| 类型定义 | `types/index.ts` | TS 类型 |
| 播放器 | `player/VideoLayer.tsx` | 视频渲染与播放事件 |

**组件职责边界**：

| 组件 | 职责 | 禁止 |
|------|------|------|
| `PetStage` | 渲染宠物、播放视频、上报播放完成 | 不含业务规则 |
| `EventSimulator` | 产生事件、调用 Event API | **不知道规则与动作** |
| `StatusBar` | 展示状态与计数 | 不修改状态 |

**关键设计**：`EventSimulator` **只调用 Event API**，不直接调用播放接口。这是保证"按钮 ≠ 播放逻辑"的关键。

**播放完成如何回传**（Phase 1 简化方案）：

| 方案 | 说明 | 选择 |
|------|------|------|
| A. 前端 onEnded 上报 | 主动调用 `POST /api/playback/complete` | ✅ 采用 |
| B. 后端按时长超时 | 后端按视频时长推算 | 兜底 |

采用 A + B 双保险：前端 `onEnded` 上报为主动路径，后端超时为兜底路径。

---

### 4.3 数据库表结构（SQLite）

文件位置：`data/pet_live.db`（运行时生成）

#### events 表 — 事件明细
| 字段 | 类型 | 约束 | 用途 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 主键 |
| event_type | TEXT | NOT NULL | gift / comment / like |
| user_id | TEXT | | 用户标识 |
| user_name | TEXT | | 用户昵称 |
| pet_id | TEXT | | 目标宠物 |
| action_name | TEXT | | 匹配到的动作（未命中为空） |
| platform | TEXT | | 来源平台（simulator） |
| payload | TEXT | | 原始数据 JSON |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 发生时间 |

索引：`idx_events_type(event_type)`、`idx_events_time(created_at)`

#### interactions 表 — 聚合计数
| 字段 | 类型 | 约束 | 用途 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 主键 |
| stat_type | TEXT | NOT NULL | `event` 或 `action` |
| stat_key | TEXT | NOT NULL | 事件类型 或 动作名 |
| pet_id | TEXT | | 宠物（预留多角色） |
| count | INTEGER | DEFAULT 0 | 累计次数 |
| last_time | TIMESTAMP | | 最近一次时间 |

唯一约束：`UNIQUE(stat_type, stat_key)`

#### pets 表 — 宠物角色（Phase 1 建表，从 config.json 同步）
| 字段 | 类型 | 用途 |
|------|------|------|
| pet_id | TEXT PK | 宠物唯一标识 |
| pet_type | TEXT | 角色类型 |
| name | TEXT | 展示名 |
| config_path | TEXT | 配置文件路径 |
| room_id | TEXT | 直播间（预留） |
| created_at | TIMESTAMP | 创建时间 |

#### actions 表 — 动作定义（Phase 1 建表，从 rules.json / 目录扫描同步）
| 字段 | 类型 | 用途 |
|------|------|------|
| action_id | INTEGER PK | 主键 |
| pet_type | TEXT | 角色类型 |
| action_name | TEXT | 动作名 |
| asset_path | TEXT | 素材相对路径 |
| priority | INTEGER | 优先级 |
| created_at | TIMESTAMP | 创建时间 |

> `users` 表 Phase 1 暂不创建（无用户系统需求），已在架构文档中预留 DDL。

---

### 4.4 接口定义

#### Event API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/events/simulate` | 模拟产生一个标准事件并注入网关 |
| `GET` | `/api/events/recent` | 查询最近事件（默认 20 条） |

**POST /api/events/simulate**

请求：
```json
{
    "event_type": "gift",
    "user_name": "模拟观众",
    "payload": { "gift_name": "小心心", "gift_count": 1 }
}
```

响应：
```json
{
    "status": "ok",
    "event": {
        "event_type": "gift",
        "matched_action": "heart",
        "state": "playing"
    }
}
```

异常响应：
```json
{
    "status": "rejected",
    "reason": "unknown event_type: xxx"
}
```

#### Action API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/actions` | 获取动作列表（可按 pet_type 过滤） |
| `GET` | `/api/actions/state` | 获取当前动作状态 |

**GET /api/actions/state**

响应：
```json
{
    "pet_id": "cat_001",
    "state": "idle",
    "current_action": null,
    "queue_size": 0
}
```

#### Playback API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/playback/status` | 当前播放状态 + 素材地址 |
| `POST` | `/api/playback/complete` | 前端上报播放完成 |
| `POST` | `/api/playback/stop` | 手动停止（调试用） |

**GET /api/playback/status**

响应：
```json
{
    "state": "playing",
    "action": "heart",
    "asset_url": "/assets/pets/cat/actions/heart/heart.mp4",
    "started_at": "2026-09-19T12:00:00Z"
}
```

#### Stats API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/stats` | 获取互动统计 |

响应：
```json
{
    "events": { "gift": 5, "comment": 3, "like": 2 },
    "actions": { "heart": 5, "dance": 2 },
    "total": 10
}
```

#### Health API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |

---

## 五、目录规划

> **实施修订（Step 1 完成后）**
>
> Step 1 实际的 45 个文件清单见 `docs/development/step1_completion.md`。
>
> 下方目录树为**原始规划**，实际实施有两处差异：
> 1. **Backend 分层调整**：采用 `core / models / repositories / services / api / config`，
>    而非 `platform / gateway / engine / playback / assets / data`（详见 4.1 修订说明）
> 2. **动作名以 Step 1 指令为准**：`idle / heart / happy / sad / surprise`
>    （原规划为 `idle / heart / dance / angry / special`）
> 3. `main.py` 与 FastAPI API 层推迟到 Step 4（Step 1 不实现 API）
>
> 树中 ✅ 已存在，🆕 为**待建**（Step 1 部分已实际落地，其余属 Step 2~5）。

### 标记说明
- 🆕 待建文件
- 📁 目录
- ✅ 已存在（Step 1 已落地）

```
D:\AI-Pet-Live\
├── PROJECT_RULES.md                                    ✅
├── README.md                                           ✅
├── architecture.md                                     ✅（已废弃）
├── development_plan.md                                 ✅（已废弃）
│
├── backend/                                            📁
│   ├── requirements.txt                                🆕
│   ├── main.py                                         🆕
│   └── app/                                            📁
│       ├── __init__.py                                 🆕
│       ├── config/
│       │   ├── __init__.py                             🆕
│       │   ├── settings.py                             🆕
│       │   └── logging_config.py                       🆕
│       ├── platform/                                   📁
│       │   ├── __init__.py                             🆕
│       │   ├── base.py                                 🆕
│       │   └── simulator_adapter.py                    🆕
│       ├── gateway/                                    📁
│       │   ├── __init__.py                             🆕
│       │   ├── event_schema.py                         🆕
│       │   └── event_gateway.py                        🆕
│       ├── engine/                                     📁
│       │   ├── __init__.py                             🆕
│       │   ├── rule_loader.py                          🆕
│       │   ├── interaction_engine.py                   🆕
│       │   ├── action_engine.py                        🆕
│       │   └── rules.json                              🆕
│       ├── playback/                                   📁
│       │   ├── __init__.py                             🆕
│       │   └── playback_manager.py                     🆕
│       ├── assets/                                     📁
│       │   ├── __init__.py                             🆕
│       │   └── asset_manager.py                        🆕
│       ├── data/                                       📁
│       │   ├── __init__.py                             🆕
│       │   ├── db.py                                   🆕
│       │   ├── schema.sql                              🆕
│       │   └── data_manager.py                         🆕
│       ├── api/                                        📁
│       │   ├── __init__.py                             🆕
│       │   ├── health_api.py                           🆕
│       │   ├── event_api.py                            🆕
│       │   ├── action_api.py                           🆕
│       │   └── playback_api.py                         🆕
│       └── models/                                     📁
│           ├── __init__.py                             🆕
│           ├── event_models.py                         🆕
│           └── action_models.py                        🆕
│
├── backend/tests/                                      📁
│   ├── __init__.py                                     🆕
│   ├── unit/                                           📁
│   │   ├── test_event_gateway.py                       🆕
│   │   ├── test_interaction_engine.py                  🆕
│   │   ├── test_action_engine.py                       🆕
│   │   ├── test_asset_manager.py                       🆕
│   │   └── test_data_manager.py                        🆕
│   └── integration/
│       └── test_event_flow.py                          🆕
│
├── frontend/                                           📁
│   ├── package.json                                    🆕
│   ├── vite.config.ts                                  🆕
│   ├── tsconfig.json                                   🆕
│   ├── index.html                                      🆕
│   └── src/
│       ├── main.tsx                                    🆕
│       ├── App.tsx                                     🆕
│       ├── index.css                                   🆕
│       ├── components/
│       │   ├── PetStage/
│       │   │   ├── index.tsx                           🆕
│       │   │   └── VideoLayer.tsx                      🆕
│       │   ├── EventSimulator/
│       │   │   ├── index.tsx                           🆕
│       │   │   └── EventButton.tsx                     🆕
│       │   └── StatusBar/
│       │       └── index.tsx                           🆕
│       ├── hooks/
│       │   ├── usePlayback.ts                          🆕
│       │   └── useStats.ts                             🆕
│       ├── services/
│       │   └── api.ts                                  🆕
│       ├── stores/
│       │   └── petStore.ts                             🆕
│       └── types/
│           └── index.ts                                🆕
│
├── data/                                               📁
│   └── pet_live.db                                     🆕（运行时生成）
│
├── assets/pets/                                        ✅（结构已就绪）
│   └── cat/
│       ├── actions/
│       │   ├── idle/idle.mp4                           🆕（素材待补）
│       │   ├── heart/heart.mp4                         🆕（素材待补）
│       │   ├── dance/dance.mp4                         🆕（素材待补）
│       │   ├── angry/angry.mp4                         🆕（素材待补）
│       │   └── special/special.mp4                     🆕（素材待补）
│       ├── sounds/                                     ✅
│       ├── images/                                     ✅
│       └── config.json                                 ✅
│
└── docs/development/
    └── phase1_design.md                                🆕（本文件）
```

### 文件统计

| 类别 | 数量 |
|------|------|
| 后端 Python 文件 | 24 |
| 后端测试文件 | 6 |
| 前端 TS/TSX 文件 | 16 |
| 配置文件 | 8 |
| 素材文件（待补） | 5 |
| **合计新增** | **约 59 个** |

---

## 六、验收标准

### 6.1 功能验收

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| F1 | 事件生成 | 点击"送礼物"能产生标准事件，格式合规 |
| F2 | 规则匹配 | `gift_heart` 正确匹配到 `heart` 动作 |
| F3 | 动作播放 | 播放 `heart.mp4`，画面正确显示 |
| F4 | 状态恢复 | 播放完成后自动回到 `idle` |
| F5 | 待机循环 | `idle.mp4` 循环播放不间断 |
| F6 | 三类事件 | gift / comment / like 均可驱动动作 |
| F7 | 计数正确 | 事件次数、动作次数准确累计 |
| F8 | 规则可配 | 修改 rules.json 重启后，动作映射同步改变（无需改代码） |
| F9 | 角色可扩展 | 复制 cat 目录为 dog 并改 config.json，无需改代码即可识别 |

### 6.2 性能验收

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| P1 | 响应延迟 | 点击到画面变化 < 300ms（本地环境） |
| P2 | 连续触发 | 连续点击 50 次不卡顿、不丢事件 |
| P3 | 内存稳定 | 连续运行 30 分钟，内存无持续增长 |
| P4 | 待机无抖动 | idle 循环 10 分钟无中断、无跳帧 |

### 6.3 异常处理验收

| 编号 | 场景 | 期望行为 |
|------|------|----------|
| E1 | 事件类型不存在 | **系统不崩溃**，返回 `rejected`，记录日志，保持 idle |
| E2 | 事件类型合法但无规则匹配 | 返回成功但不触发动作，保持 idle |
| E3 | 动作素材缺失 | 降级 idle，记录 error 日志，**不崩溃** |
| E4 | rules.json 格式错误 | 启动成功（用空规则），告警日志，**不崩溃** |
| E5 | 数据库写入失败 | 播放流程不受影响，error 日志 |
| E6 | 同一动作连续触发 | 按优先级规则处理，队列不溢出 |
| E7 | 播放中途新事件到达 | 按优先级抢占或入队，状态机不混乱 |
| E8 | 后端未启动 | 前端显示明确错误提示，不白屏 |

> **验收底线**：E1 / E3 / E4 / E5 任一场景导致系统崩溃，本阶段判定为未通过。

### 6.4 主观验收（本阶段最关键）

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| S1 | 互动感 | 至少 **3 名非开发者**观看演示后认为"宠物确实在回应我" |
| S2 | 响应可感知 | 参与者能明确感知"我做了操作 → 它回应了"的因果链 |

> 技术跑通 ≠ 玩法成立。S1/S2 不通过，需回到互动机制设计，而非继续开发。

---

## 七、开发顺序

### Step 1：地基与素材层

| 项 | 内容 |
|----|------|
| **输入** | 无（起点） |
| **输出** | 可启动的后端骨架 + 可解析素材的 Asset Manager + 数据库表 |
| **依赖** | 无 |
| **包含任务** | 1. 后端工程初始化（requirements / main.py / 配置 / 日志）<br>2. 数据库初始化（schema.sql / db.py）<br>3. Asset Manager（路径解析 / config.json 加载）<br>4. 健康检查接口<br>5. 素材占位文件准备 |
| **完成标志** | `GET /health` 返回 ok；Asset Manager 能正确解析 `cat/heart` 到 mp4 路径；DB 表创建成功 |
| **测试** | `pytest tests/unit/test_asset_manager.py` |

---

### Step 2：事件层

| 项 | 内容 |
|----|------|
| **输入** | Step 1 的工程骨架 |
| **输出** | 可产生并归一化事件的链路 |
| **依赖** | Step 1 |
| **包含任务** | 1. PlatformAdapter 抽象接口<br>2. SimulatorAdapter 实现<br>3. 统一事件结构定义（event_schema）<br>4. Event Gateway（校验 + 归一化 + 转发）<br>5. Event API（/simulate） |
| **完成标志** | 调用 `/api/events/simulate` 能产生标准事件并进入网关；非法 event_type 被正确拒绝且不崩溃 |
| **测试** | `pytest tests/unit/test_event_gateway.py` |

---

### Step 3：规则与动作层

| 项 | 内容 |
|----|------|
| **输入** | Step 2 的统一事件流 |
| **输出** | 事件 → 动作指令 → 状态变更 |
| **依赖** | Step 1、Step 2 |
| **包含任务** | 1. rules.json 设计<br>2. rule_loader（加载 + 校验 + 容错）<br>3. Interaction Engine（规则匹配 + 优先级）<br>4. Action Engine（状态机 + 队列 + 抢占）<br>5. Action API（/actions / /actions/state） |
| **完成标志** | 事件可正确映射为动作；状态机在 idle/playing/return_idle 间正确转移；素材缺失时降级 idle |
| **测试** | `pytest tests/unit/test_interaction_engine.py tests/unit/test_action_engine.py` |

---

### Step 4：播放与数据层

| 项 | 内容 |
|----|------|
| **输入** | Step 3 的播放指令 |
| **输出** | 可播放的素材地址 + 播放状态机 + 数据落库 |
| **依赖** | Step 1、Step 3 |
| **包含任务** | 1. Playback Manager（播放下发 + 完成回调 + 超时兜底）<br>2. Playback API（/status / /complete / /stop）<br>3. Data Manager（事件记录 + 聚合计数）<br>4. Stats API（/stats）<br>5. 静态素材服务挂载 |
| **完成标志** | 可获取到可访问的 mp4 地址；播放完成后状态正确回 idle；统计数据准确 |
| **测试** | `pytest tests/unit/test_data_manager.py` |

---

### Step 5：前端与联调

| 项 | 内容 |
|----|------|
| **输入** | Step 1~4 的完整后端 |
| **输出** | 可运行的完整 Demo |
| **依赖** | Step 1~4 |
| **包含任务** | 1. 前端工程初始化（Vite + React + TS）<br>2. API 封装与类型定义<br>3. PetStage（视频渲染 + 播放完成上报）<br>4. EventSimulator（三类事件按钮）<br>5. StatusBar（状态 + 计数）<br>6. Zustand 状态管理<br>7. CORS 配置与联调<br>8. 端到端测试 |
| **完成标志** | 完整流程跑通：点击 → 事件 → 规则 → 动作 → 播放 → 回 idle → 计数 +1 |
| **测试** | `pytest tests/integration/test_event_flow.py` + 手动全流程验证 |

---

### 依赖关系图

```
Step 1（地基与素材层）
   │
   ▼
Step 2（事件层）
   │
   ▼
Step 3（规则与动作层）
   │
   ▼
Step 4（播放与数据层）
   │
   ▼
Step 5（前端与联调） ──→ 验收（F/P/E/S 四类）
```

**关键路径**：Step 1 → 2 → 3 → 4 → 5，串行无并行空间（Phase 1 规模小，并行收益低于沟通成本）。

### 风险提示

| Step | 主要风险 | 应对 |
|------|----------|------|
| 1 | 素材缺失阻塞 | 先用占位 mp4 跑通链路，后替换 |
| 2 | 事件格式后期变动 | 统一格式以架构文档为准，先冻结再开发 |
| 3 | 规则设计过度复杂 | Phase 1 只支持 4 个操作符，够用即可 |
| 4 | 前后端播放状态不同步 | 前端上报 + 后端超时双保险 |
| 5 | 联调问题集中爆发 | Step 5 前先做接口连通性冒烟测试 |

---

*文档版本: v0.1*  
*最后更新: 2026-09-19*
