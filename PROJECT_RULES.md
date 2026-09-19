# AI Pet Live（AI互动宠物直播引擎）项目开发规则

## 一、开发原则

### 1. 模块化设计
- 所有代码必须按功能模块组织，禁止单文件超过 300 行
- 每个模块独立封装，接口清晰
- 模块间通过标准接口通信，禁止硬编码依赖

### 2. 新功能开发流程
```
需求分析 → 设计文档 → 评审确认 → 编码实现 → 单元测试 → 集成测试
```
- 任何新功能必须先提交设计方案（architecture/design/模块名.md）
- 获得确认后开始编码
- 禁止边写边想、无设计开发
   
### 3. 禁止删除已有功能
- 任何修改必须保留原有功能完整性
- 如需替换，必须先提供替代方案并验证
- git commit message 必须标注前缀：`feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`（完整定义见「四、Git工作流 > Commit Prefix」）

### 4. 影响范围检查
修改代码前必须：
- [ ] 列出修改的文件清单
- [ ] 评估对现有模块的影响
- [ ] 运行相关测试用例
- [ ] 确认无回归问题

### 5. 测试要求
每完成一个模块必须：
- 提供单元测试脚本（test_模块名.py）
- 提供集成测试用例
- 测试通过率 ≥ 90% 才能合入主分支

### 6. MVP优先原则
- 优先完成可运行的最小可用版本
- 不追求完美架构，追求快速验证
- Demo阶段只做核心交互流程

### 7. 接口扩展性
- 所有对外接口预留扩展字段
- 使用配置化设计，支持热更新
- 预留平台接入层（抖音、YY、Bilibili等）

---

## 二、技术栈规范

### 前端
- **框架**: React 18 + TypeScript
- **状态管理**: Zustand（轻量级，适合Demo）
- **动画**: Framer Motion
- **构建**: Vite
- **样式**: Tailwind CSS

### 后端
- **语言**: Python 3.11+
- **框架**: FastAPI（异步，适合直播场景）
- **数据库**: SQLite（Demo阶段）→ PostgreSQL（生产）
- **缓存**: Redis（可选，用于实时数据）

### 素材管理
- 视频: MP4/H.264，单文件 ≤ 50MB
- 音频: MP3/WAV，采样率 44.1kHz
- 图片: PNG/WebP，单文件 ≤ 5MB
- 存放路径: `assets/pets/{宠物类型}/{资源类型}/{动作}/{素材}`
- **禁止硬编码角色名称**，所有宠物信息必须通过 `config.json` 加载

#### 素材目录规范

```
assets/pets/
├── cat/                  # 猫咪角色
│   ├── actions/          # 动作素材（视频/动画）
│   │   ├── idle/         # 待机循环
│   │   ├── heart/        # 比心礼物
│   │   ├── dance/        # 跳舞礼物
│   │   ├── angry/        # 生气评论
│   │   └── special/      # 特殊互动
│   ├── sounds/           # 音效
│   │   └── purr.mp3      # 呼噜声示例
│   ├── images/           # 图片素材（封面、图标）
│   └── config.json       # 角色配置文件
├── dog/                  # 狗狗角色（预留）
│   ├── actions/
│   ├── sounds/
│   ├── images/
│   └── config.json
└── panda/                # 熊猫角色（预留）
    ├── actions/
    ├── sounds/
    ├── images/
    └── config.json
```

#### config.json 规范

每个宠物目录下必须有 `config.json`：

```json
{
    "pet_id": "cat_001",
    "pet_type": "cat",
    "name": "小橘",
    "actions": ["idle", "heart", "dance", "angry", "special"],
    "default_action": "idle"
}
```

- `pet_id`: 唯一标识，格式 `{类型}_{编号}`
- `pet_type`: 角色类型（用于代码枚举）
- `name`: 展示名称
- `actions`: 支持的动作列表（对应 actions/ 子目录名）
- `default_action`: 默认待机动作

---

## 三、目录结构规范

