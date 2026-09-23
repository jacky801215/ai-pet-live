# Phase 3.2-B Route B —— A1 / A2 / A4 裁决辅助（Decision Input）

> **状态**：**非冻结**（本文件是**裁决输入**，非 decision / 非契约；不构成任何实现授权）。
> **性质**：**只读汇总**。汇总既有两轮只读调查的证据，**不引入新 finding、不重新调查、不改任何代码/测试/冻结契约**。
> **目的**：把 Route B 的**三项硬前置**压到一页，供项目 owner 直接拍板。
> **不代裁**：下文给「推荐 + 代价」，**最终由 owner 裁决**（本文任何结论在被 owner 采纳并落成 decision 文档之前，
> **不具备冻结效力**）。
> **证据来源**：① `phase3_2_b_routeb_planning_report.md`（时点 HEAD `3236226`，Step 0~5 只读调查）；
> ② Route B Decision Preparation Step 1~6 只读证据；③ 本次对下列代码文件与真实库的**只读**复核。
> **日期**：2026-09-23 · **时点 HEAD**：`10498f1` · 分支 `phase1-step1-foundation` · working tree clean · commit `83`

---

## 0. Step 0 / Step 1 —— 只读核查（实测原始输出）

### 0.1 仓库状态

```
$ git status --porcelain -uall
（空）

$ git log --oneline -3
10498f1 fix: mark dog/panda as placeholder in UI (§7.1)
3236226 refactor: make pet_id an explicit SimulationPipeline constructor parameter
c26fcb9 refactor: relocate read-only telemetry projections out of pipeline

$ ls docs/development/phase3_2b_route_b_decision_input.md
NOT EXISTS        ← 本文档为新建
```

### 0.2 真实库 pet_id 分布（`sqlite3` CLI 本机缺失 ⇒ 改用 Python `sqlite3` **只读 URI** `mode=ro`）

```
$ sqlite3 database/pet_live.db "SELECT pet_id, COUNT(*) FROM events GROUP BY pet_id;"
   ('cat_001', 14)

$ sqlite3 database/pet_live.db "SELECT pet_id, COUNT(*) FROM interactions GROUP BY pet_id;"
   (None, 3)

（附：assets 表 pet_type 分布）  ('cat', 5)
```

⇒ **精确复现 MP-4 双源不对称**：`events.pet_id` = 派生值 `cat_001`（非 NULL），`interactions.pet_id` = `NULL`；**零 alias 行**。

### 0.3 三道硬锁（冻结契约原文，逐字引用）

| # | 锁 | 文件 : 行 | 原文 |
|---|---|---|---|
| **L1** | **QP-4** | `step4_api_query_boundary_decision.md:191` | 「❌ **为只读端点新增 query 参数**（`offset` / `since` / **`pet_id`** 等）—— 需新增须经 Change Request 修订本文件」 |
| **L2** | **MP-5** | `phase3_backend_multi_pet_context_decision.md:108`、`:114-116`（另见 `:158`） | 「- **pet-scoped HTTP API**（`/api/stats` / `/events/recent` / `/state` 的 pet 过滤或作用域参数）；」（列于「Phase 3.2-A **未实现**且**未授权**」）；「**登记 ≠ 解除实现约束** … 以上各项**均需另行显式授权**」；`:158`「pet-scoped HTTP API（Route B）—— 须改 `backend/app/api/*` 与读路径仓储，**另行授权**」 |
| **L3** | **MP-4** | `phase3_backend_multi_pet_context_decision.md:90-101` | 「**本条款只登记、不解决**：本差异**不视为缺陷**，Phase 3.2-A **未授权**任何修复」；「若要消除该不对称，须**另行显式授权**并单独裁决」 |

⇒ **A1 / A2 / A4 未裁之前，Route B 一行代码都动不了**（L1 是硬性 CR 前置，L2 需显式解除，L3 约束 A2）。

