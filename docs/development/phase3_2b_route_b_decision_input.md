# Phase 3.2-B Route B —— A1 / A2 / A4 裁决辅助（Decision Input）

> **状态**：**非冻结**（本文件是**裁决输入**，非 decision / 非契约；不构成任何实现授权）。
> **性质**：**只读汇总**。汇总既有两轮只读调查的证据，**不引入新 finding、不重新调查、不改任何代码/测试/冻结契约**。
> **目的**：把 Route B 的**三项硬前置（A1 / A2 / A4）**压到可拍板密度，并补齐 **A5~A9** 与实施范围、风险，
> 供项目 owner 直接拍板。
> **不代裁**：下文一律给「推荐 + 代价」，**最终由 owner 裁决**；在被 owner 采纳并落成 decision 文档之前**不具备冻结效力**。
> **日期**：2026-09-23 · **时点 HEAD**：`9adfe40` · 分支 `phase1-step1-foundation` · working tree clean · commit `84`
> （**证据来源与原始命令输出见 §九**）

---

## 一、任务背景

### 1.1 为什么需要这份文档

Route B（pet scoped HTTP API）已完成两轮**只读**调查，结论明确：

- **B-read**（`/api/stats` + `/api/events/recent` 按 pet 过滤）**技术可行且轻**（读仓储无状态，加形参 + 参数化 SQL 即可）；
- **B-live**（`/api/playback/state` + `/api/events/simulate` 按 pet 作用域）**现状下架构不可行**。

但 Route B **一步都动不了**，因为它被 **9 项授权点（A1~A9）** 卡住，其中 **A1 / A2 / A4 是三项硬前置**：
不裁 A1（合法键语义）与 A2（默认作用域语义），任何 `?pet_id=` 读参数都**无歧义断言可写**；
不裁 A4（范围），会把「读侧」与「活侧」混在一次授权里，半途撞上 MP-2 禁令。
本文档把两轮调查的证据汇总为一处，**不新增调查**。

### 1.2 当前状态（Step 0 实测）

```
$ git status --porcelain -uall                      → （空）
$ git log --oneline -3                              → 9adfe40 / 10498f1 / 3236226
$ ls docs/development/phase3_2b_route_b_decision_input.md → NOT EXISTS（本文件为新建）
```

### 1.3 三道硬锁（冻结契约原文，逐字引用）

| # | 锁 | 文件 : 行 | 原文 |
|---|---|---|---|
| **L1** | **QP-4** | `step4_api_query_boundary_decision.md:191` | 「❌ **为只读端点新增 query 参数**（`offset` / `since` / **`pet_id`** 等）—— 需新增须经 Change Request 修订本文件」 |
| **L2** | **MP-5** | `phase3_backend_multi_pet_context_decision.md:108`、`:114-116`（另见 `:158`） | 「- **pet-scoped HTTP API**（`/api/stats` / `/events/recent` / `/state` 的 pet 过滤或作用域参数）；」（列于「Phase 3.2-A **未实现**且**未授权**」）；「**登记 ≠ 解除实现约束** … 以上各项**均需另行显式授权**」；`:158`「pet-scoped HTTP API（Route B）—— 须改 `backend/app/api/*` 与读路径仓储，**另行授权**」 |
| **L3** | **MP-4** | `phase3_backend_multi_pet_context_decision.md:90-101` | 「**本条款只登记、不解决**：本差异**不视为缺陷**，Phase 3.2-A **未授权**任何修复」；「若要消除该不对称，须**另行显式授权**并单独裁决」 |

⇒ **A1 / A2 / A4 未裁之前，Route B 一行代码都动不了**（L1 是硬性 CR 前置，L2 需显式解除，L3 约束 A2）。

---

## 二、A1 —— canonical pet key 策略

### 2.1 事实（只读实测）

