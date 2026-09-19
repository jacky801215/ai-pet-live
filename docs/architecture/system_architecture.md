# AI Pet Live 系统架构设计文档

**版本**: v0.2（架构修复升级版）  
**日期**: 2026-09-19  
**作者**: Q仔  
**变更**: v0.1 → v0.2 引入 Platform Adapter Layer 与 Event Gateway，明确核心逻辑与平台接口分离

---

## 修订说明（v0.1 → v0.2）

| 项 | v0.1 | v0.2 |
|----|------|------|
| 项目定位 | AI猫无人直播系统 | AI互动宠物直播引擎 |
| 架构层级 | 5 层（展示/事件/业务/数据/素材） | 7 层（新增平台接入层、事件网关层） |
| 平台依赖 | 未隔离，存在业务直连平台风险 | 全部经 Adapter 统一进入，核心零平台依赖 |
| 事件来源 | 前端按钮直接绑定业务逻辑 | 事件模拟器 / 平台事件 → 统一网关 |
| 素材路径 | assets/pets/{type}/{res}/{action}/ | 同左，明确禁止硬编码角色名 |

> v0.1 已归档至 `docs/architecture/archive/system_architecture_v0.1.md`

---

## 一、项目目标

### 项目定位

**AI Pet Live（AI互动宠物直播引擎）**

本项目不是简单的视频播放系统，而是一个**支持直播平台互动事件输入，并根据用户行为实时触发 AI 宠物反馈的互动娱乐引擎**。

核心描述：
```
直播互动事件输入  →  实时规则匹配  →  AI 宠物反馈输出
```

> **定位说明**：项目定位为「AI 互动宠物直播」，**不是无人挂机直播**。直播展示必须明确 AI 生成内容属性（详见 PROJECT_RULES.md 产品定位原则）。

### 核心用户体验

```
观众进入直播间
    ↓
发送评论 / 赠送礼物 / 点赞 / 关注
    ↓
平台适配层接收事件
    ↓
事件网关统一格式
    ↓
互动引擎规则匹配
    ↓
动作系统选择动作
    ↓
播放控制层播放动画 + 音效
    ↓
动作结束返回待机
    ↓
数据层记录互动
```

### MVP 阶段目标

| 序号 | 目标 | 说明 |
|------|------|------|
| 1 | 可运行的本地互动 Demo | 事件模拟器驱动完整链路 |
| 2 | AI 猫角色展示 | 待机动画循环播放 |
| 3 | 事件模拟驱动 | 通过模拟器产生 gift/comment/follow 事件 |
| 4 | 动作播放与返回待机 | 播放完毕自动返回 idle |
| 5 | 互动数据记录 | SQLite 持久化 + 页面展示 |

---

## 二、整体系统架构（7 层）

```
┌──────────────────────────────────────────────────────────────────┐
│  【1】直播平台接入层  Platform Adapter Layer                       │
│  ┌──────────────┐ ┌──────────┐ ┌───────────┐ ┌───────────────┐  │
│  │ DouyinAdapter│ │YYAdapter │ │BiliAdapter│ │SimulatorAdapter│ │
│  └──────┬───────┘ └────┬─────┘ └─────┬─────┘ └───────┬───────┘  │
│         └──────────────┴─────────────┴───────────────┘          │
│              统一接口 PlatformAdapter Interface                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │  原始平台事件（各平台私有格式）
┌────────────────────────────▼─────────────────────────────────────┐
│  【2】事件网关层  Event Gateway                                    │
│  职责：接收外部事件 → 转换为统一内部事件格式                        │
│  { event_type, user_id, user_name, payload }                     │
└────────────────────────────┬─────────────────────────────────────┘
                             │  统一内部事件
┌────────────────────────────▼─────────────────────────────────────┐
│  【3】互动引擎  Interaction Engine                                 │
│  职责：事件判断 → 规则匹配 → 动作选择 → 优先级控制                  │
│  gift_heart  →  action: heart_animation                          │
└────────────────────────────┬─────────────────────────────────────┘
                             │  目标动作指令
┌────────────────────────────▼─────────────────────────────────────┐
│  【4】动作系统  Action Engine                                      │
│  职责：动作注册 / 动作状态 / 动作队列 / idle 恢复                    │
│  预留：AI 实时生成动作                                             │
└────────────────────────────┬─────────────────────────────────────┘
                             │  播放指令
┌────────────────────────────▼─────────────────────────────────────┐
│  【5】播放控制层  Playback Manager                                 │
│  职责：视频播放 / 动作切换 / 播放完成回调 / 异常恢复                  │
│  原则：播放失败不得导致系统停止                                     │
└──────────────┬──────────────────────────────┬────────────────────┘
               │  媒体资源请求                  │  播放状态
┌──────────────▼──────────────┐  ┌────────────▼────────────────────┐
│  【6】素材管理层 Asset Mgr   │  │  展示端 Viewer（OBS / 网页）      │
│  assets/pets/{pet_type}/...  │  │  渲染宠物画面                     │
└─────────────────────────────┘  └─────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  【7】数据层  Data Manager（SQLite）                              │
│  pets / actions / events / interactions / users                   │
│  预留：多角色、多直播间                                             │
└──────────────────────────────────────────────────────────────────┘
```

