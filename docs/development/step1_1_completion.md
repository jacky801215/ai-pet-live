# Step 1.1 完成报告

**任务名称**：Asset Metadata 真值化 + Git 基础初始化
**任务类型**：修正任务（不进入 Step 2）
**完成日期**：2026-09-19
**执行人**：Q仔（AI 开发负责人）

---

## 一、完成内容

### 任务 A：Asset duration 真值化

| 项 | 内容 |
|----|------|
| 新增 ffprobe duration extractor | `backend/app/services/asset_duration.py` —— 职责单一：`file_path → duration_ms` |
| Asset Manager 接入真实 duration | `register()` 未显式传 duration 时调用 ffprobe 探测；移除 `PLACEHOLDER_DURATION_MS` 常量 |
| 新增异常 | `ASSET_METADATA_ERROR`（`AssetMetadataError`），覆盖文件不存在 / ffprobe 失败 / 输出不可解析 |
| 初始化数据库更新 | `database/pet_live.db` 重新生成，duration 全部来自 ffprobe |
| 统一时长来源 | `init_assets.py` 改为调用 `AssetManager.register()`，而非自行写死时长 —— 全项目只有**一条**时长来源 |

### 任务 B：Git 初始化规则

| 项 | 内容 |
|----|------|
| 新增 `.gitignore` | 覆盖 Python 缓存 / 环境文件 / 数据库 / 前端依赖 / 构建产物 / IDE / OS |
| 保留规则 | `database/schema.sql` 必须入库，仅忽略 `*.db` / `*.sqlite` |
| git 仓库初始化 | `D:\AI-Pet-Live\.git` 已建立 |
| 生效验证 | `git check-ignore` + 造真实文件双重验证，泄漏条目为 0 |

---

## 二、修改文件列表

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/asset_duration.py` | **新增** | ffprobe 时长提取器（`get_duration_ms` / `resolve_ffprobe`） |
| `backend/tests/test_asset_duration.py` | **新增** | 19 个 duration 专项用例 |
| `.gitignore` | **新增** | 版本控制隔离规则 |
| `docs/development/step1_1_completion.md` | **新增** | 本报告 |
| `backend/app/core/exceptions.py` | 修改 | 新增 `AssetMetadataError`（code = `ASSET_METADATA_ERROR`） |
| `backend/app/core/constants.py` | 修改 | 删除 `PLACEHOLDER_DURATION_MS`，改为说明注释 |
| `backend/app/config/settings.py` | 修改 | 新增 `project_root`、`ffprobe_path`（支持 `FFPROBE_PATH` 环境变量） |
| `backend/app/services/asset_manager.py` | 修改 | `register()` 接入 ffprobe；新增 `_resolve_duration()`；清理无用导入 |
| `backend/app/repositories/asset_repository.py` | 修改 | 新增 `delete_all()`（`--reset` 所需） |
| `backend/scripts/init_assets.py` | 修改 | 改用 `AssetManager.register()`；新增 `SeedReport`；素材缺失跳过不中断 |
| `backend/tests/conftest.py` | 修改 | 新增 `make_media_file()`（ffmpeg 生成真实媒体）+ `FFMPEG_BIN` |
| `database/pet_live.db` | **重新生成** | 5 条 cat 资产，duration 来自 ffprobe |
| `docs/development/step1_completion.md` | 修改 | L1（duration 硬编码）标注为已修复 |

**未修改（守住边界）**：`database/schema.sql` 表结构、Asset API 契约、`assets/` 素材、
`frontend/`（仍为空骨架）、所有 Step 2/3/4 相关模块（均不存在）。

---

## 三、测试结果

### pytest

```
============================= test session starts =============================
collected 52 items

tests\test_asset_duration.py ...................                         [ 36%]
tests\test_asset_manager.py .................................            [100%]