| 项 | 事实 | 来源（文件 : 行） |
|---|---|---|
| `pet_ids()` 口径 | 扫描 **磁盘** `assets/pets/*/config.json` 的 `pet_id` 字段 ⇒ **`['cat_001','dog_001','panda_001']`（恒 3 个）** | `asset_manager.py:170-188`、`:267-301` |
| `known_pet_keys()` 口径 | `pet_ids()` **∪** `assets` 表 `pet_type`（`AssetRepository.list_all()`，`SELECT … FROM assets`，**全表**） | `runtime_factory.py:232-240`、`asset_repository.py:68-70` |
| ⇒ **实键全集** | ⚠️ **动态**，取决于 `assets` 表内容：**当前真实库 = 4 键** `{cat, cat_001, dog_001, panda_001}`（DB 仅 cat）；**dog/panda 素材入库后 = 6 键** `{cat, cat_001, dog, dog_001, panda, panda_001}` | 上式 + §九 实测 |
| 解析规则 | `_resolve_pet_type`：命中 `pet_id` 索引 → 对应 `pet_type`；**未命中 → 按 `pet_type` 直用**（存量兼容） | `asset_manager.py:318-343` |
| 物理同一性 | `cat` 与 `cat_001` 解析到**同一 `pet_type`**（同一套素材） | 同上 |
| 计数命名空间 | 但 `Runtime.pet_id` / `Event.pet_id` / `DataManager._pet_id` 存的是**字面键** ⇒ `cat` 与 `cat_001` **各写一套计数** | `runtime_factory.py:175`、`:157-159`；`pipeline.py:174` |
| 前端目录 | 已**只用** canonical 3 键（`AVAILABLE_PETS = cat_001 / dog_001 / panda_001`） | `frontend/src/config/pets.ts` |
| 上位裁决 | 来源：用户 3.2-A 裁决「**`pet_id` 或 `pet_type` 均合法**」 | `phase3_backend_multi_pet_context_decision.md:48` |

> ⚠️ **口径更正（非新 finding，仅对前序报告的条件化精化）**：`phase3_2_b_routeb_planning_report.md` §2.1 把「合法键全集 = **6 个**」记为**现状事实**。
> 经本次只读复核，该值**成立的前提是 `assets` 表已登记 3 个 `pet_type`**；**当前仓库真实库只登记了 `cat`** ⇒ 实键全集为 **4**，
> 且 `?pet_id=dog` / `?pet_id=panda` **当前会被 `close(1008)` 拒收**（因为 `dog`/`panda` 不在实键集内），而 `?pet_id=dog_001` 合法但**静默无动画**（= §7.1 现象）。
> **决策影响**：A1 的「合法集」不是一个静态 6 键集合，而是**随 `assets` 表变化**；无论选 A/B/C，都必须同时明确「合法集的数据源」与「入库前后的行为差异」。

### 2.2 三个 Option（**均不选择**，仅列代价）

| Option | 做法 | 影响面 | 代价 / 需修订 |
|---|---|---|---|
| **A —— 仅 canonical** | 合法集收缩为 `{cat_001, dog_001, panda_001}`；`?pet_id=cat` → `close(1008)` | WS 合法集收缩；DB 不再产生 `cat` 行；stats/events 单命名空间；前端**无需**改 | ⚠️ **直接推翻 MP-1 的既有用户裁决**（「`pet_id` 或 `pet_type` 均合法」）⇒ **修订冻结契约 + 推翻历史裁决**；⚠️ **破坏 3 个冻结测试**（`test_websocket_endpoint.py:495-520` 锁 `?pet_id=cat`、`:523-550` 锁 `?pet_id=dog`、`:553-564` 锁 `?pet_id=cat_001`）；⚠️ 存量 alias 行成**孤儿命名空间** ⇒ 需数据处置裁决（A9） |
| **B —— 保留 alias + resolver 规范化** | 新增 resolver：`cat → cat_001`；**DB 永写 canonical**、**API 永返 canonical** | WS 合法集**不变**；DB 写入口径变更；stats/events 单命名空间 | ① 新增**规范化决策点**（新模块 / 新条款）；② 触及 **MP-3 写绑定语义**（`DataManager._pet_id` 由「传入值」→「规范化值」）⇒ 需修订 MP-3 或新增条款；③ 存量 alias 行需回填裁决（A9）；④ ⚠️ **API-2 Forbidden 明文禁「把 `pet_id → pet_type` 映射搬进 API 层」** ⇒ resolver 必须落 `services/**`；⑤ ⚠️ `runtime_factory.py` 行数预算仅 **+24**（AS-4）⇒ 宜**新开**模块（如 `app/services/pet_context.py`） |
| **C —— 维持双 namespace（现状）** | 不改任何东西 | 零改动；✅ 不动任何冻结契约 | ① 同一宠物**双统计**；② ⚠️ **查询歧义由「内部」变「对外」**：Route B 一旦开放 `?pet_id=`，`GET /stats?pet_id=cat` 与 `?pet_id=cat_001` 返回**不同数字**，调用方无从判断真值；③ 该歧义在 WS 阶段已存在但**不可见**（读路径固定 NULL），B-read 会把它**可见化** |