```
AI-Pet-Live/
├── README.md                    # 项目说明
├── PROJECT_RULES.md             # 开发规则（本文件）
├── architecture.md              # ⚠️ 已废弃（早期草稿）
├── development_plan.md          # ⚠️ 已废弃（早期草稿）
│
├── backend/                     # 后端代码
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── scripts/                 # 运维/初始化脚本
│   │   └── init_assets.py       # 资产元数据初始化
│   ├── app/
│   │   ├── core/                # 基础设施（无业务逻辑）
│   │   │   ├── constants.py     # 全局常量
│   │   │   ├── exceptions.py    # 业务异常（带稳定 code）
│   │   │   └── logging_config.py
│   │   ├── config/              # 运行时配置（读 .env）
│   │   ├── models/              # 数据结构（无 IO）
│   │   ├── repositories/        # 数据访问层
│   │   │   ├── db.py
│   │   │   └── asset_repository.py
│   │   ├── services/            # 业务逻辑层
│   │   │   └── asset_manager.py
│   │   └── api/                 # API 路由（Step 4）
│   └── tests/                   # 测试
│
├── frontend/                    # 前端代码（展示端 Viewer）
│   ├── src/
│   │   ├── api/                # API 封装
│   │   ├── components/         # UI 组件
│   │   ├── player/             # 播放器
│   │   ├── stores/             # 状态管理
│   │   └── types/              # TS 类型
│   └── tests/
│
├── assets/pets/                 # 素材资源
│   ├── cat/                     # 猫咪角色
│   │   ├── actions/             # 动作素材
│   │   │   ├── idle/           # 待机
│   │   │   ├── heart/          # 比心
│   │   │   ├── happy/          # 开心
│   │   │   ├── sad/            # 难过
│   │   │   └── surprise/       # 惊喜
│   │   ├── sounds/              # 音效
│   │   ├── images/              # 图片素材
│   │   └── config.json          # 角色配置
│   ├── dog/                     # 狗狗角色
│   └── panda/                   # 熊猫角色
│
├── database/                    # 数据存储
│   ├── schema.sql               # 建表脚本
│   └── pet_live.db              # SQLite 数据库（运行时生成）
│
└── docs/                       # 设计文档
    ├── architecture/           # 架构设计（权威版本）
    │   ├── system_architecture.md
    │   └── archive/            # 历史版本归档
    ├── development/            # 开发计划与阶段设计
    │   ├── development_plan.md
    │   ├── phase1_design.md
    │   ├── step1_completion.md
    │   └── archive/
    ├── product/                # 产品与技术路线
    │   └── technical_route.md
    ├── design/                 # 模块设计
    └── change_request/         # 需求变更记录
```

### 分层约定（Backend）

| 目录 | 职责 | 禁止 |
|------|------|------|
| `core/` | 常量、异常、日志等基础设施 | 禁止含业务逻辑 |
| `config/` | 运行时配置 | 禁止硬编码密钥 |
| `models/` | 数据结构定义 | 禁止做 IO |
| `repositories/` | 数据访问（SQL / ORM） | 禁止含业务判断 |
| `services/` | 业务逻辑 | 禁止直接写 SQL |
| `api/` | 接口路由与出入参校验 | 禁止含业务逻辑 |

**架构层语义保留在类名与模块名中**，例如「事件网关层」实现为
`services/event_gateway.py`，「播放控制层」实现为 `services/playback_manager.py`。

---

## 四、Git工作流

### Branch Naming

项目分支必须使用**扁平命名**（分支名中不得包含 `/`）。

格式：

```
<phase>-<step>-<purpose>
```

示例：

```
phase1-step1-foundation
phase1-step2-event
phase1-step3-engine
phase1-step4-playback
```

禁止使用嵌套分支名（任何含 `/` 的形式）。
原因：当前开发环境下嵌套 ref 分支存在兼容风险。

### Commit Prefix

提交信息必须以以下前缀开头：

| 前缀 | 用途 |
|------|------|
| `feat:` | 新增功能 |
| `fix:` | 修复错误 |
| `refactor:` | 重构代码，不改变功能 |
| `docs:` | 文档修改 |
| `test:` | 新增或修改测试代码、测试基础设施 |
| `chore:` | 工程维护、配置、工具链、非业务变更 |

示例：

```bash
feat: 新增礼物触发模块
fix: 修复动画播放卡顿问题
refactor: 重构API接口层
docs: 更新架构设计文档
test: 新增 AssetManager 单元测试
chore: 同步提交规范
```

---

## 五、测试方法

### 单元测试
```bash
cd backend && python -m pytest tests/unit/ -v
```

### 集成测试
```bash
cd backend && python -m pytest tests/integration/ -v
```

### 前端测试
```bash
cd frontend && npm test
```

### 端到端测试（Demo验证）
```bash
# 启动后端
cd backend && uvicorn app.main:app --reload

# 启动前端
cd frontend && npm run dev

# 访问 http://localhost:5173
```

---

## 六、MVP范围（第一阶段）

详细任务清单与验收标准以 `docs/development/development_plan.md` 为准。

### 阶段定位

第一阶段（Phase 1）不是"做一个播放器"，而是**验证互动链路成立**：

```
事件模拟器 → Event Gateway → Interaction Engine → Action Engine → Playback
```

### 必须实现（P0）
- [x] 统一事件格式定义（契约见 `docs/development/step2_event_schema.md`）
- [ ] PlatformAdapter 抽象接口 + SimulatorAdapter
- [ ] EventGateway 事件归一化
- [ ] InteractionEngine 规则匹配（配置化）
- [ ] ActionEngine 状态机与队列
- [ ] AssetManager 素材路径解析（禁止硬编码角色名）
- [ ] PlaybackManager 播放与异常降级
- [ ] SQLite 数据落库
- [ ] 前端展示端 + 事件模拟器面板
- [ ] 猫角色待机动画循环
- [ ] 动作结束返回待机
- [ ] 互动次数记录

### 暂不实现（后续阶段）
- [ ] 真实直播平台接入（Phase 3 准备 / Phase 4 接入）
- [ ] OBS 展示优化（Phase 2）
- [ ] 多角色切换（狗、熊猫等）
- [ ] 用户登录系统
- [ ] 数据统计后台
- [ ] AI 语音
- [ ] AI 实时生成动作

