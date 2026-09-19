# AI Pet Live 系统架构设计文档

**版本**: v0.1  
**日期**: 2026-09-19  
**作者**: Q仔

---

## 一、项目目标

### 产品定位
AI 萌宠互动直播系统是一个让直播间观众与虚拟宠物实时互动的娱乐工具。观众通过发送评论或礼物触发宠物的响应动画，产生"我操作，它会回应"的互动体验。

### 核心用户体验
```
观众进入直播间
    ↓
发送评论 / 赠送礼物
    ↓
系统识别行为类型（评论/礼物）
    ↓
匹配对应宠物动作
    ↓
播放动画视频 + 音效
    ↓
返回待机状态
    ↓
记录互动数据
```

### MVP 阶段目标
| 序号 | 目标 | 说明 |
|------|------|------|
| 1 | 可运行的本地 Demo | 前端+后端+素材完整可执行 |
| 2 | AI 猫角色展示 | 待机动画循环播放 |
| 3 | 模拟互动触发 | 点击礼物按钮触发动作 |
| 4 | 动作播放与返回待机 | 播放完毕自动返回 idle |
| 5 | 互动次数记录 | 内存统计，页面显示 |

---

## 二、整体系统架构

```
┌────────────────────────────────────────────────────────────┐
│                      前端展示层 (React)                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │
│  │  Stage  │ │ PetView │ │ Control │ │ Status  │         │
│  │  直播画面│ │  宠物展示│ │ 控制面板 │ │  状态栏  │         │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘         │
│       └───────────┴────┬──────┴───────────┘              │
│                  状态管理 (Zustand)                        │
└────────────────────────┼──────────────────────────────────┘
                         │ HTTP API / WebSocket
┌────────────────────────▼──────────────────────────────────┐
│                      后端服务层 (FastAPI)                   │
│  ┌────────────────────────────────────────────────────┐   │
│  │                EventDispatcher (事件分发)            │   │
│  │  礼物事件 → ActionEngine → AssetManager → Playback  │   │
│  └────────────────────────────────────────────────────┘   │
└────────────────────────┼──────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────┐
│                      业务逻辑层 (Services)                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────┐│
│  │ PetManager │ │ActionEngine│ │AssetManager│ │ DataMgr ││
│  │  宠物管理   │ │  动作引擎   │ │  素材管理   │ │  数据   ││
│  └────────────┘ └────────────┘ └────────────┘ └─────────┘│
└────────────────────────┼──────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────┐
│                      数据存储层 (SQLite)                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐            │
│  │    pets    │ │   events   │ │  interaction │            │
│  │   角色表   │ │   事件表   │ │   互动记录   │            │
│  └────────────┘ └────────────┘ └────────────┘            │
└──────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────────┐
│                      素材管理层 (assets/pets/)             │
│  assets/pets/{pet_type}/{resource_type}/{action}/         │
│  视频(.mp4) / 音频(.mp3) / 图片(.png) / config.json        │
└──────────────────────────────────────────────────────────┘
```

### 层级职责说明

| 层级 | 职责 | 技术实现 |
|------|------|----------|
| 前端展示层 | UI 渲染、用户交互捕获、实时状态显示 | React + Framer Motion |
| 后端服务层 | API 暴露、事件路由、请求处理 | FastAPI |
| 业务逻辑层 | 核心业务规则：动作匹配、状态机、素材加载 | Python 模块 |
| 数据存储层 | 持久化存储：角色配置、互动记录 | SQLite |
| 素材管理层 | 静态文件组织、配置读取、路径管理 | 文件系统 |

---

## 三、核心模块设计

### 3.1 Pet 角色管理模块

**职责**：管理所有宠物角色的信息、配置和生命周期

**模块边界**：
- 从 `assets/pets/{pet_type}/config.json` 加载角色信息
- 提供角色查询 API（按 pet_id / pet_type）
- 支持多角色扩展（注册新角色无需修改代码）

