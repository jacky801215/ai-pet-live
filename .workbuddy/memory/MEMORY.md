# AI Pet Live 项目记忆

## 项目位置
- 根目录：`D:\AI-Pet-Live\`
- 迁移自：`C:\Users\Administrator\WorkBuddy\2026-09-19-11-53-39\`

## 项目定位（v0.2 已更新）
- **AI Pet Live（AI互动宠物直播引擎）**
- 不是「AI猫无人直播系统」，不是无人挂机直播
- 核心：直播互动事件输入 → 实时规则匹配 → AI宠物反馈输出
- 必须标注 AI 生成内容属性

## 当前状态
- **Step 1.1 已完成**（52/52 测试通过），下一步 Step 2 事件层
- 代码分层：`core / config / models / repositories / services / api`
- git 仓库已 init（`.gitignore` 生效），**尚未做过任何提交**

## 环境事实（本机，跨会话有效）
- 受管 Python：`C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- ffmpeg / ffprobe：`C:\ffmpeg\bin\`（**ffprobe 是 duration 的运行依赖**）
- 已装：sqlite3 / pytest / uvicorn / numpy；**未装 fastapi / pydantic**（Step 4 需要）
- Bash 工具 `cd` 与 `dirname`/`head` 报错，**不要用 shell 管道**；
  最稳姿势：写 `.py` 脚本再 `python <path>`，或 `python -c "import os; os.chdir(...)"` 包裹

## Step 1.1 关键设计决策（勿回退）
- **duration 唯一来源 = ffprobe**：`services/asset_duration.py:get_duration_ms()`
  已删除常量 `PLACEHOLDER_DURATION_MS`，全项目无第二处时长来源
- `register(duration=None)` → 探测；显式传整数 → 测试注入用
- ⚠️ **陷阱**：占位素材本身是 1 秒，所以库里 5 条都是 1000ms，**不代表硬编码**。
  验证真值化要用非 1 秒素材（2.5s → 2500ms 已实证）
- 异常三码：`ASSET_NOT_FOUND`（未登记）/ `ASSET_FILE_MISSING`（查询期文件丢）/
  `ASSET_METADATA_ERROR`（登记期读不出时长）
- 错误输出契约：`{code, message, context}` —— 用 `code` 不用 `error`
- `init_assets.py` 走 `AssetManager.register()`，不自行调 ffprobe
- 素材替换后**必须重跑** `python -m scripts.init_assets --reset`
  （多角色需 `--reset --all`，否则 dog/panda 记录会被清掉）

## Step 1 关键设计决策
- `register()` **不校验文件**（登记=声明，素材可后补）
  `get_asset()` **强制校验文件**（查询=使用）
  —— 这是修正过的职责混淆，勿回退
- 路径存**相对项目根**，运行时解析为绝对路径
- 测试用 `Settings` 注入 tmp_path 完全隔离，不碰真实 assets/database
- 占位素材用 ffmpeg 生成（H.264 / 480×480 / 1s）
- 测试目录在 `backend/tests/`（非顶层），pytest.ini 在 `backend/`

## 动作名（以 Step 1 指令为准）
`idle / heart / happy / sad / surprise`
（早期设计的 dance/angry/special 已废弃）

## 文档权威版本
- 开发规则：`PROJECT_RULES.md`（v0.2）
- 系统架构：`docs/architecture/system_architecture.md`（v0.2）
- 开发计划：`docs/development/development_plan.md`（v0.2）
- Phase 1 设计：`docs/development/phase1_design.md`（v0.1）
- 技术路线：`docs/product/technical_route.md`（v0.1）
- Step 1 报告：`docs/development/step1_completion.md`（L1 已由 Step 1.1 闭环）
- Step 1.1 报告：`docs/development/step1_1_completion.md`

## Phase 1 关键设计决策
- **Asset Manager 为支撑模块**（原需求遗漏）：Playback 需路径解析，
  否则违反红线 C3。已纳入。
- **播放同步双保险**：前端 onEnded 上报 + 后端超时兜底
- **EventSimulator 只调 Event API**，不直接调播放接口
- **开发顺序**：Step 1 地基 → Step 2 事件 → Step 3 规则动作 → Step 4 播放数据 → Step 5 前端联调
- **异常底线**：素材缺失/规则错误/DB失败/非法事件均不得崩溃，一律降级 idle

## Phase 1 暂不实现（明确禁止）
抖音 SDK、YY、Bilibili、WebSocket、OBS、AI 实时生成视频、
用户系统、商城、音效、多宠物切换、数据统计后台

## 架构（v0.2，7 层）
```
1 Platform Adapter Layer  平台接入层（Simulator/Douyin/YY/Bilibili）
2 Event Gateway           事件网关层（统一格式）
3 Interaction Engine      互动引擎（规则匹配+优先级）
4 Action Engine           动作系统（状态机+队列+idle恢复）
5 Playback Manager        播放控制层（异常降级）
6 Asset Manager           素材管理层（禁止硬编码角色名）
7 Data Manager            数据层
```

## 阶段划分（v0.2）
| Phase | 目标 | 验证命题 |
|-------|------|----------|
| 1 | 本地互动 Demo | 互动玩法是否成立 |
| 2 | 直播展示 Demo（OBS/网页） | 展示形态是否可用 |
| 3 | 官方平台接入准备 | 接入路径是否可行+合规（**Go/No-Go 闸门**） |
| 4 | 正式平台接入 | 真实直播间是否能跑通 |

## 架构红线（不可违反）
- C1 业务逻辑禁止依赖具体平台（只依赖抽象接口）
- C2 平台替换不得修改核心业务
- C3 禁止硬编码角色名，必须走 config.json
- C4 播放失败不得中断系统（降级 idle）
- C5 **禁止未经授权的数据抓取作为生产方案**
- C6 **直播展示必须标注 AI 生成内容属性**

## 素材规范
- 路径：`assets/pets/{pet_type}/{resource_type}/{action}/{asset}`
- 例：`assets/pets/cat/actions/heart/heart.mp4`
- 每个宠物必须有 `config.json`

## 技术栈
- 前端：React 18 + TypeScript + Vite + Zustand
- 后端：Python FastAPI
- 数据库：SQLite（Demo）→ PostgreSQL（生产）

⚠️ 根目录 `architecture.md` / `development_plan.md` 已废弃，勿据此开发。

## 工作方式约定
- 编码前必须先出设计，确认后再写代码
- 不删除已有功能
- 修改前检查影响范围
- 每模块必须提供测试方法
- 只走官方授权接口，不做数据抓取
