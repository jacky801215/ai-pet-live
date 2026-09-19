# AI Pet Live MVP 第一阶段开发计划

**版本**: v0.1  
**日期**: 2026-09-19  
**作者**: Q仔

---

## 一、开发目标

### 第一阶段目标
完成一个本地可运行的 AI 猫互动 Demo。

### 最终效果流程
```
用户点击礼物按钮
    ↓
系统触发猫动作
    ↓
播放对应动画视频
    ↓
动画结束自动返回待机
    ↓
记录互动次数
```

### MVP 验收标准
| 编号 | 验收项 | 通过条件 |
|------|--------|----------|
| 1 | 项目可启动 | 后端+前端同时运行，无报错 |
| 2 | 页面可访问 | http://localhost:5173 打开显示猫咪待机画面 |
| 3 | 礼物按钮可用 | 点击后触发对应动作 |
| 4 | 动画正常播放 | 点击礼物后猫咪播放动作视频 |
| 5 | 自动返回待机 | 动作播放完毕自动回到待机循环 |
| 6 | 互动次数显示 | 状态栏正确显示累计互动次数 |

---

## 二、开发阶段拆解

### Phase 0：项目初始化

**目标**：建立项目基础框架，确保开发环境可运行

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 0-1 | 创建 backend/app 目录结构 | 后端 | - | P0 |
| 0-2 | 创建 frontend/src 目录结构 | 前端 | - | P0 |
| 0-3 | 安装后端依赖（FastAPI, uvicorn, pydantic） | 后端 | 0-1 | P0 |
| 0-4 | 安装前端依赖（React, TypeScript, Vite, Tailwind） | 前端 | 0-2 | P0 |
| 0-5 | 创建后端 main.py 入口文件 | 后端 | 0-1,0-3 | P0 |
| 0-6 | 创建前端 main.tsx 入口文件 | 前端 | 0-2,0-4 | P0 |
| 0-7 | 编写后端健康检查接口 GET /health | 后端 | 0-5 | P0 |
| 0-8 | 编写前端 Hello World 组件 | 前端 | 0-6 | P0 |
| 0-9 | 验证前后端分别启动成功 | 全栈 | 0-7,0-8 | P0 |

#### 产出物
- `backend/app/main.py` — FastAPI 应用入口
- `frontend/src/main.tsx` — React 应用入口
- `backend/requirements.txt` — 后端依赖
- `frontend/package.json` — 前端依赖

#### 测试方法
```bash
# 后端测试
cd backend && python main.py
# 访问 http://localhost:8000/health，应返回 {"status": "ok"}

# 前端测试
cd frontend && npm run dev
# 访问 http://localhost:5173，应显示 Hello World
```

---

### Phase 1：宠物展示系统

**目标**：加载猫咪配置，展示待机动画循环

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 1-1 | 定义 PetConfig 数据模型 | 后端 | Phase 0 | P0 |
| 1-2 | 实现 AssetManager 素材加载 | 后端 | 1-1 | P0 |
| 1-3 | 实现 PetManager 角色加载 | 后端 | 1-2 | P0 |
| 1-4 | 创建 GET /api/pets 接口 | 后端 | 1-3 | P0 |
| 1-5 | 创建前端 PetDisplay 组件 | 前端 | Phase 0 | P0 |
| 1-6 | 创建前端 Stage 组件 | 前端 | 1-5 | P0 |
| 1-7 | 准备猫咪待机视频素材 | 素材 | Phase 0 | P0 |
| 1-8 | 接入视频循环播放逻辑 | 前端 | 1-6 | P0 |

#### 产出物
- `backend/app/models/pet.py` — 宠物数据模型
- `backend/app/services/asset_manager.py` — 素材管理器
- `backend/app/services/pet_manager.py` — 角色管理器
- `frontend/src/components/Stage.tsx` — 直播画面组件
- `frontend/src/components/PetDisplay.tsx` — 宠物展示组件
- `assets/pets/cat/actions/idle/idle.mp4` — 待机视频