### 2.3 报告性结论（**不代裁**）

> **A1 是 Route B 的硬前置且具「继承性」**：Route B 新增的 `?pet_id=` 读参数**必然继承**同一套合法键语义。
> 在 canonical 未裁决前就开放 pet-scoped 读，会把 §2.2 Option C 代价② 的**内部歧义直接固化为对外契约歧义**。
> **推荐：B**（在 A / B / C 中，B 是唯一「既保持 WS 合法集不变、又消除双命名空间」的选项；代价是需新增一条
> `services/**` 层 resolver 条款 + MP-3 增量声明）。**若 owner 倾向零改动**，则 C 必须**同时**在 decision 文档里
> 明文写明「`/stats?pet_id=cat` 与 `?pet_id=cat_001` 可能不等，且此为已知并接受」—— 否则测试无法写出无歧义断言。

---

## 三、A2 —— 默认作用域语义

### 3.1 现状：三层「默认」口径**互不相同**（实测）

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

### 3.2 ⭐ Runtime 能否区分「派生 `cat_001`」与「显式 `?pet_id=cat_001`」？——**不能**（代码级证据）

| 路径 | 代码链 | `Runtime.pet_id` | `DataManager._pet_id` |
|---|---|---|---|
| 默认（无 query） | `get_pipeline()` → `SimulationPipeline()` → `build_runtime(pet_id=None)` → `:175` `_derive_pet_id()` → `pet_ids()[0]` | **`"cat_001"`** | **`None`** |
| 显式 `?pet_id=cat_001` | `ws.py:149` `build_pipeline_for_pet("cat_001")` → `SimulationPipeline(…, pet_id="cat_001")` → `build_runtime(pet_id="cat_001")` | **`"cat_001"`** | **`"cat_001"`** |

- `Runtime` 是 `@dataclass(frozen=True)`，字段表（`runtime_factory.py:90-101`）**无任何「是否显式指定」标志** ⇒ 两条路径产出的 `Runtime` **逐字段相同**。
- **唯一差异**在 `DataManager._pet_id`（`runtime_factory.py:157-159`），而它是**私有字段**，`DataManager` 的公开 API 恰 3 个方法（`write_event` / `record_action` / `aggregate_counter`），**无公开访问器**。
- ⇒ **任何依赖「区分派生 vs 显式」的裁决，都必须先补一条契约（新增一个公开信号），否则在现状下不可实现。**

### 3.3 四个 Option（**均不选择**）

| Option | 做法 | 影响 / 代价 |
|---|---|---|
| **X —— Default = NULL bucket** | 把默认连接的 `events.pet_id` **也**改为 `NULL`，与 `interactions` 对齐 | ✅ 语义最干净（读写同源）；❌ **破坏性**：默认连接历史事件行是 `cat_001` ⇒ 新行为 `NULL` ⇒ **历史双口径**，需 migration（A9）；❌ 触及 `pipeline._record` 与 `build_runtime` 默认分支；⚠️ 需 §3.2 的公开信号契约 |
| **Y —— Default = cat_001** | 统一默认到派生键（`DataManager` 默认也写 `cat_001`） | ❌ **推翻 MP-3**（「仅显式 pet 连接按 pet 写」）；❌ 默认计数从 `NULL` 迁到 `cat_001` ⇒ **`GET /api/stats` 立刻读空** ⇒ 必须**同时**改读路径（连锁）；❌ 破坏「默认路径与 Phase 1 逐字一致」；❌ 与前端 `DEFAULT_SELECTED_PET_ID = null`（MPF-2）冲突 |
| **Z —— 保留双轨 + 显式登记** | 承认两轨并存，只把语义**写明** | ✅ 零代码改动；⚠️ 但 Route B **必须**为「无 pet 参数」定义**唯一**答案，否则 `/stats` 与 `/stats?pet_id=cat_001` 的关系无法表述 |
| **W —— 保留 NULL 默认 + 登记已知不对称** | 保留默认写 `NULL`；`?pet_id` 显式时读该 pet；**无参时维持 NULL 桶**，并明文登记「默认连接的 `events` 行写 `cat_001`、计数写 `NULL`」 | ✅ **零写路径改动、零 migration**；⚠️ 仍留 MP-4 不对称（需在 decision 文档显式声明「已知并接受」） |

