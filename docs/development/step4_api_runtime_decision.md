# AI Cat FastAPI Runtime Boundary v1.0

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.3-B-1-0
> **定位**：FastAPI **运行时 / 依赖 / 入口 / 路由 / 测试 / 静态资源**六条实现边界的**唯一准绳**。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_api_implementation_boundary.md`（v1.0 FROZEN）—— DA-1 / DA-3 / DA-5 / DA-7 / DA-8
> - `docs/development/step4_api_contract_decision.md`（v1.0 FROZEN）—— API-1–API-5、DA-2 / DA-4 / DA-6
> - `docs/development/step4_data_layer_decision.md`（v1.0 FROZEN）—— D1–D4
> - `PROJECT_RULES.md` §十四（`### 数据层与统计边界` / `### API 与跨进程边界` / `### API Implementation Boundary`）
>
> **本步边界**：**只冻结，不实现**。不建 `main.py`、不建路由、**不安装任何依赖**、不改 `requirements.txt`、
> 不改 `backend/**/*.py`、不改 `frontend/**`、不改 `database/schema.sql`。落地属 **Step 4.3-B-1**。

---

## 前置偏差与编号对照

### §一 强制前置检查（实测，全部通过）

| 项 | 期望 | 实测 |
|----|------|------|
| branch | `phase1-step1-foundation` | ✅ |
| HEAD | `3cedf2c` | ✅ `3cedf2cd06e5…` |
| working tree | clean | ✅ 空 |
| `step4_api_implementation_boundary.md` | v1.0 FROZEN | ✅ 含 `v1.0（FROZEN）`，197 行 |
| `backend/app/main.py` | 未创建 | ✅ 不存在 |
| `backend/app/routes/` | 未创建 | ✅ 不存在 |
| `backend/app/api/routes.py` | 未创建 | ✅ 不存在 |
| `backend/app/api/app.py` | 未创建 | ✅ 不存在 |

### ⚠️ `DB-*` 编号对照（本步与 4.3-B-0 的标签冲突）

本步 §四 给出的 **DB-1 ~ DB-6** 与 4.3-B-0 文档 Deferred 表中的 **DB-1 ~ DB-5** **编号相同、含义不同**。
本步**以本步定义的编号为准**；引用旧文档时一律写作 `4.3-B-0/DB-n` 以消歧。

| 本步编号 | 含义 | 对应 4.3-B-0 的条目 |
|----------|------|----------------------|
| **DB-1** | Python Runtime 选择 | `4.3-B-0/DB-1`（后半：解释器选择） |
| **DB-2** | 依赖启用方式 | `4.3-B-0/DB-1`（前半：依赖启用） |
| **DB-3** | 应用入口 | `4.3-B-0/DB-2` |
| **DB-4** | Router 位置 | （本步新增） |
| **DB-5** | 测试入口 | （本步新增） |
| **DB-6** | CORS | `4.3-B-0/DB-4` |
| **DB-R1** | 测试环境素材目录（残留） | `4.3-B-0/DB-3` —— **本步未覆盖** |
| **DB-R2** | 未知查询参数口径（残留） | `4.3-B-0/DB-5` —— **本步未覆盖** |

### §二 关键实测（裁决的事实基础）

| # | 项 | 实测结果 |
|---|----|----------|
| 1 | **依赖清单文件** | **仅** `backend/requirements.txt`；**无** `pyproject.toml` / `setup.py` / `setup.cfg` / `requirements-dev.txt` / `Pipfile` / `tox.ini` / `Makefile` / `.python-version` |
| 2 | **虚拟环境** | **无** `.venv` / `venv` / `env`（全仓扫描 `pyvenv.cfg` 为 0） |
| 3 | **CI / 脚本** | **无**（无 `.github/workflows`、无 `scripts/`） |
| 4 | **依赖声明现状** | `pytest>=7.4` 生效；`fastapi>=0.110` / `uvicorn>=0.27` / `pydantic>=2.6` **被注释**（"Phase 1 Step 4 起启用"） |
| 5 | **测试框架依赖** | 测试目录内 **零** `fastapi` / `TestClient` / `httpx` / `starlette` / `asyncio` 命中 —— 现有 409 个测试**纯标准库 + pytest** |
| 6 | **包结构** | `backend/app/` = `api`(空骨架) / `config` / `core` / `models` / `repositories` / `services`；**无入口文件** |

