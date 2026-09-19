# Step 4.0 Playback 与数据层前置裁决

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 4.0-A
> **定位**：Step 4.1（PlaybackManager）与 Step 4.2（DataManager）实现的唯一接口准绳。
> **上游冻结**（本步只读、不得修改）：
> - `docs/development/step3_playback_decision.md`（v1.0 FROZEN）—— P1–P6
> - `docs/development/step3_action_engine_decision.md`（v1.0 FROZEN）—— O1–O6
> - `docs/development/step3_action_command_decision.md`（v1.0 FROZEN）—— C1–C5
>
> **命名勘误**：本步指令中引用的 `step3_action_engine_consumption_boundary.md` **不存在**；
> 「consumption boundary」是**提交信息**用词（`docs: freeze action engine consumption boundary`），
> 对应文件为 `step3_action_engine_decision.md`。本文档按后者执行。
>
> **依赖链**：Step 4.0-A（本步）→ Step 4.1 PlaybackManager → Step 4.2 DataManager。
> 本步**必须先关闭 E21 / E22 / E23**，否则下游两层会各自发明一套映射与统计口径。

---

## Input

| 输入 | 来源 | 契约 |
|------|------|------|
| `PlaybackCommand{pet_id, action_type}` | ActionEngine（经播放端口） | `step3_playback_decision.md` P1；`step3_action_engine_decision.md` §六 |
| 播放完成 / 失败 / 超时信号 | 前端 `<video>` onEnded 上报 + 后端时长超时兜底 | `phase1_design.md` §4.2 |
| 素材解析请求（`pet_id` + `action_type`） | PlaybackManager → **AssetManager** | 本文档 D2 |
| 事件 + `action_name` 记录请求 | **调用方**（API 路由 / 编排层） | C5 / P5 |
| 现存数据层 | **仅 `assets` 表**（`pet_type, action, path, duration`），键为 `pet_type` | `database/schema.sql` |

---

## Output

| 输出 | 消费方 | 说明 |
|------|--------|------|
| 播放指令（素材 URL + 时长） | 前端 `<video>` | PlaybackManager 下发；素材信息向 **AssetManager** 取（D2） |
| `play(command) -> bool` | ActionEngine（调用方） | 是否成功下发播放（D1/D4） |
| 播放完成通知 | → **ActionEngine.restore_idle(pet_id)** | PlaybackManager 发起（D3） |
| `events` 明细（含 `action_name`） | DataManager → SQLite | **由调用方触发**（D5） |
| `interactions` 聚合（`stat_type`/`stat_key`/`value`） | Stats API | DataManager 维护（D6） |

---

## Boundary

```
ActionEngine ──PlaybackCommand──▶ PlaybackManager ──播放指令──▶ 前端 <video>
       ▲                                │                          │
       │ restore_idle(pet_id)           │ 取素材(pet_id, action)    │ onEnded / 失败
       └────────────────────────────────┤                          │
                                        ▼                          │
                                  AssetManager ◀───────────────────┘
                        （唯一素材解析点 + pet_id→pet_type 映射）

调用方 ──▶ DataManager（events 明细 + interactions 聚合）        （C5 / D5 / D6）
```

**唯一方向（冻结）**：

- **素材**：`PlaybackManager → AssetManager`（AssetManager 是唯一解析点，D2）
- **状态**：`PlaybackManager → ActionEngine`（通知完成，**不**自持状态，D3/D4）
- **记录**：`调用方 → DataManager`（PlaybackManager / ActionEngine 均**不**写库，C5/D5）
- **禁止**：`PlaybackManager → DataManager`（不得跨界写库）；`PlaybackManager` / `ActionEngine` 自行拼 `assets/pets/...`

---

## Decisions

### 裁决总表

