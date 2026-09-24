# AI Cat API Boundary Stabilization v1.0

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.3-B-2
> **定位**：Step 4.3-B-1 落地后 API 边界的**四项残留**的稳定化裁决 —— 在进入 **Step 4.1-C UI Prototype** 之前把边界钉死，
> 避免这四个问题在前端阶段被重新打开（带 UI 一起返工）。**只冻结，不写代码。**
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_api_contract_decision.md`（v1.0 FROZEN）—— API-1–API-5、DA-2 / DA-4 / DA-6
> - `docs/development/step4_api_implementation_boundary.md`（v1.0 FROZEN）—— DA-1 / DA-3 / DA-5 / DA-7 / DA-8
> - `docs/development/step4_api_runtime_decision.md`（v1.0 FROZEN）—— DB-1–DB-6、DB-R1 / DB-R2
> - `docs/development/step4_data_layer_decision.md`（v1.0 FROZEN）—— D1–D4（`events` 表结构 / DataManager 边界）
> - `docs/development/step4_ui_prototype_decision.md`（v1.0 FROZEN）—— UI-1–UI-6
> - `PROJECT_RULES.md` §一.1（**禁止单文件超过 300 行**）、§十四（`### API 与跨进程边界` / `### API Implementation Boundary` / `### FastAPI Runtime Boundary`）
>
> **本步边界**：**只冻结**。不写路由、不改 `backend/**/*.py`、不改 `frontend/**`、不改 `database/schema.sql`、
> 不改任何既有冻结文档。四项裁决（及一项自发现登记）的**落地**属后续 Step —— 见 **§五 落地清单 `L-1` … `L-5`**。

---

## §一 强制前置检查（实测，全部通过）

| 项 | 期望 | 实测 |
|----|------|------|
| branch | `phase1-step1-foundation` | ✅ |
| HEAD | `27b4e0a` | ✅ `27b4e0a feat: implement backend api boundary` |
| working tree | clean | ✅ `git status --porcelain` 为空 |
| 全量回归 | 442 passed | ✅ **442 passed in 488.67s (0:08:08)**，rc=0，Python **3.11.9** |
| `step4_api_runtime_decision.md` | v1.0 FROZEN | ✅ 含 `v1.0（FROZEN）` |
| `backend/app/main.py` | 存在（4.3-B-1 落地） | ✅ 228 行 |
| `backend/app/services/pipeline.py` | 存在（4.3-B-1 落地） | ✅ **426 行** |
| `backend/app/repositories/{event,stat}_repository.py` | 存在（只读） | ✅ |
| `backend/tests/test_api_contract.py` | 存在（33 例） | ✅ |

