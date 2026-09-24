# Step 3.3 Playback 边界裁决

> **版本**：v1.1（FROZEN）
> **v1.1 变更（CR-1，2026-09-24）**：**P1** 的 `loop` **落地** —— 由 `AssetManager` 按动作给出
> （`idle` 循环、其余单次），经 `PlaybackState.loop` 下发（API-2 第 7 字段）。见 `docs/change_request/cr-1_idle_loop.md`。
> **日期**：2026-09-19
> **产出 Step**：Step 3.3-A
> **定位**：Step 4（PlaybackManager / DataManager 实现）及其后**播放链**的唯一接口准绳。
> **上游冻结**：
> - `docs/development/step3_action_engine_decision.md`（v1.0 FROZEN）—— O1–O6，`PlaybackCommand` 最小字段
> - `docs/development/step3_action_command_decision.md`（v1.0 FROZEN）—— C1–C5，C4 播放控制归属、C5 记录归属
> - `docs/development/phase1_design.md`（§2.5/2.6/2.7）—— 播放层 / 数据层 / 素材层职责
> - `docs/architecture/system_architecture.md`（§3.5/3.6/3.7 + 依赖图）
> **来源**：`ActionEngine` 已产出 `PlaybackCommand`（Step 3.2-D），但**播放层、素材层、数据层三者的边界未冻结**。
> 若直接实现，会出现「播放、资源解析、统计」三件事混在两层 —— 即本 Step 要防止的**职责混杂**。

---

## Input

| 输入 | 来源 | 契约 |
|------|------|------|
| `PlaybackCommand{pet_id, action_type}` | ActionEngine（经播放端口下发） | 本文档 P1；`step3_action_engine_decision.md` §六 |
| 素材元数据（路径 / 时长 / 循环） | **AssetManager**（`get_action_asset` / `validate`；时长由已有 `asset_duration.py` 取自 ffprobe） | 本文档 P3 |
| 播放完成 / 失败 / 超时信号 | 前端 `<video>` onEnded 上报 + 后端时长超时兜底 | `phase1_design.md` §4.2；入口命名见 Deferred（O6-b） |
| 记录请求（事件 + action_name） | **调用方**（API 路由 / 编排层） | 本文档 P5；`step3_action_command_decision.md` C5 |

---

## Output

| 输出 | 消费方 | 说明 |
|------|--------|------|
| 播放指令（素材 URL + 动作 + 时长/循环） | 前端 Viewer（`<video>`） | 后端 `PlaybackManager` 下发；素材信息向 AssetManager 取 |
| 播放状态（`idle` / `playing`） | Action API（`/api/actions/state`） | 状态**权威**在 ActionEngine（P6） |
| 完成 / 失败上报 | → **ActionEngine**（恢复 `idle`） | `PlaybackManager` 上报，非前端直连 |
| `events` 明细行（含 `action_name`） | DataManager → SQLite | **由调用方发起**（P5），DataManager 只落库 |

---

## Boundary

播放链在 7 层架构中的位置（**冻结**）::

```
ActionEngine ──PlaybackCommand──▶ PlaybackManager ──播放指令──▶ 前端 <video>（Viewer）
                                        │                            │
                                        │ 向 AssetManager 取素材       │ onEnded / 失败
                                        ▼                            │
                                   AssetManager  ◀───────────────────┘
                                        ▲
        （唯一素材解析点）
                                        
调用方 ──▶ DataManager（events 明细；由调用方发起）        （C5 + P5）
```

| 层 | 唯一职责 | 明确不做 |
|----|----------|----------|
| **ActionEngine** | 动作域校验、状态机（`idle`/`playing`）、队列、生成 `PlaybackCommand`、**恢复 idle** | 播放、解析路径、写库 |
| **PlaybackManager** | 执行播放指令、管理播放状态、完成/异常回调、**上报**给 ActionEngine | 决定播什么、解析路径、写库 |
| **AssetManager** | **唯一素材解析点**（action → path / 存在性 / 时长 / 循环） | 播放、业务判断 |
| **DataManager** | **唯一落库点**（明细 + 聚合） | 播放、业务判断、被播放流程直接调用 |

> **红线（本 Step 的核心目的）**：`ActionEngine ↓ PlaybackCommand ↓ 播放层` 这条边界上，
> **播放、资源、统计三者各归一层**，任何一层不得越界。

---

## Decisions

### 裁决总表（P1–P6）