**⭐ 解释器能力矩阵（本步最重要的实测）**

| 解释器 | fastapi | pydantic | uvicorn | starlette | httpx | **pytest** |
|--------|---------|----------|---------|-----------|-------|-----------|
| 受管 **3.13.12**（现有测试所用） | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| 系统 **3.11.9** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

⇒ **当前没有任何一个解释器同时具备「跑测试」与「跑 FastAPI」两项能力**：
3.13 有 pytest 但缺 fastapi / pydantic；3.11 有 fastapi / pydantic 但缺 pytest。
这正是 DB-1 与 DB-2 必须成对裁决的原因。

---

## Runtime

### DB-1 裁决 —— **采用 B：Web 层固定 Python 3.11；测试环境随之迁移到 3.11**

| 项 | 冻结内容 |
|----|----------|
| **运行时** | CPython **3.11.x**（本机：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`，实测 3.11.9） |
| **测试解释器** | **与运行时一致 = 3.11**（"测试环境迁移"），即 API 测试与既有 409 个测试**同一解释器**运行 |
| **FastAPI 支持范围** | `fastapi>=0.110` / `pydantic>=2` 均支持 Python 3.8+，3.11 属**稳定长期**区间 |
| **排除 A（继续用 3.13）** | 3.13 上 `fastapi` / `pydantic` **均缺失**，需从零安装；且 3.13 属较新生态，第三方 wheel 兼容面更窄 |
| **排除 C（不固定版本）** | 会让「本机能跑、别处跑不起来」不可复现；项目已有「唯一来源」的既有约定 |

**采用 B 的理由**：3.11 是当前 FastAPI 生态最稳的长期版本；系统 3.11.9 **已装好** fastapi / pydantic / uvicorn / starlette / httpx（实测），
迁移成本仅剩「补装 pytest 一项」，且能避免 3.13 新生态的兼容风险。

**⚠️ 迁移代价（必须在 4.3-B-1 落地，本步不执行）**：系统 3.11.9 **缺 pytest**
⇒ 需在 3.11 下安装 `pytest>=7.4`，并**复测既有 409 个测试在 3.11 下全绿**，
否则「测试环境迁移」不成立（这是 DB-1 唯一的实际风险点）。

**记录（不作为结论）**：现状 409 个测试当前在受管 3.13.12 下全绿（本次会话实测）。

---

## Dependencies

### DB-2 裁决 —— **正式启用**（`requirements.txt` 取消注释，改为正式依赖）

`backend/requirements.txt`（Step 4.3-B-1 落地后的目标形态）：

```
# --- 测试 ---
pytest>=7.4