| ID | 问题 | 候选 | **裁决** |
|----|------|------|----------|
| **D1** | PlaybackManager 入口 | — | **`play(command: PlaybackCommand) -> bool`**；禁止 `play(pet_id, resource)` |
| **D2** | `pet_id → pet_type` 归属（=E21） | A ActionEngine / B PlaybackManager / C PetRegistry | **C：宠物注册表，Phase 1 由 AssetManager 承担** |
| **D3** | 播放完成通知 | 引入 `PlaybackFinished` / 直接回调 | **ActionEngine.`restore_idle(pet_id)`**；不引入消息对象 |
| **D4** | 播放失败 | raise / 自行恢复 / — | **`play() → False` + 通知 `restore_idle`**；禁 raise、禁自持状态、禁写库 |
| **D5** | 记录模型 | 新增动作表 / 复用 | **复用 `events.action_name`**；不新增动作明细表、不建 `actions` 表 |
| **D6** | `interactions` 统一（=E22） | A `event_type+count` / B `stat_type+stat_key+value` | **B** |

---

### D1 —— PlaybackManager 入口：`play(command) -> bool`

**裁决：`play(command: PlaybackCommand) -> bool`。禁止 `play(pet_id, resource)`。**

- **理由**：素材**解析权属 AssetManager**（`step3_playback_decision.md` P3）。
  若入口收 `resource`（路径），则路径会在**调用方**产生 ⇒ 出现第二个解析点。
- **关闭 E23**：`system_architecture.md:327` 的 `play(pet_id, resource: dict) -> str`
  **对齐为** `play(command: PlaybackCommand) -> bool`（路径由 PlaybackManager 自取；返回语义见 D4）。
- 返回 `bool`：`True` = 播放已成功下发；`False` = 未能播放（D4）。

---

### D2 —— `pet_id → pet_type` 归属（关闭 E21）

**裁决：C —— 由「宠物注册表」承担；Phase 1 由 AssetManager 承担该角色。**

```
pet_id  ──▶  AssetManager（内部：pet_id → pet_type）  ──▶  asset path
```

| 候选 | 排除理由 |
|------|----------|
| A ActionEngine | 需读取 `config.json` / `pets` 表 ⇒ 违反「ActionEngine 无 IO」（`step3_action_engine_decision.md` §十一） |
| B PlaybackManager | 需读取配置 ⇒ 违反「PlaybackManager 不解析素材、不读配置」（P3 / 本文档 Forbidden） |
| **C 宠物注册表（= AssetManager）** | ✅ AssetManager 已是宠物/素材的**唯一权威**；`phase1_design.md` §2.7 明确其「宠物配置加载」职责 |

**关键实证（本步实测）**：

| 事实 | 位置 |
|------|------|
| 真实 `AssetManager` 接口**以 `pet_type` 为键** | `asset_manager.py:61` `get_asset(pet_type, action)`、`:113` `exists(pet_type, action)` |
| `ActionEngine` 假设的是 **`has_action(pet_id, action_type)`** | `action_engine.py`（Step 3.2-D §七） |
| 数据库**无 `pets` 表**；`assets` 表键为 `pet_type` | `database/schema.sql:16-23` |
| `AssetManager` **不读 `config.json`**（数据源是 `assets` 表） | `asset_manager.py:82` `self._repo.find(pet_type, action)` |

⇒ **两处接口在方法名与参数上都不一致**：`has_action(pet_id, ...)` vs `exists(pet_type, ...)`。
**冻结方向**：AssetManager 对外**统一以 `pet_id` 为主键**，内部完成 `pet_id → pet_type` 映射后再查资产。
（对齐项见 Deferred **E24** / **E25**。Step 4.1 落地时必须先补该映射，否则 ActionEngine 无法接真实 AssetManager。）

**映射数据源**：`config.json`（`pet_id` / `pet_type` 均已存在；`assets/pets/*/config.json`）。
`pets` 表 Phase 1 **尚未创建**（`schema.sql` 仅 `assets`），是否建表见 Deferred **E27**。

---

### D3 —— 播放完成通知：`ActionEngine.restore_idle(pet_id)`

**裁决：PlaybackManager 在完成 / 失败 / 超时后，通知 ActionEngine 执行 `restore_idle(pet_id)`。**