**对外接口**：
```python
# backend/app/services/pet_manager.py
class PetManager:
    def load_all_pets() -> list[PetConfig]      # 加载所有角色配置
    def get_pet(pet_id: str) -> PetConfig       # 按 ID 获取角色
    def get_pet_by_type(pet_type: str) -> PetConfig  # 按类型获取
    def list_available_actions(pet_id: str) -> list[str]  # 获取支持的动作
```

**数据模型**：
```python
@dataclass
class PetConfig:
    pet_id: str           # 唯一标识 cat_001
    pet_type: str         # 枚举 cat/dog/panda
    name: str             # 展示名
    actions: list[str]    # 支持的动作列表
    default_action: str   # 默认待机动作
    avatar_url: str       # 头像路径（相对于 assets/pets/{pet_type}/images/）
```

**设计要点**：
- 禁止硬编码角色名称，全部从 config.json 读取
- 新增角色只需添加目录和 config.json，无需修改代码

---

### 3.2 Action 动作管理模块

**职责**：动作注册、匹配规则、播放控制

**模块边界**：
- 接收 Event 层的事件，匹配对应动作
- 维护动作播放状态机（idle → playing → idle）
- 管理播放队列（防止冲突）

**状态机**：
```
[idle] ──→ [playing] ──→ [idle]
  ↑                              │
  └──────────────────────────────┘
      播放完成自动返回
```

**对外接口**：
```python
# backend/app/services/action_engine.py
class ActionEngine:
    def register_action(name: str, handler: Callable)  # 注册动作处理器
    def match_action(event: InteractionEvent) -> str   # 根据事件匹配动作名
    def trigger(pet_id: str, action_name: str)         # 触发动作
    def get_current_state(pet_id: str) -> str          # 获取当前状态
    def stop_action(pet_id: str)                       # 停止当前动作
```

**动作匹配规则**（示例）：
| 事件类型 | 触发动作 | 说明 |
|----------|----------|------|
| gift_bubble | bubble | 气泡礼物 |
| gift_heart | heart | 比心礼物 |
| comment_angry | angry | 生气评论关键词 |
| comment_happy | dance | 开心评论关键词 |

---

### 3.3 Event 事件处理模块

**职责**：接收外部事件，分类转发给 ActionEngine

**来源**：
- 本地 Demo：前端按钮点击、键盘输入
- 未来直播：抖音/YY/Bilibili WebSocket 事件

**对外接口**：
```python
# backend/app/services/event_dispatcher.py
class EventDispatcher:
    def dispatch(event: dict) -> None           # 分发事件
    def register_handler(event_type: str, handler: Callable)  # 注册事件处理器
    def simulate_event(event_type: str, data: dict) -> None  # 模拟事件（测试用）
```

**事件数据格式**：
```json
{
    "event_type": "gift_heart",
    "user_id": "user_001",
    "user_name": "张三",
    "timestamp": "2026-09-19T12:00:00Z",
    "extra": {}
}
```

---

### 3.4 Asset 素材管理模块

**职责**：素材加载、路径解析、缓存管理

**目录规范**：
```
assets/pets/{pet_type}/{resource_type}/{action}/
```

**对外接口**：
```python
# backend/app/services/asset_manager.py
class AssetManager:
    def get_action_video(pet_id: str, action: str) -> str  # 获取视频路径
    def get_idle_video(pet_id: str) -> str                 # 获取待机视频
    def get_sound(sound_name: str) -> str                  # 获取音效路径
    def get_avatar(pet_id: str) -> str                     # 获取头像
    def validate_action(pet_id: str, action: str) -> bool  # 验证动作是否存在
```

**资源类型映射**：
| resource_type | 文件扩展名 | 说明 |
|---------------|-----------|------|
| video | .mp4 | 动作视频 |
| sound | .mp3/.wav | 音效 |
| image | .png/.webp | 静态图片 |

---

### 3.5 Playback 播放控制模块

**职责**：控制视频/音效播放状态，管理播放队列

**状态机**：
```
[waiting] ──→ [playing] ──→ [ended]
                     ↓
                 [return_idle]
```

