# Phase 3.2-B Pet Scoped HTTP Read API Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-23，Phase 3.2-B Governance + 实现）。生效后变更须经 Change Request。
> **编号空间**：`MB-1 ~ MB-7`（Multi-pet Boundary —— pet 作用域 **HTTP 读侧** API 边界）。
> **上游**：`phase3_2b_route_b_decision_input.md`（裁决输入，非冻结）· `phase3_2b_bread_execution_plan.md`（执行方案，非冻结）。
> **本文件是"受权增量声明"载体**：它以 **CR** 方式修订两份既有冻结文档的**局部条款**，
> 并在本文件内**完整重述修订后的语义**；两份源文档的其余内容**保持原冻结效力**。

## 编号空间声明（0 撞车核查）

本文档使用 **`MB-1 ~ MB-7`**。创建前已做全仓 0 撞车核查（2026-09-23，只读）：

- 全仓 grep `\bMB-` **零命中**（`MB-` 前缀**从未被使用**）；
- 全仓 grep `\bMB-1\b` **零命中**；全仓 grep `\bQP-6\b` **零命中**（本次 CR 新铸的 query 条款号，见 `MB-4`）；
- 子串级检查：`MB-` 不与 `MP-` / `MPF-` / `MP-5` 互相吞并（`MB-` 与 `MP-` 第二字符不同）。

既有编号空间（**不重复使用**）：`UI/UB · FE/FC/FS/FCM/FD/RV/RS/RF/FP/PI/ES · AS/DA/DB/DR/QP · PB/RB ·
WS/WM/WA/WT/WG/PC/WP/WC/WL/LI/WE/GR/OB/PH/HR · MP · MPF`。**已废止**：`GD-*` → `GR-*`。

---

## MB-1 —— 授权记录（owner 裁决，逐项登记）

本步的一切改动**仅**以下列显式裁决为依据；未列明者**仍属未授权**。

| # | 授权点 | owner 裁决 | 落地位置 |
|---|---|---|---|
| **A1** | canonical pet key 策略 | **B** —— 保留 alias + resolver 规范化 | `MB-2` |
| **A1-scope** | resolver 作用域 | **仅 HTTP 读侧**（⛔ WS 写侧逐字不变） | `MB-2` / `MB-6` |
| **A2** | 默认作用域语义 | **W** —— 保留 `NULL` 默认 + 明文登记 MP-4 不对称 | `MB-3` / `MB-5` |
| **A3** | `/api/stats` 无参语义 | **S-1** —— 无参 = `NULL` 桶（零改动） | `MB-3` |
| **A4** | Route B 范围 | **B-read only**（B-live 剥离单独立项） | `MB-6` / `MB-7` |
| **A5** | `/api/events/simulate` 是否收 `pet_id` | **不加** | `MB-6` |
| **A6** | 解除 MP-5 禁令 | **仅解除读侧** | `MB-4` |
| **A7** | QP-1 / QP-4 的 CR | **出 CR**（硬性） | `MB-4` |
| **A9** | 存量数据处置 | **无需 migration** | `MB-3` / `MB-5` |
| **P-1** | 归一化后读哪个桶 | **① 仅 canonical**（不聚合 alias） | `MB-3` |
| **P-3** | HTTP 侧 `settings` 来源 | 复用 `api/ws.py::get_ws_settings()` | `MB-4` |
| **P-4** | 非法 / 空 `pet_id` | 折 `400 INVALID_REQUEST`，**不新增错误码** | `MB-4` |

**授权范围（逐字）**：`GET /api/stats?pet_id=<key>` 与 `GET /api/events/recent?limit=<n>&pet_id=<key>`
两个**只读**端点的 pet 作用域读参数。**其余一切**（见 `MB-6`）不在授权内。

## MB-2 —— Canonical Pet Key Resolver（**仅读侧**，冻结）

- **归一化点唯一**：`backend/app/services/pet_context.py::normalize_pet_key(pet_id: str | None) -> str | None`。
- **别名表（冻结，静态）**：`cat → cat_001` · `cat_001 → cat_001` · `dog → dog_001` · `dog_001 → dog_001` ·
  `panda → panda_001` · `panda_001 → panda_001`；表外键 ⇒ 返回 `None`。
- **输入 `None` ⇒ 返回 `None`**（= 无 pet 作用域，走默认路径；与「非法」在**调用层**区分，见 `MB-4`）。
- **匹配口径**：**精确匹配、大小写敏感**（`CAT` ≠ `cat`）；**不做前缀匹配、不做模糊匹配**。
  首尾空白由**调用方**按 transport 惯例处理（与 `api/ws.py` 的 `pet_id.strip()` **同口径**），resolver 本身不 strip。