---

## 1. A1 —— canonical pet key 策略

### 1.1 事实（只读实测）

| 项 | 事实 | 来源（文件 : 行） |
|---|---|---|
| `pet_ids()` 口径 | 扫描 **磁盘** `assets/pets/*/config.json` 的 `pet_id` 字段 ⇒ **`['cat_001','dog_001','panda_001']`（恒 3 个）** | `asset_manager.py:170-188`、`:267-301` |
| `known_pet_keys()` 口径 | `pet_ids()` **∪** `assets` 表 `pet_type`（`AssetRepository.list_all()`，`SELECT … FROM assets`，**全表**） | `runtime_factory.py:232-240`、`asset_repository.py:68-70` |
| ⇒ **实键全集** | ⚠️ **动态**，取决于 `assets` 表内容：**当前真实库 = 4 键** `{cat, cat_001, dog_001, panda_001}`（DB 仅 cat）；**dog/panda 素材入库后 = 6 键** `{cat, cat_001, dog, dog_001, panda, panda_001}` | 上式 + §0.2 实测 |
| 解析规则 | `_resolve_pet_type`：命中 `pet_id` 索引 → 对应 `pet_type`；**未命中 → 按 `pet_type` 直用**（存量兼容） | `asset_manager.py:318-343` |
| 物理同一性 | `cat` 与 `cat_001` 解析到**同一 `pet_type`**（同一套素材） | 同上 |
| 计数命名空间 | 但 `Runtime.pet_id` / `Event.pet_id` / `DataManager._pet_id` 存的是**字面键** ⇒ `cat` 与 `cat_001` **各写一套计数** | `runtime_factory.py:175`、`:157-159`；`pipeline.py:174` |
| 前端目录 | 已**只用** canonical 3 键（`AVAILABLE_PETS = cat_001 / dog_001 / panda_001`） | `frontend/src/config/pets.ts` |
| 上位裁决 | 来源：用户 3.2-A 裁决「**`pet_id` 或 `pet_type` 均合法**」 | `phase3_backend_multi_pet_context_decision.md:48` |

> ⚠️ **口径更正（非新 finding，仅对前序报告的条件化精化）**：`phase3_2_b_routeb_planning_report.md` §2.1 把「合法键全集 = **6 个**」记为**现状事实**。
> 经本次只读复核，该值**成立的前提是 `assets` 表已登记 3 个 `pet_type`**；**当前仓库真实库只登记了 `cat`** ⇒ 实键全集为 **4**，
> 且 `?pet_id=dog` / `?pet_id=panda` **当前会被 `close(1008)` 拒收**（因为 `dog`/`panda` 不在实键集内），而 `?pet_id=dog_001` 合法但**静默无动画**（= §7.1 现象）。
> **决策影响**：A1 的「合法集」不是一个静态 6 键集合，而是**随 `assets` 表变化**；无论选 A/B/C，都必须同时明确「合法集的数据源」与「入库前后的行为差异」。

### 1.2 三个 Option（**均不选择**，仅列代价）

