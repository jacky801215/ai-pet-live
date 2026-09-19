# AI Pet Live（AI互动宠物直播引擎）

> 支持直播平台互动事件输入，并根据用户行为实时触发 AI 宠物反馈的互动娱乐引擎

## 项目简介

**这不是简单的视频播放系统。**

AI Pet Live 是一个互动娱乐引擎：直播平台产生互动事件（礼物、评论、点赞、关注），系统实时匹配规则并触发 AI 宠物的对应动作反馈，让观众产生"我操作，它会回应"的体验。

```
直播互动事件输入  →  实时规则匹配  →  AI 宠物反馈输出
```

### 项目定位

| 项 | 说明 |
|----|------|
| 定位 | **AI互动宠物直播** |
| 不是 | 无人挂机直播 |
| 核心价值 | 观众行为驱动宠物反馈 |

> 直播展示会**明确标注 AI 生成内容属性**（见 PROJECT_RULES.md 产品定位原则）。

### 核心链路

```
直播平台事件（gift / comment / like / follow）
    ↓
【1】Platform Adapter Layer   平台接入层
    ↓
【2】Event Gateway            事件网关层（统一格式）
    ↓
【3】Interaction Engine       互动引擎（规则匹配 + 优先级）
    ↓
【4】Action Engine             动作系统（状态机 + 队列）
    ↓
【5】Playback Manager         播放控制层
    ↓
Viewer 展示（OBS / 网页）  +  【7】Data Manager 数据落库

【6】Asset Manager 素材管理层（贯穿播放与动作）
```

---

## 当前状态

| 项 | 状态 |
|----|------|
| 阶段 | 架构修复期（文档阶段，未开始编码） |
| 已完成 | 架构设计、开发计划、技术路线、开发规范 |
| 下一步 | Phase 1 本地互动 Demo |

---

## 文档导航

| 文档 | 路径 | 内容 |
|------|------|------|
| 开发规则 | `PROJECT_RULES.md` | 开发规范、平台接入原则、产品定位原则 |
| 系统架构 | `docs/architecture/system_architecture.md` | 7 层架构设计 |
| 开发计划 | `docs/development/development_plan.md` | Phase 1~4 详细拆解 |
| 技术路线 | `docs/product/technical_route.md` | 三阶段验证路线 |

---

## 快速开始（Phase 1 完成后可用）

### 环境要求
- Node.js 18+
- Python 3.11+

### 启动

```bash
# 后端
cd backend
pip install -r requirements.txt
python main.py

# 前端（新终端）
cd frontend
npm install
npm run dev
```

### 体验流程

1. 打开浏览器访问 http://localhost:5173
2. 在**事件模拟器面板**点击事件按钮：
   - 🎁 送礼物 → 触发对应礼物动作
   - 💬 发评论 → 按规则触发动作
   - ⭐ 点关注 → 触发关注动作
3. 观察 AI 猫播放动作动画
4. 动画结束自动返回待机
5. 状态栏显示互动次数

> 注意：按钮产生的是**标准化事件**，而非直接调用播放逻辑。这是为了验证真实链路的完整性。

---

## 项目结构

```
AI-Pet-Live/
├── PROJECT_RULES.md              # 开发规则
├── README.md                     # 本文件
├── backend/                      # FastAPI 后端
│   └── app/
│       ├── platform/             # 【1】平台接入层
│       ├── gateway/              # 【2】事件网关层
│       ├── engine/               # 【3】互动引擎 【4】动作系统
│       ├── playback/             # 【5】播放控制层
│       ├── assets/               # 【6】素材管理层
│       └── data/                 # 【7】数据层
├── frontend/                     # React 前端（展示端）
├── assets/
│   └── pets/                     # 多角色素材
│       ├── cat/
│       │   ├── actions/          # idle/heart/dance/angry/special
│       │   ├── sounds/
│       │   ├── images/
│       │   └── config.json
│       ├── dog/
│       └── panda/
├── tests/                        # 测试
└── docs/                         # 设计文档
    ├── architecture/             # 架构
    ├── development/              # 开发计划
    └── product/                  # 技术路线
```

### 素材路径规范

```
assets/pets/{pet_type}/{resource_type}/{action}/{asset}
```

示例：
```
assets/pets/cat/actions/heart/heart.mp4
assets/pets/cat/sounds/purr.mp3
```

**禁止**在代码中写死角色名，所有角色信息通过 `config.json` 加载。

---

## 扩展新角色

新增宠物只需三步：

1. 创建目录 `assets/pets/{new_type}/`
2. 添加动作素材到 `actions/`、音效到 `sounds/`
3. 添加 `config.json` 配置文件

```json
{
    "pet_id": "dog_001",
    "pet_type": "dog",
    "name": "旺财",
    "actions": ["idle", "heart", "dance"],
    "default_action": "idle"
}
```

**无需修改任何代码。**

---

## 后续规划

| 阶段 | 目标 |
|------|------|
| Phase 1 | 本地互动 Demo（事件模拟器驱动） |
| Phase 2 | 直播展示 Demo（OBS / 网页） |
| Phase 3 | 官方平台接入准备（含合规审查） |
| Phase 4 | 正式平台接入（抖音 / YY / Bilibili） |

---

## 许可证

内部项目
