# AI Pet Live 开发计划

**版本**: v0.3（Phase 1 收尾修订版）  
**日期**: 2026-09-20  
**作者**: Q仔  
**变更**: 阶段划分由「技术分层」改为「验证目标分层」，Phase 1 解绑礼物按钮直连逻辑

---

## 修订说明（v0.1 → v0.2 → v0.3）

| 项 | v0.1 | v0.2 | v0.3（2026-09-20） |
|----|------|------|------|
| Phase 划分 | Phase 0~5（按技术模块） | Phase 1~4（按验证目标） | 不变 |
| Phase 1 定位 | 基础 Demo，按钮直连业务逻辑 | 本地互动 Demo，**事件模拟器驱动全链路** | 不变 |
| 事件入口 | 前端按钮 → 直接触发动作 | 按钮 → 模拟器 → Gateway → Engine → Action | 不变 |
| 平台接入 | 放在 Phase 4 且含糊 | 拆为 Phase 3（准备）+ Phase 4（接入） | 不变 |
| 展示端 | 未单独成阶段 | Phase 2 单独验证 OBS/网页展示 | 不变 |
| 模拟器按钮 | — | gift / comment / follow | **gift / comment / like**（事件契约 v1.1 白名单不含 follow，归 Phase 3+；ES v1.1） |
| comment 动作 | — | 未明确 | **只计数不保证动作播放**（动作策略归后续 Interaction Policy 阶段） |
| 1-21 / 1-22 | — | P1 | **Deferred**（音效与 PI-5 冻结一致；抢占语义待单独冻结） |
| 测试布局 | — | tests/unit + tests/integration | 实际为扁平 `tests/`（见 F-5 注记），不移动文件 |

> v0.1 已归档至 `docs/development/archive/development_plan_v0.1.md`

---

## 一、开发目标

### 最终效果（Phase 1 完成态）

```
用户在模拟器界面点击事件按钮（gift / comment / follow）
    ↓
事件模拟器产生事件
    ↓
Event Gateway 统一格式
    ↓
Interaction Engine 规则匹配
    ↓
Action Engine 选择动作
    ↓
Playback Manager 播放动画
    ↓
动作结束返回待机
    ↓
Data Manager 记录互动
```

**关键设计变化**：按钮**不再直接绑定**「播放某动画」的业务逻辑，而是**产生一个标准化事件**。这样验证的是完整链路，而非一个播放器。

### 全局验收标准

| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| G1 | 链路完整性 | 事件从模拟器进入，经网关、引擎、动作、播放，全链路可追踪 |
| G2 | 平台可替换性 | 替换 Simulator 为其他 Adapter，核心业务代码零修改 |
| G3 | 角色可扩展性 | 新增 dog/panda 角色无需修改代码 |
| G4 | 异常不影响主流程 | 素材缺失时降级 idle，系统不崩溃 |
| G5 | 数据可追溯 | 每次互动均落库，可查询统计 |

---

## 二、阶段划分

### Phase 1：本地互动 Demo

**目标**：验证「事件 → 规则 → 动作 → 播放」核心互动链路成立（不与任何真实平台耦合）

**验证的核心命题**：互动玩法本身是否成立（观众行为能否驱动宠物反馈）

#### 任务列表