### 3.4 连带：`GET /api/stats` 无参语义（A3，S-1 / S-2 / S-3）

| 子选项 | 含义 | 后果 |
|---|---|---|
| **S-1** | 无参 = **`NULL` 桶**（现状） | 与现状一致；但默认 WS 连接的 `events` 行写 `cat_001` ⇒ 默认事件在**计数视图**里不可见（仅在其 `events` 明细可见） |
| **S-2** | 无参 = **`cat_001`** | 与 `/state` 的返回一致；但**推翻**「默认写 NULL」（≈ Option Y） |
| **S-3** | 无参 = **全 pet 聚合** | 语义最直观；但需新增聚合 SQL 口径（**D6 禁第二套统计口径** ⇒ 需裁决），且与既有 `NULL` 行的关系需定义 |

### 3.5 报告性结论（**不代裁**）

> **A2 必须在 Route B 之前定死**：否则「`/api/stats` 与 `/api/stats?pet_id=cat_001` 是否应相等」这一最基本的问题**无解**，测试无法写出无歧义断言。
> **推荐：W（+ S-1）**—— 零代码改动、零 migration、可立即支撑 B-read；代价是必须在 decision 文档中**明文登记 MP-4 不对称并声明「已知并接受」**。
> ⚠️ 若 owner 后续希望**彻底消除**不对称，则须走 X（+ A9 migration 裁决），**不应**选 Y（会同时推翻 MP-3 与 MPF-2）。
> ⚠️ **独立提醒**：若 A2 最终需要「区分派生与显式」（例如为了 X），**须先补 §3.2 指出的公开信号契约** —— 这是 A2 的隐藏前置。

---

## 四、A4 —— Route B 范围：**B-read only** 还是含 **B-live**

### 4.1 既有结论复述（R-5，不重复调查）

「pet scoped HTTP API」**不是同质目标**，天然分裂为两半：

| 子路线 | 范围 | 可行性 |
|---|---|---|
| **B-read** | `GET /api/stats` + `GET /api/events/recent` 支持 `?pet_id=<key>` | ✅ **可行且轻**（读仓储**无状态**，只持有 `Database`）：加形参 + 参数化 SQL。**不需要** per-pet runtime、**不引入**任何全局态 |
| **B-live** | `GET /api/playback/state`（+ 可能 `POST /api/events/simulate`）按 pet 作用域 | ❌ **现状下不可行**（详见 §4.2） |

### 4.2 B-live 的两条出路**各自有硬障碍**

| 出路 | 是否违反 MP-2 | 后果 |
|---|---|---|
| ① **per-request 新建 runtime**（`build_pipeline_for_pet(key)`） | ⚠️ **不违反 MP-2 字面**（MP-2 禁的是「全局 current_pet / 共享 active runtime / 进程级 pet 态 / 后台 registry」，per-request 临时物件图不在其中） | ❌ **语义退化**：请求返回后状态被丢弃 ⇒ `/state` **恒返回 `idle`**，`/simulate` 的效果**无法被后续请求观察到** ⇒ 无实用价值；且每请求新建 SQLite 句柄 + 素材扫描，成本高 |
| ② **引入 pet runtime 缓存 / 注册表** | ⛔ **直接违反 MP-2** | 不可行（除非先修订 MP-2） |

> **B-live 确有真实需求（用户可见证据）**：3.2-B 前端已能经 `?pet_id=` 开 WS 收该宠物 push 帧（`useRuntimePush(petId)`），
> 但其**刷新/轮询路径**是 `GET /api/playback/state`（走默认单例）⇒ **选中宠物的播放态经 HTTP 读不回来**（读到的是默认宠物 `cat_001`）。这就是既有遗留项 B2。
> ⚠️ 连带风险 **R-10**：若只上 B-read，UI 会出现「计数随选中宠物变、播放态不变」的**新不一致**。

### 4.3 报告性结论（**不代裁**）

