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


### 事件入口边界

原始事件进入核心业务**只有一条通道**：Event Gateway。

```
平台事件 → Adapter → raw dict → Event Gateway → Event → 核心业务
                                      ↑
                            唯一的 Event 构造点
```

事件入口契约以 `docs/development/step2_event_gateway.md` 为**唯一准绳**。

强制要求：

- **禁止绕过 Event Gateway 直接构造 `Event`** —— 除 Event Gateway 外，任何模块不得调用 `Event.from_dict()`
- Event Gateway 不得创建新异常，必须原样透传 Event Model 的错误 `code`
- Event Gateway 不得重复实现字段补齐逻辑（唯一来源是 Event Model）

说明：如果允许绕过网关直接构造 `Event`，校验规则会散落到多个模块，必然出现「有的路径校验了、有的没校验」；这类缺陷不报错，只会表现为「某些事件莫名其妙没反应」。


### 平台接入检查清单

接入任何平台前必须确认：

- [ ] 是否有官方开放的互动能力接口
- [ ] 是否已取得开发者授权
- [ ] 事件数据使用范围是否符合平台协议
- [ ] Adapter 是否完整实现 PlatformAdapter 接口
- [ ] 接入开关是否可配置（不写死单平台）


### 互动引擎边界

规则契约与引擎边界以 `docs/development/step3_interaction_engine_decision.md` 为**唯一准绳**。

强制要求：

- 规则字段固定为 `id` / `event_type` / `match` / `action` / `priority` / `enabled`，不得增删改名
- `match.op` 只允许 `eq` / `contains` / `gte` / `lte`；**禁止**引入 `==` / `>=` / `<=` 等第二套语法
- RuleLoader 与 InteractionEngine 职责分离：Engine 不读文件、不解析 JSON
- InteractionEngine 不得构造 `Event`、不得读取平台字段、不得播放资源、不得操作数据库
- InteractionEngine 输出 `ActionCommand` 或 `None`；`None` 表示无动作，**不得用异常表达**

说明：规则方言一旦分裂为两套（字段名或操作符各写一套），表现为**规则永不命中、系统却不报错**——「评论没反应」这类缺陷排查成本极高。规则层与事件层同理：**契约必须先冻结，再实现**。


### 动作指令与动作引擎边界

消费链契约以 `docs/development/step3_action_command_decision.md` 为**唯一准绳**；
动作执行链契约以 `docs/development/step3_action_engine_decision.md` 为**唯一准绳**。

强制要求：

- `ActionCommand` 字段固定为 `action_type` / `payload`，不得增删改名；**禁止**携带 `event_id` / `user_id` / `priority` / `pet_id`
- `pet_id` 属**执行上下文**，由调用方在 `execute` 时**显式传入**（`execute(command, pet_id)`）；**禁止**写入 `ActionCommand`
- ActionEngine 唯一指令入口为 `execute(command, pet_id) -> bool`；**不得**接收 `Event`
- ActionEngine **不得**读取 `rules.json`、不得解析 JSON、不得做规则判断或优先级仲裁
- 动作名取值域**唯一来源**为各宠物 `config.json` 的 `actions` 数组；**禁止**在代码中内建全局动作枚举（多角色扩展的前提）
- ActionEngine **不得**直接操作播放器，必须产出 `PlaybackCommand{pet_id, action_type}` 交由播放层执行
- ActionEngine **不得**写数据库；动作记录由**调用方**发起，DataManager 只负责落库与聚合
- ActionEngine 对**动作越域 / 素材缺失 / 队列满**一律**降级 `idle` + 返回 `False`，不抛异常

说明：动作引擎一旦能接收 `Event`，它就会逐步长出「自己判断该不该播」的能力，与 InteractionEngine 的职责重叠；一旦能直接调播放器，「播放失败降级 idle」（红线 C4）的处理就会同时存在于两层，必然漂移；一旦内建动作枚举，多角色扩展即被写死成「改代码」。**边界靠结构保证，不靠自觉。**


### 播放与素材边界

播放链契约以 `docs/development/step3_playback_decision.md`（P1–P6）与
`docs/development/step4_playback_data_decision.md`（D1–D6）为**唯一准绳**。

强制要求：

