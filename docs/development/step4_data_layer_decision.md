# AI Cat Data Layer Decision v1.0

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.2-A
> **定位**：Phase 1 数据层（`events` / `interactions` / `pets`）与 DataManager 边界的**唯一契约准绳**。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step4_playback_data_decision.md`（v1.0 FROZEN）—— D1–D6，含 **D5（复用 `events.action_name`）/ D6（`stat_type`+`stat_key`+`value`）**
> - `docs/development/step4_ui_prototype_decision.md`（v1.0 FROZEN）—— UI-1–UI-6，含状态快照边界
> - `docs/development/step2_event_schema.md`（v1.1 FROZEN）—— 统一事件四字段与 `event_type` 白名单
> - `docs/development/step3_playback_decision.md`（v1.0 FROZEN）—— P5（记录时机）/ P6
> - `PROJECT_RULES.md` §十四（`### 播放与素材边界` / `### UI 与后端边界`）
>
> **命名勘误**：本步指令引用的 `docs/system_architecture.md`、`docs/phase1_design.md` **不存在**；
> 实际路径为 `docs/architecture/system_architecture.md`（581 行）、`docs/development/phase1_design.md`（927 行）。
> 本文档按实际路径执行。
>
> **本步边界**：**只冻结，不实现**。不建表、不改 `schema.sql`、不写 DataManager、不写 API、不写 UI。
> 落地属 **Step 4.2-B**。

---

## Input

| 输入 | 来源 | 契约 |
|------|------|------|
| `Event`（顶层 4 字段：`event_type` / `user_id` / `user_name` / `payload`） | 调用方（Event Gateway 之后） | `step2_event_schema.md` §2.1 |
| `event_type` 白名单 `gift` / `comment` / `like` / `system` | 事件契约 | `step2_event_schema.md` §2.3 |
| `action_name`（非空 = 动作已执行） | **调用方**在 `ActionEngine.execute()` 返回 `True` 后确定 | `step3_playback_decision.md` P5；`step4_playback_data_decision.md` D5 |
| 记录请求 | **调用方**（API 路由 / 编排层） | `step3_action_command_decision.md` C5 |
| 现有 DDL | **仅 `assets` 表** | `database/schema.sql`（实测 27 行） |
| 计划中的表定义（两处） | `system_architecture.md` §3.7 / `phase1_design.md` §4.3 | 本文档 `## Database Schema` |
| `pet_id → pet_type` 映射的数据源 | **`assets/pets/{pet_type}/config.json`**（Step 4.1-A 已实测落地，AssetManager 内存索引） | `step4_playback_data_decision.md` D2 |

---

## Output

| 输出 | 消费方 | 说明 |
|------|--------|------|
| `events` 明细行（含 `action_name`） | 追溯 / 排障 / `GET /api/events/recent` | **由调用方触发**写入（D5） |
| `interactions` 聚合行 | `GET /api/stats` | DataManager 维护（D6） |
| 统计查询结果 `{events:{}, actions:{}, total}` | Stats API → UI | `phase1_design.md` §4.4 |
| 迁移脚本（建表） | `database/schema.sql` | **Step 4.2-B 落地**，本步不写 |

---

## Database Schema

### 现状（Step 4.2-A 实测）

| 对象 | 是否存在 | 证据 |
|------|----------|------|
| `assets` 表 | ✅ 存在 | `database/schema.sql:16-23`，`(pet_type, action)` 唯一 |
| `events` 表 | ❌ **不存在** | `schema.sql` 仅含 `assets`；全仓无 `CREATE TABLE events` |
| `interactions` 表 | ❌ **不存在** | 同上 |
| `pets` 表 | ❌ **不存在** | 同上（代码中 `pets` 命中全部来自素材路径 `assets/pets/...`，非表名） |
| `data_manager.py` | ❌ 不存在 | `backend/app/services/` 实测 8 个模块，无 `data_manager.py` |
| 数据层模型 | ❌ 不存在 | `backend/app/models/` 实测 5 个模块，无 `database_event.py` / `interaction_record.py` / `pet.py` |

### 本步裁决后的表清单（Phase 1）

| 表 | Phase 1 | 落地 Step |
|----|---------|-----------|
| `assets` | ✅ 已建 | Step 1 |
| **`events`** | ✅ **本步冻结，Step 4.2-B 建** | Step 4.2-B |
| **`interactions`** | ✅ **本步冻结，Step 4.2-B 建** | Step 4.2-B |
| `pets` | ❌ **不建**（E27-A） | 延后 Phase 2 |
| `actions` | ❌ **不建**（D5 / E26） | 不建（与 `assets` 职责重叠） |
| `users` | ❌ 不建 | Phase 1 无用户系统 |