| ID | 问题 | 候选 | **裁决** |
|----|------|------|----------|
| **P1** | `PlaybackCommand` 字段 | 保持 2 字段 / 增 duration·loop·priority·audio | **保持 `{pet_id, action_type}`**；其余信息由 **AssetManager** 提供 |
| **P2** | 播放层结构 | A `ActionEngine→PlaybackManager` / B `ActionEngine→PlayerAdapter` | **A：`ActionEngine → PlaybackManager`** |
| **P3** | AssetManager 职责 | — | **唯一素材解析点**（action→path / 存在性 / 缺失降级 idle） |
| **P4** | 播放失败策略 | A return False / B raise / C fallback idle | **C：降级 `idle`**；检测发起＝PlaybackManager，状态落地＝ActionEngine |
| **P5** | DataManager 记录时机 | A ActionCommand 创建 / B ActionEngine 接受 / C Playback 成功 / D Playback 开始 | **B：ActionEngine 接受（`execute` 返回 `True`）**；与 O4 一致 |
| **P6** | idle 恢复责任 | ActionEngine / PlaybackManager / Player | **ActionEngine**（触发源＝PlaybackManager 回调） |

---

### P1 —— `PlaybackCommand` 保持 2 字段

**裁决：保持 `PlaybackCommand{pet_id, action_type}`，不新增字段。**

| 候选字段 | 不加的理由 |
|----------|------------|
| `duration` | 属**素材元数据**，已由 **AssetManager**（`asset_duration.py` + ffprobe）提供 ⇒ 放进指令＝**第二处时长来源**，必然漂移 |
| `loop` | 属**动作/素材属性**（`idle` 循环、其他单次），由 AssetManager 的素材描述给出，非「每次播放」的变量 —— **CR-1 已落地**：`AssetManager.is_looping(action)` 判定 + `LOOPING_ACTIONS` 策略表，经 `PlaybackState.loop` 下发 |
| `priority` | 属 ActionEngine **内部仲裁**（队列），播放层不需要；`ActionCommand` 已因同理由排除 priority（C1） |
| `audio` | Phase 1 **明确不实现音效**（`phase1_design.md` §三「音效播放 → P1，非核心验证项」） |

**理由汇总**：`PlaybackCommand` 是**指令**（要播放什么），不是**素材描述**（素材长什么样）。
把素材属性塞进指令，会制造「时长/循环有两个来源」——与 `step3_action_engine_decision.md` §六
「路径构造只在 AssetManager 一处」同类的**单一来源**原则冲突。
播放层需要时长/路径时，**向 AssetManager 索取**。

> 若 Step 4 发现确有播放层需要、且 AssetManager 无法提供的信息，再评估是否扩展
> —— 属破坏性变更（见 Deferred）。

**CR-1 落地（2026-09-24）**：`loop` 的**判定权归 `AssetManager`**（新增 `LOOPING_ACTIONS` 策略表与
`is_looping(action)`），动作**为空（待机）时回落 `IDLE_ACTION`**；值经 **`PlaybackState.loop`**
（API-2 第 7 字段）下发，前端**只消费**（FP-3 v1.2 白名单加 `loop`），**不判断动作语义**。
`PlaybackCommand` 仍保持 **2 字段** —— `loop` **不经指令传递**（本裁决不变）。

---

### P2 —— 播放层结构：`ActionEngine → PlaybackManager`

**裁决：A。冻结唯一边界 `ActionEngine → PlaybackManager`。**

```
ActionEngine ──PlaybackCommand──▶ PlaybackManager ──播放指令──▶ 前端 <video>
```

- 采用 A 的依据：7 层架构的播放层名为 **PlaybackManager**（`system_architecture.md` §3.5、
  `phase1_design.md` §2.5）；依赖图同层（`system_architecture.md:565,572`）。
- **不做 B（PlayerAdapter）**：Phase 1 的「播放器」是**前端 `<video>`**，
  后端无需再抽象一层播放器适配器；引入会增加无职责中间件（与 Step 2.0「Event Schema 不是模块」的判据同类）。
- 前端播放器**由 PlaybackManager 通过播放指令驱动**，不是 ActionEngine 的直接下游。

> 澄清（对齐历史接口）：`system_architecture.md:327` 的 `play(pet_id, resource: dict)` 中
> `resource` 暗示「路径由外部传入」，与 `phase1_design.md` §2.5「播放层**自己**向 AssetManager 请求路径」冲突。
> **以本文档 P3 为准**：PlaybackManager 收 `PlaybackCommand`，**自己**向 AssetManager 取路径。

---

### P3 —— AssetManager 职责（唯一素材权威）

