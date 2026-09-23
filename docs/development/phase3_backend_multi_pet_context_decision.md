# Phase 3.2-A Backend Multi-Pet Context Decision v1.0（FROZEN）

> **状态**：v1.0 **FROZEN**（2026-09-22，Phase 3.2 Governance Registration）。生效后变更须经 Change Request。
> **CR-1 修订（2026-09-23）**：**MP-5 的读侧部分解除**（见 `## Decision` 的 MP-5 与 `## 变更历史`）；
> 授权依据 = `docs/development/phase3_pet_scoped_http_api_decision.md`（v1.0 FROZEN，`MB-1 ~ MB-7`）。
> **输入**：`phase2_websocket_boundary_decision.md`（**WS-1 ~ WS-6**）、
> `phase2_websocket_event_model_decision.md`（**WM-1 ~ WM-6**）、
> `phase2_websocket_adapter_boundary_decision.md`（**WA-1 ~ WA-6**）、
> `phase2_websocket_runtime_integration_decision.md`（**WG-1 ~ WG-6**）、
> `phase2_websocket_push_boundary_decision.md`（**WP-1 ~ WP-6**）、
> `phase2_websocket_commit_point_decision.md`（**WC-1 ~ WC-6**）、
> `step4_data_layer_decision.md`（**D1 / D2 / D4**）、`step4_api_runtime_decision.md`（**DB-3 / DB-4 / DB-6**）。
> **同族文档**：`phase3_frontend_pet_context_decision.md`（**MPF-1 ~ MPF-7**，前端对应侧）。

## 本文档性质 —— 追溯冻结声明（**D6 裁决**）

本文档为**追溯冻结**（retrospective freeze）：其内容**全部是 Phase 3.2-A 已经实装、已经通过测试、
并已被用户在 Step 0 裁决过的既有行为**。

**D6 裁决原文精神**：**本登记只追溯记录既有实现，不改变历史冻结约束。**

由此推出三条硬约束：

1. 本文档**不新增**任何未实装的行为，**不引入**任何新的实现义务；
2. 本文档**不修改** `WS-*` / `WM-*` / `WA-*` / `WG-*` / `WP-*` / `WC-*` / `WL-*` / `LI-*` / `WE-*` / `GR-*` /
   `OB-*` / `PH-*` / `HR-*` / `PC-*` / `FS-*` 等任何既有冻结文档的**本体**（旧文档零改动）；
3. 本文档的冻结日期（2026-09-22）**晚于**其记录的实现日期（Phase 3.2-A），
   该时间差**如实记载**于本文件，**不追溯改写**任何历史提交或历史裁决。

## 编号空间声明

本文档使用 **`MP-1 ~ MP-5`**（Multi-Pet，**后端**侧）。

创建前已做全仓 **0 撞车核查**（2026-09-22）：全仓 43 个 `<PREFIX>-<n>` 命名空间中，
以 `MP` 开头者**仅 `{MP, MPF}`**；`MP-*` 与 `MPF-*` **互不重叠**；
子串级检查（`MP-` 是否被其它词吞并）**零命中**（`MPF-1` 中不含 `MP-` 子串）。

既有编号空间（**不重复使用**）：`UI/UB · FE/FC/FS/FCM/FD/RV/RS/RF/FP/PI/ES`（前端）、
`AS/DA/DB/DR/QP`、`PB/RB`、`WS/WM/WA/WT/WG/PC/WP/WC/WL/LI/WE/GR/OB/PH/HR`、
`MPF`（前端多宠物，见 `phase3_frontend_pet_context_decision.md`）。
**已废止**：`GD-*` → 改 `GR-*`。

## 裁决记录（Phase 3.2-A 的两处 Step-0 裁决）

Phase 3.2-A 执行期间，指令与冻结约束出现两处矛盾，按项目铁律 **STOP + 请裁决**（未自行判定）。用户裁决原文：