> **推荐：A4 = 只做 B-read**，把 **B-live 从本步剥离、单独立项裁决**。
> 理由：① B-read 技术可行且轻、无全局态、无需 migration；② B-live 无论走哪条出路都要么**语义退化**、要么**违反 MP-2**，
> 把它塞进同一次授权会让 Route B 半途撞上两难；③ 剥离后 B-read 可以立刻产生可验证的用户价值（`/stats` / `/events/recent` 按 pet 过滤）。
> ⛔ 若 owner 选择含 B-live，则**必须先额外裁决**：「per-request 新建（接受 `/state` 恒 `idle`）」vs「引入 registry（须先修订 MP-2）」—— 二者都需独立 CR。

---

## 五、A5~A9 简要说明

> 来源：Route B Planning 报告 §5.5（`phase3_2_b_routeb_planning_report.md`，时点 HEAD `3236226`）。**本节为汇总，不新增调查。**

| # | 授权点 | 说明 | 与 A1/A2/A4 的关系 | 触发的锁 |
|---|---|---|---|---|
| **A5** | **`POST /api/events/simulate` 是否接受 `pet_id`** | API-1 `:92` 明写「后端补齐 `pet_id`…**不由 UI 提供**」、`:39`「UI 不发送」⇒ 若受理即改变 API-1 不变量 | **依赖 A4**：属 B-live 侧；A4 选 B-read only 时本项**自然悬置** | API-1 需 **CR** |
| **A6** | **解除 MP-5 禁令**（显式授权 pet-scoped HTTP API） | MP-5 明文将 pet-scoped HTTP API 列为「未实现、未授权」，登记 ≠ 解除 | **A1~A4 的公共前置**：不解除则零代码可动 | ⛔ L2（显式授权） |
| **A7** | **QP-1 / QP-4 的 CR 修订**（`pet_id` 移出「禁止新增 query 参数」清单并进白名单） | QP-4 `:191` 逐字把 `pet_id` 列入禁止项；QP-1 白名单表逐字冻结三个只读端点 | **A6 之后、实现之前**的硬性动作 | ⛔ L1（**硬 CR**） |
| **A8** | **新决策文档（`MB-*`）+ §十四 登记**（含**全仓 0 撞车核查**） | 沿用 3.2-B 先例：**新文档声明受权增量**，**旧冻结文档本体零改** | 文档层，**随 A1/A2 的裁决内容一起落** | 无（流程） |
| **A9** | **存量 `events.pet_id` / `interactions.pet_id` 数据处置**（回填 / 保留 / 双读） | 仅当选 **A1=Option A**、**A1=Option B（需回填）** 或 **A2=Option X** 时触发 | **A1 / A2 的连带裁决**；选 **A1=C + A2=W** ⇒ **无需** migration | 无（migration 裁决） |

**依赖顺序**：**A1 + A2（纯语义，零代码成本）→ A4（范围）→ A6 → A7 → A8；A5 随 A4 悬置，A9 随 A1/A2 的条件分支触发。**

---

## 六、授权后实施范围（B-read）

> 本节描述**若 owner 按 §八 推荐裁决**时的实施范围与边界。**本节不构成授权**。

### 6.1 B-read 最小实现面（精确到文件 : 行）

