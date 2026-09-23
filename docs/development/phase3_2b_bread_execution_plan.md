# Phase 3.2-B B-read 执行方案

> **文档性质**：执行方案（**非冻结 · 不构成授权**）。owner 已完成 A1/A2/A4 拍板；本方案只描述**怎么实现**，
> **不含任何代码改动**，也**不替代** `docs/development/*_decision.md` 的冻结契约。
>
> **输入**：`docs/development/phase3_2b_route_b_decision_input.md`（非冻结 · 裁决输入）· 三道冻结锁
> **QP-4**（`step4_api_query_boundary_decision.md:191`）· **MP-5**（`phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158`）
> · **MP-4**（同文件 `:90-101`）。
>
> **基线（本方案生成时只读实测）**：HEAD `0aad974` · 分支 `phase1-step1-foundation` · working tree **clean** ·
> commit **86** · 后端 **550 passed** · 前端 **13 文件 / 123 用例**。
>
> **范围**：仅 **B-read**（`GET /api/stats` + `GET /api/events/recent` 的 pet 作用域读）。**B-live 已剥离**，单独立项。

## 一、拍板结果

### 1.1 owner 显式裁决

| 裁决 | owner 选择 | 含义（本方案据此展开） |
|---|---|---|
| **A1** canonical pet key | **B** —— 保留 alias + resolver 规范化 | 新增 `normalize_pet_key(key, settings) -> str \| None`；WS 合法集**不变** |
| **A1-resolver 作用域** | **仅 HTTP 读侧** | ⛔ **WS 写侧逐字不变**（`api/ws.py` 零改动）⇒ 3.2-A / 3.2-C 既有写行为与用例零影响 |
| **A2** 默认作用域 | **W** —— 保留 `NULL` 默认 + 明文登记 MP-4 不对称 | 无参读路径**逐字不变**；**零 migration** |
| **A4** Route B 范围 | **B-read only** | B-live（`/playback/state` + `/events/simulate`）**不在本方案** |

### 1.2 连带项（⚠️ **由主裁决推导，owner 未逐项勾选 ⇒ 请一并确认**）

| 裁决 | 推导值 | 推导依据 |
|---|---|---|
| **A3** `/stats` 无参语义 | **S-1**（无参 = `NULL` 桶，现状） | 裁决输入文档 §3.4：S-1 与现状一致；A2=W 下是唯一不引入新写路径的选项 |
| **A5** `/simulate` 是否收 `pet_id` | **不触发**（自然悬置） | 该文档 §五：A5「依赖 A4」，A4 = B-read only ⇒ 本项无对象 |
| **A9** 存量数据处置 | ⚠️ **未能干净推导为「不触发」** | 该文档 §五 的**条件列**写「`A1=B（需回填）`」，而**推荐列**写「A1=B + A2=W 下不触发」——**两处口径不一致**。本方案把 A9 折入 **P-2**（见 §3.4），须 owner 明示 |

### 1.3 无选项、仅记录的硬性推论

选定 B-read 后，下列三项**不是可选**，而是「不满足即零代码可动」：

| # | 动作 | 依据 |
|---|---|---|
| **A6** | 显式解除 **MP-5**（授权 pet-scoped HTTP API，**限 B-read 范围**） | MP-5 明文列其为「未实现、未授权」；**登记 ≠ 解除** |
| **A7** | **QP-1 / QP-4 的硬 CR**：`pet_id` 移出「禁止新增 query 参数」清单并进白名单 | QP-4 `:191` 逐字禁 `pet_id`；不修订则实现步第一步即撞冻结 |
| **A8** | 新增 decision 文档（**`MB-*`**）+ `PROJECT_RULES.md` §十四 登记（变体 B） | 沿用 3.2-B 先例：新文档声明受权增量，**旧冻结文档本体零改** |

> ✅ **`MB-*` 的 0 撞车核查（本方案生成**前**，只读）**：全仓 grep `\bMB-` 仅命中裁决输入文档自身 **3** 处
> （`phase3_2b_route_b_decision_input.md:178` / `:214` / `:264`），未与已登记的 **13** 个显式 FROZEN 命名空间
> （`GR HR LI MP MPF OB PC PH WC WE WG WL WP`）冲突。
> （本方案自身另有 **8** 处 `MB-*` 引用，均为**待登记名**的自指，不构成占用。）

### 1.4 ⚠️ 两处须 owner 明示的「拍板自洽性」提示（**只提示，不代裁**）