| # | 矛盾点 | 用户裁决 |
|---|---|---|
| 1 | MP-3 计数作用域：默认路径是否也按 pet 写？ | **「仅显式 pet 连接按 pet 写」** —— 默认 / HTTP / 旧 WS 路径保持 `pet_id IS NULL` |
| 2 | `?pet_id=` 的合法键集合 | **「`pet_id` 或 `pet_type` 均合法」** —— 合法集 = `AssetManager.pet_ids()` ∪ 已登记资产 `pet_type` |

## Decision（裁决总表 MP-1 ~ MP-5）

### 地位（R-MP-1 / R-MP-2 / R-MP-3）

- **R-MP-1**：`MP-*` = **connection-level pet context boundary**（连接级宠物上下文边界），
  **非** feature spec、**非**授权文件；
- **R-MP-2**：本文档 **不授权**任何实现（追溯冻结，见上「本文档性质」）；
- **R-MP-3**：本文档 **不修改** `WS` / `WM` / `WA` / `WG` / `WP` / `WC` / `WL` / `LI` / `WE` / `GR` /
  `OB` / `PH` / `HR` 及 **Event schema** · **WM-1 envelope** · **数据库 schema**。

### MP-1 —— Pet Context Ownership（连接级，冻结）

- 入口：`WS /api/ws?pet_id=<key>`，`pet_id: Optional[str] = Query(default=None)`；
  pet 上下文是**连接级**语义（方案 B），**不**进入 WM-1 envelope、**不**进入 Event schema、**不**改数据库 schema。
- **合法键** = `known_pet_keys(settings)` = `AssetManager.pet_ids()` ∪ 已登记资产的 `pet_type`
  （裁决 2：「pet_id 或 pet_type 均合法」；`AssetManager._resolve_pet_type` 对未登记为 `pet_id` 的键**按 `pet_type` 直用**）。
- **校验时机**：在 `await websocket.accept()` **之前**。
- **非法 / 空键** ⇒ `logger.info(...)` → `await websocket.close(code=1008)` → `return`：
  **不装配 runtime** · **不落 fallback pet** · **不 accept**。
- **缺省键**（无 query）⇒ 沿用注入的默认 pipeline（`Depends(get_pipeline)`），
  **向后兼容**：行为与 Phase 2.2 / Phase 1 **逐字一致**。

### MP-2 —— Runtime Isolation（per-connection，冻结）

- 合法 pet 键 ⇒ `build_pipeline_for_pet(key, settings)` 装配**该 pet 的独立物件图**
  （自有 `Database` 句柄 / `ActionEngine` 状态机 / `DataManager`），adapter 以 `build_websocket_adapter(pipeline.gateway)` **重建**以绑定该 pet 的 gateway。
- **禁**：全局 current_pet · 共享 active runtime · 进程级 pet 态 · 后台 pet registry。
- 实测证据：全仓 `backend/app/**` 的模块级可变全局**仅** `pipeline.py: _default_pipeline`（默认组合根单例，
  **不**承载 pet 上下文）；`current_pet` / `active_pet` / `pet_registry` 关键词**零命中**。

### MP-3 —— Counter Scope（仅显式 pet 连接按 pet 写，冻结）

- `DataManager(database, *, pet_id: str | None = None)`；`aggregate_counter` 分支：
  - `pet_id is None`（默认 / HTTP / 旧 WS）⇒ `_SQL_FIND_COUNTER_LEGACY`（`pet_id IS NULL`），
    与 Phase 1 及冻结读路径 `stat_repository._SQL_SELECT_COUNTERS` **逐字一致**；
  - 非空（显式 pet 连接）⇒ `_SQL_FIND_COUNTER`（`pet_id = ?`）。
- FIND 与 INSERT 的 pet 绑定**同源**（皆 `self._pet_id`），严格 `(stat_type, stat_key, pet_id)`；
  ⛔ **禁** `(stat_type, stat_key, stat_key)`。
- 组合根**刻意不传派生值**给 `DataManager`，以保证默认 / HTTP / 旧 WS 路径写 `NULL`。