| 子问题 | 裁决 |
|--------|------|
| 是否引入 `PlaybackFinished` 对象 | **不引入**（Phase 1 只有 `pet_id` 一个字段；造对象＝过度设计，与 `step3_action_engine_decision.md` O1 同理） |
| 接口形态 | **`ActionEngine.restore_idle(pet_id) -> None`** |
| 是否允许命名 `on_finished(pet_id)` | **不允许** —— 项目既有 `restore_idle(pet_id)`（`system_architecture.md:305`）语义精确；`on_*` 前缀易被误读为「回调注册」 |
| 解耦方式 | PlaybackManager **不得 `import` ActionEngine**；通过**注入的回调**通信，避免 import 级循环依赖（ActionEngine 已在依赖 PlaybackManager） |

> ⚠️ **必须同步的影响（记录，Step 4.1 处理）**：ActionEngine 将出现**第二个公开入口** `restore_idle`
> —— 它是**生命周期钩子**，不是指令入口（`execute` 仍是唯一指令入口）。
> Step 3.2-D 的守卫 `test_public_api_is_only_execute`（断言 `public == ['execute']`）
> **必须在 Step 4.1 更新为允许 `execute` + `restore_idle`**。这是 O6-b 关闭的**必然结果**。

---

### D4 —— 播放失败

**裁决：`play()` 返回 `False` + 记 `error` 日志 + 通知 `restore_idle(pet_id)`。**

| 行为 | 允许 | 说明 |
|------|------|------|
| `play()` 返回 `False` | ✅ | 向调用方（ActionEngine）表明未成功下发 |
| 记 `error` 日志 | ✅ | 素材缺失 / 解码失败 / 超时 |
| 通知 `ActionEngine.restore_idle(pet_id)` | ✅ | **发起**恢复（状态落地仍是 ActionEngine 的事） |
| `raise` 异常 | ❌ | 违反红线 **C4** + `PROJECT_RULES.md` §十一 |
| **自行**把动作状态置为 `idle` | ❌ | 状态机拥有者是 ActionEngine（P6） |
| 写数据库 | ❌ | 记录由调用方发起（C5） |

> 与 P4 一致：**检测发起＝PlaybackManager，状态落地＝ActionEngine**。
> 素材缺失在 ActionEngine 阶段已被 `has_action` 预检过滤；剩余失败面（解码 / 超时）由 PlaybackManager 兜底。

---

### D5 —— 记录模型：事件与动作都在 `events`

**裁决：事件记录 = `events` 明细；动作记录 = 复用 `events.action_name`；不新增动作明细表。**

| 概念 | 落地 |
|------|------|
| 事件记录 | `events` 一行（一次事件） |
| 动作记录 | **同一行的 `action_name`**（非空 = 动作已执行） |
| 动作**定义** | **现有 `assets` 表**（`pet_type, action, path, duration`）—— 即「什么是 heart 这个动作」 |
| 计划中的 `actions` 表 | **Phase 1 不建** —— 与 `assets` 表**职责重叠**（都存 action + path） |

**理由**：C5 / P5 已冻结「调用方写**一条** `events`」，再新增动作明细表 = **第二写入点** → 违反单一写入者
（`step3_action_command_decision.md` C5）。动作计数由 `interactions` 聚合派生。
（`actions` 表重叠记入 Deferred **E26**。）

---

### D6 —— `interactions` 表统一（关闭 E22）

**裁决：B —— `interactions(stat_type, stat_key, value)`。放弃 A。**

```
interactions
├── stat_type  TEXT      -- 'event' | 'action'
├── stat_key   TEXT      -- 事件类型（gift/comment/like/system）或 动作名（heart/happy/...）
├── value      INTEGER   -- 累计次数
├── pet_id     TEXT      -- 多角色隔离（预留）
└── last_time  TIMESTAMP
UNIQUE (stat_type, stat_key, pet_id)
```