| Option | 做法 | 影响面 | 代价 / 需修订 |
|---|---|---|---|
| **A —— 仅 canonical** | 合法集收缩为 `{cat_001, dog_001, panda_001}`；`?pet_id=cat` → `close(1008)` | WS 合法集收缩；DB 不再产生 `cat` 行；stats/events 单命名空间；前端**无需**改 | ⚠️ **直接推翻 MP-1 的既有用户裁决**（「`pet_id` 或 `pet_type` 均合法」）⇒ **修订冻结契约 + 推翻历史裁决**；⚠️ **破坏 3 个冻结测试**（`test_websocket_endpoint.py:495-520` 锁 `?pet_id=cat`、`:523-550` 锁 `?pet_id=dog`、`:553-564` 锁 `?pet_id=cat_001`）；⚠️ 存量 alias 行成**孤儿命名空间** ⇒ 需数据处置裁决（A9） |
| **B —— 保留 alias + resolver 规范化** | 新增 resolver：`cat → cat_001`；**DB 永写 canonical**、**API 永返 canonical** | WS 合法集**不变**；DB 写入口径变更；stats/events 单命名空间 | ① 新增**规范化决策点**（新模块 / 新条款）；② 触及 **MP-3 写绑定语义**（`DataManager._pet_id` 由「传入值」→「规范化值」）⇒ 需修订 MP-3 或新增条款；③ 存量 alias 行需回填裁决（A9）；④ ⚠️ **API-2 Forbidden 明文禁「把 `pet_id → pet_type` 映射搬进 API 层」** ⇒ resolver 必须落 `services/**`；⑤ ⚠️ `runtime_factory.py` 行数预算仅 **+24**（AS-4）⇒ 宜**新开**模块（如 `app/services/pet_context.py`） |
| **C —— 维持双 namespace（现状）** | 不改任何东西 | 零改动；✅ 不动任何冻结契约 | ① 同一宠物**双统计**；② ⚠️ **查询歧义由「内部」变「对外」**：Route B 一旦开放 `?pet_id=`，`GET /stats?pet_id=cat` 与 `?pet_id=cat_001` 返回**不同数字**，调用方无从判断真值；③ 该歧义在 WS 阶段已存在但**不可见**（读路径固定 NULL），B-read 会把它**可见化** |

### 1.3 报告性结论（**不代裁**）

> **A1 是 Route B 的硬前置且具「继承性」**：Route B 新增的 `?pet_id=` 读参数**必然继承**同一套合法键语义。
> 在 canonical 未裁决前就开放 pet-scoped 读，会把 §1.2 Option C 代价② 的**内部歧义直接固化为对外契约歧义**。
> **推荐：B**（在 A / B / C 中，B 是唯一「既保持 WS 合法集不变、又消除双命名空间」的选项；代价是需新增一条
> `services/**` 层 resolver 条款 + MP-3 增量声明）。**若 owner 倾向零改动**，则 C 必须**同时**在 decision 文档里
> 明文写明「`/stats?pet_id=cat` 与 `?pet_id=cat_001` 可能不等，且此为已知并接受」—— 否则测试无法写出无歧义断言。

---

## 2. A2 —— 默认作用域语义

### 2.1 现状：三层「默认」口径**互不相同**（实测）

| 层 | 默认连接（无 `?pet_id`）实际取值 | 来源 |
|---|---|---|
| `Runtime.pet_id` | **`cat_001`**（派生 = `AssetManager.pet_ids()[0]`） | `runtime_factory.py:175`、`:179-201` |
| `events.pet_id`（写入） | **`cat_001`**（`pipeline._record` 用 `self._runtime.pet_id`） | `pipeline.py:174` |
| `interactions.pet_id`（写入） | **`NULL`**（`DataManager._pet_id is None`） | `runtime_factory.py:157-159` |
| HTTP 读路径 | **固定 `pet_id IS NULL`** | `stat_repository.py:43-47` |
| `GET /api/playback/state` 返回的 `pet_id` | **`cat_001`** | `playback.py` ← `pipeline.snapshot()` |
| `GET /api/events/recent`（无参） | **读全表**（SQL **无 WHERE**）⇒ 含 `cat_001` 行 | `event_repository.py:52-53` |

⇒ **「默认」是一个混合体**：**计数**落 `NULL` 桶，**事件行 + 播放态**落派生 `cat_001`。（= MP-4 登记的不对称。）
⚠️ 附带既有不对称：`/events/recent`（无参）读**全表**，而 `/stats`（无参）只读 `NULL` 桶 —— 两者口径本就不一致。

### 2.2 ⭐ Runtime 能否区分「派生 `cat_001`」与「显式 `?pet_id=cat_001`」？——**不能**（代码级证据）