- **合法键判定来源**：`known_pet_keys(settings)`（= `AssetManager.pet_ids()` ∪ `assets` 表 `pet_type`），
  `settings` 经 `api/ws.py::get_ws_settings()` 注入 ⇒ **HTTP 读侧与 WS 侧共用同一合法集口径**。
- ⛔ **作用域硬约束**：resolver **仅**被 HTTP 读侧调用。**WS 写侧（`api/ws.py` / `DataManager` / `Runtime`）
  的行为与代码逐字不变** —— `?pet_id=cat` 经 WS 写入时**仍写 `pet_id='cat'`**，**不**被归一化。
- ⛔ resolver **不得** import 引擎类（`ActionEngine` / `InteractionEngine` / `PlaybackManager`）、
  不得 import `repositories/**`、不得访问数据库、不得出现 SQL。

## MB-3 —— 读侧作用域语义（**P-1 = ① 仅 canonical**，冻结）

| 请求 | 冻结语义 |
|---|---|
| `GET /api/stats`（无参） | **`pet_id IS NULL` 桶**（A2=W / A3=S-1）—— 与 Phase 1 及本步之前**逐字一致** |
| `GET /api/stats?pet_id=<key>` | 读 **canonical 键那一个桶**（`canonical = normalize_pet_key(key)`），**不聚合 alias** |
| `GET /api/events/recent`（无参） | **全表**（SQL **无 WHERE**）—— 与改动前**逐字一致** |
| `GET /api/events/recent?pet_id=<key>` | 仅 `pet_id = <canonical>` 的行；`limit` 语义（1..200）**不变** |

- ⭐ **P-1 = ① 的明示后果（登记，不掩盖）**：`?pet_id=cat` 与 `?pet_id=cat_001` **返回同一桶**（canonical `cat_001`）；
  但 WS 写侧**未归一化**，历史上若有以 `cat` 为键写入的行，**将不在这两个请求的任何结果中**（静默不可见）。
- ⭐ **A9 = 无需 migration 的依据（只读实测）**：当前真实库**零 alias 行** ——
  `interactions.pet_id` = `[(None, 3)]`、`events.pet_id` = `[('cat_001', 14)]`。
  ⇒ 选 ① 在当前数据下**无可见数据损失**，该缺口是**未来性 / 语义性**的。
- **兜底方案（记录，不启用）**：若后续需要消除该缺口，登记方案 = **双读兼容**
  （`pet_id IN (<canonical>, <alias…>)`，即裁决输入文档 R-11 所指的"双键聚合"）。
  ⛔ **本步未实现、未启用**；启用须另行授权（会改变既有 SQL 形态与读口径）。

## MB-4 —— Query 条款 CR（QP-1 / QP-4 修订 + 新铸 QP-6）

本 CR 修订 `docs/development/step4_api_query_boundary_decision.md`（v1.0 FROZEN）的**局部条款**；
其余条款（QP-2 / QP-3 主体 / Error Contract / 其余 Forbidden 条目）**保持 v1.0 效力不变**。

- **QP-1 修订后逐字（白名单表）**：

  | Endpoint | Allowed Query |
  |----------|---------------|
  | `GET /api/stats` | **`pet_id`**（v1.0 原文：`none`） |
  | `GET /api/events/recent` | **`limit`** · **`pet_id`**（v1.0 原文：`limit`） |
  | `GET /api/playback/state` | **none**（**不变**） |

- **QP-4 修订后逐字（首条禁令）**：
  「❌ **为只读端点新增 query 参数**（`offset` / `since` 等）—— 需新增须经 Change Request 修订本文件。
  对 `pet_id` 的例外由 **CR-1** 给出（已解除禁令并加入 QP-1 白名单）。」

- **QP-3「不新增参数」修订后逐字**：
  「除 **CR-1** 明确解除的 `pet_id` 外，本文件**不**为任何只读端点新增 query 参数（如 `offset` / `since`）；
  需新增须提 Change Request。」

- **新铸 QP-6（`pet_id` 参数行为，逐字）**：
  1. **适用端点**：**仅** `GET /api/stats` 与 `GET /api/events/recent`；`GET /api/playback/state` **不接受** `pet_id`。
  2. **合法值**：`known_pet_keys(settings)` 内任一键（`pet_id` 或 `pet_type`），见 `MB-2`。
  3. **归一化**：值经 `normalize_pet_key()` 折算为 canonical 键后再交给读仓储（**仅读侧**）。
  4. **首尾空白**：按 transport 惯例 `strip()` 后判定（与 `api/ws.py` 同口径）。
  5. **非法 / 空值 / 表外键**：一律 **`400 INVALID_REQUEST`**；**⛔ 不得新增错误码**（API 层仍恰 3 个）。
  6. **契约字段**：只有 `code`（`INVALID_REQUEST`）与 HTTP 状态（400）是契约；`message` 为人类可读描述，UI 不得依赖其文本。
  7. **与 QP-2 的关系**：**不改变**未知 query 键的处置 —— 白名单之外仍是 `400 INVALID_REQUEST`，三端点仍同一口径。