| 方案 | 问题 |
|------|------|
| A `event_type + count`（`system_architecture.md:447-455`） | 无法表达**动作计数**（动作名不是 `event_type`）；无法承载**任意** `stat_key`；扩展 `like_count`/`gift_count`/`comment_count` 需不断加固定列 |
| **B `stat_type + stat_key + value`**（`phase1_design.md:494-504`） | ✅ 通用：`(event, gift)` 与 `(action, heart)` 同表；扩展新维度**只加行不改表** |

**对齐说明**：B 即 `phase1_design.md` §4.3（Phase 1 专项）的形态，**Phase 1 专项优先于长期形态**
（同 H7 / C5 判据）；计数列由该处的 `count` 统一命名为 **`value`**（本步指令用词）。

---

## Forbidden

**PlaybackManager 不得**：

- ❌ 决定「播什么」（不读 `rules.json`、不做规则匹配）
- ❌ **自行解析素材路径 / 直接访问 `assets/`**（唯一解析点 = AssetManager，P3/D2）
- ❌ 拥有业务状态（`idle` / `playing` 状态机归 ActionEngine，D3/P6）
- ❌ 写数据库 / 做统计（属 DataManager，C5）
- ❌ `raise` 播放异常中断主流程（红线 C4，D4）
- ❌ `import` ActionEngine（用注入回调解耦，D3）

**ActionEngine 不得**：

- ❌ 读取 `config.json` / `pets` 表 做 `pet_id → pet_type` 映射（归 AssetManager，D2）
- ❌ 自行拼接素材路径（P3）

**AssetManager 之外的所有模块**：

- ❌ 出现 `assets/pets/...` 路径拼接（P3 不变量）

**DataManager 不得**：

- ❌ 被动画 / 播放流程**直接调用**（记录由调用方触发，C5）
- ❌ 承担 `pet_id → pet_type` 资源映射（D2）

**本 Step（4.0-A）不得**：

- ❌ 创建任何 Python 代码（`playback_manager.py` / `data_manager.py` / 任何 record 模型）
- ❌ 修改 `backend/**` / `tests/**` / `rules.json` / 既有冻结文档

---

## Deferred

| # | 事项 | 挂起原因 | 处理 |
|---|------|----------|------|
| **E24** | `AssetManager` 对外主键由 `pet_type` 改为 `pet_id` | 需新增映射 + 改接口（跨 `assets` 表查询路径） | **Step 4.1** |
| **E25** | 接口名不一致：`ActionEngine` 期望 `has_action(pet_id, action)`，真实为 `exists(pet_type, action)` | 同上 | **Step 4.1**（必须修复，否则接不上真实 AssetManager） |
| **E26** | `actions` 表（arch/phase1_design 计划）与现有 `assets` 表职责重叠 | 本步裁决不建 `actions` 表 | 文档对齐 |
| **E27** | `pets` 表是否存在（`pet_id`/`pet_type` 的持久化载体） | Phase 1 单宠物，config.json 足够 | **Step 4.2** 决定 |
| **E28** | `ActionEngine` 的 `restore_idle(pet_id)` 新增后，`test_public_api_is_only_execute` 守卫须同步 | 属 O6-b 关闭的必然结果 | **Step 4.1** |
| **O3-b** | `PlaybackCommand` 若确需扩展字段 | 需先证伪「AssetManager 已能提供」 | **Step 4.1** |
| **P5-C** | 「Playback 成功」级记录 | 需第二写入点，与 C5 冲突待解 | **Step 4.2+** |
| **E0** | `rule_loader.py` 376 行 / `event.py` 308 行超限 | 与播放链无关 | 独立重构 Step |
| **E10 / E14** | arch 依赖图含 `ActionEngine→DataManager`；`events.event_type` 含 `follow` | 与 C5 / A8 不一致 | 文档对齐 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 D1–D6；关闭 E21（pet_id→pet_type 归 AssetManager）/ E22（interactions 统一为 stat_type+stat_key+value）/ E23（play 入口）。 |