### 层级职责说明

| 层 | 名称 | 职责 | 关键约束 |
|----|------|------|----------|
| 1 | Platform Adapter Layer | 连接不同直播平台，屏蔽平台差异 | 业务逻辑**禁止**直接依赖任何平台 |
| 2 | Event Gateway | 事件接收与格式统一 | 替换平台时**不修改**核心业务 |
| 3 | Interaction Engine | 规则匹配、动作选择、优先级控制 | 规则配置化，禁止硬编码 |
| 4 | Action Engine | 动作注册、状态机、队列管理 | 素材缺失时必须降级到 idle |
| 5 | Playback Manager | 播放控制、完成回调、异常恢复 | 播放失败不中断系统 |
| 6 | Asset Manager | 素材定位、加载、校验 | 禁止写死角色名 |
| 7 | Data Manager | 互动记录、统计查询 | 支持多角色/多直播间扩展 |

---

## 三、核心模块设计

### 3.1 Platform Adapter Layer（直播平台接入层）

**职责**：负责连接不同直播平台，将各平台私有事件协议转换为系统约定的原始事件。

**支持计划**：
- 抖音官方互动插件 SDK
- YY
- Bilibili
- Simulator（本地事件模拟器，用于 MVP 验证）

**统一接口设计**：

```python
# backend/app/platform/base.py
class PlatformAdapter(ABC):
    """所有平台适配器的统一接口"""

    @abstractmethod
    def connect(self, config: dict) -> bool:
        """建立与平台的连接"""

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""

    @abstractmethod
    def on_event(self, callback: Callable) -> None:
        """注册事件回调，平台事件到达时调用"""

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台标识，如 douyin / yy / bilibili / simulator"""
```

**适配器实现**：

| 类 | 平台 | 阶段 |
|----|------|------|
| `SimulatorAdapter` | 本地模拟器 | Phase 1（MVP） |
| `DouyinAdapter` | 抖音 | Phase 4 |
| `YYAdapter` | YY | Phase 4 |
| `BilibiliAdapter` | Bilibili | Phase 4 |

**设计约束**：
- **禁止**业务逻辑直接依赖某个平台
- **禁止**在业务层出现平台判断分支（如 `if platform == "douyin"`）
- 平台差异必须收敛在 Adapter 内部

---

### 3.2 Event Gateway（事件网关层）

**职责**：接收外部事件，并转换为统一内部事件格式。

**输入**：不同平台的原始事件
```
gift / comment / like / follow
```

**输出统一格式**：
```json
{
    "event_type": "gift",
    "user_id": "u_10086",
    "user_name": "张三",
    "payload": {
        "gift_name": "小心心",
        "gift_count": 1,
        "platform": "simulator",
        "raw": {}
    },
    "timestamp": "2026-09-19T12:00:00Z"
}
```

**统一事件类型枚举**：

