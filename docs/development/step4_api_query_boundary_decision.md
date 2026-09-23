# AI Cat API Query Boundary v1.0

> **版本**：v1.0（FROZEN）—— **CR-1 修订见 `## Change Request`**（2026-09-23）
> **日期**：2026-09-19
> **产出 Step**：Step 4.3-B-2-A
> **定位**：只读 API 的**查询参数边界**的**唯一准绳** —— 冻结三个只读端点的「允许哪些 query 键」与「未知 query 如何处理」，
> 消除当前端点之间的**口径漂移**（stats / events/recent 拒绝、playback/state 静默忽略）。**只冻结，不写代码。**
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_api_stability_decision.md`（v1.0 FROZEN）—— **AS-D1**（本步即其冻结）
> - `docs/development/step4_api_contract_decision.md`（v1.0 FROZEN）—— API-3（`GET /api/stats` / `GET /api/events/recent`，`limit` 1..200）、API-4（`{code,message}`，3 码）
> - `docs/development/step4_api_implementation_boundary.md`（v1.0 FROZEN）—— **DA-7**（未知请求字段拒绝）、`4.3-B-0/DB-5`（未知查询参数口径）
> - `docs/development/step4_api_runtime_decision.md`（v1.0 FROZEN）—— DB-4（路由归属）、DB-5（`TestClient` 契约测试）
> - `PROJECT_RULES.md` §十四（`### API 与跨进程边界` / `### API Implementation Boundary` / `### API Boundary Stability`）
>
> **本步边界**：**只冻结**。不改 `backend/**`、不改 `frontend/**`、不改 `database/**`、不改 `tests/**`、
> 不改任何既有冻结文档。落地（含 `playback/state` 补拒绝逻辑）属后续 Step —— 见 **`## Deferred`** 的 `L-QP-*`。

---

## Input Boundary

### §一 强制前置检查（实测，全部通过）

| 项 | 期望 | 实测 |
|----|------|------|
| branch | `phase1-step1-foundation` | ✅ `phase1-step1-foundation` |
| HEAD | `cf95c13` | ✅ `cf95c13 docs: freeze api boundary stability` |
| working tree | clean | ✅ `git status --porcelain` 为空 |
| `docs/development/step4_api_stability_decision.md` | 存在 | ✅（28425 bytes；含 AS-D1 登记） |
| `PROJECT_RULES.md` | 含 `API Boundary Stability` | ✅ `PROJECT_RULES.md:746 ### API Boundary Stability` |

**本步不允许修改**（偏差即 STOP）：`backend/**` · `frontend/**` · `database/**` · `tests/**` · 既有冻结文档。

### §二 只读调查（实测，未修改任何文件）

#### 2.1 三个只读端点的未知 query 行为

| Endpoint | 未知 query（`?x=1`）当前行为 |
|----------|------------------------------|
| `GET /api/stats` | **400** `{"code":"INVALID_REQUEST","message":"出现未定义查询参数: ['x']；只允许 []"}` |
| `GET /api/events/recent` | **400** `{"code":"INVALID_REQUEST","message":"出现未定义查询参数: ['x']；只允许 ['limit']"}` |
| `GET /api/playback/state` | ⚠️ **200（静默忽略）** —— 返回正常 6 字段快照，未知参数被无声丢弃 |

补充实测（同一探针）：

| 请求 | 实测 |
|------|------|
| `GET /api/stats?foo=bar&baz=1` | 400，message 列出 `['baz', 'foo']`（**排序后**） |
| `GET /api/events/recent?x=1&limit=5` | 400（未知键优先于合法键判定） |
| `GET /api/playback/state?foo=` | ⚠️ 200（空值同样静默忽略） |
| `GET /api/stats`（无参数） | 200 `{"events":{},"actions":{},"total":0}` |
| `GET /api/events/recent`（无参数） | 200 `{"items":[],"count":0}` |
| `GET /api/playback/state`（无参数） | 200 六字段快照（`state="idle"`） |

⇒ **口径漂移确认**：同一契约维度（未知查询参数）在 **2 个端点被拒绝、1 个端点被忽略**。

#### 2.2 错误契约来源（`INVALID_REQUEST` 从哪来）

