# Phase 1 / Step 1 完成报告

**版本**: v1.0  
**完成日期**: 2026-09-19  
**作者**: Q仔  
**阶段**: Phase 1 Step 1 — 地基与素材层（Foundation & Asset Layer）

---

## 一、完成内容

### 目标达成

完成「动作名 → 素材资源 → 可播放地址」的解析闭环：

```
Action Identifier  →  Asset Manager  →  Asset Metadata  →  Playable Resource
   {"pet_type":"cat",
    "action":"heart"}
                           ↓
                   {"asset_id": "cat_action_heart",
                    "asset_path": "assets/pets/cat/actions/heart/heart.mp4",
                    "duration": 1000}
```

### 交付项

| 序 | 交付项 | 状态 |
|----|--------|------|
| 1 | 项目目录骨架（backend / frontend / assets / database / tests） | ✅ |
| 2 | Asset Manager 模块（查询 / 解析 / 校验 / 登记） | ✅ |
| 3 | 15 个占位素材（cat/dog/panda × 5 动作） | ✅ |
| 4 | SQLite `assets` 表 + 初始化数据（cat × 5） | ✅ |
| 5 | 单元测试 33 项，全部通过 | ✅ |
| 6 | 禁止项自检（无播放逻辑、无事件逻辑） | ✅ |

### 未越界确认

| 禁止项 | 检查结果 |
|--------|----------|
| Playback Manager（播放 / 播放状态 / idle-playing） | ✅ 未实现 |
| EventSimulator（测试按钮 / 模拟点赞 / 模拟礼物） | ✅ 未实现 |
| Event API（接收直播事件 / WebSocket / 平台 SDK） | ✅ 未实现 |
| 前端动画逻辑（播放器组件 / UI 状态机） | ✅ 未实现 |
| 前端仅建目录骨架（无任何组件代码） | ✅ 符合 |

自检方式：扫描 `backend/app/**/*.py` 源码中的
`playback` / `event_gateway` / `simulator` / `websocket` / `platform`
关键字 —— **零命中**。

---

## 二、新增文件列表

### Backend（21 个文件）

| 路径 | 说明 |
|------|------|
| `backend/requirements.txt` | 依赖声明（Step 1 仅需 pytest） |
| `backend/pytest.ini` | pytest 配置 |
| `backend/scripts/init_assets.py` | 资产元数据初始化脚本 |
| `backend/app/__init__.py` | 包声明 |
| `backend/app/core/__init__.py` | 包声明 |
| `backend/app/core/constants.py` | 全局常量（路径 / 动作 / 错误码） |
| `backend/app/core/exceptions.py` | 业务异常定义（4 类） |
| `backend/app/core/logging_config.py` | 统一日志配置（禁止 print） |
| `backend/app/config/__init__.py` | 包声明 |
| `backend/app/config/settings.py` | 运行时配置 |
| `backend/app/models/__init__.py` | 包声明 |
| `backend/app/models/asset.py` | AssetRecord / AssetMetadata |
| `backend/app/repositories/__init__.py` | 包声明 |
| `backend/app/repositories/db.py` | SQLite 连接与初始化 |
| `backend/app/repositories/asset_repository.py` | assets 表 DAO |
| `backend/app/services/__init__.py` | 包声明 |
| `backend/app/services/asset_manager.py` | **Asset Manager 主模块** |
| `backend/app/api/__init__.py` | 占位（Step 1 不实现 API） |
| `backend/tests/__init__.py` | 包声明 |
| `backend/tests/conftest.py` | 测试夹具（完全隔离环境） |
| `backend/tests/test_asset_manager.py` | 单元测试（33 项） |

### Database（2 个文件）

| 路径 | 说明 |
|------|------|
| `database/schema.sql` | 建表脚本 |
| `database/pet_live.db` | SQLite 数据库（运行时生成，5 条数据） |

### Assets（15 个素材 + 3 个配置）

| 路径 | 说明 |
|------|------|
| `assets/pets/{cat,dog,panda}/actions/idle/idle.mp4` | 灰蓝 占位 |
| `assets/pets/{cat,dog,panda}/actions/heart/heart.mp4` | 红 占位 |
| `assets/pets/{cat,dog,panda}/actions/happy/happy.mp4` | 黄 占位 |
| `assets/pets/{cat,dog,panda}/actions/sad/sad.mp4` | 蓝 占位 |
| `assets/pets/{cat,dog,panda}/actions/surprise/surprise.mp4` | 紫 占位 |
| `assets/pets/{cat,dog,panda}/config.json` | 动作列表已同步更新 |

素材规格：`H.264 / 480×480 / 1.000s / yuv420p / faststart / ~2.4KB`
ffprobe 校验：全部可识别、可播放。

### Frontend（6 个骨架文件）