| event_type | 说明 | payload 关键字段 |
|------------|------|------------------|
| `gift` | 赠送礼物 | gift_name, gift_count |
| `comment` | 发送评论 | content |
| `like` | 点赞 | like_count |
| `follow` | 关注 | - |
| `system` | 系统事件 | action |

**对外接口**：
```python
# backend/app/gateway/event_gateway.py
class EventGateway:
    def register_adapter(self, adapter: PlatformAdapter) -> None
    def ingest(self, raw_event: dict) -> None        # 接收原始事件
    def normalize(self, raw_event: dict) -> dict     # 转换为统一格式
    def subscribe(self, handler: Callable) -> None   # 下游订阅
```

**设计约束**：
- 后续替换直播平台时，**不修改核心业务**
- 网关是平台层与业务层之间的唯一通道

---

### 3.3 Interaction Engine（互动引擎）

**职责**：负责事件判断、规则匹配、动作选择、优先级控制。

**处理流程**：
```
统一事件 → 规则库查找（event_type + payload 条件） → 命中规则得动作名
        → 优先级仲裁（高优先级抢占） → 输出动作指令
```

**映射示例**：

| 输入事件 | 匹配条件 | 输出动作 |
|----------|----------|----------|
| `gift` | gift_name = "小心心" | `heart_animation` |
| `gift` | gift_name = "火箭" | `special_animation` |
| `comment` | content 含 "跳舞" | `dance` |
| `comment` | content 含 "生气" | `angry` |
| `like` | like_count >= 10 | `dance` |
| `follow` | - | `heart_animation` |

**对外接口**：
```python
# backend/app/engine/interaction_engine.py
class InteractionEngine:
    def load_rules(self, rules: list[dict]) -> None
    def process(self, event: dict) -> ActionCommand | None   # 事件 → 动作指令
    def get_priority(self, action: str) -> int               # 动作优先级
```

**优先级设计**：

| 优先级 | 动作类型 | 说明 |
|--------|----------|------|
| 高 | special | 大额礼物，抢占当前动作 |
| 中 | heart / dance / angry | 常规互动 |
| 低 | idle | 默认状态，可被任意动作打断 |

**设计约束**：
- 规则必须可配置（规则文件），禁止在代码中硬编码匹配逻辑
- 未命中规则时返回 `None`，不影响主流程

---

### 3.4 Action Engine（动作系统）

**职责**：管理动作注册、动作状态、动作队列、idle 恢复。

**状态机**：
```
        ┌──────────────────────────────┐
        │                              │
        ▼                              │
    [idle] ──触发──→ [playing] ──完成──┘
      ▲                  │
      │                  │ 新动作到达（高优先级）
      └──────────────────┘ 抢占
```

**对外接口**：
```python
# backend/app/engine/action_engine.py
class ActionEngine:
    def register_action(self, pet_type: str, action: str, meta: dict) -> None
    def trigger(self, pet_id: str, action: str, priority: int) -> bool
    def get_state(self, pet_id: str) -> str          # idle / playing
    def enqueue(self, pet_id: str, action: str) -> None
    def restore_idle(self, pet_id: str) -> None
```

**队列策略**：
- 当前动作播放中，新动作按优先级处理
- 高优先级动作 → 抢占当前
- 同优先级动作 → 入队，FIFO
- 队列上限可配置，超出丢弃最旧项

**扩展预留**：
- 未来支持 **AI 实时生成动作**（接口预留 `generate_action(prompt)`）

---

### 3.5 Playback Manager（播放控制层）

**职责**：视频播放、动作切换、播放完成回调、异常恢复。

**对外接口**：
```python
# backend/app/playback/playback_manager.py
class PlaybackManager:
    def play(self, pet_id: str, resource: dict) -> str      # 返回播放句柄
    def stop(self, pet_id: str) -> None
    def on_complete(self, callback: Callable) -> None        # 播放完成回调
    def get_status(self, pet_id: str) -> dict
    def recover(self, pet_id: str) -> None                   # 异常恢复
```

**异常处理规则**（对应 PROJECT_RULES 第十一条）：