- **素材路径只允许 AssetManager 解析**；任何其他模块（含 ActionEngine / PlaybackManager / DataManager / 前端）不得拼接 `assets/pets/...`
- `pet_id → pet_type` 映射由 **AssetManager 内部完成**（对外主键统一为 `pet_id`）；其他模块不得自行读 `config.json` 做映射
- PlaybackManager 唯一入口为 `play(command: PlaybackCommand) -> bool`；**不得**接收 `pet_id` + `resource` 形态的散参数
- PlaybackManager **不得直接访问 assets**（不读文件、不拼路径），素材一律向 AssetManager 索取
- PlaybackManager **不拥有业务状态**（`idle` / `playing` 状态机归 ActionEngine）；播放完成 / 失败一律通知 `ActionEngine.restore_idle(pet_id)`
- PlaybackManager 播放失败**不得 `raise`**，返回 `False` + 降级 `idle`（红线 C4）
- **数据记录由调用方触发**；PlaybackManager / ActionEngine 均**不得**写数据库，DataManager 只负责落库与聚合
- `interactions` 统计表统一为 `stat_type` / `stat_key` / `value` 形态，**不得**改用固定 `event_type` 列

说明：播放层一旦能自己解析素材路径，就必然出现第二处路径拼装，`AssetManager` 的单一权威随之失效；一旦 PlaybackManager 持有 `idle`/`playing` 状态，「谁负责回待机」就会有两个答案（红线 C4 的降级逻辑分裂）；一旦允许播放层写库，统计口径会散落到每个调用点。**与事件层、规则层同理：边界必须先冻结，再实现。**


### UI 与后端边界

UI 契约以 `docs/development/step4_ui_prototype_decision.md`（UI-1–UI-6）为**唯一准绳**。

强制要求：

- UI 与后端**只经 HTTP + JSON** 通信；Phase 1 不得引入 WebSocket / SSE（属 Phase 2）
- UI **不得**直接调用 `ActionEngine` / `AssetManager` / `DataManager` 等后端 service，一律经后端 API 层
- UI **只提交原始事件**，**不得**自行构造统一事件、**不得**绕过 Event Gateway 进入核心业务
- **跨进程只传状态快照**；`ActionCommand` / `PlaybackCommand` 等**进程内指令对象不得下发到 UI**（它们不含素材地址，下发必然逼迫 UI 自行解析路径）
- UI **只消费后端下发的 `asset_url`**，不得出现 `assets/pets/...` 路径拼接（与「播放与素材边界」同一条不变量，前端同样受约束）
- UI **不得**内建角色名（红线 C3）或全局动作枚举；角色与动作取值域一律来自后端
- UI **不拥有** `idle` / `playing` 业务状态（Owner 是 ActionEngine），只做状态投影，不得自行置状态
- UI **不得**承载规则判断（阈值、匹配、优先级），一律由 Interaction Engine 决定

说明：UI 一旦能直接调后端 service，分层就在最外层破口，「谁负责回待机」「谁负责解析素材」会立刻出现第二个答案；一旦允许把进程内指令对象（`PlaybackCommand`）下发到前端，前端就被迫知道素材结构，`AssetManager` 的单一解析点随即失效；一旦把规则阈值写进 UI，改规则就要发前端版本，规则层与前端版本被绑死。**边界靠结构保证，不靠自觉。**


### 数据层与统计边界

数据层契约以 `docs/development/step4_data_layer_decision.md`（v1.0）为**唯一准绳**。

强制要求：

- DataManager 只负责**落库与聚合**，**不得参与业务决策**（不匹配规则、不判定动作、不触发播放）
- DataManager **禁止**接收 / 订阅 `Event`、`ActionCommand`、`PlaybackCommand` 等**模型对象或事件流**，
  只收**基本类型参数** —— 数据层对上游模型**零依赖**
- DataManager 入口只允许**写入明细 / 聚合计数 / 只读查询**三类；**不得**出现 `evaluate()` / `execute()` / `play()`
- **动作只记聚合、不记明细**：动作记录复用 `events.action_name`；**禁止**为动作新增第二写入点
- **统计模型唯一来源**：`interactions` 统一为 `stat_type` / `stat_key` / `value`；
  `stat_type` **只允许** `event` / `action`（`stat_key` 为事件类型或动作名）；
  **禁止**改用固定 `event_type` 列、**禁止**引入第二套统计维度或第三套口径
- **记录由调用方触发**；DataManager **不得**被事件 / 播放主流程**直接调用**
- 写库失败**不得**影响事件与播放主流程（try/except + error 日志，红线 C4 同理）

说明：数据层一旦能收 `Event`，事件契约的破坏性变更就会直接穿透到数据库 schema，且 DataManager 会逐步长出「自己判断该记什么」的能力；一旦允许为动作再开一个写入点，「一次动作只写一处」立即失效，动作计数会出现两个来源；一旦统计维度不锁死为 `event` / `action` 两类，`GET /api/stats` 的 `events` / `actions` 两个键就无法从表结构直接派生。**数据层是链路末端，末端一旦能反向影响上游，分层即失效。**


### API 与跨进程边界

API 契约以 `docs/development/step4_api_contract_decision.md`（v1.0）为**唯一准绳**。