| 路径 | 代码链 | `Runtime.pet_id` | `DataManager._pet_id` |
|---|---|---|---|
| 默认（无 query） | `get_pipeline()` → `SimulationPipeline()` → `build_runtime(pet_id=None)` → `:175` `_derive_pet_id()` → `pet_ids()[0]` | **`"cat_001"`** | **`None`** |
| 显式 `?pet_id=cat_001` | `ws.py:149` `build_pipeline_for_pet("cat_001")` → `SimulationPipeline(…, pet_id="cat_001")` → `build_runtime(pet_id="cat_001")` | **`"cat_001"`** | **`"cat_001"`** |

- `Runtime` 是 `@dataclass(frozen=True)`，字段表（`runtime_factory.py:90-101`）**无任何「是否显式指定」标志** ⇒ 两条路径产出的 `Runtime` **逐字段相同**。
- **唯一差异**在 `DataManager._pet_id`（`runtime_factory.py:157-159`），而它是**私有字段**，`DataManager` 的公开 API 恰 3 个方法（`write_event` / `record_action` / `aggregate_counter`），**无公开访问器**。
- ⇒ **任何依赖「区分派生 vs 显式」的裁决，都必须先补一条契约（新增一个公开信号），否则在现状下不可实现。**

### 2.3 四个 Option（**均不选择**）

| Option | 做法 | 影响 / 代价 |
|---|---|---|
| **X —— Default = NULL bucket** | 把默认连接的 `events.pet_id` **也**改为 `NULL`，与 `interactions` 对齐 | ✅ 语义最干净（读写同源）；❌ **破坏性**：默认连接历史事件行是 `cat_001` ⇒ 新行为 `NULL` ⇒ **历史双口径**，需 migration（A9）；❌ 触及 `pipeline._record` 与 `build_runtime` 默认分支 |
| **Y —— Default = cat_001** | 统一默认到派生键（`DataManager` 默认也写 `cat_001`） | ❌ **推翻 MP-3**（「仅显式 pet 连接按 pet 写」）；❌ 默认计数从 `NULL` 迁到 `cat_001` ⇒ **`GET /api/stats` 立刻读空** ⇒ 必须**同时**改读路径（连锁）；❌ 破坏「默认路径与 Phase 1 逐字一致」；❌ 与前端 `DEFAULT_SELECTED_PET_ID = null`（MPF-2）冲突 |
| **Z —— 保留双轨 + 显式登记** | 承认两轨并存，只把语义**写明** | ✅ 零代码改动；⚠️ 但 Route B **必须**为「无 pet 参数」定义**唯一**答案，否则 `/stats` 与 `/stats?pet_id=cat_001` 的关系无法表述 |
| **W —— 保留 NULL 默认 + 登记已知不对称** | 保留默认写 `NULL`；`?pet_id` 显式时读该 pet；**无参时维持 NULL 桶**，并明文登记「默认连接的 `events` 行写 `cat_001`、计数写 `NULL`」 | ✅ **零写路径改动、零 migration**；⚠️ 仍留 MP-4 不对称（需在 decision 文档显式声明「已知并接受」） |

### 2.4 连带：`GET /api/stats` 无参语义（A3，S-1 / S-2 / S-3）

| 子选项 | 含义 | 后果 |
|---|---|---|
| **S-1** | 无参 = **`NULL` 桶**（现状） | 与现状一致；但默认 WS 连接的 `events` 行写 `cat_001` ⇒ 默认事件在**计数视图**里不可见（仅在其 `events` 明细可见） |
| **S-2** | 无参 = **`cat_001`** | 与 `/state` 的返回一致；但**推翻**「默认写 NULL」（≈ Option Y） |
| **S-3** | 无参 = **全 pet 聚合** | 语义最直观；但需新增聚合 SQL 口径（**D6 禁第二套统计口径** ⇒ 需裁决），且与既有 `NULL` 行的关系需定义 |

