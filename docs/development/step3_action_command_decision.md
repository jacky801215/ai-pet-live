# Step 3.2 ActionCommand 消费链裁决

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 3.2-A
> **定位**：Step 3.2-B（ActionEngine 实现）及其后**消费链实现**的唯一接口准绳。
> **上游冻结**：
> - `docs/development/step3_interaction_engine.md`（v1.0 FROZEN）—— 生产方契约
> - `docs/development/step3_interaction_engine_decision.md`（v1.0 FROZEN）—— 规则层裁决
> **来源**：Step 3.1 已产出 `ActionCommand`，但「谁消费它、怎么消费、边界在哪」未冻结；
> 既有文档（`phase1_design.md` 与 `system_architecture.md`）给出**不同答案**，需裁决后实现。

---

## 一、本文档存在的理由

Step 3.1 让 `ActionCommand` 可被生产（`InteractionEngine.evaluate()` 已可产出），
但**消费侧完全未定义**。若直接实现，会立刻遇到四个必须回答的问题：

1. `ActionCommand` 字段是否要扩展（带上身份 / 优先级）？
2. ActionEngine 的入口叫什么？（避免与 `normalize` / `evaluate` / `load` 撞名）
3. ActionEngine 到底做到哪一步为止？（它自己播，还是生成播放请求？）
4. 动作日志由谁发起记录？

而既有文档对 3、4 两问**结论相反**：

| 问题 | `phase1_design.md`（Phase 1 专项） | `system_architecture.md`（长期形态） |
|------|-----------------------------------|--------------------------------------|
| ActionEngine 是否碰播放 | 「**不直接操作视频**」，输出「状态变更 + **播放请求**」(§2.4) | 职责仅「动作注册 / 状态 / 队列 / idle 恢复」(§3.4) |
| 谁记录动作 | 未指明（§2.6 只写「**动作成功触发后**」记动作计数） | 附录依赖图：**ActionEngine ──→ DataManager（记录）** |

不作裁决直接实现，就会出现「文档说 A、代码做 B」——与 `step2_event_schema.md` §6.1
所描述的**静默失效**同一类问题：不报错，但边界与文档长期背离。

**因此本文档是冻结动作的必要组成部分。**

---

## 二、既有定义定位（§二 只读检索结论）

### 2.1 ActionCommand 是否已有「动作类型」定义？—— **没有全局枚举**

- 动作名取值域来自**每个宠物自己的** `config.json`（`system_architecture.md:387`）：
  `"actions": ["idle", "heart", "dance", "angry", "special"]`。
- 即动作字典是**per-pet 配置**，不是代码常量 —— 符合 `PROJECT_RULES.md` **C3「禁止硬编码角色名」**。
- `step2_event_schema.md` **C9**（`heart` vs `heart_animation`）**仍挂起**，属 Step 4。
- 素材路径规范：`assets/pets/{pet_type}/{resource_type}/{action}/{asset}`
  ⇒ **动作名离开 pet 上下文无法解析素材**，这一点决定了 C2/C4 的接口形态。

### 2.2 ActionEngine 是否已有历史接口？—— **有，且已漂移**

`system_architecture.md:298-306`（路径 `backend/app/engine/action_engine.py`）：

| 历史方法 | 说明 |
|----------|------|
| `register_action(pet_type, action, meta)` | 动作注册 |
| `trigger(pet_id, action, priority)` | 触发动作，返回 bool |
| `get_state(pet_id)` | `idle` / `playing` |
| `enqueue(pet_id, action)` | 入队 |
| `restore_idle(pet_id)` | 恢复待机 |

`phase1_design.md §2.4`：职责＝动作状态管理（`idle` / `playing` / `return_idle`）；
**边界＝管理状态与队列，不直接操作视频**；输入＝动作指令；输出＝状态变更 + 播放请求；
**依赖＝Asset Manager（校验动作存在性）**；路径＝`services/action_engine.py`（§2.4 上方模块表 `:405`）。

### 2.3 播放控制职责在哪？—— **PlaybackManager**