### MP-4 —— Known Asymmetry（登记不解决）

- **现象**：`events.pet_id` 与 `interactions.pet_id` **不同源** ——
  `pipeline._record` 以 `pet_id=self._runtime.pet_id` 调 `write_event`（默认路径 = 派生值 `AssetManager.pet_ids()[0]`，**非 NULL**），
  而 `aggregate_counter` 用 `DataManager._pet_id`（默认路径 = **NULL**）。
- **行为后果**：默认连接的 `events` 行与显式 `?pet_id=<同一派生键>` 连接的 `events` 行
  在 `events` 表内**不可区分**；仅 `interactions` 能区分（`NULL` vs 该键）。
- **本条款只登记、不解决**：本差异**不视为缺陷**，Phase 3.2-A **未授权**任何修复。

> **登记 ≠ 解除实现约束**：上述登记**不等于**授权改写 `events` / `interactions` 的写入口径、
> **不解除** MP-3 的作用域约束，**不构成**对既有实现的变更许可。
> 若要消除该不对称，须**另行显式授权**并单独裁决。

### MP-5 —— Scope Freeze（未实现、未授权）—— **CR-1 修订：读侧部分解除**

Phase 3.2-A **未实现**且**未授权**以下各项（**除 CR-1 明确解除者外**）：

- pet registry（宠物注册表）· 全局 current_pet · 共享 active runtime；
- **pet-scoped HTTP API**（`/api/stats` / `/events/recent` / `/state` 的 pet 过滤或作用域参数）
  —— ⬅ **【CR-1 修订】**：**pet-scoped HTTP 读侧 API 已授权**（限 `GET /api/stats` +
  `GET /api/events/recent` 的 `?pet_id=` 读参数，**仅读侧**）；**写侧与 registry 仍禁** =
  `POST /api/events/simulate` 的 pet 作用域 · `GET /api/playback/state`（**B-live**）· pet registry ·
  全局 current_pet · 共享 active runtime **一律仍属未授权**。
  依据 = `docs/development/phase3_pet_scoped_http_api_decision.md`（v1.0 FROZEN，**MB-1 ~ MB-7**）；
- `reconnect` · `heartbeat` · `retry` · 消息重放 · 多连接并存；
- `WM-1` / envelope / **Event schema** / **数据库 schema** 的任何变更；
- **pipeline 构造清理**（把 `pet_id` 提升为 `SimulationPipeline` 的显式构造参数，
  以移除 `build_pipeline_for_pet` 的 `SimulationPipeline.__new__` 手工绑定）。

> **登记 ≠ 解除实现约束**：本条款的登记**不代表**解除上述任何禁令，也**不代表**授权实现。
> 以上各项**均需另行显式授权**；其中「pipeline 构造清理」与「pet-scoped HTTP API」已分别登记为
> 后续候选路线（Route A / Route B），**必须经新的显式授权**方可进入执行。
>
> **⬅ CR-1（2026-09-23）**：Route B 的**读侧**已取得该显式授权（`MB-1`）；**写侧（B-live）仍未授权**，
> 其前置条件记录于 `phase3_pet_scoped_http_api_decision.md` **MB-7**。本段其余文字**继续有效**。

## 落地证据（追溯冻结的事实基础）

| 项 | 事实 |
|---|---|
| 实现提交 | `150111c` `feat: add websocket pet context routing`（4 文件，+432 / −15） |
| 验证提交 | `3baa069` `test: add multi-pet end-to-end validation coverage`（1 文件，+578，19 用例） |
| 实现落点 | `backend/app/api/ws.py` · `backend/app/services/runtime_factory.py` · `backend/app/services/data_manager.py` |
| 测试落点 | `backend/tests/platform/test_multi_pet_e2e.py`（12 函数 / 19 用例，端到端黑盒，走真实 dispatcher） |
| 回归基线 | 后端 **540 passed / 0 failed / 0 errors**（`safe_delete=False`，Post Verification 复确认） |
| 已知折衷 | `build_pipeline_for_pet` 以 `SimulationPipeline.__new__` 手工绑 `_runtime` / `_playback_clock` / `_last_event`（`pipeline.py` 当时不在授权范围）——见 MP-5 |