| # | 文件 | 现状（只读实测） | 最小改动 |
|---|---|---|---|
| 1 | `backend/app/repositories/stat_repository.py` | `:43-47` `_SQL_SELECT_COUNTERS` **模块级常量硬编码** `WHERE pet_id IS NULL`；`:61` `def stats(self) -> dict` **无形参**；`:76` `conn.execute(_SQL_SELECT_COUNTERS)` | `stats(pet_id: str \| None = None)`；SQL 拆为「NULL 版（**逐字保留**）」+「`pet_id = ?` 版」；**默认分支必须与现状逐字一致** |
| 2 | `backend/app/repositories/event_repository.py` | `:48` 9 列常量；`:52-53` `_SQL_LIST_RECENT` = `SELECT … FROM events ORDER BY created_at DESC, id DESC LIMIT ?`（**无 WHERE**）；`:73` `def list_recent(self, limit: int)`；`:85` execute | `list_recent(limit, pet_id=None)`；可选 `WHERE pet_id = ?`；**无参分支逐字不变** |
| 3 | `backend/app/api/stats.py` | `:34` `DEFAULT_LIMIT=20` · `:36` `MAX_LIMIT=200`；`:115` `/stats` → `reject_unknown_query(request.query_params, frozenset())`（**拒全部**）；`:135` `/events/recent` → `frozenset({"limit"})` | 白名单 → `frozenset({"pet_id"})`；解析 + 校验 `pet_id`（复用 `known_pet_keys`）；非法 → **`400 INVALID_REQUEST`**；透传仓储 |
| 4 | `backend/app/api/_query.py` | `reject_unknown_query(query_params, allowed_keys)` = **唯一闸门**（QP-2：三端点同策略） | **无需改**（QP-2 不破） |
| 5 | （若 A1=B）新模块 `backend/app/services/pet_context.py` | — | `normalize_pet_key(key, settings) -> str \| None`；⚠️ **不得**落 `runtime_factory.py`（行数预算 +24） |
| 6 | 契约层 | ⛔ `step4_api_query_boundary_decision.md:191`（QP-4 逐字禁 `pet_id`）· ⛔ `phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158`（MP-5 未授权） | **必须** CR 修订 QP-1/QP-4 + **必须**显式解除 MP-5 |

### 6.2 ⛔ 不触碰清单

`database/schema.sql`（**无需迁移**：`UNIQUE(stat_type, stat_key, pet_id)` 是 Phase 1 既有 DDL）· `app/platform/**` · `api/ws.py` · `api/playback.py` · `app/services/pipeline.py` · `frontend/**`（除另行授权）。

### 6.3 约束（**不得放松任何一条守卫**）

**AS-1** 错误码恰 3 个（非法 `pet_id` 折为 `400 INVALID_REQUEST`，**不得**新增 code）· **D6** `interactions` 是唯一统计载体（**不得**引入第二套统计口径）· **AS-4** 组合根三模块 `< 300` 行 · **DB-3/4/6** `api/**` 零引擎 import · **QP-2** 未知键一律 400、三端点同策略。

### 6.4 授权清单（若按 §八 推荐裁决）

| # | 动作 | 类型 | 依据 |
|---|---|---|---|
| 1 | **QP-1 / QP-4 的 CR**：把 `pet_id` 移出「禁止新增的 query 参数」清单并加入白名单 | ⛔ **硬性 CR**（修订冻结文件本体） | `step4_api_query_boundary_decision.md:191` |
| 2 | **显式解除 MP-5 禁令**（授权 pet-scoped HTTP API，**限 B-read 范围**） | ⛔ 显式授权 | `phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158` |
| 3 | 新增 decision 文档（`MB-*`）+ **0 撞车核查**；⛔ **旧冻结文档本体零改** | 文档层 | A8 |
| 4 | `PROJECT_RULES.md` §十四 登记（**变体 B**，锚点 = `HR-6` / `HR-5` 行之后，⛔ **绝不含 `## 十五`**） | 追加 | §十四 维护铁律 |
| 5 | **A9 存量数据处置**（仅当选 A / 选 X / 选 B 且需回填时） | migration 裁决 | A9 |

---

## 七、风险清单（R-1 ~ R-11，沿用 Route B Planning 报告 §5.3）