| 序号 | 任务 | 模块 | 依赖 | 优先级 |
|------|------|------|------|--------|
| 1-1 | 后端工程初始化（FastAPI 骨架） | 全局 | - | P0 |
| 1-2 | 前端工程初始化（React + TS + Vite） | 全局 | - | P0 |
| 1-3 | 定义统一事件数据结构 | Gateway | 1-1 | P0 |
| 1-4 | 实现 PlatformAdapter 抽象接口 | Platform | 1-1 | P0 |
| 1-5 | 实现 SimulatorAdapter | Platform | 1-4 | P0 |
| 1-6 | 实现 EventGateway（事件归一化） | Gateway | 1-3,1-5 | P0 |
| 1-7 | 定义规则配置文件（rules.json） | Engine | 1-3 | P0 |
| 1-8 | 实现 InteractionEngine（规则匹配 + 优先级） | Engine | 1-7 | P0 |
| 1-9 | 实现 ActionEngine（注册 / 状态 / 队列 / idle 恢复） | Engine | 1-1 | P0 |
| 1-10 | 实现 AssetManager（路径解析 + config 加载） | Assets | 1-1 | P0 |
| 1-11 | 实现 PlaybackManager（播放 + 回调 + 异常降级） | Playback | 1-9,1-10 | P0 |
| 1-12 | SQLite 初始化脚本（pets/actions/events/interactions/users） | Data | 1-1 | P0 |
| 1-13 | 实现 DataManager（记录 + 统计） | Data | 1-12 | P0 |
| 1-14 | 串联主链路（Gateway → Engine → Action → Playback） | 全局 | 1-6,1-8,1-9,1-11,1-13 | P0 |
| 1-15 | 前端展示端（宠物画面 + 待机循环） | Viewer | 1-2,1-11 | P0 |
| 1-16 | 前端事件模拟器面板（gift/comment/like 三类按钮，ES v1.1） | Viewer | 1-14 | P0 |
| 1-17 | 前端状态栏（播放状态 + 互动计数） | Viewer | 1-13 | P0 |
| 1-18 | 猫咪素材准备（idle + heart + dance + angry + special） | Assets | 1-1 | P0 |
| 1-19 | 单元测试（Engine / Assets / Data） | Tests | 1-8,1-10,1-13 | P0 |
| 1-20 | 集成测试（事件到播放全链路） | Tests | 1-14 | P0 |
| 1-21 | 音效播放支持 | Playback | 1-11 | P1（**Deferred**：与 PI-5 冻结一致，归播放模型设计阶段） |
| 1-22 | 播放队列与优先级抢占增强 | Action | 1-9 | P1（**Deferred**：现 priority 仅为规则选择，运行时抢占语义待单独冻结） |

#### 产出物
- `backend/app/platform/base.py` — 平台抽象接口
- `backend/app/platform/simulator_adapter.py` — 本地模拟器适配器
- `backend/app/gateway/event_gateway.py` — 事件网关
- `backend/app/engine/interaction_engine.py` — 互动引擎
- `backend/app/engine/rules.json` — 规则配置
- `backend/app/engine/action_engine.py` — 动作系统
- `backend/app/playback/playback_manager.py` — 播放控制
- `backend/app/assets/asset_manager.py` — 素材管理
- `backend/app/data/data_manager.py` — 数据层
- `frontend/src/components/PetStage.tsx` — 宠物展示
- `frontend/src/components/EventSimulator.tsx` — 事件模拟器面板
- `frontend/src/components/StatusBar.tsx` — 状态栏

#### 依赖关系
```
1-1/1-2 (工程初始化)
      ↓
1-4 → 1-5 → 1-6 (平台层 → 网关)
      ↓
1-7 → 1-8 (规则 → 引擎) ─┐
1-9 (动作系统) ──────────┼→ 1-14 (主链路串联) → 1-16
1-10 → 1-11 (资源→播放) ─┘
1-12 → 1-13 (数据) ──────────┘
```

#### 验收标准
- [ ] 点击"送礼物"按钮 → 猫咪播放 heart 动画 → 返回待机
- [ ] 点击"发评论"按钮 → 事件被**接收、落库并计入统计**；**不保证动作播放**
      （comment 动作策略归后续 Interaction Policy 阶段冻结 —— Phase 1 收尾裁决 F-2，2026-09-20）
- [ ] 点击"点赞"按钮 → 事件链路与 gift 同构（提交 → 回读 → 展示更新）
      （follow 已移出 Phase 1：事件契约 v1.1 白名单 `comment/gift/like/system` 不含 follow，
      归 Phase 3+；模拟器按钮为 gift / comment / like —— ES v1.1）
- [ ] 互动次数正确累计并落库
- [ ] 删除某个动作素材后，触发该动作时系统降级 idle 且不崩溃
- [ ] 修改 rules.json 后重启，动作映射随之改变（无需改代码）

#### 测试方法
```bash
# 单元测试
cd backend && python -m pytest tests/unit/ -v

# 集成测试：链路完整性
cd backend && python -m pytest tests/integration/test_event_flow.py -v

# 手动测试
# 1. 启动后端 uvicorn app.main:app --reload
# 2. 启动前端 npm run dev
# 3. 依次点击三类事件按钮，观察动作与计数
```