## 冲突检查结果

| 对照项 | 结论 |
|---|---|
| **WM-1 / WM-\*** | ✅ 无冲突：envelope 逐字段沿用，pet 上下文**不进入** envelope |
| **WS-\* / WA-\* / WG-\* / WP-\* / WC-\* / WL-\* / LI-\* / WE-\* / GR-\* / OB-\* / PH-\* / HR-\*** | ✅ 无冲突：本步**未修改**任何既有冻结条款本体 |
| **PC-\* / FS-\* / FD-\* / RF-\* / RS-\* / FCM-\*** | ✅ 无冲突：本步为后端边界；前端对应侧由 **MPF-\*** 覆盖 |
| **D1 / D2 / D4**（数据层） | ✅ 无冲突：`interactions` 仍是唯一统计载体；`stat_type` 仍限 `event` / `action` |
| **API-1 ~ API-3** | ✅ 无冲突：不新增 / 不修改任何 HTTP 端点与 DTO（pet 作用域**仅**经 WS 连接级 query） |
| **DB-3 / DB-4 / DB-6** | ✅ 无冲突：`api/**` 仍零引擎 `import`；组合根职责不变 |
| **数据库 schema** | ✅ 无变更：`UNIQUE(stat_type, stat_key, pet_id)` 为 Phase 1 冻结 DDL 既有约束，**无需迁移** |

## 设计验证清单

| 检查项 | 结果 |
|---|---|
| 编号空间 `MP-*` 全仓 0 撞车（创建前核查） | ✅ |
| `MP-*` 与 `MPF-*` 互不重叠、零子串碰撞 | ✅ |
| 本文档**不修改**任何既有冻结文档本体 | ✅ |
| 默认路径行为零变更（缺省 `pet_id` ⇒ 默认 pipeline） | ✅ |
| `WM-1` envelope / Event schema / DB schema 零变更 | ✅（MP-1 / MP-5） |
| 非法 pet 键 ⇒ 拒收连接且不装配 runtime | ✅（MP-1） |
| 无全局 current_pet / 无 pet registry | ✅（MP-2） |
| 纯追溯记载：无新增实现义务、无追溯改写历史 | ✅（D6） |

## 落地项（归后续授权步）

- `PROJECT_RULES.md` §十四 登记：`### WebSocket Pet Context Boundary`（本步已完成）。
- **pipeline 构造清理**（Route A）—— 须改 `pipeline.py`，另行授权；注意 AS-4 组合根模块 `<300 行` 守卫。
- **pet-scoped HTTP API**（Route B）—— 须改 `backend/app/api/*` 与读路径仓储，另行授权。
- **canonical pet key 规范化**（`pet_type` 别名与 `pet_id` 的命名空间统一）—— 另行授权。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-22 | 首次冻结（追溯冻结，`MP-1 ~ MP-5`）。编号空间 `MP-*`（0 撞车）；记录 Phase 3.2-A 两处 Step-0 用户裁决；`MP-4` / `MP-5` 保留「登记 ≠ 解除实现约束」声明；既有冻结文档本体零修改。 |
| CR-1 | 2026-09-23 | **MP-5 读侧部分解除**（owner 裁决 **A6**）：**pet-scoped HTTP 读侧 API 已授权**（限 `GET /api/stats` + `GET /api/events/recent` 的 `?pet_id=`，**仅读侧**）；**写侧 · `/api/playback/state`（B-live）· registry 仍禁**。授权依据 = `phase3_pet_scoped_http_api_decision.md`（v1.0 FROZEN，`MB-1 ~ MB-7`）。除本条款外，本文件其余内容**保持 v1.0 冻结**。 |