### 2.5 报告性结论（**不代裁**）

> **A2 必须在 Route B 之前定死**：否则「`/api/stats` 与 `/api/stats?pet_id=cat_001` 是否应相等」这一最基本的问题**无解**，测试无法写出无歧义断言。
> **推荐：W（+ S-1）**—— 零代码改动、零 migration、可立即支撑 B-read；代价是必须在 decision 文档中**明文登记 MP-4 不对称并声明「已知并接受」**。
> ⚠️ 若 owner 后续希望**彻底消除**不对称，则须走 X（+ A9 migration 裁决），**不应**选 Y（会同时推翻 MP-3 与 MPF-2）。
> ⚠️ **独立提醒**：若 A2 最终需要「区分派生与显式」（例如为了 X），**须先补 §2.2 指出的公开信号契约** —— 这是 A2 的隐藏前置。

---

## 3. A4 —— Route B 范围：**B-read only** 还是含 **B-live**

### 3.1 既有结论复述（R-5，不重复调查）

「pet scoped HTTP API」**不是同质目标**，天然分裂为两半：

| 子路线 | 范围 | 可行性 |
|---|---|---|
| **B-read** | `GET /api/stats` + `GET /api/events/recent` 支持 `?pet_id=<key>` | ✅ **可行且轻**（读仓储**无状态**，只持有 `Database`）：加形参 + 参数化 SQL。**不需要** per-pet runtime、**不引入**任何全局态 |
| **B-live** | `GET /api/playback/state`（+ 可能 `POST /api/events/simulate`）按 pet 作用域 | ❌ **现状下不可行**（详见 §3.3） |

### 3.2 B-read 最小实现面（精确到文件 : 行）

| # | 文件 | 现状（只读实测） | 最小改动 |
|---|---|---|---|
| 1 | `backend/app/repositories/stat_repository.py` | `:43-47` `_SQL_SELECT_COUNTERS` **模块级常量硬编码** `WHERE pet_id IS NULL`；`:61` `def stats(self) -> dict` **无形参**；`:76` `conn.execute(_SQL_SELECT_COUNTERS)` | `stats(pet_id: str \| None = None)`；SQL 拆为「NULL 版（**逐字保留**）」+「`pet_id = ?` 版」；**默认分支必须与现状逐字一致** |
| 2 | `backend/app/repositories/event_repository.py` | `:48` 9 列常量；`:52-53` `_SQL_LIST_RECENT` = `SELECT … FROM events ORDER BY created_at DESC, id DESC LIMIT ?`（**无 WHERE**）；`:73` `def list_recent(self, limit: int)`；`:85` execute | `list_recent(limit, pet_id=None)`；可选 `WHERE pet_id = ?`；**无参分支逐字不变** |
| 3 | `backend/app/api/stats.py` | `:34` `DEFAULT_LIMIT=20` · `:36` `MAX_LIMIT=200`；`:115` `/stats` → `reject_unknown_query(request.query_params, frozenset())`（**拒全部**）；`:135` `/events/recent` → `frozenset({"limit"})` | 白名单 → `frozenset({"pet_id"})`；解析 + 校验 `pet_id`（复用 `known_pet_keys`）；非法 → **`400 INVALID_REQUEST`**；透传仓储 |
| 4 | `backend/app/api/_query.py` | `reject_unknown_query(query_params, allowed_keys)` = **唯一闸门**（QP-2：三端点同策略） | **无需改**（QP-2 不破） |
| 5 | 契约层 | ⛔ `step4_api_query_boundary_decision.md:191`（QP-4 逐字禁 `pet_id`）· ⛔ `phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158`（MP-5 未授权） | **必须** CR 修订 QP-1/QP-4 + **必须**显式解除 MP-5 |

