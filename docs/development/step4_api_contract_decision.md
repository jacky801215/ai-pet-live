# AI Cat Backend API Contract v1.1

> **版本**：v1.1（FROZEN）
> **v1.1 变更（CR-1，2026-09-24）**：**API-2** 的 `PlaybackState` **6 → 7 字段**（+ `loop: boolean`）；
> `asset_url` 语义补「**待机（无动作）时 = 该宠物的待机素材**」。见 `docs/change_request/cr-1_idle_loop.md`。
> **日期**：2026-09-19
> **产出 Step**：Step 4.3-A
> **定位**：UI ↔ Backend 之间**唯一线上契约**（HTTP + JSON）。UI 只经本契约与后端交互，不得逾越。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_ui_prototype_decision.md`（v1.0 FROZEN）—— UI-1–UI-6，含「UI 只发原始事件、只收状态快照、只消费 asset_url」
> - `docs/development/step4_data_layer_decision.md`（v1.0 FROZEN）—— D1–D4（events / interactions 表、DataManager 边界、只读查询归 Stats API）
> - `docs/development/step4_playback_data_decision.md`（v1.0 FROZEN）—— D5（复用 `events.action_name`）/ D6（统计口径）
> - `docs/development/step3_playback_decision.md`（v1.0 FROZEN）—— P1–P6（播放边界、失败降级 C4）
> - `docs/development/step3_action_engine_decision.md`（FROZEN）—— ActionEngine 边界与 `restore_idle`
> - `docs/development/step3_action_command_decision.md`（FROZEN）—— C5（记录由调用方触发）
> - `docs/development/step2_event_schema.md`（v1.1 FROZEN）—— 统一事件四字段与 `event_type` 白名单
> - `PROJECT_RULES.md` §十四（`### 播放与素材边界` / `### UI 与后端边界` / `### 数据层与统计边界`）
>
> **本步边界**：**只冻结契约，不实现**。不写路由、不写 OpenAPI、不接 WebSocket、不改任何 `backend/**/*.py`、
> 不改 `frontend/**`、不改 `database/schema.sql`。落地属 **Step 4.3-B**。

---

## Input

### 本步前置偏差与裁决（实测）

| 项 | 指令假设 | 实测 | 裁决 |
|----|----------|------|------|
| `backend/app/api/` | 不存在 | **存在**：0 字节 `__init__.py`，commit `5e24b04`（Step 1 骨架） | 已 STOP 报告 → **用户裁决「视为无害，继续」**；本步不触碰 `backend/`，故不对齐 |
| `backend/app/routes/` | 不存在 | ❌ 不存在 ✅ | 一致 |
| `backend/app/services/api_service.py` | 不存在 | ❌ 不存在 ✅ | 一致 |
| `websocket` / `openapi.json` | 不存在 | ❌ 不存在 ✅（全仓无相关文件） | 一致 |
| `frontend/**` | （§二 需调查） | 仅 6 个 `.gitkeep`，**零代码** | 与 Step 1 骨架一致 |

### 契约输入

| 输入 | 来源 | 契约 |
|------|------|------|
| **原始事件**（raw event） | UI → `POST /api/events/simulate` | `step2_event_schema.md` v1.1 顶层字段；UI **只需发 3 项**：`event_type` / `user_name` / `payload`（`user_id` 可省） |
| **`pet_id`** | **后端补齐** | Phase 1 单角色默认：`cat_001`（来源 `assets/pets/cat/config.json`）—— **UI 不发送** |
| **`action`** | **规则输出**（InteractionEngine） | **UI 绝不发送**；这是规则层产物，不是请求参数 |
| **时间戳** | **后端补齐** | 服务器 `now` → 落 `events.created_at` —— **UI 不发送** |
| 只读查询请求 | UI → `GET /api/stats`、`GET /api/events/recent` | 本契约「Data Query API」 |
| 现有真实入口链（实测） | — | `EventGateway.normalize(raw_event)` → `InteractionEngine.evaluate(event)` → `ActionEngine.execute(command, pet_id)`；结束回调 `ActionEngine.restore_idle(pet_id)` |