| # | 风险 | 级别 | 缓解 |
|---|---|---|---|
| **R-1** | **QP-4 明文禁止**为只读端点新增 `pet_id` query ⇒ 不先 CR 就动代码 = 违反冻结 | 🔴 高 | 先出 CR；CR 未批前**零代码** |
| **R-2** | **MP-5 明文**将 pet-scoped HTTP API 列为「未实现、未授权」⇒ 需显式解除 | 🔴 高 | 取得显式授权（A6） |
| **R-3** | canonical key 未裁决 ⇒ `?pet_id=cat` 与 `cat_001` 返回不同数字，歧义由**内部**变**对外** | 🔴 高 | 先裁 A1 |
| **R-4** | 默认作用域未裁决 ⇒「`/stats` 是否等于 `/stats?pet_id=cat_001`」无解，测试无法写无歧义断言 | 🔴 高 | 先裁 A2 |
| **R-5** | **B-live 架构不可行**：`/state`（+`/simulate`）需 per-pet runtime；per-request 新建 ⇒ 状态丢弃、`/state` 恒 `idle`；加 registry ⇒ 违反 MP-2 | 🔴 高 | **把 B-live 从本步剥离**（A4） |
| **R-6** | 非法 `pet_id` 的错误必须折为 **`400 INVALID_REQUEST`**（AS-1：恰 3 个 code）⇒ 不得新增 code | 🟡 中 | 复用既有 `InvalidRequestError` |
| **R-7** | AS-4 行数预算：`runtime_factory.py` 仅 **+24**；resolver（~+25）若落此处会撞 300 行守卫 | 🟡 中 | **新开** `app/services/pet_context.py`；改前先算预算 |
| **R-8** | 既有契约测试假设「读路径只反映 NULL 作用域」⇒ 改读路径会破既有断言（`test_api_contract.py`） | 🟡 中 | 同步改写断言；全量回归仍须 `550 passed`，正向数字变化须记录 `before → after` |
| **R-9** | 前端 `AVAILABLE_PETS` 是静态**子集**（3 canonical）⇒ 若后端 legal set 收窄（Option A）或规范化（Option B），需确认前端仍一致 | 🟢 低 | 前端已在 canonical 形态；Option A/B 下**无需**改 |
| **R-10** | 前端刷新路径读默认宠物状态（B2 遗留）⇒ 若 B-read 上线而 B-live 不上线，UI 会出现「计数随选中宠物变、播放态不变」的**新不一致** | 🟡 中 | 要么同时给出 B-live 裁决，要么明确「UI 暂不用 HTTP 读 pet 计数」 |
| **R-11** | `/api/stats` 在 Option B 下需双键聚合（或规范化）⇒ SQL 复杂度上升；若漏掉即静默漏计数 | 🟡 中 | 规范化在**写入侧**统一（Option B），读侧不必聚合 |

---

## 八、owner 拍板区

> **本节是 owner 的裁决位**。执行方给出推荐与代价，**不代裁**；owner 可直接在「裁决」列填写。

### 8.1 三项硬前置

| 裁决 | 可选项 | 执行方推荐 | 一句话理由 | 裁决（**owner 填写**） |
|---|---|---|---|---|
| **A1** canonical pet key | A / B / C（§2.2） | **B** —— alias + resolver 规范化（落 `services/**` 新模块） | 唯一「WS 合法集不变 **且** 消除双计数命名空间」的选项；代价 = 新增 resolver 条款 + MP-3 增量声明 | ☐ A　☐ B　☐ C |
| **A2** 默认作用域 | X / Y / Z / W（§3.3） | **W** —— 保留 `NULL` 默认 + 明文登记 MP-4 不对称（「已知并接受」） | 零代码改动、零 migration，可立即支撑 B-read；选 Y 会同时推翻 MP-3 与 MPF-2 | ☐ X　☐ Y　☐ Z　☐ W |
| **A4** Route B 范围 | B-read only / 含 B-live | **B-read only**；B-live **剥离单独立项** | B-read 可行且轻；B-live 两条出路分别撞「语义退化」与「MP-2 禁令」 | ☐ B-read only　☐ 含 B-live |

### 8.2 连带项（**随 8.1 条件触发**）

| 裁决 | 触发条件 | 推荐 | 裁决（**owner 填写**） |
|---|---|---|---|
| **A3** `/stats` 无参语义（§3.4） | 总是（随 A2） | **S-1**（`NULL` 桶，现状） | ☐ S-1　☐ S-2　☐ S-3 |
| **A5** `/simulate` 是否收 `pet_id` | 仅当 A4 含 B-live | **不收**（维持 API-1「UI 不发送」） | ☐ 收　☐ 不收 |
| **A9** 存量数据处置 | 仅当 A1=A、A1=B（需回填）或 A2=X | **无需**（推荐组合 A1=B + A2=W 下不触发） | ☐ 回填　☐ 保留　☐ 双读　☐ 不适用 |

### 8.3 必做项（无选项，仅确认）

| # | 动作 | 说明 | 确认（**owner 填写**） |
|---|---|---|---|
| **A6** | 解除 MP-5 禁令 | 显式授权 pet-scoped HTTP API（限 B-read 范围） | ☐ 批准 |
| **A7** | QP-1 / QP-4 的 CR | `pet_id` 移出禁止清单、进白名单（硬性） | ☐ 批准 |
| **A8** | 新 decision 文档 `MB-*` + §十四 登记 | 含全仓 0 撞车核查；旧冻结文档本体零改 | ☐ 批准 |