| 异常 | 处理方式 |
|------|----------|
| 视频文件不存在 | 记录错误日志 → 降级返回 idle |
| 视频解码失败 | 记录错误日志 → 降级返回 idle |
| 播放超时 | 强制停止 → 返回 idle |
| 音效加载失败 | 忽略音效，视频继续播放 |

**核心原则**：播放失败**不能导致系统停止**。

---

### 3.6 Asset Manager（素材管理层）

**职责**：素材定位、加载、校验。

**素材路径规范**：
```
assets/pets/{pet_type}/{resource_type}/{action}/{asset}
```

**目录结构**：
```
assets/
└── pets/
    ├── cat/
    │   ├── actions/          # 动作视频
    │   │   ├── idle/
    │   │   ├── heart/
    │   │   ├── dance/
    │   │   ├── angry/
    │   │   └── special/
    │   ├── sounds/           # 音效
    │   ├── images/           # 图片素材
    │   └── config.json       # 角色配置
    ├── dog/
    └── panda/
```

**示例路径**：
```
assets/pets/cat/actions/heart/heart.mp4
assets/pets/cat/sounds/purr.mp3
assets/pets/cat/images/avatar/avatar.png
```

**config.json 规范**：
```json
{
    "pet_id": "cat_001",
    "pet_type": "cat",
    "name": "小橘",
    "actions": ["idle", "heart", "dance", "angry", "special"],
    "default_action": "idle"
}
```

**对外接口**：
```python
# backend/app/assets/asset_manager.py
class AssetManager:
    def get_action_asset(self, pet_type: str, action: str, res_type: str) -> str | None
    def get_sound(self, pet_type: str, sound_name: str) -> str | None
    def get_image(self, pet_type: str, image_name: str) -> str | None
    def load_pet_config(self, pet_type: str) -> dict
    def validate(self, pet_type: str, action: str) -> bool
```

**设计约束**：
- **禁止**代码中写死 `cat`
- 所有角色信息通过 `config.json` 加载
- 新增角色只需添加目录 + config.json，无需改代码

---

### 3.7 Data Manager（数据层）

**职责**：互动记录、统计数据。

#### pets 表 — 宠物角色
| 字段 | 类型 | 用途 |
|------|------|------|
| pet_id | TEXT PK | 宠物唯一标识（cat_001） |
| pet_type | TEXT | 角色类型（cat/dog/panda） |
| name | TEXT | 展示名称 |
| config_path | TEXT | 配置文件路径 |
| room_id | TEXT | 所属直播间（预留） |
| created_at | TIMESTAMP | 创建时间 |

#### actions 表 — 动作定义
| 字段 | 类型 | 用途 |
|------|------|------|
| action_id | INTEGER PK | 自增主键 |
| pet_type | TEXT | 角色类型 |
| action_name | TEXT | 动作名（heart） |
| asset_path | TEXT | 素材相对路径 |
| priority | INTEGER | 优先级 |
| created_at | TIMESTAMP | 创建时间 |

#### events 表 — 事件记录
| 字段 | 类型 | 用途 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| event_type | TEXT | 事件类型（gift/comment/like/follow） |
| user_id | TEXT | 用户 ID |
| user_name | TEXT | 用户名 |
| pet_id | TEXT | 目标宠物 |
| action_name | TEXT | 匹配动作 |
| platform | TEXT | 来源平台 |
| payload | TEXT | 原始数据（JSON） |
| created_at | TIMESTAMP | 发生时间 |

#### interactions 表 — 互动统计
| 字段 | 类型 | 用途 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| pet_id | TEXT | 宠物 ID |
| room_id | TEXT | 直播间（预留） |
| event_type | TEXT | 事件类型 |
| count | INTEGER | 累计次数 |
| last_time | TIMESTAMP | 最近一次时间 |

#### users 表 — 用户（预留）
| 字段 | 类型 | 用途 |
|------|------|------|
| user_id | TEXT PK | 用户 ID |
| user_name | TEXT | 昵称 |
| platform | TEXT | 来源平台 |
| created_at | TIMESTAMP | 首次出现时间 |

