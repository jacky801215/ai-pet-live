> ⚠️ **本文档已废弃（2026-09-19）**
>
> 本文件为早期开发计划草稿，其阶段划分（阶段一~三）已被取代。
>
> 权威版本请见：
> - 开发计划：`docs/development/development_plan.md`（v0.2，Phase 1~4）
> - 系统架构：`docs/architecture/system_architecture.md`（v0.2）
> - 技术路线：`docs/product/technical_route.md`
>
> 保留此文件仅作历史追溯，请勿据此开发。

---

# AI Pet Live - 开发计划

## 阶段一：MVP 本地 Demo

### 任务列表

| 任务 | 优先级 | 说明 | 状态 |
|------|--------|------|------|
| 项目初始化 | P0 | 创建目录结构、配置依赖 | 待开发 |
| 后端 API | P0 | FastAPI 基础路由、动作接口 | 待开发 |
| 前端组件 | P0 | Stage、PetDisplay、ControlPanel | 待开发 |
| 素材准备 | P1 | 猫角色视频/图片/音效 | 待开发 |
| 集成测试 | P1 | 端到端验证核心流程 | 待开发 |

### 后端模块开发顺序

```
1. backend/app/models/pet.py           - 数据模型
2. backend/app/config/settings.py      - 配置管理
3. backend/app/services/asset_manager.py - 素材管理器
4. backend/app/services/action_engine.py - 动作引擎（核心）
5. backend/app/services/platform_bridge.py - 平台桥接（预留接口）
6. backend/app/api/routes.py           - API 路由
7. backend/main.py                     - 入口
```

### 前端组件开发顺序

```
1. frontend/src/components/StatusBar.tsx   - 状态栏
2. frontend/src/components/PetDisplay.tsx  - 宠物展示
3. frontend/src/components/ControlPanel.tsx - 控制面板
4. frontend/src/components/Stage.tsx       - 直播画面
5. frontend/src/App.tsx                    - 主组件
6. frontend/src/main.tsx                   - 入口
```

## 阶段二：真实平台接入

- 抖音直播 API 适配
- YY 直播 API 适配
- 评论/礼物事件处理

## 阶段三：多角色扩展

- 狗角色框架（assets/pets/dog/）
- 熊猫角色框架（assets/pets/panda/）
- 角色管理系统（动态加载 config.json）