> **Migration 形态**：Phase 1 使用**幂等建表脚本**（`CREATE TABLE IF NOT EXISTS`），
> 沿用 `database/schema.sql` + `Database.initialize()` 现有机制，**不引入 Alembic 等迁移框架**。
> 理由：Phase 1 单库单进程、无存量生产数据；引入迁移框架属过度设计（同 `PlaybackCommand` 不加字段的判据）。

---

## events

### D1 —— 现状确认（实测）

| 指令询问项 | 实测结果 | 说明 |
|------------|----------|------|
| 是否已有 `events` 表 | **否** | 未创建 |
| 字段列表 | **无** | 表不存在 ⇒ 无字段 |
| 是否已有 `action_name` | **否** | 未落地；计划中存在于 `events.action_name` |
| 是否已有 `timestamp` | **否** | 未落地；且两处计划的字段名为 **`created_at`** |
| 是否已有 `event_id` | **否** | 未落地；且两处计划的主键名为 **`id`** |

**命名勘误（本步冻结）**：指令用词 `timestamp` / `event_id` 与两份上游计划的 **`created_at`** / **`id`** 不一致。
本裁决**采用计划名**（`created_at` / `id`），理由：`system_architecture.md:445` 与 `phase1_design.md:490`
两处**独立一致**，且 `pets` / `actions` / `users` 计划表同样使用 `created_at` —— 采用本文档独有命名会制造第二套方言。

### 冻结字段集（9 字段）

| 字段 | 类型 | 约束 | 用途 |
|------|------|------|------|
| `id` | INTEGER | PK AUTOINCREMENT | 主键（指令所称 `event_id`） |
| `event_type` | TEXT | NOT NULL | `gift` / `comment` / `like` / `system` |
| `user_id` | TEXT | **可 NULL** | 用户标识；匿名/系统事件为 `null` |
| `user_name` | TEXT | **可 NULL** | 展示名；缺失补 `""`，显式 `null` 保留 |
| `pet_id` | TEXT | 可 NULL | 目标宠物（对外主键，与 `PetContext` 一致） |
| `action_name` | TEXT | 可 NULL | **非空 = 动作已执行**（P5 / D5） |
| `platform` | TEXT | 可 NULL | 来源平台（Phase 1 = `simulator`） |
| `payload` | TEXT | 可 NULL | 原始数据 JSON 序列化 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 发生时间（指令所称 `timestamp`） |

**索引**：`idx_events_type(event_type)`、`idx_events_time(created_at)`

### 三条冻结语义

1. **`action_name` 是唯一动作凭据**（D5）：不新增动作明细表、不建 `actions` 表。一次事件写**一行** `events`；
   未命中规则 / 动作越域 / 队列满被丢弃 ⇒ `action_name` 留空。动作计数由 `interactions` 聚合派生。
2. **`user_id` / `user_name` 的 NULL 语义不可改写**（`step2_event_schema.md` §2.3）：
   `user_id` 缺失**禁止**补常量（如 `"anonymous"`，会造成独立用户数坍缩）；`user_name` 缺失补 `""`、显式 `null` 保留。
3. **`payload` 存 JSON 串，不拆列**：平台字段一律留在 `payload` 内（`PROJECT_RULES.md` §十四「事件契约」：
   禁止把平台字段提升到顶层）。数据库同样**不得**为平台字段加列。

> **E14 记录（不修改）**：`system_architecture.md:438` 的 `events.event_type` 注释含 `follow`，
> 而事件契约白名单（v1.1）**已移除 `follow`**。本裁决以事件契约为准（`gift`/`comment`/`like`/`system`），
> 该文档注释待对齐 → 见 Deferred。

---

## interactions

### D2 —— 现状确认（实测）

**`interactions` 表不存在。** E22（两套定义并存）在文档层**仍然 pending**；
本步按 `step4_playback_data_decision.md` **D6** 关闭它，落地属 Step 4.2-B。

### 裁决 A —— `stat_type` / `stat_key` / `value`（关闭 E22）

**采用 A**（与 D6 一致）。**放弃 B（`event_type` + `count`）。**

**冻结 DDL**：

```
interactions
├── id          INTEGER PK AUTOINCREMENT
├── stat_type   TEXT      NOT NULL   -- 只允许 'event' | 'action'
├── stat_key    TEXT      NOT NULL   -- 事件类型 或 动作名
├── pet_id      TEXT      NULL       -- 多角色隔离（预留）
├── value       INTEGER   NOT NULL DEFAULT 0
├── last_time   TIMESTAMP NULL
└── UNIQUE (stat_type, stat_key, pet_id)
```

**冻结语义（关键）**：

| 维度 | `stat_type` | `stat_key` |
|------|-------------|------------|
| 事件计数 | `'event'` | `event_type`：`gift` / `comment` / `like` / `system` |
| 动作计数 | `'action'` | 动作名：`heart` / `happy` / `idle` / `sad` / `surprise`（取值域同 `config.json`） |