| 项 | 实测 |
|----|------|
| 允许键常量 | `backend/app/api/stats.py:39 _STATS_QUERY_KEYS = frozenset()`；`:40 _RECENT_QUERY_KEYS = frozenset({"limit"})` |
| 拒绝实现 | `backend/app/api/stats.py:80 _reject_unknown_query(request, allowed)`，在 `:134`（stats）与 `:154`（recent）调用；**`api/playback.py` 无此 helper、且无 `Request` 形参** |
| 抛出物 | `_reject_unknown_query` 抛业务异常（`PetLiveError` 子类）⇒ 走**全局** handler，不落框架默认 |
| **全局异常处理位置** | `backend/app/main.py:133 _register_exception_handlers(app)`（在 `create_app()` 内 `:215` 调用） |
| 注册的 handler（3 个，均 `async def`，经 `@app.exception_handler(...)` 装饰器） | ① `RequestValidationError` → **400 `INVALID_REQUEST`**（`:142`）② `PetLiveError` → 按折叠表映射（`:150`）③ `Exception` → **500 `INTERNAL_ERROR`**（`:158`） |
| 错误码常量 | `backend/app/main.py:68 CODE_INVALID_REQUEST = "INVALID_REQUEST"`；`:73` 映射 `INVALID_REQUEST → 400`；`:79 _INVALID_REQUEST_CODES` |
| 响应构造 | `main.py:115 _error_response(status, code, message)` → `{"code","message"}` |
| FastAPI validation 行为 | `Query(ge=1, le=200)` 与 DTO 的 `extra="forbid"` 触发 `RequestValidationError`，其**默认 422** 已被 `:142` 的 handler **折叠为 400**（无 422 泄漏） |

#### 2.3 现有测试覆盖

| 项 | 结论 |
|----|------|
| **已覆盖** | `tests/test_api_contract.py::test_stats_rejects_unknown_query_params` —— 仅 `GET /api/stats` |
| **缺失** | ❌ `GET /api/events/recent` 的未知 query 用例 ❌ `GET /api/playback/state` 的未知 query 用例（**漂移之所以未被发现，正因无此用例**） |
| 其它相关 | `tests/test_api_contract.py` 是唯一使用 `params=` 的测试文件；`limit` 越界已有参数化用例 `test_recent_events_limit_out_of_range_rejected`（`0` / `201` / `"abc"`） |

### 输入边界（不变量）

1. **只读端点只接受**本文件 `## Allowed Query Parameters` 列明的 query 键；其余一律拒绝。
2. **`limit` 是唯一带值的查询参数**（仅 `GET /api/events/recent`），其合法域为整数 `1..200`（API-3）。
3. **未知 query 的处理方式在三个只读端点间必须一致** —— 这是本文件的全部目的；**任何**「某个端点特例」都属违反。
4. 本文件的裁决**不扩展** API-4 的错误码集合（仍 3 个），也**不**修改 `PlaybackState` 六字段与任何响应体结构。

---

## Allowed Query Parameters

### QP-1 Endpoint × Allowed Query 参数表（冻结）

| Endpoint | Allowed Query |
|----------|---------------|
| `GET /api/stats` | **`pet_id`**（**CR-1** 新增；v1.0 原文为 `none`） |
| `GET /api/events/recent` | **`limit`** · **`pet_id`**（**CR-1** 新增；v1.0 原文为 `limit`） |
| `GET /api/playback/state` | **none**（无任何合法 query 键；**CR-1 未放开**） |

| 项 | 冻结内容 |
|----|----------|
| **白名单式** | 表外任何键 ⇒ 见 `## Unknown Query Handling`（QP-2） |
| **键名精确匹配** | 大小写敏感（`Limit` ≠ `limit`）；不做前缀匹配、不做别名 |
| **`none` 的含义** | 该端点**不定义任何** query 参数 ⇒ **任何** query 键（含 `?x=`、`?x=1`）都属未知 |
| **键名 vs 键值**（CR-1 澄清） | 上一条「不做别名」指 **query 键名**；`pet_id` 的**键值**归一化（`cat → cat_001`）由 **QP-6** 单独定义，二者不冲突 |
| **实测一致性** | v1.0 实测与 `_STATS_QUERY_KEYS = frozenset()`、`_RECENT_QUERY_KEYS = frozenset({"limit"})` 逐字吻合；**CR-1 后**二者分别为 `frozenset({"pet_id"})` 与 `frozenset({"limit", "pet_id"})`；`playback` **无**白名单实现（见 `## Deferred` `L-QP-1`） |