### 8.4 裁决生效后的动作顺序

**A1 + A2（纯语义）→ A4（范围）→ A6（解除 MP-5）→ A7（QP CR）→ A8（decision 文档 + 登记）→ 才可进入 B-read 实现步**（按项目刚性模板：授权清单 → 代码 → 全量回归 → 单目的提交）。

---

## 九、证据来源

### 9.1 来源清单

| # | 来源 | 性质 / 时点 |
|---|---|---|
| ① | `phase3_2_b_routeb_planning_report.md`（Route B Planning 报告） | 只读调查，Step 0~5；**时点 HEAD `3236226`** |
| ② | Route B Decision Preparation（Step 1~6 只读证据） | 只读调查；canonical 归一化点 / 默认作用域数据流 / 真实库分布 |
| ③ | 本次只读复核（2026-09-23） | 对下列代码文件与真实库的只读复核 |

**本次只读复核涉及的仓库文件**：`backend/app/services/runtime_factory.py` · `backend/app/services/asset_manager.py` ·
`backend/app/repositories/stat_repository.py` · `backend/app/repositories/event_repository.py` · `backend/app/repositories/asset_repository.py` ·
`backend/app/api/stats.py` · `backend/app/api/ws.py` · `backend/tests/platform/test_websocket_endpoint.py` ·
`docs/development/step4_api_query_boundary_decision.md` · `docs/development/phase3_backend_multi_pet_context_decision.md` ·
`docs/development/phase3_frontend_pet_context_decision.md` · `assets/pets/{cat,dog,panda}/config.json` · `database/pet_live.db`。

### 9.2 原始命令输出（Step 0 / Step 1）

```
$ git status --porcelain -uall          → （空）
$ git log --oneline -3                  → 9adfe40 / 10498f1 / 3236226
$ ls docs/development/phase3_2b_route_b_decision_input.md → NOT EXISTS（新建）
```

⚠️ **`sqlite3` CLI 本机缺失** ⇒ 第 7 组命令改用 Python `sqlite3` **只读 URI**（`file:…?mode=ro`），其余命令原样执行：

```
$ sqlite3 database/pet_live.db "SELECT pet_id, COUNT(*) FROM events GROUP BY pet_id;"
   ('cat_001', 14)

$ sqlite3 database/pet_live.db "SELECT pet_id, COUNT(*) FROM interactions GROUP BY pet_id;"
   (None, 3)

（附）assets 表 pet_type 分布：  ('cat', 5)
```

⇒ **精确复现 MP-4 双源不对称**：`events.pet_id` = 派生值 `cat_001`（非 NULL），`interactions.pet_id` = `NULL`；**零 alias 行**。
⇒ 并据此得出 §2.1 的「实键全集 = 4」结论（`pet_ids()` 3 个 ∪ `assets.pet_type` 1 个）。

### 9.3 冻结契约原文引用（逐字）

```
$ sed -n '191p' docs/development/step4_api_query_boundary_decision.md
- ❌ **为只读端点新增 query 参数**（`offset` / `since` / `pet_id` 等）—— 需新增须经 Change Request 修订本文件

$ grep -n "pet-scoped HTTP API" docs/development/phase3_backend_multi_pet_context_decision.md
108:- **pet-scoped HTTP API**（`/api/stats` / `/events/recent` / `/state` 的 pet 过滤或作用域参数）；
158:- **pet-scoped HTTP API**（Route B）—— 须改 `backend/app/api/*` 与读路径仓储，另行授权。
```

### 9.4 本文件边界声明

- ✅ 本次**未修改任何生产代码、测试、冻结契约**；**未重新调查**（仅对既有结论做条件化精化，见 §2.1 更正框）。
- ✅ 本文档是**裁决输入**，**不是** decision / 不是契约；在 owner 采纳并落成 decision 文档前**无冻结效力**。
- ⛔ 本文档**不构成**任何实现授权；**特别不构成** QP-1/QP-4 的修订、MP-5 的解除。
- **待 owner 裁决**：**A1 / A2 / A4**（§8.1）+ 连带项（§8.2）+ 必做项确认（§8.3）。裁决前 Route B **不得进入实现**。