`system_architecture.md §3.5` / `phase1_design.md §2.5`：
职责＝播放 MP4、管理播放状态、完成回调、异常恢复；
**边界＝只负责播放与回调，不决定播什么**；输入＝**素材路径 + 播放指令**；依赖＝Asset Manager。
关键流程：收到播放指令 → **向 Asset Manager 请求素材路径** → 下发播放命令（前端执行）
→ 等待完成（前端上报 或 时长超时）→ 完成回调 → Action Engine 回 idle。

### 2.4 数据记录职责在哪？—— **DataManager**

`system_architecture.md §3.7` / `phase1_design.md §2.6`：
职责＝互动记录、统计数据；**边界＝只写不管播放，异步非阻塞**；依赖＝SQLite。
记录项：事件记录（网关接收事件后）/ 事件计数 / **动作计数（动作成功触发后，按 `action_name`）**。
相关表：`events`（含 `action_name` 列）/ `interactions`。
设计要点：写库失败**不影响播放主流程**（try/except + error 日志）。

---

## 三、裁决总表（C1–C5）

| ID | 问题 | 候选 | **裁决** |
|----|------|------|----------|
| **C1** | `ActionCommand` 是否保持 `{action_type, payload}` | 保持 / 扩展 | **保持冻结不变**；`event_id` / `user_id` / `priority` **继续禁止** |
| **C2** | ActionEngine 唯一入口名 | `execute` / `run` / `handle` | **`execute`** |
| **C3** | ActionEngine 职责边界 | — | **只做「ActionCommand → 动作执行」**（状态机 / 队列 / 抢占 / 素材存在性校验） |
| **C4** | ActionEngine 是否直接控制播放器 | A 直接控制 / B 生成播放请求 | **B**：ActionEngine 产出 `PlaybackCommand` 交给播放层 |
| **C5** | 动作执行日志谁负责 | A ActionEngine / B DataManager 自主 / C 调用方 | **C：调用方发起**；DataManager 只负责落库与聚合 |

---

## 四、C1 — ActionCommand 冻结确认

**裁决：保持 `{"action_type": "heart", "payload": {}}` 不变。**

- 字段集固定为 **2 个**，**禁止**新增 `event_id` / `user_id` / `priority`（理由见
  `step3_interaction_engine_decision.md` §8.2）。
- `payload` 为动作参数桶，Phase 1 允许为空；**禁止**把 `Event.payload` 原样灌入
  （否则 `ActionCommand` 退化为 `Event` 的副本）。

**补充：动作类型的来源（本次定位结论）**

| 项 | 结论 |
|----|------|
| 动作字典在哪 | 每个宠物的 **`config.json` 的 `actions` 数组** |
| 是否全局枚举 | **否** —— 必须是 per-pet 配置（`PROJECT_RULES.md` C3） |
| 动作名最终取值 | **未冻结**（`heart` vs `heart_animation`，C9）→ **Step 4** |
| 为何需要 pet 上下文 | 素材路径为 `assets/pets/{pet_type}/.../{action}/` ⇒ 动作名单独存在时**无法解析素材** |

> 这直接决定了 C2 与 C4 的接口形态：**指令必须带着「给哪只宠物执行」的上下文**。

---

## 五、C2 — ActionEngine 入口

**裁决：`execute`**

```
execute(command: ActionCommand) -> bool
```

### 5.1 命名理由（按 §三 判断标准：与既有名不冲突）

| 现有入口 | 所属 |
|----------|------|
| `normalize(raw_event) -> Event` | EventGateway |
| `evaluate(event) -> ActionCommand \| None` | InteractionEngine |
| `load(path) -> RuleSet` | RuleLoader |

`execute` 与三者**互不同名**，且形成一条语义清晰的动词链：
**normalize（归一）→ evaluate（求值）→ execute（执行）**。

`run` 过于笼统（零信息量）；`handle` 暗示「回调 / 事件处理」，与本层「同步执行一条具体指令」
的语义不符（该结论与 `step3_interaction_engine_decision.md` §11.1 O3 的取舍一致）。

### 5.2 为什么不沿用历史的 `trigger(pet_id, action, priority)`

`system_architecture.md:302` 把上下文拆成三个裸参数。若沿用：