### QP-3 `limit` 行为（**保持已有契约，不新增**）

| 项 | 冻结内容 |
|----|----------|
| **适用端点** | **仅** `GET /api/events/recent` |
| **合法域** | 整数 `1 <= N <= 200`；省略时默认 `20` |
| **越界 / 非法值** | 一律 **400 `INVALID_REQUEST`** |
| **必测取值** | `limit=0` · `limit=201` · `limit=-1` · `limit=abc` |

**实测证据（四例全部 400 `INVALID_REQUEST`）**

| 请求 | 状态 | `message` |
|------|------|-----------|
| `GET /api/events/recent?limit=0` | 400 | `请求参数非法: query.limit: Input should be greater than or equal to 1` |
| `GET /api/events/recent?limit=201` | 400 | `请求参数非法: query.limit: Input should be less than or equal to 200` |
| `GET /api/events/recent?limit=-1` | 400 | `请求参数非法: query.limit: Input should be greater than or equal to 1` |
| `GET /api/events/recent?limit=abc` | 400 | `请求参数非法: query.limit: Input should be a valid integer, unable to parse string as an integer` |
| `GET /api/events/recent?limit=1` / `?limit=200` | 200 | ——（边界内合法） |

| 附加约束 | 内容 |
|----------|------|
| **禁止 422** | FastAPI 的原生 `RequestValidationError` 默认 422 → **必须**由全局 handler 折为 **400**（已落地，见 §2.2） |
| **禁止吞掉越界** | **不得**把 `limit=0` 静默改成 `1`、**不得**把 `limit=201` 静默截断为 `200` —— 拒绝而非纠偏 |
| **不新增参数** | 除 **CR-1** 明确解除的 `pet_id` 外，本文件**不**为任何只读端点新增 query 参数（如 `offset` / `since`）；需新增须提 Change Request |

---

## Unknown Query Handling

### QP-2 Unknown Query Policy（冻结）

| 项 | 冻结内容 |
|----|----------|
| **统一口径** | 未知 query parameter ⇒ **400 `INVALID_REQUEST`** |
| **三端点一致** | `GET /api/stats`、`GET /api/events/recent`、`GET /api/playback/state` **同一策略**，**无特例** |
| **核心禁令** | **禁止静默忽略**未知 query 参数 |
| **判定范围** | 请求 URL 中出现的**所有** query 键（含空值键 `?foo=`）逐一对照 QP-1 白名单；**只要有任一键不在白名单**即拒绝 |
| **多键情形** | 允许多个未知键同时被报出（实现可列出全部，见实测 `['baz','foo']`） |
| **不区分来源** | 无论未知键出现在合法键之前还是之后（`?x=1&limit=5` 与 `?limit=5&x=1`）**同样拒绝** |

**规范示例（契约形态）**

```http
GET /api/playback/state?foo=bar
```

```json
{ "code": "INVALID_REQUEST", "message": "unknown query parameter" }
```

| 项 | 冻结内容 |
|----|----------|
| **契约字段** | **只有 `code`**（=`INVALID_REQUEST`）与 HTTP 状态（=400）是契约；`message` 是**人类可读描述**，UI **不得**依赖其文本（与 API-4「UI 不得依赖 `context`」同理） |
| **`message` 要求** | 必须能标识「未知查询参数」这一事实；**允许**实现提供更具体的描述（如列出未定义参数名与允许集） |
| **既定偏差（登记，非契约）** | 当前 `stats` / `recent` 的 `message` 为中文描述（`出现未定义查询参数: ['x']；只允许 []`），与上方示例的英文文本**不同**；因 `message` 非契约字段，**本条不强制逐字一致**（见 `## Deferred` `L-QP-2`） |

**为何统一为「拒绝」（沿用 DA-7 判据）**：DA-7 已冻结「契约外顶层**请求体**字段一律拒绝，不得静默忽略」，
理由是**拒绝比忽略更早暴露契约错误**（忽略会把笔误推迟到联调才发作）。查询参数与请求体属同一类「调用方
与契约不一致」的事实，故沿用同一判据：**同一契约的同一维度不应有两种答案**。

