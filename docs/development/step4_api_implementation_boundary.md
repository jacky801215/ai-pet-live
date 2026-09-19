# AI Cat API Implementation Boundary v1.0

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.3-B-0
> **定位**：`step4_api_contract_decision.md`（v1.0 FROZEN）遗留 **DA 项**的落地裁决；**只冻结实现边界，不实现**。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_api_contract_decision.md`（v1.0 FROZEN）—— API-1–API-5、DA-1–DA-8
> - `docs/development/step4_data_layer_decision.md`（v1.0 FROZEN）—— D1–D4（DataManager 边界、只读查询归 Stats API）
> - `docs/development/step4_ui_prototype_decision.md`（v1.0 FROZEN）—— UI-1–UI-6
> - `PROJECT_RULES.md` §十四（`### 播放与素材边界` / `### UI 与后端边界` / `### 数据层与统计边界` / `### API 与跨进程边界`）
>
> **本步边界**：**只冻结，不实现**。不建路由、不建应用入口、不装依赖、不写仓储、不改 `backend/**/*.py`、
> 不改 `frontend/**`、不改 `database/schema.sql`。落地属 **Step 4.3-B-1**。

---

## 前置偏差与裁决（实测）

| 项 | 指令假设 | 实测 | 裁决 |
|----|----------|------|------|
| `backend/app/routes/` | 不存在 | ❌ 不存在 ✅ | 一致 |
| `backend/app/api/routes.py` | 不存在 | ❌ 不存在 ✅ | 一致 |
| `backend/app/services/api_service.py` | 不存在 | ❌ 不存在 ✅ | 一致 |
| **`frontend/src/api/*`** | 不存在 | ⚠️ 目录存在，内含 `frontend/src/api/.gitkeep`（0 字节） | 已 STOP 报告 → **用户裁决「视为无害，继续」**（同 Step 4.3-A 先例）；本步不改 `frontend/` |

### §二 关键实测（决定后续裁决的事实基础）

| # | 项 | 实测结果 |
|---|----|----------|
| 1 | **FastAPI 依赖** | `backend/requirements.txt` 中 `fastapi` / `uvicorn` / `pydantic` **被注释预留**（"Phase 1 Step 4 起启用"），**非生效依赖**。探测：受管 3.13.12 → fastapi ❌ pydantic ❌；系统 3.11.9 → 全部 ✅ |
| 2 | **应用入口** | **不存在**：全仓无 `main.py` / `app.py` / `asgi.py` / `wsgi.py`；源码零 `FastAPI(` / `create_app` / `APIRouter` / `include_router` 命中 |
| 3 | **Asset 路径来源** | `constants.ASSETS_ROOT = PROJECT_ROOT/"assets"/"pets"`；实体 `assets/pets/{pet_type}/actions/{action}/{action}.mp4` |
| 4 | **URL 前缀来源** | `constants.ASSET_URL_PREFIX = "/assets/pets"`（注释："供 Phase 4 播放层使用"） |
| 5 | **AssetManager 是否产出 URL** | **否** —— URL 相关代码 **0 处**；只产出 `AssetMetadata.asset_path`（相对路径，已含 `assets/pets/`） |
| 6 | **静态挂载方案** | **不存在** —— 全仓无 `StaticFiles` / `mount(`（命中的 `static` 均为 `@staticmethod`） |

---

## DA-1 Read Query Boundary

### 裁决 —— **采用 B**

> **B：新增 `backend/app/repositories/event_repository.py` 与 `backend/app/repositories/stat_repository.py`**（Step 4.3-B-1 落地）

**冲突回顾**：API 层不得直接 SQL（API-3）；`DataManager` 目前只有 3 个写 API（Step 4.2-B 冻结），无只读出口。

**三方案评审**

| 方案 | 内容 | 结论 |
|------|------|------|
| A | `DataManager` 增加 `list_events()` / `get_stats()` | ❌ 排除 |
| **B** | 新增 `event_repository.py` / `stat_repository.py` | ✅ **采用** |
| C | API 层直接调用既有 repository | ⚠️ **退化为 B** |

**采用 B 的理由**
1. **与既有结构一致**：仓库已有 `repositories/asset_repository.py` + `repositories/db.py`，Repository 模式是既定范式（`Database` 负责连接/事务，Repository 负责 SQL 与行映射）。
2. **不推翻已冻结的 DataManager 契约**：Step 4.2-B 已把 `DataManager` 公开 API 冻结为**恰好 3 个写入方法**（有 AST 守卫）；方案 A 必须改冻结文档。

**排除 A 的理由**：`DataManager` 的定位是**写入 + 聚合**（D4）。加查询会让它同时承担读/写两类职责，
且 4.2-B 的 `test_public_api_is_exactly_three_methods` 守卫会立即失败 —— 扩 API 等于修改冻结契约。