1. 与 `ActionCommand` 的封装**重复**（`action` 已含在指令里）；
2. `pet_id` 与 `action` 分离后，调用方可以拼出「宠物 A 的动作 + 宠物 B 的上下文」这类非法组合；
3. 与 `InteractionEngine.evaluate(event) -> ActionCommand` 的既有形态**不一致**（一个吃对象、一个吃散参数）。

⇒ 冻结为 **`execute(command: ActionCommand) -> bool`**。
`pet_id` 的传递方式见 §5.3。

### 5.3 关于 `pet_id`（**显式挂起，不在本步冻结**）

`ActionCommand` 不含 `pet_id`（它属于「执行上下文」，不属于「指令内容」）。
`pet_id` 有两条可能路径：① `execute(command, pet_id=...)`；② 引擎实例绑定单宠物。
Phase 1 只需单宠物（cat），**两种都可行**，故**不在此处单方面扩 `ActionCommand` 字段**。
⇒ 记为 **O1**，由 Step 3.2-B 决定。

### 5.4 返回值

Phase 1 冻结为 **`bool`**：`True` = 指令已被接受（已播放或已入队）；
`False` = 未被接受（素材不存在而降级 idle / 队列满被丢弃）。

- 依据：`system_architecture.md:302` 的 `trigger(...) -> bool` 已是该语义。
- 返回 `bool` 也是 **C5（调用方记录）** 的判定依据 —— 没有它，调用方无法区分
  「动作真的触发了」与「指令被降级丢弃」。
- 是否需要更细的结果（区分「降级原因」）⇒ 记为 **O2**，由 Step 3.2-B 决定。

---

## 六、C3 — ActionEngine 职责边界

| | 内容 |
|---|---|
| ✅ **负责** | **`ActionCommand` → 动作执行**：动作状态机（`idle` / `playing` / `return_idle`）、动作队列、优先级抢占、idle 恢复、**素材存在性校验** |
| ❌ **不负责** | **`Event`**（不得接收 / 不得依赖）<br>**规则匹配**（不得读规则、不得做条件判断）<br>**用户统计**（不落库、不聚合）<br>**平台接入**（不得感知平台）<br>**播放实现**（不持有播放器，见 C4） |

**素材存在性校验的归属**：ActionEngine 触发前向 **Asset Manager** 校验（`phase1_design.md:238-240`）；
不存在 → **降级 idle + warn 日志，不抛异常**，并**返回 `False`**（供 C5 判定）。

> 不变量：**路径构造只在 Asset Manager 一处**。ActionEngine 只问「这个动作存在吗」，
> 播放层只问「这个动作的素材路径是什么」。两处都不自己拼路径。

---

## 七、C4 — 播放控制归属

**裁决：B —— ActionEngine 生成播放请求，不直接控制播放器。**

```
ActionEngine ──execute──▶ (状态机 / 队列 / 存在性校验)
                              │
                              └──▶ PlaybackCommand ──▶ PlaybackManager ──▶ Player
```

### 7.1 理由

1. `phase1_design.md §2.4` 边界原文：**「不直接操作视频」**，输出为**「播放请求」**。
2. `phase1_design.md §2.5` 播放层输入为**「素材路径 + 播放指令」** ⇒ 播放层是**被指令驱动**的一方。
3. `system_architecture.md §3.5` PlaybackManager 职责含「视频播放、动作切换、播放完成回调、异常恢复」——
   这些**全是播放层自己的事**，ActionEngine 无权代做。
4. 若 ActionEngine 直接持有播放器，则「播放失败降级 idle」（红线 **C4：播放失败不得中断系统**）
   的处理逻辑会**同时出现在两层**，必然漂移。

### 7.2 `PlaybackCommand`（**最小定义，字段集待 Step 4 冻结**）

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet_id` | string | 目标宠物（素材路径必须的上下文） |
| `action_type` | string | 要播放的动作名 |

**明确不包含**：`priority`（属 ActionEngine 内部仲裁，播放层不需要）、`asset_path`
（路径由播放层向 Asset Manager 解析 —— 见 §6「路径构造只在 Asset Manager 一处」）。

> ⚠️ `PlaybackCommand` 的**完整字段集**（是否含 `duration` / `loop` / `audio` 等）
> **属 Step 4（播放层契约）**，本文档只冻结「ActionEngine 不直接操作播放器」这条边界。记为 **O3**。

---

## 八、C5 — 数据记录归属

**裁决：C —— 由调用方发起记录；DataManager 只负责落库与聚合。**

```
调用方（Phase 1：API 路由 / 编排层）
   │
   ├── gateway.normalize(raw)      -> Event
   ├── engine.evaluate(event)      -> ActionCommand | None
   ├── action_engine.execute(cmd)  -> bool
   └── data_manager.record_*(...)  <- 记录在这里发起（唯一发起处）