**为何不统一为「忽略」**：忽略会让 QP-1 的白名单**失去强制力** ——
`?limit=20&limti=20`（拼错）将静默返回默认 20 条，调用方以为生效；且与 DA-7 的既有判据相反。

---

## Error Contract

| 项 | 冻结内容 |
|----|----------|
| **错误码** | **仅** `INVALID_REQUEST`（本文件不引入任何新 code；API 层错误码仍**恰好 3 个**） |
| **HTTP 状态** | **400** |
| **响应体** | `{"code": "INVALID_REQUEST", "message": <人类可读描述>}` |
| **产生路径** | API 层白名单校验 → 抛业务异常（`PetLiveError` 子类）→ `main.py::_register_exception_handlers` 内的 `PetLiveError` handler 按折叠表映射为 `400 INVALID_REQUEST` |
| **`limit` 越界路径** | FastAPI `Query(ge/le)` → `RequestValidationError` → 同一模块内的 `RequestValidationError` handler 折为 `400 INVALID_REQUEST`（**不得**泄漏 422） |
| **禁止** | ❌ 返回 FastAPI 默认 validation detail（`{"detail":[{"loc":…,"msg":…,"type":…}]}`）❌ 返回 422 ❌ 新增错误码 ❌ 在响应中泄露堆栈 / 物理路径 / SQL 片段 |

---

## Forbidden

### QP-4 明确禁止

- ❌ **API 层自行忽略未知 query 参数**（任何端点、任何键：**不得**静默丢弃）
- ❌ **不同 endpoint 使用不同策略**（禁止为 `playback/state` 特例化「宽松」、禁止为某端点单独豁免）
- ❌ **返回 FastAPI 默认 validation detail**（`{"detail": […]}` 形态）
- ❌ **扩展新的错误 code**（仍只 3 个：`INVALID_REQUEST` / `ASSET_NOT_FOUND` / `INTERNAL_ERROR`）
- ❌ **返回 422**（必须折为 400）
- ❌ **为只读端点新增 query 参数**（`offset` / `since` 等）—— 需新增须经 Change Request 修订本文件
  （**CR-1 例外**：`pet_id` 的禁令已由 CR-1 解除并加入 QP-1 白名单，行为见 `QP-6` / `## Change Request`）
- ❌ **把 `limit` 越界「纠偏」**（`0 → 1`、`201 → 200` 等静默截断/抬升）
- ❌ **在 query 校验里做业务判断**（如允许 `?action=happy` 之类）—— API 层只做白名单比对

### 本 Step（4.3-B-2-A）不得

- ❌ 修改 `backend/**`（含 `api/playback.py` 补拒绝逻辑）
- ❌ 修改 `tests/**`（含补 `playback/state` 未知 query 用例）
- ❌ 修改 `frontend/**` / `database/**`
- ❌ 修改任何既有冻结文档
- ❌ 进入 **Step 4.3-B-2-L2**（`DataManager.write_event` CR 实施）

---

## Deferred

### QP-5 登记

| # | 事项 | 状态 / 处理 |
|---|------|-------------|
| **QP-5.1** | `POST` 请求体的未知字段（`extra="forbid"`） | **已由 `DA-7` 管理**，本文件**不重复定义**、不修改 |
| **QP-5.2** | OpenAPI schema generation（`/openapi.json`、`/docs`） | **禁止范围**（API-5 / DB-3 已冻结为关闭）；本文件不涉及 |
| **QP-5.3** | WebSocket query contract | **Phase 2**；Phase 1 契约不含 push 通道（API 契约 Forbidden），届时另立文件 |

### 本步衍生的落地项（**本步不实现**）

| # | 事项 | 落地要点 |
|---|------|----------|
| **L-QP-1** | `GET /api/playback/state` 补未知 query 拒绝 | 复用 `stats.py::_reject_unknown_query` 等价逻辑（建议提取为 `api/_query.py` 共享 helper，避免第三份实现）；白名单 = **空集**（`frozenset()`） |
| **L-QP-2** | 三端点 `message` 文本是否逐字统一 | **待裁决**（见 QP-2 既定偏差）：① 统一为规范示例文本 ② 保持现有中文描述（仅保证 `code`/状态一致）。**不影响 UI**（`message` 非契约字段） |
| **L-QP-3** | 补测试：`events/recent` 与 `playback/state` 的未知 query 用例 | 使漂移不再可能复发（当前仅 `stats` 有覆盖） |