### 与指令示例写法的映射（必须澄清）

指令 §三 给出的示例为 `点赞：("like", "total")`、`礼物：("gift", "heart")`。
本裁决**采用 A 的列名**，但**值语义按上表冻结**，映射关系如下：

| 指令示例 | 本裁决等价写法 | 说明 |
|----------|----------------|------|
| `("like", "total")` | `("event", "like")` | 同一事实。维度由 `stat_type='event'` 承载，**不需要**第二层 `"total"` 键（省一层即省一次 JOIN 与一处口径） |
| `("gift", "heart")` | `("action", "heart")` **＋** `("event", "gift")` | 指令写法把「礼物**事件**」与「heart **动作**」压进同一行，**丢失礼物事件计数**（同一 `heart` 也可能由非礼物规则触发，反之亦然）。本裁决拆为两行，两者都可查 |

**判定依据（硬证据）**：`phase1_design.md` §4.4 的 Stats API 契约响应为

```json
{ "events": { "gift": 5, "comment": 3, "like": 2 },
  "actions": { "heart": 5, "dance": 2 },
  "total": 10 }
```

—— 响应是**两个并列维度**（`events` / `actions`），与 `stat_type ∈ {event, action}` 一一对应；
若按指令示例的 `("like","total")` 形态，`events` 与 `actions` 两个键**无法从表结构中派生**。
同时 D6 已冻结「`(event, gift)` 与 `(action, heart)` 同表」，§十四 已冻结列名形态。⇒ 三处一致，本裁决不制造新方言。

### `value` vs `count` 命名

`phase1_design.md:501` 用 `count`；D6 已裁决**统一为 `value`**（本步指令用词）。本裁决沿用 **`value`**。

### 唯一来源

`interactions` 是**全项目唯一的统计聚合载体**。**禁止**再引入固定列（`like_count` / `gift_count` / …）
或第二套统计口径 —— 扩展新维度只需**加行不改表**。

---

## pets

### D3 —— 现状确认（实测）

**`pets` 表不存在**（代码中 `pets` 的命中全部来自素材路径字面量 `assets/pets/...`，非表名）。

### 裁决 A —— Step 4.2 不创建 `pets` 表

| 候选 | 结论 |
|------|------|
| **A 不创建（延后 Phase 2）** | ✅ **采用** |
| B 现在创建 | ❌ 排除 |

**理由**：

1. **数据已存在且可用**：`assets/pets/{pet_type}/config.json` 已提供 `pet_id` / `pet_type`
   （实测 `cat_001`/`cat`、`dog_001`/`dog`、`panda_001`/`panda`）。
2. **Step 4.1-A 已实测证明**：`AssetManager` 通过该 config 建立**内存索引**即可完成
   `pet_id → pet_type` 映射，**全程不需要 `pets` 表**（D2 的落地不依赖数据库）。
3. **Phase 1 单宠物**：建表只增加一份需要与 config.json 同步的**冗余副本** —— 两个数据源必然漂移
   （config.json 改了、表没同步 ⇒ 映射结果随查询路径不同而不同）。这与「唯一来源」原则直接冲突。
4. **Phase 1 无 `room_id` / 多角色需求**：`room_id` 属直播间管理，Phase 2 起。

> **冲突记录**：`phase1_design.md:506` 写「pets 表 — **Phase 1 建表**，从 config.json 同步」，
> 与本裁决 A **不一致**。本裁决以「不建」为准（理由同上），该处待文档对齐 → 见 Deferred。

---

## DataManager Boundary

### D4 —— 边界冻结

```
调用方（API 路由 / 编排层）
        │  基本类型参数（不是 Event / ActionCommand / PlaybackCommand 对象）
        ▼
   DataManager ──▶ SQLite（events 明细 / interactions 聚合）
        ▲
        └─ 只读查询 ──▶ Stats API ──▶ UI
```

| 项 | 内容 |
|----|------|
| **允许** | `write_event(...)` —— 写一条 `events` 明细（**含可空 `action_name`**） |
| **允许** | `record_action(...)` —— 动作计数语义化封装，**等价于** `aggregate_counter('action', action_name, +1)`。「**动作只记聚合、不记明细**」，它是**唯一**与动作相关的写入动作 |
| **允许** | `aggregate_counter(stat_type, stat_key, delta)` —— 更新 `interactions` 聚合行（UPSERT `value` + `last_time`） |
| **允许** | 只读查询（供 Stats API） |
| **禁止** | `evaluate()` —— 规则匹配属 InteractionEngine |
| **禁止** | `execute()` —— 动作执行属 ActionEngine |
| **禁止** | `play()` —— 播放属 PlaybackManager |
| **禁止** | `subscribe(Event)` / 接收事件流 —— DataManager **不得**接收或订阅 `Event`、`ActionCommand`、`PlaybackCommand` 等模型对象或事件流，只收**基本类型参数** |
| **禁止** | 被播放 / 事件主流程**直接调用**（记录由调用方发起，C5） |
| **禁止** | 承担 `pet_id → pet_type` 映射（D2 归 AssetManager） |
| **禁止** | 影响主流程 —— 写库失败必须 try/except + error 日志，**不得**中断播放与事件链路（红线 C4 同理） |