**对外接口**：
```python
# backend/app/services/playback_manager.py
class PlaybackManager:
    def play(pet_id: str, video_path: str, sound_path: str = None) -> None
    def stop(pet_id: str) -> None
    def get_status(pet_id: str) -> PlaybackStatus
    def queue_action(pet_id: str, action: str) -> None  # 加入播放队列
    def clear_queue(pet_id: str) -> None
```

**播放队列策略**：
- 当前播放中时，新动作加入队列
- 播放完成后自动取队列下一个
- 队列满时丢弃最旧的动作（FIFO）

---

### 3.6 Data 数据模块

**职责**：持久化互动记录，提供统计接口

**对外接口**：
```python
# backend/app/services/data_manager.py
class DataManager:
    def record_interaction(user_id: str, event_type: str, pet_id: str) -> None
    def get_interaction_count(pet_id: str) -> int
    def get_today_stats() -> dict
    def export_stats() -> list[dict]
```

**SQLite 表结构**（见第四节）

---

## 四、前后端通信设计

### API 接口设计

| 方法 | 路径 | 说明 | 请求体 | 响应体 |
|------|------|------|--------|--------|
| GET | `/api/pets` | 获取所有宠物 | - | `{pets: [...]}` |
| GET | `/api/pets/{pet_id}` | 获取单个宠物 | - | `{pet: {...}}` |
| POST | `/api/events/dispatch` | 分发事件 | `{event_type, user_id, data}` | `{status: "ok"}` |
| POST | `/api/events/simulate` | 模拟事件（Demo用） | `{event_type}` | `{status: "ok"}` |
| GET | `/api/stats/interactions` | 获取互动统计 | - | `{count: N, recent: [...]}` |
| GET | `/api/playback/status/{pet_id}` | 获取播放状态 | - | `{state: "idle\|playing"}` |

### 通信协议
- **HTTP REST**：常规 CRUD 操作
- **WebSocket（预留）**：直播实时事件推送
- **SSE（可选）**：前端状态实时推送

### 数据格式（JSON）
```json
// 宠物信息
{
    "pet_id": "cat_001",
    "pet_type": "cat",
    "name": "小橘",
    "avatar_url": "/assets/pets/cat/images/avatar/default.png",
    "actions": ["idle", "heart", "dance", "angry", "special"]
}

// 互动记录
{
    "event_type": "gift_heart",
    "user_id": "user_001",
    "user_name": "张三",
    "pet_id": "cat_001",
    "timestamp": "2026-09-19T12:00:00Z"
}
```

---

## 五、数据库设计（MVP SQLite）

### 表结构