## MB-5 —— 已知不对称登记（**登记 ≠ 解决**）

- **MP-4 双源不对称（明文「已知并接受」，A2=W 的代价）**：
  `events.pet_id` 取 `runtime.pet_id`（默认路径 = 派生值 `cat_001`，**非 NULL**）；
  `interactions.pet_id` 取 `DataManager._pet_id`（默认路径 = **NULL**）
  ⇒ **默认连接与显式 `?pet_id=cat_001` 连接的 `events` 行在表内不可区分**。
  **本步不解决、不视为缺陷**；⛔ 不授权改写任何写入口径。
- **R-10 读侧语义不对称（本步使其更可见）**：
  `/api/events/recent`（无参）读**全表**（含 `cat_001` 行），而 `/api/stats`（无参）只读 **`NULL` 桶**
  ⇒ 同一个"默认"在两个端点上的口径**本就不同**；B-read 上线后，调用方**更可能**观察到这一差异。
  **本步不消除**，如实登记。
- **R-10 前端不一致（本步不处理）**：前端刷新路径读默认播放态 ⇒ 若只上 B-read 而 B-live 未立项，
  会出现「计数可随 pet 变、播放态不变」的新不一致。
  ⛔ **本步前端零改动**；未上 B-live 前，**UI 不得**消费 pet 作用域 HTTP 读（见 `MB-6`）。

## MB-6 —— Scope Freeze（本步**未授权**的范围）

- ⛔ **B-live**：`GET /api/playback/state` 与 `POST /api/events/simulate` 的 pet 作用域 —— **未授权、未实现**（见 `MB-7`）。
- ⛔ **写侧归一化**：WS / `DataManager` / `Runtime` 的 `pet_id` 口径**逐字不变**（resolver 仅读侧）。
- ⛔ **registry 类结构**：pet registry · 全局 current_pet · 共享 active runtime · 进程级 pet 态。
- ⛔ **schema / 协议**：数据库 schema · `WM-1` envelope · Event schema · `PlaybackState` 6 字段 · 错误码集合。
- ⛔ **前端**：`frontend/**` 零改动；**不得**新增 pet 级 HTTP 消费、pet 级统计读路径（`MPF-7` 对该侧**仍有效**）。
- ⛔ **其它**：reconnect · heartbeat · retry · 消息重放 · 多连接并存 · 新依赖 · metrics / tracing / OTEL。
- ⛔ **旧冻结文档本体**：除本 CR 明列的 `QP-1` / `QP-3` / `QP-4`（+ 新铸 `QP-6`）与 `MP-5` 局部条款外，
  **其余一字不改**。

## MB-7 —— B-live 前置条件（记录，不实现）

B-live 若未来立项，**前置裁决**（缺一不可）：

1. **`/api/playback/state` 的 pet 作用域**须先裁：「per-request 新建 runtime（⇒ `/state` **恒返回 `idle`**，语义退化）」
   **vs** 「引入 pet runtime 缓存 / 注册表（⛔ **须先修订 `MP-2`**）」——二者均需独立 CR。
2. **`POST /api/events/simulate` 收 `pet_id`** 会改变 `API-1` 的不变量（「后端补齐 `pet_id`，UI 不发送」）⇒ 须 `API-1` CR。
3. `MP-5` 的**写侧**解除（本步仅解除了读侧）。

---

## 落地证据

| 项 | 事实 |
|---|---|
| 治理提交 | 见 `## 变更历史`（QP-1/QP-4 CR + MP-5 读侧解除 + 本文件 + `PROJECT_RULES.md` §十四 登记） |
| 实现落点 | `backend/app/services/pet_context.py`（新增）· `repositories/stat_repository.py` · `repositories/event_repository.py` · `api/stats.py` |
| 回归基线 | 后端 `550 → 550 + N`（N = 本步新增用例数，见交付报告） |
| 未触碰 | `database/schema.sql` · `app/platform/**` · `api/ws.py`（除复用 `get_ws_settings` 外）· 组合根三件套 · `frontend/**` |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-23 | 首次冻结（`MB-1 ~ MB-7`）。编号空间 `MB-*` 0 撞车；登记 A1/A2/A3/A4/A5/A6/A7/A9 + P-1/P-3/P-4；以 CR 方式修订 `QP-1`/`QP-4` 并新铸 `QP-6`、修订 `MP-5` 读侧（写侧与 registry 仍禁）；登记 MP-4 双源不对称与 R-10 语义不对称；A9 兜底方案（双读兼容）**仅登记不启用**；B-live 前置条件记录在案。 |