> **F-5 注记（2026-09-20，Phase 1 收尾裁决）**：实际测试目录为 `backend/tests/` **扁平布局**
>（无 `unit/`、`integration/` 子目录）；集成链路验证由 `tests/test_api_contract.py`（36 例）与
> `tests/test_pipeline.py`（13 例）承担。前端测试位于 `frontend/tests/`（9 个文件，vitest）。
> **维持现有布局，不移动测试文件**；上方 `tests/unit/`、`tests/integration/` 路径仅为早期规划示意。

---

### Phase 2：直播展示 Demo

**目标**：验证宠物画面可作为直播画面源使用

**验证的核心命题**：展示形态是否满足直播场景（画面、背景、实时性）

#### 任务列表

| 序号 | 任务 | 模块 | 依赖 | 优先级 |
|------|------|------|------|--------|
| 2-1 | 透明背景渲染 | Viewer | Phase 1 | P0 |
| 2-2 | 画面尺寸适配（16:9 / 9:16） | Viewer | 2-1 | P0 |
| 2-3 | OBS 浏览器源接入验证 | Viewer | 2-1 | P0 |
| 2-4 | WebSocket 实时状态推送 | 全局 | Phase 1 | P0 |
| 2-5 | 展示端与事件源分离部署验证 | 全局 | 2-4 | P1 |
| 2-6 | 快捷键触发事件（本地调试用） | Viewer | Phase 1 | P1 |
| 2-7 | 性能测试（连续触发 100 次不卡顿） | Tests | 2-4 | P1 |
| 2-8 | 多宠物切换展示 | Viewer | Phase 1 | P2 |

#### 依赖关系
```
Phase 1（完整链路）
      ↓
2-1 → 2-2 / 2-3
      ↓
2-4 → 2-5 / 2-7
```

#### 验收标准
- [ ] OBS 添加浏览器源后，宠物画面正常显示且背景透明
- [ ] 事件触发后画面实时响应（延迟 < 500ms）
- [ ] 连续触发 100 次事件无卡顿、无内存泄漏
- [ ] 展示端可在另一台机器上运行

#### 测试方法
```bash
# OBS 验证
# 1. 启动前端
# 2. OBS → 添加 → 浏览器源 → URL: http://localhost:5173
# 3. 检查背景是否透明、动作是否响应

# 性能测试
node tests/perf/trigger_stress.js
```

---

### Phase 3：官方平台接入准备

**目标**：完成平台接入的接口设计与合规审查，**不接入真实平台**

**验证的核心命题**：接入路径是否可行、是否合规

#### 任务列表

| 序号 | 任务 | 模块 | 依赖 | 优先级 |
|------|------|------|------|--------|
| 3-1 | 抖音互动插件 SDK 调研（能力 / 申请条件） | Platform | Phase 2 | P0 |
| 3-2 | YY / Bilibili 接口能力调研 | Platform | Phase 2 | P0 |
| 3-3 | 各平台事件协议 → 统一事件格式 映射表 | Platform | 3-1,3-2 | P0 |
| 3-4 | 实现 DouyinAdapter 骨架（未接真实 SDK） | Platform | 3-3 | P0 |
| 3-5 | 实现 YYAdapter / BilibiliAdapter 骨架 | Platform | 3-3 | P1 |
| 3-6 | 平台合规审查（授权、数据使用范围） | 全局 | 3-1 | P0 |
| 3-7 | 接入开关与配置化（可切换平台） | Platform | 3-4 | P0 |
| 3-8 | 平台异常模拟测试（断连、限流） | Tests | 3-4 | P1 |

#### 依赖关系
```
Phase 2
      ↓
3-1 / 3-2 (平台调研)
      ↓
3-3 (映射设计) → 3-4 / 3-5 (适配器骨架)
      ↓
3-6 (合规审查) → 3-7 (可切换配置)
```

#### 验收标准
- [ ] 每个平台有完整的事件映射表
- [ ] Adapter 骨架可编译、可单元测试（用 mock 数据）
- [ ] 配置文件可切换平台，核心业务代码零修改
- [ ] 合规审查结论明确（可接入 / 不可接入 / 条件接入）