---

## 七、需求变更管理

任何新增需求：

必须创建：

docs/change_request/需求名称.md


内容：

- 需求描述
- 为什么需要
- 影响模块
- 修改方案
- 是否影响MVP范围


未经确认，不得修改核心架构。


## 八、代码质量要求

Python：

必须：

- 类型提示
- 函数说明
- 避免重复代码


前端：

必须：

- TypeScript类型完整
- 组件单一职责
- 禁止大量业务代码写入页面


提交前：

运行：

Python:
pytest

Frontend:
npm run build

确保无错误。

## 九、环境变量管理


禁止：

代码中出现：

API_KEY=
PASSWORD=
TOKEN=


统一使用：

.env


例如：

BACKEND_URL=
DATABASE_URL=
AI_API_KEY=


提交代码禁止上传：

.env

## 十、日志规范


所有核心模块必须记录日志：

包括：

- 用户事件
- 礼物事件
- 动作触发
- 错误信息


禁止：

使用print作为正式日志。


统一：

logging模块。

## 十一、异常处理


任何模块必须：

- 捕获异常
- 返回明确错误信息
- 不影响主流程


例如：

视频不存在：

不能导致系统停止。

应该：

记录错误

返回idle动作。

## 十二、数据设计原则


禁止：

把角色写死。


例如：

错误：

cat_action


正确：

pet_type:
cat

action:
heart


所有数据支持未来多角色。

## 十三、安全规范


禁止：

- 保存用户敏感信息
- 明文保存密码
- 上传密钥


API：

必须验证输入。

禁止直接执行用户输入代码。

## 十四、平台接入原则


项目定位为互动直播引擎，平台接入是核心能力，但必须遵守以下原则：


### 禁止

**未经授权的数据抓取**作为生产方案。


包括但不限于：

- 逆向解析直播平台私有协议
- 绕过官方接口抓取弹幕/礼物数据
- 模拟客户端登录获取事件流
- 任何形式的非官方数据管道


说明：抓取方案仅可用于**本地技术预研**，且不得进入生产环境、不得对外交付。


### 强制

所有直播平台必须：

**通过 Adapter 接口接入。**


要求：

- 平台差异只允许存在于 Adapter 实现内部
- 核心业务层禁止出现平台判断分支（如 `if platform == "douyin"`）
- 新增平台不得修改核心业务代码
- 平台断连、限流、协议变更不得导致主流程崩溃


### 事件契约

统一事件契约以 `docs/development/step2_event_schema.md` 为**唯一准绳**。

顶层字段固定为 4 个，不得增删改名：

```
event_type / user_id / user_name / payload
```

强制要求：

- 所有平台特有字段必须放入 `payload`
- 禁止将平台字段提升到事件顶层
- 网关校验必须拒绝出现顶层扩展字段的事件
- 顶层字段变更属破坏性变更，必须走需求变更流程

说明：顶层字段是**核心业务与直播平台之间的隔离面**。

如果允许平台字段上浮，顶层字段集会随接入平台数量线性膨胀，最终「统一事件」退化为「所有平台字段的并集」；到那时核心业务无法避免平台判断分支，Adapter 隔离设计随之失效。这是架构防线中最靠外的一环，一旦破口后面全部失守。


### 平台接入检查清单

接入任何平台前必须确认：

- [ ] 是否有官方开放的互动能力接口
- [ ] 是否已取得开发者授权
- [ ] 事件数据使用范围是否符合平台协议
- [ ] Adapter 是否完整实现 PlatformAdapter 接口
- [ ] 接入开关是否可配置（不写死单平台）


## 十五、产品定位原则


### 项目定位

**AI互动宠物直播**


不是：

**无人挂机直播。**


### 核心差异

| 项 | 本项目 | 无人挂机直播 |
|----|--------|--------------|
| 内容来源 | 根据互动实时响应 | 循环播放固定内容 |
| 用户关系 | 观众行为驱动反馈 | 观众被动观看 |
| 技术核心 | 事件 → 规则 → 动作 | 播放列表 |
| 价值主张 | "我操作，它会回应" | 填充直播时长 |


### 强制要求

直播展示必须：

**明确 AI 生成内容属性。**


具体要求：

- 直播画面或简介中标注宠物形象为 AI 生成
- 不得将 AI 生成内容宣称为真实拍摄
- 不得利用 AI 形象进行误导性营销
- 互动反馈说明中需说明其由程序规则驱动


### 禁止

- 以"真人扮演"方式包装 AI 生成宠物
- 隐瞒 AI 生成属性诱导打赏
- 使用 AI 生成内容冒充真实动物直播


## 十六、AI开发汇报格式


每次任务完成必须输出：


### 完成任务

xxx


### 修改文件

- xxx
- xxx


### 测试结果

通过：

xxx


失败：

xxx


### 风险提示

xxx


### 下一步建议

xxx

*版本: v0.2（架构修复升级版）*
*最后更新: 2026-09-19*
*维护者: Q仔*