### 输入边界（不变量）

1. **UI 只发原始事件，不知道阈值**（UI-4）：UI 不得判断「该触发什么动作」，也不得发送规则输出。
2. **平台字段一律留在 `payload` 内**（§十四「事件契约」）：禁止把平台字段上浮为顶层键。
3. **`user_id` 缺失不得补常量**（`step2_event_schema.md` §2.3）：后端补 `None`，禁止补 `"anonymous"`（会造成独立用户数坍缩）。

---

## Output

| 输出 | 消费方 | 说明 |
|------|--------|------|
| **PlaybackState 快照** | UI | 唯一播放态载体；`POST /api/events/simulate` 与 `GET /api/playback/state` 同构返回 |
| `GET /api/stats` 统计体 | UI | `{events:{}, actions:{}, total}`（`phase1_design.md` §4.4） |
| `GET /api/events/recent` 事件列表 | UI | 追溯 / 排障 |
| **统一错误体** | UI | `{"code","message"}` |

**输出不变量**：
- UI **只消费 `asset_url`**，**绝不自行拼接素材路径**（P3 / UI-6）。
- 播放态快照**不得**包含 `PlaybackCommand` 原文、`action_type`、`path`、`pet_type`、`AssetMetadata` 原文。
- 后端返回的一切 URL 均为**对外可解析 URL**，不含宿主机物理路径。

---

## Event API

### API-1 裁决 —— Event 输入（采用方案 A）

`POST /api/events/simulate`

**请求体（仅允许下列键）**

```json
{
  "event_type": "like",
  "user_name": "Tom",
  "payload": { "count": 1 }
}
```

| 键 | 必填 | 类型 | 说明 |
|----|------|------|------|
| `event_type` | ✅ | `str` | 白名单：`gift` / `comment` / `like` / `system`（v1.1） |
| `user_name` | ❌ | `str \| null` | 缺失补 `""`，显式 `null` 保留（§2.3） |
| `user_id` | ❌ | `str \| null` | 缺失补 `null`，**禁止**补常量 |
| `payload` | ❌ | `object` | 省略补 `{}`；显式 `null` **拒绝** |

**后端补齐（不由 UI 提供）**：`pet_id`（默认角色 `cat_001`）、`action`（InteractionEngine 规则输出）、时间戳（服务器 `now` → `events.created_at`）。

**响应** `200` → `<PlaybackState>`（与「Playback State API」**同构**）

```json
{ "pet_id": "cat_001", "state": "playing", "action": "happy",
  "asset_url": "/assets/pets/cat/actions/happy/happy.mp4",
  "queue_size": 0, "last_event": "like" }
```

> **为何响应用裸快照、不加 `accepted` 包裹**：事件被拒一律走 `4xx`（见 Error Contract），故 `200` 必然已受理；
> 而 UI **唯一**需要的返回物就是最新快照（UI-5）。Phase 1 无 push 通道，因此由事件响应顺带回传快照，
> 避免「发事件 + 再查状态」两次往返。加包裹键属过度设计（同「不引入 Alembic」的判据）。

**反例（必须拒绝）**

| 请求 | 结果 |
|------|------|
| `{"action":"happy"}` | `400 INVALID_REQUEST` —— **`action` 属规则输出**，UI 无权发送 |
| `{"event_type":"like","action_type":"happy"}` | `400 INVALID_REQUEST` |
| `{"event_type":"gift","asset_url":"/x.mp4"}` | `400 INVALID_REQUEST` —— UI 不得指定素材 |
| `{"event_type":"follow"}` | `400 INVALID_REQUEST` —— 不在 v1.1 白名单 |

---

## Playback State API

### API-2 裁决 —— PlaybackState 输出

`GET /api/playback/state` → `200 <PlaybackState>`（无事件时返回 `state="idle"` 快照）