**接口签名**：方法名与语义本步冻结；**具体参数列表属 Step 4.2-B**（不越界到实现）。
唯一确定的约束：参数一律为**基本类型**（`str` / `int` / `dict`），**不得**为模型对象。

**为何「收基本类型」而不是收 `Event`**：一旦 DataManager 接收 `Event`，它就必须依赖事件模型；
事件契约变更（顶层字段属破坏性变更）会立刻波及数据层，且 `DataManager` 会逐步长出「自己判断该记什么」的能力。
传基本类型使数据层**对上游模型零依赖** —— 与「AssetManager 是唯一素材解析点」同类的单向不变量。

---

## Forbidden

**本 Step（4.2-A）不得**：

- ❌ 创建 `DataManager`（`backend/app/services/data_manager.py`）
- ❌ 创建数据层模型（`database_event.py` / `interaction_record.py` / `pet.py`）
- ❌ 创建数据库表、修改 `database/schema.sql`
- ❌ 创建 API（`/api/stats` / `/api/events/recent`）
- ❌ 创建 UI、WebSocket
- ❌ 修改 `AssetManager` / `ActionEngine`
- ❌ 修改任何既有冻结文档

**Step 4.2-B 落地时不得**：

- ❌ 为动作新增明细表 / 第二写入点（D5）
- ❌ 引入固定统计列（`event_type` + `count` 形态）或第三套统计口径（D6）
- ❌ 在 `interactions` 中存非 `{'event','action'}` 的 `stat_type`
- ❌ 创建 `pets` / `actions` / `users` 表（本步裁决）
- ❌ 让 DataManager 接收模型对象或订阅事件流
- ❌ 把平台字段提升为 `events` 的独立列
- ❌ 写库失败上抛中断主流程

---

## Deferred

| # | 事项 | 挂起原因 | 处理 |
|---|------|----------|------|
| **E27** | `pets` 表是否创建 | **本步已裁决：不创建（A）** | Phase 2（多角色 / 直播间接入）时重新裁决 |
| **E22** | `interactions` 两套定义 | **本步已裁决：A（`stat_type`/`stat_key`/`value`）** | Step 4.2-B 落地；arch `:453` 形态作废 |
| **E26** | `actions` 表与 `assets` 表职责重叠 | D5 裁决不建 | 文档对齐 |
| **E14** | `system_architecture.md:438` `events.event_type` 注释含 `follow`（契约已移除） | 与 v1.1 不一致 | 文档对齐 |
| **E0** | `rule_loader.py` 377 行 / `event.py` 309 行超 300 行 | 与数据层无关 | 独立重构 Step |
| **E29** | `AssetManager` 的 `pet_type` 兼容路径 | 存量测试未迁移 `pet_id` | 独立清理 Step |
| **D2-1** | `phase1_design.md:506` 写「pets 表 Phase 1 建表」 | 与本步裁决 A 冲突 | 文档对齐 |
| **D2-2** | `phase1_design.md:501` 用 `count`，D6 统一为 `value` | 命名差异 | 文档对齐 |
| **D2-3** | `phase1_design.md:504` `UNIQUE(stat_type, stat_key)`（未含 `pet_id`），D6 为三元唯一 | 多角色预留差异 | 文档对齐 |
| **D2-4** | `Phase 1 无迁移框架` → 表结构变更只能靠 `IF NOT EXISTS` | Phase 1 无存量数据，够用 | Phase 2 评估 Alembic |
| **D2-5** | `events.payload` 的 JSON 序列化格式未冻结（`ensure_ascii` / 排序） | 需与 `POST /api/events/simulate` 的响应形态一并定 | Step 4.2-B |
| **D2-6** | 事件保留策略 / 清理（`events` 无限增长） | Phase 1 无数据量 | 未定 |
| **D2-7** | 独立访客数（`user_id` 去重）统计 | `interactions` 当前只支持计数维度 | Phase 2+ |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 `events` 字段集（9 字段，采用 `id`/`created_at` 计划名）、`interactions` = `stat_type`/`stat_key`/`value`（关闭 E22）、`pets` 不建（裁决 E27-A）、DataManager 边界（D4）。 |