| 路径 | 说明 |
|------|------|
| `frontend/src/api/.gitkeep` | 目录占位 |
| `frontend/src/components/.gitkeep` | 目录占位 |
| `frontend/src/player/.gitkeep` | 目录占位 |
| `frontend/src/stores/.gitkeep` | 目录占位 |
| `frontend/src/types/.gitkeep` | 目录占位 |
| `frontend/tests/.gitkeep` | 目录占位 |

### Documentation（1 个文件）

| 路径 | 说明 |
|------|------|
| `docs/development/step1_completion.md` | 本报告 |

**统计：新增 45 个文件**（Backend 21 + Database 2 + Assets 15 + Frontend 6 + Docs 1）

---

## 三、Asset Manager 接口说明

### 模块定位

Phase 1 **支撑模块**。为播放层提供"动作 → 可播放资源"的解析能力。

**明确不做**：播放、播放状态管理、动作推荐、AI 决策、上传/CDN/缓存优化。

### 核心接口

#### `get_asset(pet_type, action) -> AssetMetadata`

主入口。查询资产元数据。

```python
meta = manager.get_asset("cat", "heart")
meta.asset_id      # "cat_action_heart"
meta.asset_path    # "assets/pets/cat/actions/heart/heart.mp4"
meta.duration      # 1000
meta.absolute_path # 绝对路径（内部校验用，不对外输出）
meta.to_dict()     # {"asset_id", "asset_path", "duration"}
```

**异常**：

| 异常 | code | 触发条件 |
|------|------|----------|
| `InvalidRequestError` | `INVALID_REQUEST` | 参数为空 / 含分隔符 / 路径穿越 |
| `AssetNotFoundError` | `ASSET_NOT_FOUND` | 元数据未登记 |
| `AssetFileMissingError` | `ASSET_FILE_MISSING` | 已登记但物理文件缺失 |

**关键约束**：查询失败**必须显式报错**，禁止自动拼接路径兜底，禁止返回空字符串。

#### `find_asset(pet_type, action) -> AssetMetadata | None`

宽容版查询：查不到返回 `None`。注意——**参数非法仍然抛异常**，宽容仅针对"查不到"。

#### `register(pet_type, action, path, duration) -> AssetMetadata`

登记或更新资产（幂等，`UNIQUE(pet_type, action)`）。

**设计要点**：登记是**声明**行为，素材文件允许后补，因此**不做文件存在性校验**（缺失仅记录警告）。
文件可用性由 `get_asset()` 在查询时强制校验。

> 这是 Step 1 开发中发现并修正的一处职责混淆：初版 `register()` 会因文件未就位而抛错，
> 导致"先登记后补素材"的正常流程走不通。

#### 辅助接口

| 方法 | 说明 |
|------|------|
| `exists(pet_type, action) -> bool` | 是否可用（已登记且文件存在） |
| `list_actions(pet_type) -> list[str]` | 该角色已登记的动作名 |
| `list_assets(pet_type) -> list[AssetMetadata]` | 该角色全部可用资产（跳过文件缺失项） |

### 装配方式

```python
from app.services.asset_manager import build_default_manager

manager = build_default_manager()          # 生产
manager = build_default_manager(settings)  # 测试（注入隔离配置）
```

装配链：`Settings → Database → AssetRepository → AssetManager`

### 数据表

```sql
CREATE TABLE assets (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_type  TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    path      TEXT    NOT NULL,
    duration  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (pet_type, action)
);
CREATE INDEX idx_assets_pet_type ON assets (pet_type);
CREATE INDEX idx_assets_action   ON assets (action);
```

---

## 四、测试结果

### 执行命令

```bash
cd backend
python -m pytest -q
```

### 结果

```
collected 33 items
tests/test_asset_manager.py ................................. [100%]
============================= 33 passed in 1.34s ==============================
```

**通过率：33/33 = 100%**

### 用例分布

| 分组 | 数量 | 覆盖内容 |
|------|------|----------|
| A1 正常查询 | 5 | 单动作 / asset_id / 契约字段 / duration / 五动作全覆盖 |
| A2 不存在动作 | 5 | ASSET_NOT_FOUND / **禁止路径猜测** / 不返回空串 / find_asset / exists |
| 多角色隔离 | 3 | cat↔dog 路径不混淆 / 不跨角色泄漏 / 动作列表按角色隔离 |
| 文件缺失 | 2 | ASSET_FILE_MISSING / 列表跳过缺失项 |
| 参数校验 | 11 | 空值 / 空白 / 路径穿越 / 分隔符 / duration 非法 / path 非法 |
| A3 免改代码 | 3 | 新增动作 / 新增角色 / upsert 幂等 |
| 空库边界 | 3 | 空库报错 / 未知角色空列表 / schema 存在 |