#### 测试方法
```python
# 单元测试：资产路径解析
cd backend && python -m pytest tests/unit/test_asset_manager.py -v

# 集成测试：宠物列表接口
curl http://localhost:8000/api/pets
```

---

### Phase 2：动作系统

**目标**：实现动作匹配、播放控制和状态管理

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 2-1 | 定义 ActionEvent 数据模型 | 后端 | Phase 0 | P0 |
| 2-2 | 实现 ActionEngine 动作匹配 | 后端 | 2-1 | P0 |
| 2-3 | 实现 PlaybackManager 播放控制 | 后端 | 2-2 | P0 |
| 2-4 | 创建 POST /api/events/dispatch 接口 | 后端 | 2-3 | P0 |
| 2-5 | 创建 GET /api/playback/status/{pet_id} 接口 | 后端 | 2-3 | P0 |
| 2-6 | 创建前端 GiftPanel 按钮组件 | 前端 | Phase 0 | P1 |
| 2-7 | 实现动作播放状态管理（Zustand Store） | 前端 | 2-6 | P1 |

#### 产出物
- `backend/app/models/event.py` — 事件数据模型
- `backend/app/services/action_engine.py` — 动作引擎
- `backend/app/services/playback_manager.py` — 播放管理器
- `frontend/src/stores/petStore.ts` — 宠物状态管理
- `frontend/src/components/GiftPanel.tsx` — 礼物按钮面板

#### 测试方法
```python
# 单元测试：动作匹配规则
cd backend && python -m pytest tests/unit/test_action_engine.py -v

# 集成测试：触发动作接口
curl -X POST http://localhost:8000/api/events/simulate \
  -H "Content-Type: application/json" \
  -d '{"event_type": "gift_heart"}'
```

---

### Phase 3：互动系统

**目标**：完成前端交互逻辑，实现完整的礼物触发流程

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 3-1 | 创建前端 ControlPanel 组件 | 前端 | Phase 2 | P0 |
| 3-2 | 创建前端 StatusBar 组件 | 前端 | Phase 0 | P0 |
| 3-3 | 实现礼物按钮点击事件 | 前端 | 3-1 | P0 |
| 3-4 | 实现状态更新回调到后端 | 前端 | 3-3 | P0 |
| 3-5 | 创建 App.tsx 主组件整合所有子组件 | 前端 | 3-2,3-4 | P0 |
| 3-6 | 添加前端 WebSocket 支持（预留） | 前端 | Phase 2 | P2 |

#### 产出物
- `frontend/src/components/ControlPanel.tsx` — 控制面板组件
- `frontend/src/components/StatusBar.tsx` — 状态栏组件
- `frontend/src/App.tsx` — 主应用组件
- `frontend/src/stores/eventStore.ts` — 事件状态管理

#### 测试方法
```
# 手动测试
1. 打开浏览器访问 http://localhost:5173
2. 点击礼物按钮
3. 观察猫咪播放动画
4. 确认动画结束后返回待机
5. 确认互动次数增加
```

---

### Phase 4：数据记录

**目标**：实现 SQLite 数据库持久化，记录互动数据

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 4-1 | 创建 SQLite 数据库初始化脚本 | 后端 | Phase 0 | P0 |
| 4-2 | 实现 DataManager 数据管理模块 | 后端 | 4-1 | P0 |
| 4-3 | 创建 GET /api/stats/interactions 接口 | 后端 | 4-2 | P0 |
| 4-4 | 在 PlayBackManager 中添加记录调用 | 后端 | 4-2,2-3 | P0 |
| 4-5 | 更新 StatusBar 显示统计数据 | 前端 | 3-2 | P0 |

#### 产出物
- `backend/app/services/data_manager.py` — 数据管理器
- `data/pet_live.db` — SQLite 数据库文件（运行时生成）
- `frontend/src/components/StatusBar.tsx` — 更新统计显示