**裁决：AssetManager 是全项目**唯一**素材解析点。**

| 事项 | 归属 | 说明 |
|------|------|------|
| `action → asset path` | **AssetManager** | 路径格式 `assets/pets/{pet_type}/{res_type}/{action}/{asset}` |
| 素材存在检查 | **AssetManager** | 对外 `validate(pet_type, action)` / `get_action_asset(...) -> str \| None`（`system_architecture.md:396-400`） |
| 缺失素材处理 | **AssetManager 判定 → 调用层降级 idle** | AssetManager 返回 `None`；由 ActionEngine / PlaybackManager 降级 `idle` + 记日志，**不抛异常** |
| 时长 / 循环等元数据 | **AssetManager** | 时长已由 `backend/app/services/asset_duration.py` 提供（Step 1.1） |

**不变量（冻结）**：**全项目只有一个路径解析点 = AssetManager**。
`ActionEngine`、`PlaybackManager`、`DataManager`、前端 **一律不得**自行拼接 `assets/pets/...`。

> 与已实现一致：`ActionEngine` 只调用 `asset_manager.has_action(pet_id, action_type)`
> （Step 3.2-D），从不拼路径。PlaybackManager（Step 4）须沿用同一约束。

---

### P4 —— 播放失败策略：降级 `idle`（C）

**裁决：C —— 降级 `idle`。禁止 raise，`return False` 不适用。**

| 候选 | 结论 |
|------|------|
| A `return False` | ❌ 不适用 —— `execute()` 的 `bool` 语义是「指令是否被**接受**」，与「播放是否**成功**」不同层；且失败多为**异步**（前端上报 / 超时），无法用同步返回值表达 |
| B `raise exception` | ❌ 禁止 —— 违反红线 **C4**（播放失败不得中断系统）与 `PROJECT_RULES.md` §十一 |
| **C 降级 `idle`** | ✅ **采用** |

**责任归属（冻结）**：

| 环节 | 责任方 |
|------|--------|
| **检测**播放失败 / 解码失败 / 超时 | **PlaybackManager** |
| 记录 `error` 日志 | **PlaybackManager** |
| **发起**恢复 idle（回报） | **PlaybackManager** |
| **落地**状态到 `idle` | **ActionEngine**（P6） |

对应 `phase1_design.md` §2.5 异常处理矩阵与 `system_architecture.md:334-343`：
**播放失败不能导致系统停止**。

---

### P5 —— DataManager 记录时机：ActionEngine 接受（B）

**裁决：B —— 在 **ActionEngine 接受**（`execute()` 返回 `True`）时确定 `action_name`，
由**调用方**写一条 `events` 明细。** 与 `step3_action_engine_decision.md` §七（O4）一致。

**「事件发生」与「动作成功执行」如何区分（关键）**：

| 概念 | 判据 | 是否计入动作统计 |
|------|------|------------------|
| **事件发生** | 只要事件经 Event Gateway 归一化成功 ⇒ `events` 行**始终**写 | 否 |
| **动作成功执行**（Phase 1 定义） | `action_name` **非空** = ActionEngine 接受（素材存在已过 `has_action` 预检） | 是 |

- 未命中规则（`evaluate` 返回 `None`）、动作越域、队列满被丢弃 ⇒ `action_name` 留空，**不计动作**。
- 这使 `like` 类「静默失效」（如 E16）在数据里表现为**事件计数上升、动作计数不升**，**可被数据发现**。

**为何不选 C（Playback 成功）/ D（Playback 开始）**：
选 C/D 需要**播放完成信号**驱动写入 ⇒ 会引入**第二写入点**，
违反 `step3_action_command_decision.md` C5「**调用方唯一发起、DataManager 只落库聚合**」；
且播放完成回调属 **O6-b（Step 4）**，Phase 1 尚无该信号。⇒ **C/D 推迟到 Step 4**。

> 素材相关失败（文件不存在 / 越域）在 `execute()` 阶段已被过滤（`has_action` 预检 → 返回 `False`），
> 因此 Phase 1 用 B 已能覆盖主要失败面；剩余失败面（解码 / 超时）属播放层，见 Deferred。

---

### P6 —— idle 恢复责任：ActionEngine

**裁决：属于 ActionEngine。**

- **依据**：状态机（`idle` / `playing`）的拥有者是 ActionEngine（`step3_action_command_decision.md` C3；
  `step3_action_engine_decision.md` §九）。恢复 `idle` 是**状态机转移**，只能由状态机拥有者执行。