**扩展预留**：
- 多角色：通过 `pet_id` / `pet_type` 隔离
- 多直播间：通过 `room_id` 隔离

---

## 四、前后端通信设计

### API 接口设计

| 方法 | 路径 | 说明 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| GET | `/api/pets` | 获取宠物列表 | - | `{pets:[...]}` |
| GET | `/api/pets/{pet_id}` | 获取单个宠物 | - | `{pet:{...}}` |
| POST | `/api/simulator/event` | 模拟器注入事件 | `{event_type, payload}` | `{status:"ok"}` |
| GET | `/api/gateway/status` | 网关状态 | - | `{adapters:[...]}` |
| POST | `/api/events/ingest` | 平台事件入口 | 统一事件格式 | `{status:"ok"}` |
| GET | `/api/playback/status/{pet_id}` | 播放状态 | - | `{state:"idle\|playing"}` |
| GET | `/api/stats/interactions` | 互动统计 | - | `{count:N}` |
| GET | `/api/actions/{pet_type}` | 动作列表 | - | `{actions:[...]}` |

### 通信方式

| 方式 | 用途 | 阶段 |
|------|------|------|
| HTTP REST | 常规查询与命令 | Phase 1 |
| WebSocket | 实时状态推送、平台事件流 | Phase 2 |
| SSE | 轻量状态推送（可选） | Phase 3 |

### 数据流（完整链路）

```
SimulatorAdapter / DouyinAdapter
        ↓ 原始事件
EventGateway.normalize()
        ↓ 统一事件
InteractionEngine.process()
        ↓ 动作指令
ActionEngine.trigger()
        ↓ 播放请求
AssetManager.get_action_asset()  ← 读 assets/pets/{pet_type}/...
        ↓ 资源路径
PlaybackManager.play()
        ↓
Viewer 渲染  +  DataManager.record()
```

---

## 五、架构约束清单（红线）

| 编号 | 约束 | 说明 |
|------|------|------|
| C1 | 业务逻辑禁止依赖具体平台 | 只能依赖 PlatformAdapter 抽象 |
| C2 | 平台替换不得修改核心业务 | 差异收敛在 Adapter |
| C3 | 禁止硬编码角色名 | 必须通过 config.json |
| C4 | 播放失败不得中断系统 | 必须降级返回 idle |
| C5 | 禁止未经授权的数据抓取 | 生产方案必须走官方接口 |
| C6 | 直播展示须标明 AI 生成属性 | 见 PROJECT_RULES 产品定位原则 |
| C7 | 单文件不超过 300 行 | 模块化要求 |

---

## 六、未来扩展设计

### 平台接入
- 所有平台经 `PlatformAdapter` 接口接入
- 新增平台只需实现接口，不改核心业务

### AI 语音
- 动作触发时调用 TTS 生成语音
- 缓存至 `assets/pets/{pet_type}/sounds/`

### AI 实时生成动作
- `ActionEngine.generate_action()` 接口预留
- 未来接入视频生成模型

### 多宠物 / 多直播间
- 通过 `pet_id` / `room_id` 隔离
- 支持同一系统服务多个直播间

### 商业化
- 会员专属动作
- 礼物价格映射
- 数据统计后台

---

## 附录：模块依赖关系图

```
[平台层]  SimulatorAdapter | DouyinAdapter | YYAdapter | BilibiliAdapter
                    │
                    ▼
[网关层]  EventGateway  ──→ 统一事件
                    │
                    ▼
[引擎层]  InteractionEngine ──→ ActionCommand
                    │
                    ▼
          ActionEngine ──→ 播放指令
             │       │
             │       └──────→ DataManager（记录）
             ▼
[资源层]  AssetManager  ←  assets/pets/{pet_type}/...
             │
             ▼
[播放层]  PlaybackManager ──→ Viewer（OBS / 网页）
```

**禁止方向**：任何逆向箭头（业务层 → 具体平台）均不允许。

---

*文档版本: v0.2*  
*最后更新: 2026-09-19*