```

### 8.1 理由

1. **`phase1_design.md §2.4` 的「依赖」列只有 `Asset Manager`** —— ActionEngine
   **不持有数据层依赖**。若由它记录，该依赖列即失真。
2. **用户统计不属 ActionEngine 职责**（C3）。
3. **统一由调用方发起** ⇒ 事件记录与动作记录**只有一处跨切面逻辑**，
   不会出现「某条路径记了、某条没记」—— 与 `PROJECT_RULES.md` §十四「事件入口边界」
   用「唯一通道」消除散落校验的论证**同构**。
4. `events` 表**已有 `action_name` 列**（`system_architecture.md:442`）⇒ 调用方在
   `evaluate()` 之后已同时持有 `Event` 与匹配到的动作，**一条事件记录即可承载动作名**；
   动作计数由聚合查询导出，无需第二处写入点。
5. 与 H7 同类判据：**Phase 1 专项设计（`phase1_design.md`）优先于长期形态（`system_architecture.md`）**。

### 8.2 明确排除 B（DataManager 自主记录）

Phase 1 的链路是**同进程同步**调用；让 DataManager 自行订阅 / 监听会引入
订阅者生命周期与线程安全议题，且**改变了模块的对外形态** ——
该取舍在 `step2_event_gateway.md` §9.2（D4）已被否定，此处保持一致。

### 8.3 DataManager 的职责（不变，重申）

- **唯一写入者**：落库 + 聚合查询。
- **只写不管播放**、**异步非阻塞**。
- **写库失败不得影响播放主流程**（try/except + error 日志）。

> 记录时机（含被丢弃的指令是否入账）⇒ 记为 **O4**，由 Step 3.2-B 随调用方一起冻结。

---

## 九、数据流与类型边界（冻结）

```
Platform Adapter
      │  raw dict
      v
Event Gateway ──normalize──▶ Event
                              │
                              v
Interaction Engine ──evaluate──▶ ActionCommand | None
                                   │
                                   v
                             ActionEngine ──execute──▶ bool
                                   │
                                   v
                              PlaybackCommand
                                   │
                                   v
                             PlaybackManager ──▶ Player      （Step 4）