**冻结结构（7 字段，不得增删改名）**

```json
{
  "pet_id": "cat_001",
  "state": "playing",
  "action": "happy",
  "asset_url": "/assets/pets/cat/actions/happy/happy.mp4",
  "queue_size": 0,
  "last_event": "like",
  "loop": false
}
```

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| `pet_id` | `str` | ❌ | 对外主键（与 `PetContext` / `AssetManager` 一致） |
| `state` | `str` | ❌ | **仅** `"idle"` \| `"playing"` |
| `action` | `str \| null` | ✅ | 当前动作名；`idle` 时为 `null`（**不内建动作枚举**，UI-3） |
| `asset_url` | `str \| null` | ✅ | 已解析的对外素材 URL；**待机（无动作）时 = 该宠物的待机（`idle`）素材**；素材不可解析时为 `null`（**CR-1**） |
| `queue_size` | `int` | ❌ | 待播队列长度（`>= 0`） |
| `last_event` | `str \| null` | ✅ | 最近一次被受理的 `event_type`；无则 `null` |
| `loop` | `bool` | ❌ | **CR-1**：当前媒体是否循环播放 —— 待机（`idle`）为 `true`、其余动作为 `false`（判定归 `AssetManager`，前端只消费） |

**禁止返回**（Path 解析属 AssetManager）

| 禁止键 | 原因 |
|--------|------|
| `action_type` | 内部命名，不得外泄（API-2 明示反例） |
| `path` / `asset_path` | 物理路径解析属 AssetManager，UI 不得接触（P3 / UI-6） |
| `pet_type` | 仅内部映射用；对外主键是 `pet_id` |
| `command` / `metadata` | `PlaybackCommand` / `AssetMetadata` 原文不得下发 |
| `thinking` / `mood` | 已由 UI-3 删除 |

### `asset_url` 形态（勘误登记）

指令 API-2 的示例 `/assets/cat/happy.mp4` 是**简写**。实测真实形态由
`constants.ASSET_URL_PREFIX = "/assets/pets"` 与已登记素材相对路径
`assets/pets/{pet_type}/actions/{action}/{action}.mp4` 共同决定：

```
/assets/pets/{pet_type}/actions/{action}/{action}.mp4
```

本契约冻结的是**字段语义**（「后端生成、UI 只消费」的不透明 URL 字符串）与**生成方**
（AssetManager），具体形态见 Deferred DA-4。

> **与 UI-3 的分层关系（`counts`）**：UI-3 把 `counts` 列入 **UI 内部状态**，而 UI-5 明确
> 「UI 只收 PlaybackState 快照（**含 `asset_url`**）」—— 冻结的 UI 文档本身已区分「内部状态」与「线上快照」两层。
> 因此 `counts` **不在** `PlaybackState` 中：其唯一来源是 `GET /api/stats`，由 UI 自行合并。
> 即 `UI 内部状态 = PlaybackState 快照 ∪ 统计体`。见 Deferred DA-2。

---

## Data Query API

### API-3 裁决 —— Data 查询（**只读**）

| 接口 | 响应 |
|------|------|
| `GET /api/stats` | `{"events": {"gift": 5, "comment": 3, "like": 2}, "actions": {"heart": 5, "happy": 2}, "total": 10}` |
| `GET /api/events/recent?limit=20` | `{"items": [<EventItem>...], "count": 20}` |

**`GET /api/stats`** —— 与 `phase1_design.md` §4.4 逐字一致；两个并列维度分别对应 `interactions.stat_type ∈ {event, action}`（D6）。

**`GET /api/events/recent`**
- 查询参数 `limit`：可选，默认 `20`，范围 `1..200`；越界 → `400 INVALID_REQUEST`。
- 排序：`created_at DESC, id DESC`（同秒内按 `id` 兜底）。
- `<EventItem>`：

```json
{ "id": 12, "event_type": "like", "user_id": null, "user_name": "Tom",
  "pet_id": "cat_001", "action_name": null, "platform": "simulator",
  "payload": { "count": 1 }, "created_at": "2026-09-19 10:00:00" }
```