强制要求：

- **API 层是 UI 与后端之间唯一通道**（HTTP + JSON）；UI **不得**直接调用后端 service
- **API 层只做协议转换与调用编排**，**不得**承载业务规则 ——
  规则匹配属 InteractionEngine、动作执行属 ActionEngine、播放属 PlaybackManager、素材路径解析属 AssetManager
- UI **只发原始事件**，**不得**发送规则输出（`action` / `action_type`）或素材信息（`path` / `asset_url`）；
  `action` 是规则产物，**不是**请求参数
- **后端补齐** `pet_id` / `action` / 时间戳；请求体只允许事件契约中的字段
- UI **只收 PlaybackState 快照**（含 `asset_url`）；**禁止**下发 `PlaybackCommand` 原文、`action_type`、`path`、`pet_type`
- UI **只消费 `asset_url`**，**不得**自行拼接素材路径（P3）
- **禁止 API 层直接 SQL**：不得拼接 SQL、不得持有 `sqlite3` 连接、不得绕过数据层
- **错误体统一**为 `{"code","message"}`（可选 `context`，**UI 不得依赖**）；
  API 层错误码**只允许** `INVALID_REQUEST` / `ASSET_NOT_FOUND` / `INTERNAL_ERROR`
- **禁止**在响应中泄露堆栈 / 物理路径 / SQL 片段 / 内部对象原文
- **只有 `pet_id` 是对外主键**；`pet_id → pet_type` 映射归 AssetManager，**禁止**搬进 API 层
- Phase 1 契约**不含 push 通道**（无 WebSocket / SSE / 长轮询）；引入须经 Change Request 修订 API 契约
- **未登记素材禁止路径拼接兜底**（Step 1 验收 A2）；播放失败一律降级 `idle`，**不上抛 UI**（红线 C4）

说明：一旦允许 UI 发送 `action`，规则层就被绕过——前端会逐步长出「自己判断该触发什么动作」的逻辑，规则从此有两个来源；一旦允许 API 层直接 SQL，数据层契约（`interactions` 口径、`events` 字段集）就会被第二个写入/读取点绕过，Step 4.2 的裁决随即失效；一旦让快照携带 `path`，UI 就被迫承担路径解析，`AssetManager` 作为唯一解析点的地位不保（P3）。**API 层是边界，不是业务层：越界的 API 会让分层在「第一个 HTTP 请求」处就崩掉。**


### API Implementation Boundary

实现边界以 `docs/development/step4_api_implementation_boundary.md`（v1.0）为**唯一准绳**。

强制要求：

- **SQL 只允许出现在两个位置**：`app/repositories/**` 与 `app/services/data_manager.py`；
  API 层**禁止**出现 SQL 字面量、**禁止** `import sqlite3`、**禁止**持有 `Database` 连接
- **写入唯一出口**：一切写入（`events` / `interactions`）**必须**经 `DataManager`；
  **禁止** Repository 提供写方法 —— **仓储只读**
- **`DataManager` 公开 API 冻结为 3 个写入方法**；**禁止**为其新增查询方法（查询走 Repository）
- **`INTERNAL_ERROR` 是 API 边界兜底码**：**禁止**新增 `InternalError` 等异常类、
  **禁止**修改 `backend/app/core/exceptions.py`；未捕获异常一律由 API 层统一 catch
  （完整堆栈只进日志，**响应体不得**含堆栈）
- **静态素材只挂载 `assets/pets`**（`StaticFiles` → `/assets/pets`）；
  **禁止**挂载项目根（会暴露 `database/`、`.env`）、**禁止**为 `/assets` 另开路由或逐文件转发
- **`asset_url` 由后端生成**（`"/" + asset_path`，与 `ASSET_URL_PREFIX` 自洽）；UI **不得**拼接素材路径
- **未知顶层请求字段一律拒绝**（`400 INVALID_REQUEST`），**不得**静默忽略
- **Phase 1 不实现 `events` 清理**：**禁止**为此引入线程 / 定时任务 / 后台 worker；
  查询侧以 `limit` 限制单次返回量

说明：一旦允许 API 层出现 SQL，第「数据层与统计边界」条冻结的 `interactions` 口径与 `events` 字段集立刻出现第二个读写点；一旦允许 Repository 提供写方法，「写入唯一出口」失效，`DataManager` 的 try/except 降级（红线 C4）会被绕过；一旦把静态目录挂在项目根，`database/pet_live.db` 与 `.env` 就会随 HTTP 裸露；一旦允许忽略未知字段，契约错误会从「首轮调用即报错」推迟到「UI 联调才暴露」。**实现边界与线上契约是同一条线：契约规定「谁说什么」，实现边界规定「谁能碰什么」。**


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