#### pets 表 - 宠物角色
```sql
CREATE TABLE pets (
    pet_id     TEXT PRIMARY KEY,  -- 唯一标识，如 cat_001
    pet_type   TEXT NOT NULL,     -- 类型，如 cat/dog/panda
    name       TEXT NOT NULL,     -- 展示名
    config_path TEXT,             -- config.json 路径
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### events 表 - 互动事件记录
```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,    -- 事件类型，如 gift_heart
    user_id     TEXT,             -- 用户ID
    user_name   TEXT,             -- 用户名
    pet_id      TEXT NOT NULL,    -- 触发宠物
    action_name TEXT NOT NULL,    -- 匹配的动作
    data        TEXT,             -- 额外数据（JSON）
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_pet ON events(pet_id);
CREATE INDEX idx_events_time ON events(created_at);
```

#### interactions 表 - 互动统计
```sql
CREATE TABLE interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id      TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    count       INTEGER DEFAULT 1,
    last_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pet_id, event_type)
);
```

#### users 表 - 用户预留（MVP 不强制）
```sql
CREATE TABLE users (
    user_id   TEXT PRIMARY KEY,
    user_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 说明
- MVP 阶段使用 SQLite，数据存储在 `data/pet_live.db`
- users 表预留，本地 Demo 阶段 user_id 可为模拟值
- 生产环境可迁移至 PostgreSQL

---

## 六、未来扩展设计

### 平台接入（预留接口）
```
backend/app/services/platform/
├── base.py          # 平台基类（抽象接口）
├── douyin.py        # 抖音接入（待定）
├── yy.py            # YY接入（待定）
└── bilibili.py      # Bilibili接入（待定）
```

**扩展方式**：继承 BasePlatform，实现事件转换方法

### AI 语音（预留）
- 动作触发时调用 TTS API 生成语音
- 语音文件缓存到 `assets/pets/{type}/sounds/`

### 多宠物支持
- 当前架构已支持多宠物（按 pet_id 隔离）
- 前端增加宠物切换组件

### 商业化模块（预留）
- 会员专属动作
- 礼物价格配置
- 数据统计后台

---

## 七、MVP 开发拆解

### Phase 1：基础 Demo
**目标**：一个可运行的最小版本

| 任务 | 模块 | 说明 | 优先级 |
|------|------|------|--------|
| 初始化项目 | 全局 | 创建目录结构、依赖配置 | P0 |
| 后端骨架 | backend | FastAPI 启动、健康检查 | P0 |
| 前端骨架 | frontend | React 启动、首页框架 | P0 |
| 素材目录 | assets | 准备猫咪待机/礼物视频 | P0 |

**验收标准**：
- `http://localhost:5173` 能访问
- 页面显示猫咪待机动画
- 点击按钮触发动作，播放后返回待机

---

### Phase 2：互动系统
**目标**：完整的互动流程

| 任务 | 模块 | 说明 | 优先级 |
|------|------|------|--------|
| PetManager | backend/services | 加载 config.json | P0 |
| ActionEngine | backend/services | 动作匹配逻辑 | P0 |
| AssetManager | backend/services | 素材路径管理 | P0 |
| ControlPanel | frontend/components | 礼物按钮面板 | P0 |
| StatusBar | frontend/components | 互动次数显示 | P0 |

**验收标准**：
- 点击礼物按钮，猫咪播放对应动画
- 状态栏显示互动次数
- 动画结束自动返回待机

---

### Phase 3：OBS 展示优化
**目标**：适配直播推流场景

| 任务 | 模块 | 说明 | 优先级 |
|------|------|------|--------|
| 透明背景 | frontend | 去除窗口背景 | P1 |
| 窗口大小适配 | frontend | 适配 OBS 画布 | P1 |
| 快捷键支持 | frontend | 键盘触发动作 | P1 |

**验收标准**：
- 可作为 OBS 浏览器源使用
- 背景透明
- 快捷键触发互动

---

### Phase 4：直播接口（预留）
**目标**：接入真实直播平台

| 任务 | 模块 | 说明 | 优先级 |
|------|------|------|--------|
| WebSocket 服务 | backend/api | 实时事件接收 | P2 |
| 抖音适配器 | backend/platform | 事件转换 | P2 |
| YY 适配器 | backend/platform | 事件转换 | P2 |

**验收标准**：
- 直播间弹幕触发宠物动作
- 礼物事件正确匹配

---

## 附录：模块依赖关系图

```
frontend
    ├── components/StatusBar ───────┐
    ├── components/PetDisplay ──────┤──→ backend (HTTP API)
    ├── components/ControlPanel ────┘
    └── stores/petStore ──────────────────────────┐
                                                  │
backend (FastAPI)                                │
    ├── api/routes.py ← HTTP 入口                │
    ├── services/event_dispatcher.py ←───────────┤
    ├── services/action_engine.py ←───────────────┤
    ├── services/pet_manager.py ←─────────────────┤
    ├── services/asset_manager.py ←───────────────┤
    ├── services/playback_manager.py ←────────────┤
    ├── services/data_manager.py ←────────────────┤
    └── models/ (Pydantic schemas) ←──────────────┘

assets/pets/ ← asset_manager.py 读取
    └── config.json
```

---

*文档版本: v0.1*  
*最后更新: 2026-09-19*