**排除 C 的理由（关键澄清）**：C **不是真正的第三选项**。现有 repositories 只有 `asset_repository.py`
（只服务 assets 表），**不存在** event / stat 仓储 —— 要让 API「调用既有 repository」，必须先有新仓储，
即 C 必然退化为 B。而若 C 被理解为「API 层自己写 SQL」，则直接违反 API-3。

### 冻结的分层与不变量

```
API 层（app/api/**）
   ├─ 写路径 ─▶ DataManager（app/services/data_manager.py）── 唯一写入出口
   └─ 读路径 ─▶ EventRepository / StatRepository（app/repositories/**）
                     └─▶ Database（app/repositories/db.py）
```

| 不变量 | 内容 |
|--------|------|
| **SQL 归属** | SQL 语句**只允许**出现在 `app/repositories/**` 与 `app/services/data_manager.py` 两处 |
| **写入唯一出口** | 一切写入（`events` / `interactions`）**必须**经 `DataManager`；**禁止**仓储提供写方法 |
| **仓储只读** | 新仓储只暴露只读方法；`Database` 连接**不得**被 API 层直接持有 |
| **API 层零 SQL** | API 层不得出现 SQL 字面量、不得 `import sqlite3` |
| **DataManager 不变** | 公开 API 保持 3 个；本步与其后续 Step 均**不得**为其新增查询方法 |

### 冻结的仓储接口（签名，实现属 4.3-B-1）

```
EventRepository.list_recent(limit: int) -> list[dict]     # created_at DESC, id DESC
StatRepository.stats() -> dict                            # {"events": {}, "actions": {}, "total": int}
```

- 返回值为**基本类型容器**（`dict` / `list[dict]`），**不引入新模型类**；
- `payload` 的「字符串 → 对象」反序列化**由 API 层完成**（库内保持 JSON 字符串，D1）。

---

## DA-3 Internal Error Mapping

### 裁决 —— **保持 500 `{"code":"INTERNAL_ERROR","message":"..."}`，API 层统一 catch；禁止新增异常类**

| 项 | 冻结内容 |
|----|----------|
| `INTERNAL_ERROR` 载体 | **不新增异常类**（不修改 `exceptions.py`）；作为 **API 边界的兜底码**存在 |
| 落地方式 | API 层注册**全局异常处理器**：`PetLiveError` → 按其 `code` 映射 HTTP 状态；其余未捕获 `Exception` → `500 INTERNAL_ERROR` |
| 日志 | 未捕获异常**必须** `logger.exception` 记录完整堆栈（日志内），但**响应体不得**含堆栈 |
| 与 API-4 一致 | 错误码仍只 3 个；业务细码按 4.3-A 的折叠表处理 |

**映射（沿用 4.3-A API-4，本步确认落地口径）**

| 抛出 | HTTP | `code` |
|------|------|--------|
| `InvalidRequestError`（含 `EVENT_*` 折叠） | 400 | `INVALID_REQUEST` |
| `AssetNotFoundError` / `ASSET_FILE_MISSING` | 404 | `ASSET_NOT_FOUND` |
| `AssetMetadataError` / `PetLiveError`(基类) / 任意未捕获异常 | 500 | `INTERNAL_ERROR` |

**禁止**：❌ 新增 `InternalError` 等异常类 ❌ 修改 `backend/app/core/exceptions.py`
❌ 把堆栈 / 物理路径 / SQL 片段写入响应体 ❌ 让异常逃逸出进程（PROJECT_RULES 第十一条）

---

## DA-5 Static Asset Hosting

### 裁决 —— **采用 A：FastAPI `StaticFiles` 直接托管 `/assets/*`**

> **A：`app.mount("/assets/pets", StaticFiles(directory=<PROJECT_ROOT>/assets/pets))`**

| 项 | 冻结内容 |
|----|----------|
| 挂载点 | **唯一**挂载 `/assets/pets` → `<PROJECT_ROOT>/assets/pets` |
| `asset_url` 生成 | `asset_url = "/" + asset_path`（`asset_path` 已含 `assets/pets/`，故与 `ASSET_URL_PREFIX="/assets/pets"` **天然自洽**）；示例：`assets/pets/cat/actions/heart/heart.mp4` → `/assets/pets/cat/actions/heart/heart.mp4` |
| URL 生成方 | **后端**（AssetManager 提供相对路径 → API 层拼 `ASSET_URL_PREFIX`）；**UI 永不拼路径**（P3 / UI-6） |
| 替代方案 | ❌ 排除 B（独立前端服务器托管）—— 当前**无独立前端部署链**，`frontend/` 仅骨架；❌ 排除 C（占位 URL）—— 会让 UI 拿到不可播放地址，违背「本地可运行 Demo」目标 |

**排除 B 的理由**：Phase 1 只有本地 Demo，`frontend/` 尚为 0 代码骨架，引入第二个服务器/端口只增加部署面。

### 安全约束（硬性）