- **触发源**：PlaybackManager 的**完成 / 失败 / 超时**回调 → 调 ActionEngine 恢复 `idle`。
- **前端 `<video>`**：只上报 `onEnded`（`phase1_design.md` §4.2 方案 A），**不管理状态**；
  超时为后端兜底（方案 B）。
- 回调**入口命名与形态**（如 `on_playback_complete(pet_id)`）属 **O6-b → Step 4**，本步只冻结**责任归属**。

> ⚠️ **当前实现缺口（已知，非缺陷）**：`ActionEngine`（Step 3.2-D）尚未实现 idle 恢复入口
> —— 因该入口随播放完成信号一起冻结（O6-b）。Phase 1 实现 PlaybackManager 时一并落地。

---

## Forbidden

**ActionEngine 不允许**：

- ❌ 自行拼接素材路径 / 直接操作播放器（只产 `PlaybackCommand`，见 `step3_action_engine_decision.md` §十一）

**PlaybackManager 不允许**：

- ❌ 决定「播什么」（不得读 `rules.json`、不得做规则匹配 / 条件判断）
- ❌ 自行拼接素材路径（**唯一解析点 = AssetManager**，P3）
- ❌ 写数据库 / 做统计（属 DataManager）
- ❌ 把播放失败**上抛**为异常中断主流程（红线 C4）

**AssetManager 之外的所有模块**：

- ❌ 出现 `assets/pets/...` 路径字面量 / 路径拼接（P3 不变量）

**DataManager 不允许**：

- ❌ 被动画 / 播放流程**直接调用**（记录由**调用方**发起，C5）
- ❌ 参与播放控制

**本 Step（3.3-A）不允许**：

- ❌ 创建 `playback_manager.py` / `player.py` / `data_manager.py`
- ❌ 修改 `backend/**` / `tests/**` / `rules.json` / `PROJECT_RULES.md`

---

## Deferred

| # | 事项 | 挂起原因 | 处理 |
|---|------|----------|------|
| **O6-b** | 播放完成 / 失败回调的**入口命名与形态**（如 `on_playback_complete`） | 随 PlaybackManager 一起冻结 | **Step 4** |
| **O3-b** | `PlaybackCommand` 若确需扩展字段（`duration`/`loop`） | 需先证伪「AssetManager 已能提供」 | **Step 4** —— **CR-1 已闭环**：`AssetManager` 已能提供 ⇒ `PlaybackCommand` **不扩展** |
| **P5-C** | 「Playback **成功**」级记录（更精确的动作计数） | 需播放完成信号 + 第二写入点，与 C5 冲突待解 | **Step 4+** |
| **E0** | `rule_loader.py`（376 行）/ `event.py`（308 行）超 300 行 | 与播放链无关 | 独立重构 Step |
| **E10** | `system_architecture.md:565-567` 依赖图含 `ActionEngine → DataManager` | 与 C5（调用方发起）不一致 | 对齐 C5 |
| **E14** | `system_architecture.md:438` `events.event_type` 含 `follow` | 应为 `gift/comment/like/system`（= A8） | 对齐 |
| **E21** | `system_architecture.md:396` AssetManager 接口用 `pet_type`，而 ActionEngine 用 `pet_id` | `pet_id → pet_type` 映射归属未定 | 对齐（建议：映射归 AssetManager） |
| **E22** | `interactions` 表两套定义：arch（`:447-455`，`event_type`+`count`）vs `phase1_design.md:494-504`（`stat_type`+`stat_key`） | 数据层未实现，两处口径不一 | Step 4 实现前裁决 |
| **E23** | `system_architecture.md:327` `play(pet_id, resource: dict)` 暗示路径外部传入 | 与 P3（播放层自取路径）冲突 | 对齐 P3 |

> **PROJECT_RULES 判断（§七，本步禁改）**：现有 §十四 已覆盖「ActionEngine 不得直接操作播放器」
> 与「记录由调用方发起」；**唯一缺口**是「**素材路径只允许 AssetManager 解析**」这条跨 Step 永久不变量。
> 建议补充，但 §三 明令禁止本步修改 ⇒ 记为 **待办**（下一 Step 或随 Step 4 一并加入）。

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 P1–P6；冻结 `ActionEngine → PlaybackManager` 唯一播放边界与 AssetManager 唯一解析不变量。 |
| v1.1 | 2026-09-24 | **CR-1**：P1 的 `loop` 落地（AssetManager 按动作判定、经 `PlaybackState.loop` 下发）；`PlaybackCommand` 仍 2 字段。P2–P6 逐字不变。 |