============================= 52 passed in 5.26s ==============================
EXIT CODE: 0
```

| 分类 | 数量 | 说明 |
|------|------|------|
| 原 Step 1 用例 | 33 | 全部保持通过（T5 回归） |
| 新增 duration 用例 | 19 | T1~T4 全覆盖 + 边界 |
| **合计** | **52 passed** | 0 failed / 0 skipped |

### ffprobe

| 验证 | 输入 | 输出 | 结果 |
|------|------|------|------|
| 真实素材原始输出 | `cat/actions/heart/heart.mp4` | ffprobe stdout = `'1.000000'` | ✅ |
| `get_duration_ms` 转换 | 同上 | `1000` ms | ✅ |
| **非 1 秒素材** | 2.5 秒测试素材 | `2500` ms | ✅ 非硬编码 |
| 落库一致性 | 2.5 秒素材 register 后查库 | `2500` ms（register 返回值与库内一致） | ✅ |
| 素材可播放性 | 5 个 cat 动作 mp4 | h264 / 480×480 / 1.000s | ✅ |

### 数据库

```
action      duration    path
happy       1000        assets/pets/cat/actions/happy/happy.mp4
heart       1000        assets/pets/cat/actions/heart/heart.mp4
idle        1000        assets/pets/cat/actions/idle/idle.mp4
sad         1000        assets/pets/cat/actions/sad/sad.mp4
surprise    1000        assets/pets/cat/actions/surprise/surprise.mp4
```

> ⚠️ **必须注意**：这里 5 条都是 `1000ms`，**不是**因为仍在硬编码，
> 而是因为占位素材本身就是 1 秒（指令要求「时长约 1 秒」）。
> 区分旧实现与新实现的决定性证据是上面表格里的 **2.5 秒 → 2500ms**；
> 以及测试 `test_register_duration_is_not_hardcoded`（1s 与 3s 素材登记后 duration 必须不同）。

---

## 四、验收表

| 项目 | 结果 | 证据 |
|------|------|------|
| duration 非硬编码 | ✅ | 2.5s 素材 → 2500ms；1s 与 3s 登记结果不同 |
| duration 来源为 ffprobe | ✅ | `asset_duration.py` 子进程调用 ffprobe，无手工解析 |
| Asset Manager 无硬编码 duration | ✅ | `PLACEHOLDER_DURATION_MS` 已删除；`register` 走 `_resolve_duration()` |
| 3 秒素材读取 | ✅ | T2：3000ms ± 100ms 通过 |
| 异常处理 | ✅ | T3：`ASSET_METADATA_ERROR`（文件不存在/目录/非法媒体/ffprobe 缺失） |
| 数据库重新生成 | ✅ | `SELECT action,duration FROM assets` 返回 5 条 |
| 原 33 测试保持 | ✅ | 52 passed = 33 + 19 |
| .gitignore 生效 | ✅ | `check-ignore` 全项 IGNORED；造真实文件后泄漏条目 = 0 |
| `database/schema.sql` 未被误忽略 | ✅ | `check-ignore` 返回 TRACKABLE |
| 未引入 Step 2 内容 | ✅ | 文件级/源码级关键字扫描：EventGateway / SimulatorAdapter / Event API 零命中 |
| 未引入 Step 3/4 内容 | ✅ | PlaybackManager / WebSocket / FastAPI 零命中 |
| 未引入前端代码 | ✅ | `frontend/` 仅 6 个 `.gitkeep` |

### Git 检查结果（`git status --untracked-files=all`）

未跟踪条目 62 个，**不包含**：

- ❌ `database/pet_live.db` —— 未出现 ✅
- ❌ `__pycache__` —— 未出现 ✅
- ❌ `.env` —— 未出现 ✅

---

## 五、设计说明与偏离项

### 1｜`register(duration=None)` 保留了显式覆盖参数

指令只要求「duration 改为 ffprobe 读取」。我把签名改为 `duration: int | None = None`：

- `None`（默认，**生产路径**）→ ffprobe 探测
- 显式整数（**测试注入**）→ 直接采用

理由：33 个既有用例中 7 处依赖显式注入。若直接移除该参数，要么破坏回归，要么让测试去生成真实媒体。
保留覆盖参数后，两条路径都健康：生产不猜测，测试不依赖外部二进制。

### 2｜异常字段名用 `code` 而非 `error`

指令示例为 `{"error":"ASSET_METADATA_ERROR", ...}`，实际输出为：

```json
{"code": "ASSET_METADATA_ERROR", "message": "Cannot read media duration", "context": {...}}
```

**偏离原因**：`PetLiveError.to_dict()` 是 Step 1 已确立的全局契约（`code` / `message` / `context`），
`ASSET_NOT_FOUND`、`ASSET_FILE_MISSING` 均沿用。单独为本次新异常改用 `error` 会造成项目内两种错误格式并存。
若你要求严格对齐指令示例，我可以统一改字段名 —— 但那会牵动三个既有异常与全部相关断言。

### 3｜新增 `ASSET_FILE_MISSING` 与 `ASSET_METADATA_ERROR` 的分工

| 异常 | 触发场景 | 语义 |
|------|----------|------|
| `ASSET_FILE_MISSING` | 已登记，查询时文件丢了 | 元数据在，素材不在 |
| `ASSET_METADATA_ERROR` | 登记时读不出时长（文件不存在/损坏/ffprobe 挂） | 无法建立元数据 |

两者不可合并：前者是**查询期**问题，后者是**登记期**问题。

### 4｜`init_assets.py` 的装配方式调整

不再使用 `build_default_manager()`，改为显式构造 `Database → AssetRepository → AssetManager`。
原因：`--reset` 需要调 `repository.delete_all()`，而 `build_default_manager()` 不暴露仓储。
顺带避免了访问 `manager._repo._database` 这类私有链路。同时新增了仓储层 `delete_all()`（数据操作属仓储职责）。

---

## 六、遗留问题

| 编号 | 问题 | 影响 | 建议处理 |
|------|------|------|----------|
| M1 | **素材替换后元数据会过期** | 换掉 `heart.mp4`（如 3.2s）若未重跑 `init_assets`，库内仍是旧时长，Step 4 超时兜底会误判 | 在 `init_assets` 加 `--verify` 模式，或 Step 4 装配时做一次一致性校验 |
| M2 | **ffprobe 成为运行时依赖** | 部署环境缺 ffmpeg 会导致登记失败（查询不受影响） | 部署文档需声明 FFmpeg 依赖；已支持 `FFPROBE_PATH` 环境变量 |
| M3 | `init_assets --reset` 会丢失 dog/panda 记录 | `--reset` 清空全表后只重建 `cat`（默认角色） | 需要多角色时用 `--reset --all`；建议后续把 `--reset` 的默认行为改为「按当前 pet_types 删除」 |
| M4 | **git 仓库已 init 但零提交** | 尚无基线快照，隔离效果未经过真实提交检验 | 建议尽快做首次提交（`PROJECT_RULES` 要求 `feat:` / `fix:` / `refactor:` / `docs:` 前缀）。我未自行提交 —— 分支策略（是否走 `feature/模块名`）由你决定 |
| M5 | `database/pet_live.db` 已被 git 忽略 | 新克隆的仓库无数据库，必须手动初始化 | 属预期设计；需在 README 补充 `python -m scripts.init_assets --reset` 步骤 |
| M6 | 占位素材仍是纯色 | 无法验证视觉表现 | 不阻塞机制验证，素材替换由设计侧推进 |

---

## 七、Step 1.1 完成条件核对

- [x] duration 来源变为 ffprobe
- [x] Asset Manager 无硬编码 duration
- [x] 数据库重新生成
- [x] 新增 duration 测试（19 个）
- [x] 原测试全部通过（33 个）
- [x] `.gitignore` 生效
- [x] 未引入 Step 2/3/4 内容

**结论**：Step 1.1 全部完成条件满足。基础设施层已具备可信元数据来源与版本控制隔离，
可以进入 Step 2（Event Layer 设计与实现准备）。

---

*报告生成时间：2026-09-19 13:21*