1. **A7 不能选「不出 CR」**：任何 pet 作用域读参数都必须先改 QP-4 本体，否则实现步第一步即违反冻结（R-1）。
2. **A6 不能选「不解除」**：不解除 MP-5 则 B-read 无合法实现空间（R-2）。

## 二、实现范围

### 2.1 生产代码（4 个文件：**改 3 + 新增 1**）

| # | 文件 | 现状（只读实测 `文件:行`） | 本步改动 |
|---|---|---|---|
| 1 | `backend/app/repositories/stat_repository.py` | `:43-47` `_SQL_SELECT_COUNTERS` **模块级常量硬编码** `WHERE pet_id IS NULL`；`:61` `def stats(self) -> dict`（**无形参**）；`:76` `conn.execute(_SQL_SELECT_COUNTERS)` | `stats(pet_id: str \| None = None)`；**新增**一个 `pet_id = ?` 版常量，**原常量逐字保留**；`pet_id is None` ⇒ 执行**原常量 + 原调用形态**（默认分支逐字不变）；⚠️ `:18-19` 模块 docstring 中「查询条件固定为 `pet_id IS NULL`」须做**最小诚实修订** |
| 2 | `backend/app/repositories/event_repository.py` | `:47-49` `_COLUMNS`（9 列）；`:52-54` `_SQL_LIST_RECENT` = `SELECT … FROM events ORDER BY created_at DESC, id DESC LIMIT ?`（**无 WHERE**）；`:73` `def list_recent(self, limit: int)`；`:85` execute | `list_recent(limit: int, pet_id: str \| None = None)`；`pet_id is None` ⇒ **逐字执行原 SQL**；非 None ⇒ `WHERE pet_id = ?`。`:23-24`「**不校验、不判断**（参数合法性由调用方负责）」的定位**保持不变** |
| 3 | `backend/app/api/stats.py` | `:109-116` `read_stats` → `:115` `reject_unknown_query(request.query_params, frozenset())`（**拒全部**）；`:119-138` `read_recent_events` → `:135` `frozenset({"limit"})`；`:34/:36` `DEFAULT_LIMIT=20` / `MAX_LIMIT=200` | 白名单 → `frozenset({"pet_id"})` / `frozenset({"limit", "pet_id"})`；新增 `pet_id` Query 形参；经 **resolver** 校验与规范化后**透传仓储**；非法 → `400 INVALID_REQUEST` |
| 4 | `backend/app/services/pet_context.py` | **不存在**（决策输入文档 §6.1 第 5 行已指定此落点） | 新增：`normalize_pet_key(key, settings) -> str \| None`。⛔ **不得**落 `runtime_factory.py`（AS-4 预算仅 **+24 行**，见 R-7） |

**⛔ 不触碰**：`app/api/_query.py`（QP-2 唯一闸门，**无需改**）· `api/ws.py` · `api/playback.py` · `app/platform/**` ·
`app/services/pipeline.py` · `runtime_factory.py` · `playback_state.py` · `database/schema.sql`（**零 migration**）· `frontend/**`。

### 2.2 测试

| 类型 | 内容 |
|---|---|
| **新增**（建议单文件，如 `backend/tests/test_pet_scoped_read_api.py`） | 用例清单见 §4.1 |
| **同步** | ⚠️ 实测后**预期无需改写任何既有断言**（依据见 §4.2）；仍须以全量回归确认 |

### 2.3 文档

| # | 文档 | 动作 |
|---|---|---|
| 1 | `docs/development/step4_api_query_boundary_decision.md`（**FROZEN**） | **CR 修订**：`pet_id` 移出禁止清单、进白名单（QP-1 / QP-4） |
| 2 | `docs/development/phase3_backend_multi_pet_context_decision.md`（**FROZEN**） | **受权增量声明**：解除 MP-5（限 B-read）+ 明文登记 MP-4 不对称「**已知并接受**」（A2=W 的代价） |
| 3 | `docs/development/phase3_2b_bread_decision.md`（新，`MB-*`） | 新增决策文档，声明受权增量；**旧冻结文档本体零改** |
| 4 | `PROJECT_RULES.md` §十四 | 登记 `MB-*` 块（**变体 B**）。锚点 = `HR-6` / `HR-5` 行之后，⛔ **绝不含 `## 十五`**；H2 恒 16、§十四 H3 恒 45 |

### 2.4 ⛔ 不触碰清单（汇总）

- **契约侧**：除 §2.3 第 1、2 项的**受权增量**外，其余冻结文档**一律不动**。
- **代码侧**：§2.1 末尾的 ⛔ 清单。
- **数据侧**：`database/schema.sql` · 存量数据（**除** A9 裁决为「回填」）。