- `payload` 在**响应中为对象**（由 API 层把库中的 JSON 字符串反序列化后返回）；库内仍是字符串（D1）。

**禁止**：
- ❌ **API 层直接写 SQL**（不得拼接 SQL、不得持有 `sqlite3` 连接、不得绕过数据层）。
- ❌ 任何写操作（本契约只定义**只读**查询；写路径是 Event API）。

> ⚠️ **落地缺口（Deferred DA-1）**：`DataManager` 当前公开 API 仅
> `write_event` / `record_action` / `aggregate_counter`（Step 4.2-B 冻结，本步**禁止扩展**），
> **无只读方法**；而 API-3 又禁止 API 层直接 SQL ⇒ 只读查询的**内部承载者**必须在 Step 4.3-B 裁决。
> D4 已允许 DataManager 提供只读查询，故该缺口不阻塞本步冻结。

---

## Error Contract

### API-4 裁决 —— 统一错误体

```json
{ "code": "INVALID_REQUEST", "message": "event_type 不在白名单: follow" }
```

**API 层错误码（仅 3 个）**

| `code` | HTTP | 触发 | 现有载体（实测） |
|--------|------|------|------------------|
| `INVALID_REQUEST` | `400` | 请求体缺字段 / 类型错 / 含禁止字段 / 参数越界 | ✅ `InvalidRequestError`（`exceptions.py:38`） |
| `ASSET_NOT_FOUND` | `404` | `pet_id` + `action` 未登记 | ✅ `AssetNotFoundError`（`exceptions.py:48`） |
| `INTERNAL_ERROR` | `500` | 未捕获异常的兜底 | ⚠️ **代码中尚无** → Deferred DA-3 |

**与现有实现的天然一致性（实测证据）**：`backend/app/core/exceptions.py` 的
`PetLiveError.to_dict()` 输出即为 `{"code": <str>, "message": <str>[, "context": {...}]}` —— 与 API-4 逐字吻合；
该类文件头部注释已写明「每个异常携带稳定的 `code`，**供 API 层与前端识别**」。

**业务细码的折叠规则**：API 契约码只有 3 个，业务层更细的码（`exceptions.py` 中已存在）
在 API 边界按下表折叠；原始细码**可**经 `context.biz_code` 透出（`to_dict()` 已支持 `context`），
但 **UI 不得依赖** `context`（属可选扩展，非契约字段）。

| 业务细码 | 折叠为 API 码 | 说明 |
|----------|---------------|------|
| `EVENT_TYPE_INVALID` / `EVENT_PAYLOAD_INVALID` / `EVENT_SCHEMA_INVALID` | `INVALID_REQUEST` (400) | 事件契约校验失败 |
| `ASSET_FILE_MISSING` | `ASSET_NOT_FOUND` (404) | 对 UI 而言与「素材不可用」同义 |
| `ASSET_METADATA_ERROR` | `INTERNAL_ERROR` (500) | 服务端元数据问题 |
| `PET_LIVE_ERROR`（基类） | `INTERNAL_ERROR` (500) | 兜底 |

**错误体禁止项**：❌ 堆栈 / `traceback` ❌ 物理路径 ❌ SQL 片段 ❌ 内部对象原文（`AssetMetadata` 等）。

> **播放期素材错误不上抛 UI**（P 系列 + 红线 C4）：播放失败一律降级 `idle` 并记日志，
> 因此 `ASSET_FILE_MISSING` / `ASSET_METADATA_ERROR` 在正常播放路径上**不会**出现在 HTTP 响应里；
> 上表映射仅作 API 边界兜底。

---

## Forbidden

### 本 Step（4.3-A）不得