#### 风险闸门
> **Phase 3 结束时必须做一次 Go / No-Go 决策**：若官方接口不可得或授权不可行，则退回 Phase 2 的展示型方案，不进入 Phase 4。

---

### Phase 4：正式平台接入

**目标**：接入官方直播互动能力

**验证的核心命题**：真实直播间互动是否可跑通并稳定

#### 任务列表

| 序号 | 任务 | 模块 | 依赖 | 优先级 |
|------|------|------|------|--------|
| 4-1 | 平台开发者账号与授权申请 | 全局 | Phase 3 | P0 |
| 4-2 | DouyinAdapter 接入真实 SDK | Platform | 4-1 | P0 |
| 4-3 | 真实事件联调（礼物 / 评论 / 关注） | Platform | 4-2 | P0 |
| 4-4 | 高并发事件压测 | Tests | 4-3 | P0 |
| 4-5 | 断线重连与限流处理 | Platform | 4-3 | P0 |
| 4-6 | 真实直播场景灰度验证 | 全局 | 4-4,4-5 | P1 |
| 4-7 | 其他平台接入（YY / Bilibili） | Platform | 4-3 | P2 |

#### 依赖关系
```
Phase 3（Go 决策通过）
      ↓
4-1 (授权) → 4-2 (SDK接入) → 4-3 (联调)
                                  ↓
                          4-4 / 4-5 (压测 & 稳定性)
                                  ↓
                            4-6 (灰度验证)
```

#### 验收标准
- [ ] 真实直播间礼物事件可触发宠物动作
- [ ] 断线后自动重连成功率 > 95%
- [ ] 峰值 50 事件/秒下系统稳定
- [ ] 数据落库完整，可追溯

---

## 三、优先级说明

| 级别 | 含义 | 适用范围 |
|------|------|----------|
| P0 | 必须完成 | 阻塞后续阶段 |
| P1 | 优化项 | 不影响主流程，可延后 |
| P2 | 未来功能 | 明确不在当前阶段 |

**当前阶段（架构修复期）**：仅产出文档，不编码。编码从 Phase 1 开始。

---

## 四、风险分析

### 技术风险

| 风险 | 等级 | 影响 | 应对 |
|------|------|------|------|
| 官方 SDK 不可得 / 审核不通过 | **高** | Phase 4 无法进行 | Phase 3 设 Go/No-Go 闸门，提前调研 |
| 平台事件格式频繁变更 | 中 | Adapter 需反复修改 | 差异收敛在 Adapter，核心不动 |
| 视频播放性能不足 | 中 | 直播间卡顿 | Phase 2 性能测试先行 |
| 高并发事件丢失 | 中 | 互动体验断裂 | 事件队列 + 限流设计 |
| AI 生成内容合规风险 | **高** | 平台封禁 | 明确标注 AI 属性，见产品定位原则 |

### 开发风险

| 风险 | 等级 | 影响 | 应对 |
|------|------|------|------|
| 素材准备延迟 | 中 | 阻塞 Phase 1 | 先用占位素材跑通链路，后替换 |
| 阶段范围蔓延 | 中 | 交付延期 | 严格按 P0 清单执行 |
| 事件模拟器与实际平台行为偏差 | 中 | Phase 4 返工 | Phase 3 映射表先行设计 |

### 架构风险

| 风险 | 等级 | 影响 | 应对 |
|------|------|------|------|
| 平台逻辑渗漏到核心层 | **高** | 失去可替换性 | 红线 C1/C2 强制约束 + Code Review |
| 角色硬编码 | 中 | 无法扩展多宠物 | 红线 C3 + config.json 强制 |
| 播放异常中断系统 | 中 | 直播事故 | 红线 C4 + 异常降级测试 |
| 单文件膨胀 | 低 | 维护困难 | 单文件 ≤ 300 行 |

---

## 五、阶段依赖总览

```
Phase 1  本地互动 Demo
   │  验证：互动玩法成立
   ▼
Phase 2  直播展示 Demo
   │  验证：展示形态可用
   ▼
Phase 3  官方平台接入准备
   │  验证：接入路径可行 + 合规        ← Go / No-Go 闸门
   ▼
Phase 4  正式平台接入
      验证：真实直播间可跑通
```

---

*文档版本: v0.3*  
*最后更新: 2026-09-20*