# --- Web 层（Phase 1 Step 4.3-B-1 起正式启用）---
fastapi>=0.110
uvicorn>=0.27
pydantic>=2.6
```

| 项 | 冻结内容 |
|----|----------|
| **启用方式** | **取消注释**（正式依赖），**不是**手动环境安装 |
| **理由** | 依赖清单是**唯一来源**：手动装会让「本机可跑」与仓库可复现性脱钩；注释态会让 CI/新机器漏装 |
| **版本策略** | 保持 `>=` 下限声明（与既有 `pytest>=7.4` 一致），**本步不引入 lock 文件 / pin 精确版本** |
| **新增传递依赖** | `httpx`（`TestClient` 需要）—— 见 DB-5；实测两解释器**均已具备**，故 `requirements.txt` **不额外声明**（FastAPI/starlette 生态外置，Phase 1 不展开） |
| **禁止** | ❌ 在代码中 `try: import fastapi` 做可选降级 ❌ 把依赖装进受管解释器而不更新清单 ❌ 引入 poetry / pipenv 等新工具链 |

---

## Application Entry

### DB-3 裁决 —— **`backend/app/main.py`**

```python
# backend/app/main.py（结构示意，落地属 Step 4.3-B-1）
app = FastAPI(...)
# 1) include_router —— 挂载 app/api/ 下的路由
# 2) app.mount("/assets/pets", StaticFiles(...)) —— 见「Static Assets」
```

| 职责（**允许**） | 内容 |
|------------------|------|
| 应用构造 | `app = FastAPI(...)` 与元信息 |
| 路由挂载 | `include_router(...)`，路由本体在 `app/api/**` |
| 静态挂载 | `/assets/pets` → `StaticFiles`（DA-5） |
| 中间件 / CORS | 按 DB-6 |
| 全局异常处理 | 按 DA-3（`PetLiveError` 映射 + `INTERNAL_ERROR` 兜底） |

| **禁止**（越界即破坏分层） |
|----------------------------|
| ❌ 业务逻辑（规则匹配 / 动作决策） |
| ❌ SQL 或任何 `sqlite3` 使用（按 `PROJECT_RULES` §十四「API Implementation Boundary」：SQL 只允许在 `repositories/**` 与 `data_manager.py`） |
| ❌ 直接调用 `ActionEngine` / `InteractionEngine` / `PlaybackManager`（必须经 API 层编排） |
| ❌ 直接持有 `Database` / 建表 / 初始化数据 |
| ❌ 定义路由处理函数（路由属 `app/api/**`） |

**入口命名唯一性**：**只允许** `backend/app/main.py` 作为 ASGI 入口；
**禁止** `backend/app/api/app.py`、`backend/app/routes/`、`backend/app/services/api_service.py`（§一 已确认三者均不存在）。

---

## Router Boundary

### DB-4 裁决 —— 路由归属 **`backend/app/api/`**

```
backend/app/api/
├── __init__.py     # 已存在（Step 1 空包，0 字节）—— 4.3-B-1 可放 APIRouter 汇总
├── events.py       # POST /api/events/simulate            （API-1）
├── playback.py     # GET  /api/playback/state              （API-2）
└── stats.py        # GET  /api/stats、GET /api/events/recent（API-3）
```

| 项 | 冻结内容 |
|----|----------|
| **归属** | `backend/app/api/`（**复用 Step 1 已存在的空包**，避免另起目录） |
| **文件划分** | 按**契约分组**：`events` / `playback` / `stats` 三个模块，一一对应 API-1 / API-2 / API-3 |
| **路由层职责** | 协议转换（HTTP ↔ 基本类型）、参数校验（DA-7 `extra="forbid"`）、调用编排、响应组装 |
| **路由层禁止** | ❌ SQL ❌ 业务规则 ❌ 素材路径解析（归 AssetManager）❌ 直接持有 `Database` |
| **禁止** | ❌ `backend/app/services/api_service.py`（API 编排**不得**藏进 services 层，会与既有 6 个 service 的职责混淆）❌ `backend/app/routes/`（同义重复目录） |

**分层落点（与 DA-1 一致）**：路由 → `DataManager`（写）/ `EventRepository`·`StatRepository`（读）。

---

## Testing Boundary

### DB-5 裁决 —— 新增 **`backend/tests/test_api_contract.py`**，使用 `TestClient`

| 项 | 冻结内容 |
|----|----------|
| **测试文件** | `backend/tests/test_api_contract.py`（**新增**，落地属 4.3-B-1） |
| **测试手段** | `fastapi.testclient.TestClient`（同步接口，**不引入** `pytest-asyncio` / `httpx.AsyncClient`） |
| **覆盖范围（契约级）** | ① `POST /api/events/simulate`（含 API-1 反例：发 `action` / `action_type` / `asset_url` / 白名单外 `event_type` ⇒ 400）② `GET /api/playback/state` ③ `GET /api/stats` ④ `GET /api/events/recent` ⑤ **错误契约**（`{code,message}` 三码 + 未知顶层字段 400 + 非法 `limit` 400） |
| **隔离要求** | 复用 `conftest.py` 的临时 `project_root` + 临时 SQLite + `schema_path=constants.SCHEMA_PATH`（**真实 DDL**），**不触碰**真实 `database/pet_live.db` |
| **禁止** | ❌ 真起 uvicorn 端口做 HTTP 直连（`TestClient` 足够，S-3）❌ 断言 HTML / 前端产物（前端属 4.1-C） |

**本步约束（§二.3 的要求）**：现有测试**不依赖** `TestClient` / `httpx` / `fastapi`（实测零命中），
故**本步不提前引入**任何测试依赖；`httpx` 在 4.3-B-1 由 `TestClient` 隐式使用（两解释器实测均已具备）。

---

## Static Assets

**沿用 4.3-B-0 的 DA-5 裁决（A）**，本步仅确认运行时口径：

| 项 | 冻结内容 |
|----|----------|
| 挂载 | `app.mount("/assets/pets", StaticFiles(directory=<PROJECT_ROOT>/assets/pets), name="assets")` |
| 挂载点唯一 | **只有** `/assets/pets`；**禁止**挂载项目根 |
| `asset_url` | `"/" + asset_path`（`asset_path` 已含 `assets/pets/`，与 `ASSET_URL_PREFIX="/assets/pets"` 自洽） |
| 生产素材目录 | 真实目录 `<PROJECT_ROOT>/assets/pets`（已存在 `cat` / `dog` / `panda` + `config.json`） |
| ⚠️ 测试素材目录 | `StaticFiles` 要求目录**存在**，否则**导入即抛错**。测试环境如何提供 `assets/pets` **本步未裁决** → **DB-R1** |

---

## CORS

### DB-6 裁决 —— **采用 A：Phase 1 启用，仅放行 localhost 开发源**

| 项 | 冻结内容 |
|----|----------|
| **结论** | **启用** CORS 中间件（`CORSMiddleware`），**白名单式**放行本机开发源 |
| **允许源** | `http://localhost:5173`、`http://127.0.0.1:5173`（Vite dev server 默认端口） |
| **允许方法** | `GET` / `POST`（Phase 1 契约只有这两种） |
| **允许头** | `Content-Type`（Phase 1 全 JSON，无自定义头、无凭证） |
| **允许凭证** | **否**（`allow_credentials=False` —— 无会话/无 Cookie） |
| **理由** | 下一阶段 **UI Prototype（4.1-C）** 的前端 dev server 与后端**不同源**，不放行将直接被浏览器拦断，UI 无法联调 |
| **排除 B（暂不启用）** | 会让 4.1-C 联调第一步就卡在跨域，被迫追加改动；提前一条中间件比事后排查便宜 |
| **禁止** | ❌ `allow_origins=["*"]`（与白名单式放行矛盾）❌ 放行任意 `0.0.0.0` / 外网源 ❌ 生产环境沿用本配置（生产部署另裁） |

---

## Deferred

| # | 事项 | 状态 / 处理 |
|---|------|-------------|
| **DB-R1** | **测试环境的静态素材目录**（`StaticFiles` 要求目录存在，测试不得用真实 `database/`；是否给 `tmp_path/assets/pets` 或指向真实目录） | 本步未覆盖（残留自 `4.3-B-0/DB-3`）→ **4.3-B-1 必须裁决**，否则应用**导入即失败** |
| **DB-R2** | **未知查询参数**口径（如 `GET /api/stats?x=1`：拒绝 or 忽略） | 本步未覆盖（残留自 `4.3-B-0/DB-5`）→ 4.3-B-1 |
| **DR-1** | **3.11 下补装 pytest 并复测既有 409 测试** | DB-1=B 的必要前置；4.3-B-1 首个动作 |
| **DR-2** | **`uvicorn` 启动方式**（`uvicorn app.main:app --reload` 的 host / port / reload 口径） | 属运维口径，非契约；4.3-B-1 或运行文档 |
| **DR-3** | **`httpx` 是否需显式写入 `requirements.txt`** | 当前由 FastAPI 测试生态隐式提供；若新机器缺则需补声明 |
| **DR-4** | **是否引入 `python-multipart`**（表单/文件上传用） | Phase 1 全 JSON，**暂不需要**；如 UI 改表单再评估 |
| **DA-4** | `asset_url` 精确形态（是否含 `/actions/{action}/`） | 证据指向 `/` + `asset_path`；4.3-B-1 定稿 |
| **DA-6** | 事件细码（`EVENT_*`）是否直接作为 API `code` | 保持折叠（4.3-A）；需精确区分则提 Change Request |
| **DA-8** | `events` 保留策略 | Phase 1 不实现清理（4.3-B-0 裁决 C） |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 **DB-1 = B**（Web 层与测试环境统一为 Python 3.11）、**DB-2 = 正式启用**（`requirements.txt` 取消注释）、**DB-3 = `backend/app/main.py`**（零业务逻辑 / 零 SQL）、**DB-4 = `backend/app/api/{events,playback,stats}.py`**（禁 `api_service.py`）、**DB-5 = `backend/tests/test_api_contract.py`**（`TestClient`，契约级覆盖）、**DB-6 = A**（CORS 允许 localhost dev）。另记录 `DB-*` 编号冲突对照与残留项 DB-R1 / DB-R2。 |