- ❌ 创建 FastAPI 应用 / 路由 / DTO / 依赖注入
- ❌ 创建 OpenAPI 描述文件 / 接口 SDK
- ❌ 创建 WebSocket / SSE / 长轮询通道
- ❌ 创建前端代码（`frontend/**` 零改动）
- ❌ 修改任何 `backend/**/*.py`（含 `api/__init__.py`）
- ❌ 修改 `database/schema.sql`
- ❌ 修改任何既有冻结文档

### Step 4.3-B 落地时不得

- ❌ 接受 UI 发送 `action` / `action_type` / `path` / `asset_url` / `pet_type` / `state` / `queue_size`
- ❌ 在响应中返回 `action_type` / `path` / `asset_path` / `pet_type` / `PlaybackCommand` / `AssetMetadata` 原文
- ❌ API 层直接 SQL、持有 `sqlite3` 连接或绕过数据层
- ❌ 在 API 层承载业务规则（规则匹配属 InteractionEngine、动作执行属 ActionEngine、播放属 PlaybackManager）
- ❌ 把 `pet_id → pet_type` 映射搬进 API 层（归 AssetManager）
- ❌ 扩展 `DataManager` 为业务决策者（D4）
- ❌ 为平台字段在 `events` 表加列（D1）
- ❌ 通过「路径拼接」兜底未登记素材（Step 1 验收 A2）
- ❌ 引入 push 通道（WebSocket / SSE / 长轮询）——Phase 1 契约不含 push；如需须经 Change Request 修订本契约

---

## Deferred

| # | 事项 | 挂起原因 | 处理 |
|---|------|----------|------|
| **DA-1** | `interactions` / `events` 只读查询的内部承载者 | `DataManager` 只有 3 个写入 API（4.2-B 冻结、本步禁止扩展），API-3 又禁止 API 层直接 SQL | Step 4.3-B 裁决（D4 已允许 DataManager 提供只读查询） |
| **DA-2** | `counts` 不在线上快照中；UI-3 与 API-2 的字段差集 | UI-3 描述「内部状态」、UI-5 描述「线上快照」，两层 | 待 UI 文档侧对齐；UI 用 `GET /api/stats` 合并 |
| **DA-3** | `INTERNAL_ERROR` 码在 `exceptions.py` 中不存在 | 需在 API 边界兜底映射（新增异常类须独立授权） | Step 4.3-B（优先在边界映射，不改 `exceptions.py`） |
| **DA-4** | `asset_url` 真实形态（是否含 `/actions/{action}/`） | 指令示例为简写（`/assets/cat/happy.mp4`） | Step 4.3-B 定稿；`ASSET_URL_PREFIX` 已存在 |
| **DA-5** | `/assets/...` 静态素材由谁托管（FastAPI StaticFiles / 前端 dev proxy） | 属部署形态，非契约 | Step 4.3-B |
| **DA-6** | 事件细码（`EVENT_*`）是否允许直接作为 API `code` 透出 | 当前折叠为 `INVALID_REQUEST` | 若 UI 需精确区分则提 Change Request |
| **DA-7** | 请求体出现未知键时的口径（忽略 vs 拒绝） | 与「顶层 4 字段之外的字段必须拦截」的事件契约需对齐 | Step 4.3-B 定稿 |
| **DA-8** | `events` 保留策略 / 清理（无限增长） | 同 D2-6 | 未定 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 API-1（Event 只发原始事件，后端补 `pet_id`/`action`/时间戳）、API-2（`PlaybackState` 六字段，禁 `action_type`/`path`）、API-3（只读 `GET /api/stats`、`GET /api/events/recent`，禁 API 层 SQL）、API-4（`{code,message}`，3 码 `INVALID_REQUEST`/`ASSET_NOT_FOUND`/`INTERNAL_ERROR`）、API-5（本步仅 docs + `PROJECT_RULES.md`）。 |
| v1.1 | 2026-09-24 | **CR-1**：API-2 `PlaybackState` **6 → 7 字段**（+ `loop: boolean`）；`asset_url` 补「待机时 = 待机素材」。其余 API-1/3/4/5 逐字不变。 |