## 三、实现顺序

### 3.1 阶段 3-A —— 契约层（**零代码**，硬前置）

1. 出 **QP-1 / QP-4 的 CR**（修订冻结文件本体）。**CR 未批 ⇒ 零代码**（R-1）。
2. 在 MP-5 所属决策文档落**受权增量声明**：解除禁令（限 B-read）+ 登记 MP-4 不对称。
3. 新增 `MB-*` decision 文档（含 0 撞车核查），并按 §十四 维护铁律完成登记。
4. **单目的提交**（docs-only，subject 无 body）。

### 3.2 阶段 3-B —— resolver + 读路径（**先 resolver，后读路径**）

5. 新增 `app/services/pet_context.py`：`normalize_pet_key(key, settings) -> str | None`。
6. 改 `stat_repository.py`：加可选形参 + 新常量；**原常量与原调用形态逐字保留**；docstring 最小诚实修订。
7. 改 `event_repository.py`：同上。
8. 改 `api/stats.py`：白名单 + Query 形参 + resolver 校验 + 透传；非法 → `400`。

### 3.3 阶段 3-C —— 验证与提交

9. **只读结构自检**：`api/stats.py` 零 SQL 字面量、零引擎 import；`pet_context.py` 不 import 三个引擎类。
10. **全量回归**：后端 pytest（须 `N passed` + `safe_delete=False`）+ 前端 `npm test`（预期 **123 → 123**）。
11. **行数预算复查**：三组合根模块仍 `< 300`（`pipeline.py` 290 / `playback_state.py` 156 / `runtime_factory.py` 275 —— 本步应**零净增**）。
12. **单目的提交**（代码 + 测试，subject 无 body）。

### 3.4 ⚠️ 阶段 3 的前置待确认项（**P-1 ~ P-4，须 owner 在进入实现前明示**）

**P-1（语义 · 最关键）** —— 读侧 resolver 归一化后，`GET /api/stats?pet_id=cat` 读哪个桶？

- **① 仅 canonical**（`cat` → `cat_001`，只读 `cat_001` 桶）：与「消除双命名空间」目标最一致；
  **代价**：若历史上存在 `cat` 行，将成为**静默不可见**（⇒ 触发 A9）。
- **② alias 聚合**（`cat` ⇒ 读 `pet_id IN ('cat','cat_001')`）：不丢数据；
  **代价**：SQL 复杂度上升 —— 这正是裁决输入文档 **R-11** 警告的「双键聚合」路径，且与 B 方案「DB 永写 canonical」的单一**写**口径**并存两套读口径**。
- **只读事实（降级依据）**：**当前真实库零 alias 行** —— `interactions.pet_id` = `[(None, 3)]`、`events.pet_id` = `[('cat_001', 14)]`。
  ⇒ 选 **①** 在**当前数据下无可见损失**，缺口是**未来性 / 语义性**的。
- ⛔ 本方案**不代裁 P-1**；它决定 3-B 的 SQL 形态。

**P-2（A9 处置）** —— 随 P-1 定：选 ① ⇒ 需明确「**回填**」还是「**明文登记不处理**」；选 ② ⇒ 无需处置。
> ⚠️ 提示：裁决输入文档 §五 对 A9 的**条件列与推荐列口径不一致**（见 §1.2）。

**P-3（`settings` 来源）** —— resolver 需 `settings`，而 `api/stats.py` 当前只用 `get_pipeline()` 依赖。
候选：复用 `api/ws.py:102-111` 的 `get_ws_settings`（`Settings.default()`，可被 `dependency_overrides` 覆盖），或在本步新增等价依赖。
⛔ 约束：**不得**改变 `get_pipeline()` 的既有契约；**不得**引入进程级 pet 态（MP-2）。

**P-4（HTTP 非法输入口径）** —— 非法 / 空 `pet_id` 一律折为 `400 INVALID_REQUEST`（**AS-1：错误码恰 3 个，不得新增**）。
与 WS 侧的 `close(1008)` 属**不同层**的等价处理，不构成契约冲突。

## 四、测试策略

### 4.1 新增用例（后端）