**⛔ B-read 明确不触碰**：`database/schema.sql`（**无需迁移**：`UNIQUE(stat_type, stat_key, pet_id)` 是 Phase 1 既有 DDL）· `app/platform/**` · `api/ws.py` · `playback.py` · `pipeline.py`。
**约束（不得放松）**：**AS-1** 错误码恰 3 个（非法 `pet_id` 折为 `400 INVALID_REQUEST`，**不得**新增 code）· **D6** `interactions` 是唯一统计载体（**不得**引入第二套统计口径）· **AS-4** 三模块 `<300` 行 · **DB-3/4/6** `api/**` 零引擎 import。

### 3.3 B-live 的两条出路**各自有硬障碍**

| 出路 | 是否违反 MP-2 | 后果 |
|---|---|---|
| ① **per-request 新建 runtime**（`build_pipeline_for_pet(key)`） | ⚠️ **不违反 MP-2 字面**（MP-2 禁的是「全局 current_pet / 共享 active runtime / 进程级 pet 态 / 后台 registry」，per-request 临时物件图不在其中） | ❌ **语义退化**：请求返回后状态被丢弃 ⇒ `/state` **恒返回 `idle`**，`/simulate` 的效果**无法被后续请求观察到** ⇒ 无实用价值；且每请求新建 SQLite 句柄 + 素材扫描，成本高 |
| ② **引入 pet runtime 缓存 / 注册表** | ⛔ **直接违反 MP-2** | 不可行（除非先修订 MP-2） |

> **B-live 确有真实需求（用户可见证据）**：3.2-B 前端已能经 `?pet_id=` 开 WS 收该宠物 push 帧（`useRuntimePush(petId)`），
> 但其**刷新/轮询路径**是 `GET /api/playback/state`（走默认单例）⇒ **选中宠物的播放态经 HTTP 读不回来**（读到的是默认宠物 `cat_001`）。这就是既有遗留项 B2。
> ⚠️ 连带风险 **R-10**：若只上 B-read，UI 会出现「计数随选中宠物变、播放态不变」的**新不一致**。

### 3.4 报告性结论（**不代裁**）

> **推荐：A4 = 只做 B-read**，把 **B-live 从本步剥离、单独立项裁决**。
> 理由：① B-read 技术可行且轻、无全局态、无需 migration；② B-live 无论走哪条出路都要么**语义退化**、要么**违反 MP-2**，
> 把它塞进同一次授权会让 Route B 半途撞上两难；③ 剥离后 B-read 可以立刻产生可验证的用户价值（`/stats` / `/events/recent` 按 pet 过滤）。
> ⛔ 若 owner 选择含 B-live，则**必须先额外裁决**：「per-request 新建（接受 `/state` 恒 `idle`）」vs「引入 registry（须先修订 MP-2）」—— 二者都需独立 CR。

---

## 4. 一页速览（推荐裁决，**供 owner 拍板，不代裁**）

| 裁决 | 推荐 | 一句话理由 | 前置 / 后置 |
|---|---|---|---|
| **A1** canonical pet key | **B** —— alias + resolver 规范化（落 `services/**` 新模块） | 唯一「WS 合法集不变 **且** 消除双计数命名空间」的选项；代价是需新增 resolver 条款 + MP-3 增量声明 | 后置 A9（存量 alias 行处置）；⚠️ 须同时明确「合法集数据源随 `assets` 表变化」 |
| **A2** 默认作用域 | **W** —— 保留 `NULL` 默认 + 明文登记 MP-4 不对称（「已知并接受」） | 零代码改动、零 migration，可立即支撑 B-read | 若改选 X ⇒ 需 A9 migration 裁决；**若需「区分派生 vs 显式」⇒ 须先补公开信号契约**（§2.2） |
| **A4** Route B 范围 | **B-read only**；**B-live 剥离单独立项** | B-read 可行且轻；B-live 两条出路分别撞「语义退化」与「MP-2 禁令」 | 后置 A5（`/simulate` 收 `pet_id`?）/ R-10（前端新不一致） |