---

## Change Request

### CR-1 —— pet 作用域读参数（`pet_id`）授权修订

> **授权依据**：owner 显式裁决 **A6 / A7**（见 `docs/development/phase3_pet_scoped_http_api_decision.md` **MB-1**）。
> **范围**：**仅 HTTP 读侧** —— `GET /api/stats` 与 `GET /api/events/recent`；**不含** `GET /api/playback/state`
> （B-live **未授权**，见该文件 `MB-6` / `MB-7`）。**WS 写侧不受影响。**

**修订后的逐字条款**

1. **QP-1（白名单表，修订后）**：

   | Endpoint | Allowed Query |
   |----------|---------------|
   | `GET /api/stats` | **`pet_id`** |
   | `GET /api/events/recent` | **`limit`** · **`pet_id`** |
   | `GET /api/playback/state` | **none** |

2. **QP-4（首条禁令，修订后）**：
   「❌ **为只读端点新增 query 参数**（`offset` / `since` 等）—— 需新增须经 Change Request 修订本文件。
   对 `pet_id` 的例外由 **CR-1** 给出（已解除禁令并加入 QP-1 白名单）。」

3. **QP-3（「不新增参数」行，修订后）**：
   「除 **CR-1** 明确解除的 `pet_id` 外，本文件**不**为任何只读端点新增 query 参数（如 `offset` / `since`）；
   需新增须提 Change Request。」

4. **新铸 QP-6（`pet_id` 参数行为）**：
   ① **适用端点**仅 `GET /api/stats` 与 `GET /api/events/recent`（`playback/state` **不接受** `pet_id`）；
   ② **合法值** = `known_pet_keys(settings)`（`pet_id` 或 `pet_type`）；
   ③ **归一化**：值经 `normalize_pet_key()` 折算为 canonical 键后再交给读仓储（**仅读侧**）；
   ④ **首尾空白**按 transport 惯例 `strip()` 后判定（与 `api/ws.py` 同口径）；
   ⑤ **非法 / 空 / 表外键** ⇒ 一律 **`400 INVALID_REQUEST`**，**⛔ 不得新增错误码**（API 层仍恰 3 个）；
   ⑥ **契约字段**只有 `code` 与 HTTP 状态，`message` 为人类可读描述（UI 不得依赖其文本）；
   ⑦ **不改变 QP-2**：白名单之外仍是 `400 INVALID_REQUEST`，三端点仍同一口径。

**本 CR 未修订（保持 v1.0 冻结不变）**：QP-2 · QP-3 主体（`limit` 1..200、禁 422、禁纠偏）· QP-5 ·
Error Contract · 其余全部 Forbidden 条目。

---

## Change History

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。冻结 **QP-1**（`stats` = none、`events/recent` = `limit`、`playback/state` = none）、**QP-2**（未知 query 统一 `400 INVALID_REQUEST`，三端点一致，禁静默忽略）、**QP-3**（`limit` 1..200，越界/非法一律 400，禁 422、禁纠偏）、**QP-4**（禁忽略 / 禁特例 / 禁默认 detail / 禁新 code / 禁 422 / 禁新增参数）、**QP-5**（POST body 未知字段归 DA-7、OpenAPI 属禁止范围、WebSocket query 属 Phase 2）。登记落地项 L-QP-1/2/3。 |
| CR-1 | 2026-09-23 | **经 Change Request 修订**（授权依据 = `phase3_pet_scoped_http_api_decision.md` v1.0 FROZEN，`MB-1 ~ MB-7`）：QP-1 为 `/api/stats` 与 `/api/events/recent` 新增 **`pet_id`** 白名单；自 QP-4 首条禁令**移除 `pet_id`**（标注 CR-1 例外）；修订 QP-3「不新增参数」行；**新铸 QP-6**（`pet_id` 参数行为）。源文件其余条款保持 v1.0 冻结。 |