| # | 用例 | 断言要点 |
|---|---|---|
| **T-1** | `/stats?pet_id=<canonical>` | 返回该 pet 桶计数；与无参结果**可不同** |
| **T-2** | `/stats`（无参）**回归** | 仍读 `NULL` 桶 ⇒ **逐字等于改动前**（A2=W 的核心不变量） |
| **T-3** | `/events/recent?limit=N&pet_id=<canonical>` | 仅返回该 pet 行 |
| **T-4** | `/events/recent`（无参）**回归** | 仍读全表（**无 WHERE**）⇒ 逐字等于改动前 |
| **T-5** | 非法 `pet_id`（不存在的键） | `400` + `code == "INVALID_REQUEST"` |
| **T-6** | 未知参数（`x`）仍拒 | `400`（QP-2 不破） |
| **T-7** | `normalize_pet_key` 单元测试 | `cat → cat_001`；`cat_001 → cat_001`；未知 → `None`；空白 / 大小写口径 |
| **T-8** | 结构守卫 | `api/stats.py` 零 SQL 字面量、零引擎 import；`pet_context.py` 不 import `ActionEngine` / `InteractionEngine` / `PlaybackManager` |

### 4.2 既有用例影响（**实测结论 ⇒ R-8 由「中」下调为「低」**）

- 两个「未知 query 参数」用例用的是 **`x`**（`test_api_contract.py:357` / `:372` / `:379`），**不是** `pet_id`
  ⇒ 把 `pet_id` 加入白名单**不会**破坏它们。
- 无参路径逐字不变 ⇒ 「默认只反映 `NULL` 桶」的既有断言**继续成立**。
- ⇒ **预期既有 550 全数不变**；本轮数字变化应**仅**来自新增用例。
  ⚠️ 须以实测为准；如出现**既有**用例失败且无法解释 ⇒ **STOP**。

### 4.3 结构守卫（**不得放松任何一条**）

| 守卫 | 位置 | 本步约束 |
|---|---|---|
| `api/**` 不得出现 SQL 字面量 | `test_api_contract.py:578-586`；`SQL_KEYWORDS = ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM")`，对**所有字符串常量（含 docstring）**大小写不敏感匹配 | ⛔ `api/stats.py` 的**注释 / docstring 也不得**出现上述字面量 |
| `api/**` 不得 import 引擎 | `test_api_contract.py:567-575`（`ENGINE_NAMES` / `ENGINE_MODULES`） | 本步不引入 |
| 引擎 import 只许落组合根两模块 | `test_pipeline.py:327-342`，`allowed = {"services/runtime_factory.py", "services/pipeline.py"}` | ⛔ 新模块 `pet_context.py` **不得** import 三个引擎类 |
| 组合根三模块 `< 300` 行 | `test_pipeline.py:345-353`（判据 `if size >= 300` ⇒ **300 即 FAIL**） | 本步应**零净增**（290 / 156 / 275） |
| `api/**` 零 `sqlite3` import | `test_api_contract.py:578-586` | 本步不引入 |

> 说明：`pet_context.py` **不在** `COMPOSITION_ROOT_MODULES` 内 ⇒ **不受** 300 行守卫；但**受**引擎 import 守卫。

### 4.4 回归口径

- **后端**：全量 pytest；成功标志 = `N passed` + **`safe_delete=False`**；`before → after` 必须记录。
- **前端**：`npm test`（`vitest run`）—— 本步前端**零改动**，预期 **123 → 123**。
- **串行**：禁止与 pytest 并发（历史实测会把 pytest 从 ~2min 拖到 ~7.5min）。

## 五、风险与回滚

| # | 风险 | 级别 | 缓解 / 本方案处置 |
|---|---|---|---|
| **R-1** | QP-4 明文禁 `pet_id`；不先 CR 就动代码 = 违反冻结 | 🔴 高 | 阶段 3-A 先出 CR；**CR 未批前零代码** |
| **R-2** | MP-5 明文「未授权」 | 🔴 高 | A6 显式解除（限 B-read） |
| **R-3** | canonical 未裁 ⇒ 对外数字歧义 | 🔴 高 | **已裁 A1=B** ⇒ 对外只返 canonical（桶口径由 **P-1** 定） |
| **R-4** | 默认作用域未裁 ⇒ 无参语义无解 | 🔴 高 | **已裁 A2=W（+S-1）** ⇒ 无参 = `NULL` 桶，逐字不变 |
| **R-5** | B-live 架构不可行 | 🔴 高 | **已剥离**（A4 = B-read only） |
| **R-6** | 非法 `pet_id` 需折为既有 code | 🟡 中 | AS-1：复用 `INVALID_REQUEST`，**不新增 code** |
| **R-7** | AS-4 行数预算 | 🟡 中 | resolver 落**新**模块；三组合根模块**零净增** |
| **R-8** | 既有断言假设「读路径只反映 `NULL` 作用域」 | 🟢 **低**（原 🟡，经实测下调） | 无参路径逐字不变 + 未知参数用例用 `x` ⇒ 预期无需改写 |
| **R-9** | 前端静态子集一致性 | 🟢 低 | 前端已用 canonical ⇒ **无需改** |
| **R-10** | 只上 B-read ⇒ UI「计数随 pet 变、播放态不变」新不一致 | 🟡 中 | **本步不处理**，作为**已知遗留**登记；未上 B-live 前 UI 不使用 pet 计数 |
| **R-11** | B 方案读口径复杂 ⇒ 漏计数 | 🟡 中 | 由 **P-1** 决定；选 ② 才涉及双键聚合，须补往返用例 |