**三项的依赖顺序**：**A1 + A2（纯语义裁决，零代码成本）→ A4（范围裁决）→ 才可进入 A6/A7 的契约动作**。

---

## 5. 若按上述推荐裁决，接下来的授权清单（**不含实现**）

| # | 动作 | 类型 | 依据 |
|---|---|---|---|
| 1 | **QP-1 / QP-4 的 CR**：把 `pet_id` 移出「禁止新增的 query 参数」清单并加入白名单 | ⛔ **硬性 CR**（修订冻结文件本体） | `step4_api_query_boundary_decision.md:191` |
| 2 | **显式解除 MP-5 禁令**（授权 pet-scoped HTTP API，**限 B-read 范围**） | ⛔ 显式授权 | `phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158` |
| 3 | 新增 decision 文档（`MB-*`？）+ **0 撞车核查**；⛔ **旧冻结文档本体零改** | 文档层 | 规划报告 A8（`MB-` 前缀需先做全仓 0 命中确认） |
| 4 | `PROJECT_RULES.md` §十四 登记（**变体 B**，锚点 = `HR-6` / `HR-5` 行之后，⛔ **绝不含 `## 十五`**） | 追加 | §十四 维护铁律 |
| 5 | **A9 存量数据处置**（仅当选 A / 选 X / 选 B 且需回填时） | migration 裁决 | 规划报告 A9 |

---

## 6. 与 A1/A2/A4 直接相关的既有风险（沿用 R-1~R-11，不新增）

| # | 风险 | 级别 | 缓解 |
|---|---|---|---|
| R-1 | QP-4 **明文禁止**为只读端点新增 `pet_id` query ⇒ 不先 CR 就动代码 = 违反冻结 | 🔴 | CR 未批前**零代码** |
| R-2 | MP-5 明文将 pet-scoped HTTP API 列为未授权 | 🔴 | 取得显式授权 |
| R-3 | canonical 未裁 ⇒ `?pet_id=cat` 与 `cat_001` 返回不同数字，歧义由内部变对外 | 🔴 | 先裁 A1 |
| R-4 | 默认作用域未裁 ⇒「`/stats` 是否等于 `/stats?pet_id=cat_001`」无解 | 🔴 | 先裁 A2 |
| R-5 | B-live 架构不可行（per-request 语义退化 / registry 违反 MP-2） | 🔴 | 剥离 B-live（A4） |
| R-6 | 非法 `pet_id` 必须折为 `400 INVALID_REQUEST`（AS-1 恰 3 code） | 🟡 | 复用既有 `InvalidRequestError` |
| R-7 | AS-4 行数预算：`runtime_factory.py` 仅 **+24** ⇒ resolver 落此处会撞 300 行守卫 | 🟡 | 新开 `app/services/pet_context.py` |
| R-8 | 既有契约测试假设「读路径只反映 NULL 作用域」⇒ 改读路径会破既有断言 | 🟡 | 同步改写断言；全量回归须 `550 passed`，数字变化记 `before → after` |
| R-10 | 只上 B-read ⇒ UI 出现「计数随宠变、播放态不变」新不一致 | 🟡 | 或同时给 B-live 裁决，或明确「UI 暂不用 HTTP 读 pet 计数」 |

---

## 7. 本文件边界声明

- ✅ **本次未修改任何生产代码、测试、冻结契约、`PROJECT_RULES.md`**；**未重新调查**（仅对既有结论做条件化精化，见 §1.1 更正框）。
- ✅ 本文档是**裁决输入**，**不是** decision / 不是契约；在 owner 采纳并落成 decision 文档前**无冻结效力**。
- ⛔ 本文档**不构成**任何实现授权；**特别不构成** QP-1/QP-4 的修订、MP-5 的解除。
- **待 owner 裁决**：**A1 / A2 / A4**（三项硬前置）。裁决前 Route B **不得进入实现**。