调用方 ──▶ DataManager（事件记录 / 动作记录）                  （C5）
```

| 边界 | 类型 | 冻结来源 |
|------|------|----------|
| Gateway → Engine | `Event` | `step2_event_gateway.md` |
| Engine → ActionEngine | `ActionCommand` **或 `None`** | `step3_interaction_engine.md` |
| ActionEngine → 播放层 | `PlaybackCommand` | 本文档 §7.2 |
| ActionEngine → 调用方 | `bool` | 本文档 §5.4 |

`None` 与 `False` 都是**正常结果**，不是错误，**不得用异常表达**。

---

## 十、禁止项

**ActionEngine 不允许**：

- ❌ 接收 / 依赖 `Event`（它只认识 `ActionCommand`）
- ❌ 读取 `rules.json` / 解析 JSON / 读文件
- ❌ 做规则判断 / 条件求值 / 优先级仲裁（属 Interaction Engine）
- ❌ 直接操作播放器（应产出 `PlaybackCommand`）
- ❌ 写数据库 / 做聚合统计（属 DataManager）
- ❌ 平台接入 / 平台字段判断

**本 Step（3.2-A）不允许**：创建 ActionEngine / Player / Playback / DataManager，修改 `backend/`。

---

## 十一、实现约束提醒（Step 3.2-B 必读）

Step 3.2-B 将新增 `backend/app/services/action_engine.py`，实现时必须遵守：

| 约束 | 来源 | 状态 |
|------|------|------|
| **单文件 ≤ 300 行** | `PROJECT_RULES.md` §一 | ⚠️ **现存违反**：`rule_loader.py` **376 行**、`event.py` **308 行** |
| 日志走 `logging`，禁止 `print` | `phase1_design.md:421` | — |
| 单文件按功能模块组织，禁止超限 | `PROJECT_RULES.md` §一 | — |

> **⚠️ 必须处理的历史遗留**：`backend/app/services/rule_loader.py`（Step 3.1 产出，**376 行**）
> 与 `backend/app/models/event.py`（Step 2.1-B 产出，**308 行**）已超出 300 行上限。
> 此事**不在本 Step 的允许范围内**（§五 禁止修改 `backend/`），已记入第十二节 **E0**，
> 须在后续步骤专门拆分（例如把规则数据结构与 schema 常量从 `rule_loader.py` 拆出）。

---

## 十二、与既有文档的对齐清单（记录，本步不修改）

| # | 位置 | 不一致内容 | 建议处理 |
|---|------|------------|----------|
| **E0** | `backend/app/services/rule_loader.py`（376 行）<br>`backend/app/models/event.py`（308 行） | 超出 `PROJECT_RULES.md` §一「禁止单文件超过 300 行」 | 专门的重构 Step |
| **E10** | `system_architecture.md:565-567` | 附录依赖图含 `ActionEngine ──→ DataManager（记录）` | 与 **C5** 裁决不一致（Phase 1 由调用方发起）→ 对齐 |
| **E11** | `system_architecture.md:302` | `trigger(pet_id, action, priority) -> bool` | 对齐为 `execute(command: ActionCommand) -> bool` |
| **E12** | `system_architecture.md:299` | 路径 `backend/app/engine/action_engine.py` | 对齐为 `services/action_engine.py`（同 E4 / G4 类） |
| **E13** | `system_architecture.md:394` | 路径 `backend/app/assets/asset_manager.py` | 实际为 `backend/app/services/asset_manager.py` |
| **E14** | `system_architecture.md:438` | `events.event_type` 注释列 `gift/comment/like/follow` | 应为 `gift/comment/like/system`（= `step2_event_schema.md` §6.4 **A8**） |
| **E15** | `system_architecture.md:250-257` | 规则映射表含 `follow`、动作名 `*_animation` | 阶段归属标注（E3 / C9 已记录） |

> **处理原则**：与 `step2_event_schema.md` §6.4、`step2_event_gateway.md` §9.3 相同 ——
> 后续修正既有文档时**必须在提交信息中说明，不得无声改写**。

---

## 十三、未冻结事项（禁止在 Step 3.2-B 自行扩大）

| # | 项目 | 挂起原因 | 处理 |
|---|------|----------|------|
| **O1** | `pet_id` 如何传给 `execute`（参数 vs 实例绑定） | `ActionCommand` 不应承载执行上下文 | **Step 3.2-B** |
| **O2** | `execute` 返回值是否升级为结果对象（含降级原因） | Phase 1 只需 bool | **Step 3.2-B** |
| **O3** | `PlaybackCommand` 完整字段集 | 消费者属播放层 | **Step 4** |
| **O4** | 记录时机与被丢弃指令是否入账 | 与调用方一同冻结 | **Step 3.2-B** |
| **O5** | 动作名最终取值域（`heart` vs `heart_animation`） | `step2_event_schema.md` C9 | **Step 4** |
| **O6** | `ActionEngine` 队列上限 / 抢占细节 | `phase1_design.md:234` 已给 Phase 1 简化规则（上限 3），实现细节待定 | **Step 3.2-B** |

---

## 十四、变更管理

本文档冻结后：

- **`ActionEngine` 入口名（`execute`）与其「不直接操作播放器」边界**属**破坏性约束** ——
  变更会使消费链上下游同时失效。
- 任何变更必须走 `PROJECT_RULES.md` §七「需求变更管理」流程。
- 变更后本文档**版本号递增**，并在第十五节记录变更历史。
- **禁止**在实现代码中「顺手」让 ActionEngine 接收 `Event` 或直接调用播放器 ——
  那正是本文档要防止的边界腐化。

---

## 十五、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 C1–C5。 |