**回滚**：本步**零 schema 变更、零 migration** ⇒ 回滚 = `git revert` 单个提交即可，**无需数据回滚**。
若 P-1 选 ② 且实现后才发现漏计数 ⇒ 影响面**仅限读 SQL**，可独立回退而不动任何写入路径。

## 六、授权清单

| # | 授权项 | 类型 | 依据 |
|---|---|---|---|
| 1 | **QP-1 / QP-4 的 CR**（修订冻结文件本体） | ⛔ **硬性 CR** | `step4_api_query_boundary_decision.md:191` |
| 2 | 显式**解除 MP-5**（限 B-read 范围） | ⛔ 显式授权 | `phase3_backend_multi_pet_context_decision.md:108` / `:114-116` / `:158` |
| 3 | 新增 `MB-*` decision 文档（0 撞车已核） | 文档 | A8 |
| 4 | `PROJECT_RULES.md` §十四 登记（变体 B） | 追加 | §十四 维护铁律 |
| 5 | 生产代码**改**：`app/repositories/stat_repository.py` · `app/repositories/event_repository.py` · `app/api/stats.py` | 改 | §2.1 |
| 6 | 生产代码**新增**：`app/services/pet_context.py` | 新增 | A1=B · 决策输入文档 §6.1 |
| 7 | 测试：新增 pet-scoped 读用例文件（+ 如确需的既有断言同步） | 新增 | §4 |
| 8 | **P-1 ~ P-4 的明示**（进入实现前） | 前置裁决 | §3.4 |

⛔ **未列入本清单者一律不动**：`api/ws.py` · `api/playback.py` · `app/platform/**` · `pipeline.py` ·
`runtime_factory.py` · `playback_state.py` · `frontend/**` · `database/schema.sql` 均**不在**本步范围。

## 七、下一步

1. **owner 确认本方案**（含 §1.2 连带项、§3.4 的 **P-1 ~ P-4**）。
2. **阶段 3-A**：出 CR + 解除 MP-5 + 新增 `MB-*` + §十四 登记（docs-only 单目的提交）。
3. **阶段 3-B / 3-C**：resolver → 读路径 → 全量回归 → 单目的提交。
4. **不在本步范围**：B-live（`/playback/state` + `/events/simulate`，须先裁「per-request 新建（`/state` 恒 `idle`）」vs
   「引入 registry（须先修订 MP-2）」）· R-10 的 UI 不一致 · Route C / D · Route ④ 真实素材生产。

> **本方案不构成授权**；授权以 §六 的显式条文与 owner 的明示裁决为准。

### 7.1 证据来源（本次只读实测）

- **仓库状态**：`git status --porcelain -uall`（**空**）· `git log --oneline -3` = `0aad974` / `35e635c` / `9adfe40` ·
  目标方案文档生成前 **NOT EXISTS**。
- **读路径现状**：`stat_repository.py:43-47` / `:61` / `:76`；`event_repository.py:47-49` / `:52-54` / `:73` / `:85`。
- **API 现状**：`api/stats.py:34` / `:36` / `:109-116` / `:119-138`；`api/_query.py::reject_unknown_query`。
- **守卫实测**：`test_api_contract.py:532-540`（`ENGINE_NAMES` / `ENGINE_MODULES` / `SQL_KEYWORDS`）、`:567-575`、`:578-586`；
  `test_pipeline.py:77`（`COMPOSITION_ROOT_MODULES`）、`:327-342`、`:345-353`。
- **既有用例实测**：`test_api_contract.py:355-381`（未知参数用例使用 `x`，非 `pet_id`）。
- **WS 侧 settings 依赖**：`api/ws.py:102-111`。
- **`MB-*` 0 撞车**（生成前）：全仓 grep `\bMB-` 仅命中 `phase3_2b_route_b_decision_input.md:178` / `:214` / `:264`；
  加上本方案自指后为 **11** 处（2 文件），均非命名空间占用。