### 关键验收项

| 编号 | 验收项 | 结果 |
|------|--------|------|
| **A1** | `{"pet_type":"cat","action":"heart"}` → `heart.mp4` | ✅ 通过 |
| **A2** | `{"pet_type":"cat","action":"unknown"}` → `ASSET_NOT_FOUND` | ✅ 通过 |
| **A2+** | 磁盘有文件但未登记 → 仍报 ASSET_NOT_FOUND（不自动拼路径） | ✅ 通过 |
| **A3** | 新增 `cat/actions/test/test.mp4` 仅加数据即可访问 | ✅ 通过 |
| **多角色隔离** | `cat/heart` 与 `dog/heart` 路径不混淆 | ✅ 通过 |

### 真实环境验证（非测试环境）

| 验证项 | 结果 |
|--------|------|
| `get_asset("cat","heart")` | ✅ `cat_action_heart` → `assets/pets/cat/actions/heart/heart.mp4`，1000ms |
| 五个动作全查询 | ✅ idle / heart / happy / sad / surprise 全部命中 |
| 未登记角色 dog/panda | ✅ 正确返回 `ASSET_NOT_FOUND` |
| 非法参数（空值 / 穿越） | ✅ 正确返回 `INVALID_REQUEST` |
| A3 端到端（新增 test 动作） | ✅ 登记后立即可查，验证后已回滚 |
| 素材 ffprobe 校验 | ✅ 5/5 为 h264 / 480×480 / 1.000s |
| 数据库内容 | ✅ 5 条记录，索引与唯一约束正确 |

---

## 五、遗留问题

### 高优先级

| 编号 | 问题 | 影响 | 建议处理 |
|------|------|------|----------|
| L1 | ~~**duration 为硬编码常量 1000ms**，非从视频文件读取真实时长~~ → **已于 Step 1.1 修复**（ffprobe 真值化，见 `step1_1_completion.md`） | ~~若替换为真实动画（如 3.2s），元数据时长不符，可能导致播放超时兜底逻辑误判~~ → 已消除 | ✅ 已闭环 |
| L2 | dog / panda 素材已生成但**未入库**（超出 Step 1 指令范围） | 素材存在但查询不可用 | 需要时执行 `python -m scripts.init_assets --all` |
| L3 | `frontend/` 仅有目录骨架，无 `package.json` / 构建配置 | 前端不可运行（符合本 Step 范围） | Step 5 补全 |

### 中优先级

| 编号 | 问题 | 影响 | 建议处理 |
|------|------|------|----------|
| L4 | FastAPI / pydantic 未安装 | Step 4 挂 API 时需补装 | 已在 `requirements.txt` 中注释预留 |
| L5 | SQLite 连接未做连接池 / 并发保护 | 单线程可用，并发写入可能 `database is locked` | Phase 2 引入 WebSocket 时评估 |
| L6 | 素材为纯色占位，非真实动画 | 无法验证视觉表现 | 素材替换由设计侧推进，不影响机制验证 |

### 低优先级

| 编号 | 问题 | 建议 |
|------|------|------|
| L7 | `Database.connect()` 每次新建连接，无长连接 | Phase 1 事件量小，无需优化 |
| L8 | 未加 `ruff` / `mypy` 静态检查 | 待代码量增长后引入 |
| L9 | 未初始化 git 仓库（无法验证 `.gitignore` 是否生效） | 需要时初始化，注意忽略 `.env` / `*.db` |

### 已知设计权衡（非缺陷）

| 项 | 说明 |
|----|------|
| 双异常码 `ASSET_NOT_FOUND` / `ASSET_FILE_MISSING` | 指令只要求前者；拆分后能区分"没登记"与"登记了但文件丢了"，排错更快 |
| 路径存相对项目根 | 便于跨机器迁移；绝对路径在运行时解析 |
| `register()` 不校验文件 | 有意的职责分离，见第三节说明 |

---

## 六、Step 1 完成标志核对

| 完成条件 | 结果 |
|----------|------|
| [x] 项目目录存在 | ✅ backend / frontend / assets / database / tests 全部就位 |
| [x] Asset Manager 可查询 | ✅ A1 验收通过 |
| [x] 五个占位素材存在 | ✅ 15 个 mp4（cat/dog/panda × 5），ffprobe 校验可播放 |
| [x] Asset metadata 可读取 | ✅ SQLite 5 条记录，索引与约束正确 |
| [x] 单元测试通过 | ✅ 33/33 = 100% |
| [x] 未引入播放逻辑 | ✅ 源码关键字扫描零命中 |
| [x] 未引入事件逻辑 | ✅ 源码关键字扫描零命中 |

**Step 1 全部完成条件已满足。**

---

*报告版本: v1.0*  
*最后更新: 2026-09-19*