#### 测试方法
```python
# 单元测试：数据统计
cd backend && python -m pytest tests/unit/test_data_manager.py -v

# 集成测试：统计数据接口
curl http://localhost:8000/api/stats/interactions
```

---

### Phase 5：Demo 整合

**目标**：前后端联调，验证完整流程

#### 任务列表

| 序号 | 任务 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 5-1 | 整合所有前端组件到 App.tsx | 前端 | Phase 3 | P0 |
| 5-2 | 验证前后端 CORS 配置 | 后端 | Phase 0 | P0 |
| 5-3 | 完整流程端到端测试 | 全栈 | Phase 4 | P0 |
| 5-4 | 修复发现的问题 | 全栈 | 5-3 | P0 |
| 5-5 | 编写 README 使用说明 | 文档 | Phase 5 | P1 |
| 5-6 | 编写测试用例汇总 | 测试 | Phase 4 | P1 |

#### 产出物
- 完整的可运行 Demo
- README.md 使用说明
- 测试报告

#### 测试方法
```bash
# 端到端测试脚本
python tests/e2e/test_full_flow.py

# 或手动测试
# 1. 启动后端：cd backend && python main.py
# 2. 启动前端：cd frontend && npm run dev
# 3. 访问 http://localhost:5173
# 4. 按顺序点击所有礼物按钮
# 5. 检查状态栏计数是否正确
# 6. 检查数据库记录是否正确
```

---

## 三、依赖关系图

```
Phase 0 (项目初始化)
    │
    ├──→ Phase 1 (宠物展示系统) ──→ Phase 2 (动作系统) ──→ Phase 3 (互动系统)
    │                                        │
    │                                        └──→ Phase 4 (数据记录)
    │
    └──────────────────────────────────────────→ Phase 5 (Demo 整合)
```

---

## 四、开发优先级与时间估算

| Phase | 预估工时 | 优先级 | 阻塞风险 |
|-------|----------|--------|----------|
| Phase 0 | 0.5 天 | P0 | 低 |
| Phase 1 | 1 天 | P0 | 中（需准备素材） |
| Phase 2 | 1.5 天 | P0 | 中（核心逻辑） |
| Phase 3 | 1 天 | P0 | 低 |
| Phase 4 | 0.5 天 | P0 | 低 |
| Phase 5 | 1 天 | P0 | 低 |

**总计**：约 5.5 个工作日

---

## 五、风险与应对

| 风险 | 等级 | 应对措施 |
|------|------|----------|
| 素材准备延迟 | 高 | 使用占位视频/图片先行开发，后续替换 |
| 视频播放兼容性 | 中 | 选择 MP4/H.264 通用格式 |
| 前后端端口冲突 | 低 | 后端 8000，前端 5173，固定端口 |
| 状态同步问题 | 中 | 使用 Zustand 集中管理状态 |

---

## 六、验收清单

### Phase 0 验收
- [ ] 后端服务可启动，健康检查返回 ok
- [ ] 前端服务可启动，页面可访问
- [ ] 依赖安装无报错

### Phase 1 验收
- [ ] 猫咪待机动画循环播放
- [ ] 配置从 config.json 加载
- [ ] GET /api/pets 返回正确数据

### Phase 2 验收
- [ ] 点击礼物按钮触发动作
- [ ] 动作播放后返回待机
- [ ] 播放状态接口正确

### Phase 3 验收
- [ ] 完整 UI 界面可用
- [ ] 交互流畅无卡顿
- [ ] 所有按钮功能正常

### Phase 4 验收
- [ ] 互动记录持久化到 SQLite
- [ ] 统计数据接口正确
- [ ] 状态栏显示互动次数

### Phase 5 验收
- [ ] 端到端流程完整
- [ ] 无严重 Bug
- [ ] README 文档完整

---

*文档版本: v0.1*  
*最后更新: 2026-09-19*