> 回归解释器：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`（DB-1=B 冻结口径）。
> 耗时 488s 属**环境开销**（本机新建 SQLite 文件约 1.4s/次），非逻辑问题。

---

## §二 只读审计（裁决的事实基础）

### 2.1 残留①：404 / 405 错误契约（**实测探针**）

本步用 `TestClient` 对**已构造的 app** 逐项取证（临时库 + 临时素材，不触碰真实 `database/pet_live.db`）：

**（a）落 API-4 统一体 `{"code","message"}` —— 全部 400 / 全部经已注册处理器**

| 请求 | 状态 | 响应体 `code` / `message` |
|------|------|---------------------------|
| `POST /api/events/simulate`，body = `{not-json` | 400 | `INVALID_REQUEST` / `请求参数非法: 1: JSON decode error` |
| `POST /api/events/simulate`，**无 body** | 400 | `INVALID_REQUEST` / `请求参数非法: request: Field required` |
| `POST /api/events/simulate`，`{"event_type":"like","action":"happy"}` | 400 | `INVALID_REQUEST` / `请求参数非法: action: Extra inputs are not permitted` |
| `POST /api/events/simulate`，`{"event_type":"like","payload":null}` | 400 | `INVALID_REQUEST` / `payload 显式传入 null 属非法类型；无扩展字段请传 {}` |
| `POST /api/events/simulate`，`{"event_type":"follow"}` | 400 | `INVALID_REQUEST` / `event_type 不在 Phase 1 白名单: 'follow'` |
| `GET /api/stats?x=1` | 400 | `INVALID_REQUEST` / `出现未定义查询参数: ['x']；只允许 []` |
| `GET /api/events/recent?limit=abc` | 400 | `INVALID_REQUEST` / `请求参数非法: query.limit: …` |
| `GET /api/events/recent?limit=999` | 400 | `INVALID_REQUEST` / `请求参数非法: query.limit: Input should be less than or equal to 200` |

**（b）落框架默认 `{"detail": …}` —— 路由层 / 静态层，未经 API-4 处理器**

| 请求 | 状态 | 响应体 | 备注 |
|------|------|--------|------|
| `GET /api/unknown` | 404 | `{"detail":"Not Found"}` | 路由未匹配 |
| `POST /api/stats` | 405 | `{"detail":"Method Not Allowed"}` | 带 `Allow: GET` |
| `GET /assets/pets/cat/actions/nope/nope.mp4` | 404 | `{"detail":"Not Found"}` | StaticFiles 未命中 |
| `GET /assets/pets/../../database/schema.sql` | 404 | `{"detail":"Not Found"}` | ✅ 越界被拒 |
| `GET /.env` | 404 | `{"detail":"Not Found"}` | ✅ 项目根未挂载 |
| `GET /database/schema.sql` | 404 | `{"detail":"Not Found"}` | ✅ 项目根未挂载 |

**（c）安全面与 CORS（顺带复核，均符合既有冻结）**

| 项 | 实测 |
|----|------|
| CORS 预检 `Origin: http://localhost:5173` | 200，`access-control-allow-origin: http://localhost:5173`，`allow-methods: GET, POST`，**无** `allow-credentials` |
| CORS 非白名单源 `http://evil.example.com` | **不回显** `access-control-allow-origin` ✅ |

⇒ **事实结论**：现有实现已形成**两段式**错误面 ——「**已知 4 端点上的业务/校验错误**」走 API-4 统一体；
「**路由层与静态层错误**」落框架默认。**该两段式既非「全统一」也非「全不管」，需要明确定性并冻结。**

### 2.2 残留②：DataManager 事件字段

| # | 项 | 实测 |
|---|----|------|
| 1 | `DataManager.write_event` 签名 | `(self, event_type, payload, action_name=None)` —— **无** `user_id` / `user_name` / `pet_id` / `platform` 形参 |
| 2 | `DataManager` 公开 API | `aggregate_counter` / `record_action` / `write_event`（**恰好 3 个**，有守卫 `test_public_api_is_exactly_three_methods`） |
| 3 | `events` 表列（D1 冻结） | 含 `user_id` / `user_name` / `pet_id` / `platform` —— **列在，值恒 NULL** |
| 4 | 模拟 `gift` + `user_name="Tom"` + `user_id="u1"` 后 | `GET /api/events/recent` 首项：`user_id=null`、`user_name=null`、`pet_id=null`、`platform=null` |
| 5 | 上游**是否已携带**这些值 | ✅ `Event` 模型顶层字段 = `("event_type","user_id","user_name","payload")` —— `user_id` / `user_name` **已在** `Event` 上；`pet_id` 在组合根手上（`self._pet_id`） |
| 6 | API-3 契约 | `<EventItem>` **9 字段，含** `user_id` / `user_name` / `pet_id` / `platform`，示例中**有值**（`"user_name":"Tom"`, `"platform":"simulator"`） |

⇒ **事实结论**：四列恒 NULL **不是**契约设计，而是 `write_event` 形参不足导致的**数据保真缺口**；
「列在（D1）→ 契约要求下发（API-3）→ 上游已携带（Event）→ 却写不进去」三处互相矛盾。
另有既有守卫 `test_recent_events_identity_columns_are_null`（`test_api_contract.py:387`）**断言四列恒 NULL** —— 若解冻，该断言必须同步改写。

### 2.3 残留③：pipeline 对私有成员的依赖

| # | 依赖点 | 形态 | 严重度判断依据 |
|---|--------|------|----------------|
| 1 | `self._asset_manager._pet_index_map()` | **直接私有方法调用**（`pipeline.py:404`，带 `# noqa: SLF001`） | ⚠️ **高**：`AssetManager` 公开 API = `exists` / `find_asset` / `get_asset` / `list_actions` / `list_assets` / `register` —— **无任何 pet 列举方法**；`_pet_index_map()` 是纯内部实现 |
| 2 | `getattr(self._action_engine, "_state", STATE_IDLE)` | `getattr` + 默认值 | ⚪ **低**：`action_engine.py:37-38` **明文冻结**——「动作队列以内部状态 `_pending` 保存（队首即「当前/下一个」），**仅供测试与遥测只读查看**」 |
| 3 | `getattr(self._action_engine, "_pending", None)` | `getattr` + 默认值 | ⚪ **低**：同上，**冻结节已明文允许遥测只读** |

**变更代价实测**：

| 目标 | 是否破坏既有守卫 |
|------|------------------|
| 为 `AssetManager` 新增公开 `pet_ids()` | ✅ 无守卫（`tests/test_asset_manager.py` 无公开 API 断言）—— 仍需改 `asset_manager.py`（早期冻结文件） |
| 为 `ActionEngine` 新增公开 `pending_count()` | ❌ **直接破坏** `test_action_engine.py:264 test_public_api_is_execute_plus_restore_idle`（断言公开 API **恰好** `["execute","restore_idle"]`） |
| 用 `pending_count()` 替代现有 `_pending` 读取 | ❌ **不成立**：`snapshot()` 需要**队首动作名**（`_action_of(pending[0])`）与 `queue_size = len(pending)-1`，**仅长度不够**；真要公开须是 `pending_actions()` / `current_action()` 级别 |

### 2.4 残留④：`pipeline.py` 规模

| 项 | 实测 |
|----|------|
| 文件总行数 | **426** |
| 模块 docstring / imports / 常量 | L1–40 / L42–60 / L62–77 |
| `PlaybackSnapshot`（frozen dataclass，6 字段） | L80–99（20 行） |
| `SimulationPipeline` | **L102–408（307 行，17 个方法）** |
| `_default_pipeline` + `get_pipeline()` | L411–426 |
| **规则冲突** | `PROJECT_RULES.md:6` §一.1 —— 「所有代码必须按功能模块组织，**禁止单文件超过 300 行**」→ **426 > 300，字面违规** |
| 既有 AST 守卫覆盖面 | 仅 `api/**` 与 `main.py`（`test_api_contract.py:536/547/558/570`）—— **无**「pipeline 是唯一引擎 import 者」的守卫 |

---

## §三 裁决

### AS-1 404 / 405 错误契约 —— **采用 A：只管业务错误（保持现状）**

| 项 | 冻结内容 |
|----|----------|
| **统一错误体的适用范围** | 仅 **`/api/**` 四个契约端点**在**业务 / 校验路径**上产生的错误 ⇒ `{"code","message"}` |
| **框架级错误**（未知路径 404、方法不允许 405、静态资源未命中） | **沿用框架默认**（Starlette `{"detail": …}`），**不**折成 `{code,message}` |
| **API 层错误码数量** | **恰好 3 个**（`INVALID_REQUEST` / `ASSET_NOT_FOUND` / `INTERNAL_ERROR`），**不新增第 4/5 个 code** |
| **已折 400 的情形**（保持不变） | `POST /api/events/simulate` 上的一切请求体问题（缺字段 / 类型错 / **JSON 解析失败** / 未知顶层字段 / `payload:null` / 白名单外 `event_type`）与只读端点的非法 `limit` ⇒ `400 INVALID_REQUEST` |
| **UI 禁用行为** | UI **不得**解析 / 依赖 404、405 响应体形状 —— UI 只调用 4 个已知端点 |

**采用 A 的理由**

1. **不触碰已冻结的错误码全集**：`PROJECT_RULES.md` §十四「API 与跨进程边界」已冻结「API 层错误码**只允许** 3 个」。
   采用 B 必须为 404/405 新增 code（如 `NOT_FOUND` / `METHOD_NOT_ALLOWED`），等于**修订一条已冻结规则**。
2. **语义归属正确**：404/405 是 **HTTP 传输层 / 路由层**事实，不属于「事件契约 → 规则 → 动作 → 播放」业务链路；
   API-4 定义的三个码**全部**是业务语义码，本就不覆盖路由层。
3. **无实际影响面**：UI 只调用 `POST /api/events/simulate`、`GET /api/playback/state`、`GET /api/stats`、
   `GET /api/events/recent` 四个路径 —— 正常联调**不可能**触发 404/405。
4. **不变量更简单**：两段式（业务统一 / 框架默认）比全统一（需维护 5 个 code 的映射表）更少状态，
   且与「框架默认行为」零耦合 —— 未来换 Starlette 版本也不会让契约漂移。

**排除 B 的理由**：B 的收益（UI 拿到形状一致的错误体）在 Phase 1 **无消费者**；代价是修订冻结规则 + 新增两个码。
按「过度设计判据」（同「不引入 Alembic」）排除。

**风险登记**：若未来 UI 需要区分「端点不存在」与「业务拒绝」（如灰度路由 / 版本探测），须提 **Change Request** 修订本条。

---

### AS-2 事件身份字段 —— **采用 B：小范围 Change Request，扩展 `write_event`**

> **授权范围（本步授予的 CR）**：允许为 `DataManager.write_event` **增补 keyword-only 可选形参**，
> 使 `events` 的 `user_id` / `user_name` / `pet_id` / `platform` 四列**落真实值**。

**冻结的目标签名（落地属 §五 `L-2`）**

```python
def write_event(
    self,
    event_type: str,
    payload: Mapping[str, Any],
    action_name: str | None = None,
    *,
    user_id: str | None = None,
    user_name: str | None = None,
    pet_id: str | None = None,
    platform: str = "simulator",
) -> None:
```

| 项 | 冻结内容 |
|----|----------|
| **兼容性约束（硬性）** | 新形参**必须** keyword-only **且**带默认值 ⇒ 既有全部调用点（`pipeline._record`、`test_data_manager.py` 14 处）**零改动**仍通过 |
| **公开方法数不变** | 仍**恰好 3 个**方法 ⇒ 守卫 `test_public_api_is_exactly_three_methods` 不受影响 |
| **分层不变** | 仍只收**基本类型**（`str` / `Mapping`）—— DataManager 对上游模型**零依赖**（D4 不变量保持） |
| **写入出口唯一** | 仍**只有** `DataManager` 写 `events`；**禁止**仓储或 API 层旁路写入 |
| **字段语义（沿用 `step2_event_schema.md` v1.1）** | `user_id` 缺失 = `None`（**禁止补常量** `"anonymous"`）；`user_name` 缺失补 `""`、显式 `null` 保留 `None`；`payload` 保持「唯一写 `{}`、显式 `null` 拒绝」 |
| **`pet_id` 来源** | 组合根（`self._pet_id`，Phase 1 = `cat_001`）—— 由 `AssetManager` 索引派生，**不是**请求参数（API-1） |
| **`platform` 默认值** | `"simulator"`（与 API-3 示例一致）；Phase 1 无真实平台接入 |
| **字段集不变** | `events` **仍是 9 列**，**禁止**增删列；仅取值为真实值 —— D1 表结构**零改动** |
| **同步改写既有守卫** | `test_api_contract.py:387 test_recent_events_identity_columns_are_null` **必须**改写为「四列落真实值」断言（落地时一并完成） |

**采用 B 的理由**

1. **关闭一处自相矛盾**：D1 已建列、API-3 已要求下发、`Event` 已携带 → 却因形参不足恒写 NULL。缺口在**实现**，不在设计；补齐是实现「完成 D1 的既定意图」，而非改变契约。
2. **向后兼容、零破坏**：keyword-only + 默认值，**不动**任何既有调用点与守卫；方法数不变。
3. **边界不变**：仍只收基本类型、仍是唯一写入出口、仍不接收模型对象（D4 四条不变量**全部保持**）。
4. **UI 立刻受益**：`GET /api/events/recent` 不再返回恒 null 的身份列 —— 事件列表能显示「谁送了什么」，属 Phase 1 demo 的可见价值。

**排除 A（保持冻结）的理由**：A 会让 API-3 的 9 字段契约中**四列永久为死字段**，UI 拿到「结构完整但语义为空」的数据；
且该缺口会在 UI 阶段以「为什么用户名都是空的」形式重新打开 —— 与本步「在进 UI 前钉死边界」的目标直接冲突。

**变更性质声明**：本条**修改** Step 4.2-B 冻结的 `write_event` 签名 ⇒ 属 **Change Request**，由**本条授权**。
授权范围**严格限于**「增补 keyword-only 可选形参」，**不得**扩展方法数、**不得**改变既有 3 参数的行为与校验。

---

### AS-3 私有成员访问 —— **采用 B：仅补 `AssetManager.pet_ids()`**

| 项 | 冻结内容 |
|----|----------|
| **新增（授权）** | `AssetManager` **新增公开只读** `pet_ids() -> list[str]`，返回已登记 `pet_id` 的**字典序**列表；数据来源为其内部索引 |
| **`pipeline._pet_index()` 改写** | 落地时改为消费 `pet_ids()`，**移除** `# noqa: SLF001` 与对 `_pet_index_map()` 的直接调用（§五 `L-3`） |
| **`ActionEngine` 遥测读取：保持现状** | `_state` / `_pending` 的 `getattr` 只读遥测**继续保留**，理由见下；**不**为其新增公开方法 |
| **禁止（重申）** | **禁止**新增 `pending_count()`；**禁止**修改 `test_public_api_is_execute_plus_restore_idle` 守卫；**禁止**把 `_pending` 变成第二命令入口 |
| **遥测读取的护栏（硬性）** | 对 `_state` / `_pending` 的访问**必须**满足全部三条：① 只读、② 经 `getattr(..., 默认值)` 不抛异常、③ 不写入、不改动队列 —— 违反任一条即属越界 |

**采用 B（而非 A「全采纳」）的理由**

1. **两处依赖的严重度不同**：`_pet_index_map()` 是**直接私有方法调用**，且 `AssetManager` **完全没有** pet 列举出口 —— 属真缺口；
   而 `ActionEngine._pending` / `_state` 的只读遥测**已被冻结节明文允许**（`action_engine.py:37-38`），并非越界。
2. **A 会打破已冻结的守卫**：`test_public_api_is_execute_plus_restore_idle` 断言 `ActionEngine` 公开 API **恰好**为
   `["execute","restore_idle"]`（Step 4.1-A 冻结）。加 `pending_count()` 会立即让其失败 ⇒ 必须同时修改冻结测试 ⇒
   属**修订已冻结契约**，代价与收益不成比例。
3. **A 的接口设计本身不成立**：`pending_count()` **不足以**支撑 `snapshot()`（缺队首动作名）。若坚持「全采纳」，
   实际接口须是 `pending_actions()` / `current_action()` —— 等于把 `ActionEngine` 的**队列内容**变成公开契约面，
   显著扩大冻结面，与「只补一个已明文允许的只读口」相比风险高一个量级。
4. **B 用最小改动消除「直接私有调用」这一类**：文件里唯一带 `# noqa: SLF001` 的显式越界点被移除；
   剩下的两处是**契约已允许**的遥测只读，并加护栏固化。

**排除 C（全不采纳）的理由**：C 会让 `_pet_index_map()` 的私有依赖长期存在 —— 而它恰好是**唯一**的显式越界点，
且 UI/API 阶段若需要「多角色」立刻会用到这里，届时 `AssetManager` 内部实现一变，组合根即静默失效。

**风险登记**：Phase 1 单角色，`pet_ids()` 的收益在 Phase 1 不显著（只消除了一个 noqa）；价值在 Phase 2 多角色时兑现。

---

### AS-4 `pipeline.py` 拆分 —— **采用 B：拆为三个模块**

| 项 | 冻结内容 |
|----|----------|
| **目标结构** | `app/services/` 下 **3 个模块**，各 ≤ **300 行**（消除 §一.1 违规） |
| **① `services/runtime_factory.py`** | **装配**职责：`Runtime`（frozen dataclass，持有 settings / database / 4 个 service / 3 个 gateway-engine / `data_manager` / 2 个仓储 / `pet_id`）与 `build_runtime(settings=None, *, clock=None) -> Runtime`。**不**编排、**不**持播放窗口 |
| **② `services/playback_state.py`** | **播放窗口与快照值对象**：迁入 `PlaybackSnapshot`（6 字段**不变**）+ 常量 `STATE_IDLE` / `STATE_PLAYING` / `DEFAULT_DURATION_MS` / `MAX_EXPIRY_STEPS` + 新增 `PlaybackClock`（持有 `clock` 与 `playing_until`，提供 `arm(duration_s)` / `disarm()` / `is_due()` / `deadline()`）。**纯时间逻辑**，**禁止** import 任何 service |
| **③ `services/pipeline.py`** | 保留 `SimulationPipeline`（编排：`simulate` / `snapshot` / `_record` / 私有投影方法）+ `_default_pipeline` + `get_pipeline()` |
| **`PlaybackSnapshot` 必须 re-export** | `pipeline.py` **必须** `from app.services.playback_state import PlaybackSnapshot` 并保持其出现在模块命名空间 ⇒ `api/playback.py` **零改动**，AST 守卫（`api/**` 只 import 组合根）继续成立 |
| **引擎 import 归属（不变量重述）** | Web 侧引擎 import 者由「`pipeline.py` **唯一**」放宽为「**仅** `services/runtime_factory.py` 与 `services/pipeline.py`」；**`api/**` 与 `main.py` 仍零引擎 import**（守卫不放松） |
| **`restore_idle` 调用时机** | 仍**只**在 `pipeline._expire_if_due()`（编排层）—— `PlaybackClock` **不得**回调 `ActionEngine`（保持「轮询驱动到期」裁决） |
| **拆分不得改变的行为** | `PlaybackSnapshot` 6 字段 / API 响应体 / 错误码 / 路由 —— **全部零变化**；拆分是**纯结构重构** |

**采用 B（而非 A 接受 426 行）的理由**

1. **A 与已冻结的硬规则字面冲突**：`PROJECT_RULES.md:6` §一.1 明文「**禁止**单文件超过 300 行」，非「建议」。
   采用 A 就必须**修订 §一.1**（加入「组合根例外」）—— 那是**改规则**，成本高于重构本身，且开了一个会被反复援引的先例。
2. **拆分接缝天然存在**：三段职责本就是三类事实 ——「装配」「时间窗口」「编排」，且**后两段零耦合**
   （`PlaybackClock` 是纯函数式时间逻辑，不需要任何 service 引用）。
3. **零行为变化**：`PlaybackSnapshot` re-export 让 `api/**` 完全无感；守卫覆盖面（仅 `api/**` + `main.py`）不含「pipeline 唯一 import 引擎」，故放宽 import 归属**不触发**任何守卫失败。

**排除 C（原地精简到 ≤300 行）的理由**：本模块最重的资产是**契约溯源注释**（模块 docstring 40 行，逐条指向冻结文档与用户裁决）。
压缩到 ≤300 行意味着先删注释 —— 与「注释即契约溯源」的项目惯例（既有限制：模块 docstring 普遍承载裁决依据）直接冲突，
属**以破坏可追溯性换取行数合规**，代价不可接受。

---

## §四 本步**不**改变的事项（防止误读）

| 项 | 状态 |
|----|------|
| API-2 `PlaybackState` | ✅ 本步零变化（**CR-1** 起为 7 字段） |
| 3 个 API 错误码 | ✅ **零变化**（AS-1=A） |
| `events` 表结构（9 列 DDL） | ✅ **零变化**（AS-2 只改写入形参，不增删列） |
| `DataManager` 公开方法**数** | ✅ **零变化**（仍 3 个） |
| `ActionEngine` 公开 API | ✅ **零变化**（AS-3=B 明确不新增） |
| 4 条路由路径与方法 | ✅ **零变化** |
| `asset_url` 生成口径 | ✅ **零变化**（`"/" + asset_path`） |
| 静态挂载点 / CORS 白名单 | ✅ **零变化** |

---

## §五 落地清单（后续 Step 执行；本步**不**写代码）

| # | 事项 | 对应裁决 | 落地位置 / 注意 |
|---|------|----------|-----------------|
| **L-1** | 无（AS-1 = 保持现状，**无代码改动**） | AS-1 | 仅需在 `PROJECT_RULES` §十四 记录口径 |
| **L-2** | 扩展 `DataManager.write_event` 签名（keyword-only 可选形参）并让 `pipeline._record` 传 `user_id` / `user_name` / `pet_id` / `platform`；**同步改写** `test_recent_events_identity_columns_are_null` | AS-2 | 触及 2 个已冻结文件：`data_manager.py`（签名）+ `test_api_contract.py`（守卫断言）；**不得**改既有 3 参数行为 |
| **L-3** | 新增 `AssetManager.pet_ids()`；`pipeline._pet_index()` 改消费它并移除 `# noqa: SLF001` | AS-3 | 触及早期冻结文件 `asset_manager.py`；新增方法须为**只读**、返回 `list[str]` |
| **L-4** | 按 AS-4 拆为 `runtime_factory.py` + `playback_state.py` + `pipeline.py`（三文件各 ≤300 行） | AS-4 | 必须保证 `PlaybackSnapshot` **仍可从 `pipeline` 导入**（否则 `api/playback.py` 与守卫同破） |
| **L-5** | 统一只读端点的未知查询参数口径（见 §六 自发现登记） | — | 待裁决；若采纳，改 `api/playback.py` |

> **落地顺序建议**：L-2 → L-3 → L-4（L-4 最后，避免重构与新特性叠加导致 diff 不可审）。
> **每次落地必须**：全量回归（3.11.9）+ 提交前核验（`git status` / 冻结文件未动 / 行数 / 守卫）—— 沿用既有交付模板。

---

## §六 自发现登记（**不在** §二 四类之内，**未**纳入 §三 裁决）

> 本步取证时发现一处**用户指令未列出**的不一致，按「不自判」纪律**仅登记、不裁决**，供后续裁决。

**AS-D1：只读端点的未知查询参数口径不一致**

| 端点 | 未知查询参数（如 `?x=1`）实测 | 依据 |
|------|------------------------------|------|
| `GET /api/stats` | **400 `INVALID_REQUEST`**（`出现未定义查询参数: ['x']`） | `api/stats.py:134` → `_reject_unknown_query` |
| `GET /api/events/recent` | **400 `INVALID_REQUEST`** | `api/stats.py:154` → `_reject_unknown_query` |
| `GET /api/playback/state` | ⚠️ **200（静默忽略）** | `api/playback.py` **无**任何查询参数校验 |

- **事实**：同一契约维度（未知查询参数）在**两个**端点被拒绝、在**一个**端点被忽略。
- **牵连的既有冻结**：`4.3-B-0/DB-5` 曾写「与 DA-7 同理」，而 `DA-7` 的裁决是**拒绝**；`4.3-B-0` 把定稿推给 4.3-B-1，
  而 4.3-B-1 仅对 `stats.py` 落地 ⇒ 该口径**至今未被完整冻结**。
- **实际影响面**：UI 调用 `/api/playback/state` **不带**参数 ⇒ Phase 1 **无实际影响**；属**一致性**问题，非功能缺陷。
- **建议口径（**待裁决**，本步不冻结）**：统一为**拒绝**（沿用 DA-7 判据：拒绝比忽略更早暴露契约错误），落地为 `L-5`。
- **备选**：登记为「已知不一致，Phase 1 接受」，或统一为「忽略」（与 DA-7 既有判据相反，代价更高）。

---

## Forbidden

### 本 Step（4.3-B-2）不得

- ❌ 创建 / 修改任何 `backend/**/*.py`（含 `main.py` / `api/**` / `services/**` / `repositories/**`）
- ❌ 修改 `backend/tests/**`（含改写 `test_recent_events_identity_columns_are_null`）
- ❌ 修改 `frontend/**`（UI Prototype 属 Step 4.1-C，**本步不进入**）
- ❌ 修改 `database/schema.sql`
- ❌ 修改任何既有冻结文档（`step4_api_contract_decision.md` / `step4_api_implementation_boundary.md` / `step4_api_runtime_decision.md` / `step4_data_layer_decision.md` / `step4_ui_prototype_decision.md` / `step2_event_schema.md`）
- ❌ 为 404/405 新增 API 错误码（AS-1=A 明确排除）
- ❌ 新增 `ActionEngine` 公开方法（AS-3=B 明确排除）
- ❌ 进入 **Step 4.1-C UI Prototype**

### 落地时（L-2 / L-3 / L-4）不得

- ❌ 改变 `write_event` 既有 3 参数的行为与校验（只允许**增补** keyword-only 可选形参）
- ❌ 为 `DataManager` 新增方法（查询走仓储；方法数锁 3）
- ❌ 为 `events` 增删列（D1 表结构不变）
- ❌ 让 `PlaybackSnapshot` 从 `pipeline` 模块消失（须 re-export，否则 `/api/**` 守卫同破）
- ❌ 让 `PlaybackClock` 直接回调 `ActionEngine`（播放到期推进**只**归 `pipeline` 编排层）
- ❌ 拆分时改动任何对外行为（响应体 / 错误码 / 路由 / `asset_url` 口径）

---

## Deferred

| # | 事项 | 状态 / 处理 |
|---|------|-------------|
| **AS-D1** | 只读端点未知查询参数口径不一致（`/api/playback/state` 静默忽略） | **登记，待裁决**（建议统一为拒绝 → `L-5`），见 §六 |
| **AS-D2** | 404/405 若未来需 UI 区分 → 须新增 code | 与 AS-1=A 冲突，**须提 Change Request 修订本步** |
| **AS-D3** | `INTERNAL_ERROR` 在 `exceptions.py` 中不存在（边界兜底码） | 沿用 `4.3-B-0/DA-3`：**优先边界映射，不改 `exceptions.py`** —— 已由 4.3-B-1 落地 |
| **AS-D4** | `asset_url` 精确形态 | 沿用 `4.3-B-0/DA-4`：已由 4.3-B-1 落定为 `"/" + asset_path` |
| **AS-D5** | 事件细码（`EVENT_*`）是否直接作为 API `code` | 沿用 `DA-6`：保持**折叠**为 `INVALID_REQUEST`；需精确区分则提 Change Request |
| **AS-D6** | `events` 保留策略（无限增长） | 沿用 `4.3-B-0/DA-8`：Phase 1 **不实现清理**；接入真实平台（Phase 2）前必须重新裁决 |
| **AS-D7** | `pipeline.py` 无专属单测（仅由 `test_api_contract.py` 间接覆盖） | 拆分（`L-4`）时评估是否补 `tests/test_pipeline.py`；**不阻塞**本步 |
| **AS-D8** | `DataManager.write_event` 的 `platform` 取值域（`"simulator"` 之外是否允许） | Phase 1 仅模拟器，**单一取值**；接入平台时重新裁决 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。审计 Step 4.3-B-1 落地后的四项残留，裁决 **AS-1 = A**（404/405 保持框架默认，错误码仍恰好 3 个）、**AS-2 = B**（授权小范围 Change Request，`write_event` 增补 keyword-only 可选形参，四列落真实值）、**AS-3 = B**（仅新增 `AssetManager.pet_ids()`；`ActionEngine` 遥测只读保持，不新增 `pending_count()`）、**AS-4 = B**（拆为 `runtime_factory.py` + `playback_state.py` + `pipeline.py`，各 ≤300 行）。另登记自发现项 **AS-D1**（只读端点未知查询参数口径不一致）。落地清单 L-1…L-5 属后续 Step。 |