- **只挂载 `assets/pets`**，**禁止**挂载项目根 —— 否则 `database/pet_live.db`、`.env` 等将可被下载。
- **禁止**为 `/assets` 另开路由、**禁止**用 `FileResponse` 逐文件转发（绕过 StaticFiles 会重造路径解析，与 AssetManager 职责重叠）。
- 未登记素材**不得**通过路径拼接兜底（Step 1 验收 A2）；静态挂载只解决「如何把已登记的素材送出」，**不改变**「素材必须先登记」的前置条件。
- ⚠️ 静态目录在**测试环境**中的提供方式（临时 `assets/pets`）见 Deferred **DB-3**。

---

## DA-7 Unknown Request Fields

### 裁决 —— **采用 A：拒绝，`400 INVALID_REQUEST`**

| 项 | 冻结内容 |
|----|----------|
| 口径 | 请求体出现**契约外顶层字段** ⇒ **400 `INVALID_REQUEST`**（不是忽略） |
| 落地 | 请求 DTO 使用 `extra="forbid"`（Pydantic v2 `ConfigDict`） |
| 覆盖范围 | `POST /api/events/simulate` 的**顶层**字段（允许键只有 `event_type` / `user_id` / `user_name` / `payload`） |

**采用 A 的理由**：与事件契约的一致性 —— `step2_event_schema.md` 已冻结「顶层 4 个字段之外出现字段 ⇒ `EVENT_SCHEMA_INVALID`」；
模拟器 API 是开发者试跑接口，**拒绝比忽略更容易暴露契约错误**（B 会让笔误静默通过，问题推迟到 UI 联调才暴露）。

**边界澄清（不在本条范围）**：`payload` **内部**字段的合法性由事件级校验负责（各事件类型必填/禁填），
本裁决只管**顶层**未知键。

---

## DA-8 Event Retention

### 裁决 —— **采用 C：Phase 1 暂不实现清理**

| 项 | 冻结内容 |
|----|----------|
| 清理机制 | **本阶段不实现**；`events` 表数据**保留**（无 TTL、无裁剪任务） |
| 理由 | 仓库**已有 `events` 表**，但**没有**任何后台任务体系（无调度器、无 worker、无定时器） |
| 附带约束 | **禁止**为清理引入线程 / `asyncio` 定时任务 / 后台任务 —— 属过度设计，且会给单进程 demo 引入并发风险 |
| 查询侧保护 | `GET /api/events/recent` 用 `limit`（1..200，默认 20）限制单次返回量，避免响应体随数据量线性膨胀 |

**风险登记**：`events` 会**无限增长**。Phase 1 为本地 Demo、数据量可控（人工模拟器触发，非平台真实流量），
风险可接受。**触发条件**：接入真实直播平台（Phase 2）**之前必须重新裁决**本条。

---

## Deferred

| # | 事项 | 状态 / 处理 |
|---|------|-------------|
| **DA-2** | `counts` 不在线上快照中（UI-3 描述内部状态、API-2 描述线上快照） | 已在 4.3-A 裁决分层；待 **UI 文档侧对齐** |
| **DA-4** | `asset_url` 精确形态（是否含 `/actions/{action}/`） | 本步证据（`asset_path` 已含 `assets/pets/`，与 `ASSET_URL_PREFIX` 自洽）**指向** `/` + `asset_path`；**Step 4.3-B-1 定稿** |
| **DA-6** | 事件细码（`EVENT_*`）是否允许直接作为 API `code` | 保持**折叠**为 `INVALID_REQUEST`（4.3-A 裁决）；UI 如需精确区分则提 Change Request |
| **DB-1** | **依赖启用方式** | `fastapi` / `pydantic` 在**受管 3.13.12 缺失**、在**系统 3.11.9 存在**；需在 4.3-B-1 裁决「启用哪个解释器 + 安装/解除注释」，并写回 `requirements.txt` |
| **DB-2** | **应用入口位置与命名**（`backend/app/main.py`？`create_app()`？ASGI 可调用对象） | 4.3-B-1 定；本步不建 |
| **DB-3** | **测试环境的素材目录**（静态挂载要求 `assets/pets` 存在） | 4.3-B-1 定（测试需临时目录或指向真实目录） |
| **DB-4** | **CORS / 跨域**（前端 dev server 与后端不同源） | 4.3-B-1 评估；若 UI 直连后端则需 CORS |
| **DB-5** | **未知查询参数**口径（如 `GET /api/stats?x=1`） | 与 DA-7 同理；4.3-B-1 统一口径 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 **DA-1 = B**（新增 `event_repository.py` / `stat_repository.py`，仓储只读、DataManager 保持 3 个写 API）、**DA-3**（保持 `INTERNAL_ERROR` 边界码，API 层统一 catch，禁新增异常类）、**DA-5 = A**（FastAPI `StaticFiles` 挂载 `/assets/pets`）、**DA-7 = A**（未知顶层字段拒绝 400）、**DA-8 = C**（Phase 1 不实现清理）。 |
