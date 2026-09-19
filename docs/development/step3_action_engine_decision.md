# Step 3.2-B ActionEngine 消费链裁决

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 3.2-B
> **定位**：Step 3.2-B 实现（`ActionEngine`）及其后**动作执行链实现**的唯一接口准绳。
> **上游冻结**：
> - `docs/development/step3_action_command_decision.md`（v1.0 FROZEN）—— C1–C5 消费链边界
> - `docs/development/step3_interaction_engine.md`（v1.0 FROZEN）—— 生产方契约
> - `docs/development/step2_event_schema.md`（v1.1 FROZEN）—— C9 动作命名（挂起）
> **来源**：Step 3.2-A 已冻结「ActionEngine 做什么、不做什么」及入口名 `execute`；
> 但 `execute` **怎么收 pet 上下文、返回什么、播放请求给谁、何时记账、动作名从哪来、队列怎么定**
> 六个问题未冻结。既有文档（`phase1_design.md` 与 `system_architecture.md`）对其中若干给出**不同答案**，需裁决后实现。

---

## 一、本文档存在的理由

Step 3.2-A 冻结了 `ActionEngine` 的**边界**（C1–C5），但边界之内仍有六个问题没有答案：

1. **O1**：`ActionCommand` 不含 `pet_id`（C1 冻结），那「给哪只宠物执行」怎么传进来？
2. **O2**：`execute` 返回 `bool` 够不够？要不要区分「为什么没执行」？
3. **O3**：`PlaybackCommand` 到底带哪些字段？谁来消费它？
4. **O4**：动作记录在哪个时点写？被丢弃的指令算不算动作？
5. **O5**：动作名（`action_type`）的**合法取值域**在哪定义？越域怎么办？
6. **O6**：队列上限、满时丢弃策略、优先级抢占的边界在哪？

其中 5、6 两问**已发现真实不一致**（不止于文档口径）：

| 问题 | 冲突方 A | 冲突方 B |
|------|----------|----------|
| **O5 动作取值域** | `rules.json`（Step 3.1 已实现）产出 `dance` | 各宠物 `config.json` 的 `actions` **不含 `dance`**；`assets/pets/cat/actions/dance/` **目录不存在** |
| **O6 满队列策略** | `phase1_design.md:234`「队列上限 3，**满则丢弃**」 | `system_architecture.md:312`「超出**丢弃最旧项**」 |

O5 的冲突**已经在代码里生效**：`like_dance` 规则一旦命中，`ActionCommand(action_type="dance")`
会被 ActionEngine 判定为「素材不存在」→ 降级 idle。即 **`like` 互动必然静默失效**，
且系统不报错 —— 正是 `step2_event_schema.md` §6.1 所描述的**静默失效**同类问题。

**因此本文档是冻结动作的必要组成部分，且其 O5 结论直接决定 Step 3.2-B 实现的生效条件。**

---

## 二、既有定义定位（§二 只读检索结论）

### 2.1 状态：`ActionEngine` 是链路中**第一个有状态模块**

| 模块 | 状态 |
|------|------|
| EventGateway | **无状态**（纯归一化） |
| InteractionEngine | **无状态**（纯求值，契约明示） |
| **ActionEngine** | **有状态**：动作状态机 + 队列 |

⇒ 设计必须明确「状态归谁持有、并发是否安全」（O6）。

### 2.2 竞态根因：`ActionCommand` 被冻结成**无 identity、无 priority**

`step3_action_command_decision.md` §四裁决 `ActionCommand = {action_type, payload}`，
**明确禁止** `event_id` / `user_id` / `priority`。后果：

- 「给哪只宠物执行」**不在**指令里 ⇒ O1 必须补上下文（**参数**或**实例绑定**）。
- 「谁优先级高」**不在**指令里 ⇒ O6 的「高优先级抢占」**失去比较依据**
  （`phase1_design.md:234` 的抢占行依赖 priority，但该值已无来源）。

> 这不是缺陷，是**有意的信息最小化**：指令只表达「做什么」，
> 「给谁做 / 何时做 / 能不能插队」属**执行上下文与执行策略**。
> O1/O6 的任务就是把这两类信息放到**正确的位置**，而不是塞回指令。

### 2.3 动作名取值域 ground truth（本步实测）

| 来源 | 动作集合 | 与磁盘是否一致 |
|------|----------|----------------|
| `assets/pets/cat/config.json` | `idle / heart / happy / sad / surprise` | ✅ 一致 |
| `assets/pets/dog/config.json` | `idle / heart / happy / sad / surprise` | ✅ 一致 |
| `assets/pets/panda/config.json` | `idle / heart / happy / sad / surprise` | ✅ 一致 |
| `assets/pets/cat/actions/`（磁盘目录） | `idle/ heart/ happy/ sad/ surprise/`（各含 `<action>.mp4`） | ✅ 一致 |
| **`backend/app/config/rules.json`（Step 3.1）** | **`heart` / `dance`** | ❌ **`dance` 越域** |

**结论**：`dance` 不属于任何宠物的动作域，也无对应素材目录。
`like_dance` 规则（`like_count >= 3 → dance`）在当前实现下**必然降级 idle**。

### 2.4 历史接口（已漂移，待对齐）

`system_architecture.md:298-306`（路径 `backend/app/engine/action_engine.py`）：

| 历史方法 | 本步处置 |
|----------|----------|
| `register_action(pet_type, action, meta)` | 动作注册 → Phase 1 **不做**（动作域来自 config，非运行时注册） |
| `trigger(pet_id, action, priority) -> bool` | → `execute(command, pet_id) -> bool`（见 O1；priority 删除见 O6） |
| `get_state(pet_id) -> str` | 保留语义（`idle` / `playing`） |
| `enqueue(pet_id, action)` | 内部实现，非公开入口 |
| `restore_idle(pet_id)` | 保留语义（idle 恢复，触发源＝播放完成回调） |

---

## 三、裁决总表（O1–O6）

| ID | 问题 | 候选 | **裁决** |
|----|------|------|----------|
| **O1** | `pet_id` 来源 | A `execute` 参数 / B 实例绑定 / C 塞 `payload` / D 新 Context 对象 | **A：`execute(command, pet_id)` 显式参数** |
| **O2** | `execute` 返回值 | A `bool` / B 结果对象（含降级原因） | **A：保持 `bool`** |
| **O3** | `PlaybackCommand` | 最小 / 完整 | **最小 `{pet_id, action_type}`**；完整字段集 → **Step 4** |
| **O4** | 记录时机 | A execute 后一次写 / B 两处写 | **A：`execute()` 返回后由调用方写**一条 `events`**；聚合派生** |
| **O5** | 动作名取值域 | A 全局枚举（代码常量） / B per-pet `config.json` | **B：per-pet `config.json` 的 `actions`**；越域 → 降级 idle |
| **O6** | 队列与抢占 | — | **FIFO + 上限 3 + 满丢最旧**；**Phase 1 不实现 priority 抢占** |

---

## 四、O1 — `pet_id` 的来源

**裁决：`execute(command: ActionCommand, pet_id: str) -> bool` —— 显式参数。**

### 4.1 为什么是参数（A），而不是实例绑定（B）

| 判据 | A（参数） | B（实例绑定） |
|------|-----------|---------------|
| 与 C3 边界一致 | ✅ `pet_id` 是**执行上下文**，不是引擎固有属性 | ⚠️ 把「一只宠物」耦进实例生命周期 |
| 多宠物扩展 | ✅ 一个引擎服务多宠物 | ❌ N 只宠物需 N 个引擎实例 |
| 与 `AssetManager` 协同 | ✅ 每次调用按 pet 解析 | ⚠️ 实例与 Asset 查询需额外对齐 |
| 调用点可读性 | ✅ 「给谁执行」在调用处可见 | ❌ 隐式状态，需回看构造 |

Phase 1 只有一只猫，A/B 都可行；**取 A 是因为它以零额外成本保留了多角色扩展性**
（`PROJECT_RULES.md` §一「模块化 / 预留扩展」、§十二「所有数据支持未来多角色」）。

### 4.2 明确排除 C（塞进 `payload`）

`ActionCommand.payload` 是**动作参数桶**（如「比心 × N」的参数），语义是「动作怎么做」。
把 `pet_id` 塞进去＝「动作对谁做」，两者是不同维度；
一旦污染，指令会逐步退化为「事件 + 上下文」的杂糅体 —— C1 冻结 `payload` 的初衷即被破坏。

### 4.3 明确排除 D（新 `ExecutionContext` 对象）

Phase 1 只有一个上下文字段，为此造对象属**过度设计**。
当上下文增至 2 个以上（如 `pet_id` + `room_id` + `platform`）时再引入，属后续 Step。

### 4.4 `pet_id` 与 `pet_type` 的分工（不变量）

- 调用方传 **`pet_id`**（如 `cat_001`）。
- **`pet_id → pet_type` 的映射属 `AssetManager`**（`phase1_design.md §2.7` 提供按 `pet_id` / `pet_type` 查询）。
- ActionEngine **不自己拼素材路径**（C3 不变量：路径构造只在 `AssetManager` 一处）。

> 是否让 `execute` 直接收 `pet_type`：**否** —— `pet_id` 是更外层、更稳定的标识；
> 需要 `pet_type` 的地方由 AssetManager 内部转换，避免上层到处传 `pet_type`。

### 4.5 与 C2 的关系（澄清，非改判）

C2 冻结的是**入口名**与**指令参数**，其 §5.3 已**显式挂起** `pet_id` 传递方式（记为 O1）。
本裁决正是关闭 O1，**不构成对 C2 的修改**。

---

## 五、O2 — `execute` 的返回值

**裁决：保持 `bool`。**

```
True  = 指令已被接受（已播放 或 已入队）
False = 未被接受（动作越域 / 素材缺失 → 降级 idle；队列满被丢弃）
```

### 5.1 理由

1. **调用方唯一用途是「判定是否记账」**（O4）：`True` 才记 `action_name`，`False` 留空。
   `bool` 已足够承载该决策。
2. **降级原因不入返回值**：把「为什么没执行」（越域 / 素材缺 / 队列满）做成枚举返回，
   会把 ActionEngine 的**内部原因分类**固化成对调用方的契约 —— 每加一种原因就是一次接口变更。
   Phase 1 原因由 **ActionEngine 记日志**（`warn` / `error`）承载即可。
3. 与 `system_architecture.md:302` 的 `trigger(...) -> bool` 语义一致。

### 5.2 未来升级路径（记录，不在本步）

若前端需要展示「为什么没反应」，则 Step 4 引入 `ExecutionResult`（含 `accepted: bool` + `reason: str`）。
**属破坏性变更**，必须走 `PROJECT_RULES.md` §七流程并递增版本。

---

## 六、O3 — `PlaybackCommand`

**裁决：沿用 C4 §7.2 的**最小字段集**，完整字段集留 Step 4。**

```
PlaybackCommand { pet_id, action_type }
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet_id` | string | 目标宠物（素材解析的上下文） |
| `action_type` | string | 要播放的动作名 |

### 6.1 明确不包含（重申 C4 §7.2）

- **`asset_path`** —— 路径由**播放层**向 AssetManager 解析（路径构造只在 AssetManager 一处）。
- **`priority`** —— 属 ActionEngine 内部仲裁，播放层不需要。

### 6.2 谁产出、谁消费（冻结）

```
ActionEngine ──execute──▶ (状态机 / 队列 / 存在性校验)
                              │
                              └──▶ PlaybackCommand ──▶ 播放端口 ──▶ PlaybackManager（Step 4）
```

- `PlaybackCommand` **由 ActionEngine 产出**，交给**播放端口**（Phase 1 由装配层注入的可调用对象，
  可为 no-op 以便单测）。
- **不返回给调用方** —— `execute` 对调用方只返回 `bool`（O2）。
- **`PlaybackCommand` 的模型文件（`models/playback_command.py`）与 `PlaybackManager` 属 Step 4**，
  本步**不创建**。

### 6.3 完整字段集挂起项

`duration` / `loop` / `audio` / `transition` 等**属 Step 4（播放层契约）**。
本文档只冻结「ActionEngine 不直接操作播放器、只产出 `{pet_id, action_type}`」。

---

## 七、O4 — DataManager 记录时机

**裁决：`execute()` 返回后，由调用方写**一条** `events` 明细；聚合计数由 DataManager 内部派生。**

### 7.1 时点与内容

```
调用方（Phase 1：API 路由 / 编排层）
   │
   ├── gateway.normalize(raw)          -> Event
   ├── engine.evaluate(event)          -> ActionCommand | None
   ├── action_engine.execute(cmd, pet_id) -> bool
   └── data_manager.record_event(      <- 唯一发起处，唯一写入点
           event, action_name = cmd.action_type if accepted else "")
```

- **写入时机**：`execute()` **返回之后**（此时才知 `action_name` 是否真的触发）。
- **一次写入**：一条 `events` 行同时承载「事件」与「命中并成功触发的动作名」。
- **动作计数**：`SELECT action_name, COUNT(*) FROM events WHERE action_name <> '' GROUP BY action_name`
  （聚合派生，**不设第二写入点**）。

### 7.2 被丢弃 / 降级的指令如何记账（关键）

| 情形 | `events` 是否入账 | `action_name` | 计入动作计数 |
|------|------------------|---------------|--------------|
| 命中且 `execute` = `True` | ✅ | 动作名 | ✅ |
| 命中但越域 / 素材缺失（`execute` = `False`） | ✅ | **空** | ❌ |
| 队列满被丢弃（`execute` = `False`） | ✅ | **空** | ❌ |
| `evaluate` 返回 `None`（无规则命中） | ✅ | 空 | ❌ |

**原则**：**「事件发生」≠「动作触发」**。
事件一律入账（它确实发生了）；只有动作真的被接受才计动作数。
这样 `like` 事件（即使因越域降级）在数据里**计数上升、动作数不升** —— **缺陷可被数据发现**，而非被掩盖。

### 7.3 理由

1. **C5 已冻结「调用方发起、DataManager 只落库聚合」** —— 本裁决只补「何时、写什么」。
2. **单一写入点**消除「某条路径记了、某条没记」的分裂（与 §十四「事件入口边界」同构）。
3. **区分事件与动作**：若被丢弃指令也计动作数，则统计会系统性高估「宠物实际回应次数」，
   与核心验收 S1/S2（用户是否感知到「它回应了」）直接冲突。

### 7.4 与 `phase1_design.md §2.6` 的偏离（记录）

`phase1_design.md:299` 写「事件记录：**网关接收事件后**」，字面早于 `evaluate`。
但该表述**无法承载 `action_name`**（此刻尚无动作），与 C5 单一写点冲突。
**以 C5 + 本裁决为准**（Phase 1 专项中**更晚冻结**的契约优先），记入第十三节 **E17**。

---

## 八、O5 — 动作名取值域

**裁决：`action_type` 的合法取值域 = 各宠物 `config.json` 的 `actions` 数组（唯一权威）；ActionEngine 不定义、不硬编码动作名，越域一律降级 idle。**

### 8.1 为什么是 per-pet `config.json`（B），而不是全局枚举（A）

| 判据 | A：全局代码枚举 | B：per-pet `config.json` |
|------|------------------|---------------------------|
| `PROJECT_RULES.md` §二「禁止硬编码角色名称」 | ❌ 内建动作清单即硬编码 | ✅ 全配置化 |
| 多角色扩展（§十二） | ❌ 新角色需改代码 | ✅ 复制目录改 config 即可 |
| 与 `AssetManager`（§2.7 读 config）一致 | ⚠️ 两处来源 | ✅ 单一来源 |
| 素材存在性 | ⚠️ 需另行校验 | ✅ 动作目录即素材 |

动作字典是**per-pet 配置**（`step3_action_command_decision.md` §四已定位），本裁决确认其为**唯一取值域来源**。

### 8.2 ActionEngine 如何「知道」取值域（不再引入第三处来源）

ActionEngine **不**自己持有动作域清单，而是通过 `AssetManager` 的**存在性校验**间接判定：

```
execute(command, pet_id)
    │
    └── asset_manager.resolve(pet_id, action_type)
            ├── 解析出素材路径 → 合法，继续执行
            └── 解析失败（None） → 越域 / 素材缺失
                                    → 降级 idle + warn 日志 + 返回 False
```

**不变量**：动作名的「合法集合」= `config.json.actions` ∩ 磁盘目录；
**判断这件事的代码只在 `AssetManager`**，ActionEngine 只消费其结论。

### 8.3 越域行为的统一出口

动作名**越域**与**素材缺失**在本项目是**同一条降级路径**（都表现为 AssetManager 解析失败）：

> **降级 idle + `warn`/`error` 日志 + 返回 `False`，不抛异常。**
> （与 `PROJECT_RULES.md` §十一、红线 C4 一致。）

### 8.4 ⚠️ 已发现的实际缺陷（必须修正）

`backend/app/config/rules.json`（Step 3.1 产出）含：

```json
{ "id": "like_dance", "event_type": "like",
  "match": {"field": "payload.like_count", "op": "gte", "value": 3},
  "action": "dance" }
```

而 **`dance` 不属于任何宠物动作域**，`assets/pets/cat/actions/dance/` **不存在**。
⇒ 该规则命中后**必然降级 idle**，`like` 互动**静默失效**（无报错、无动作、无动作计数）。

**处置**（属 `backend/` 与 `assets/`，**本步禁改**，记入第十三节 **E16**，必须在实现 ActionEngine **之前**修正）：

| 方案 | 改动面 | 评价 |
|------|--------|------|
| **(a) 规则动作改用现存动作**（如 `dance` → `happy` / `surprise`） | 仅 `rules.json` | ✅ **推荐**：Step 1 已冻结动作集为 `idle/heart/happy/sad/surprise`，漂移的是规则 |
| (b) 补充 `dance` 素材并在各 `config.json` 的 `actions` 加入 `dance` | 素材 + 3 个 config | ⚠️ 扩大素材面，且与 Step 1 冻结动作集冲突 |

> **具体映射到哪个动作**（`happy` 还是 `surprise`）属产品判断，需确认后落地；本裁决只冻结
> 「规则产出的动作必须落在 per-pet 动作域内」这条约束。

### 8.5 挂起项：动作命名的**文字拼写**

`heart` / `special`（`phase1_design.md`）vs `heart_animation` / `special_animation`
（`system_architecture.md`）—— 属 `step2_event_schema.md` **C9**，**挂起 → Step 4**。
本裁决**不改 C9**：O5 裁决的是**取值域来源与校验位置**，不是**动作名的字面拼写**。

### 8.6 挂起项：全局规则与 per-pet 动作域的映射

`rules.json` 是**全局**的（非 per-pet），而其 `action` 必须落在**某只宠物**的动作域内。
Phase 1 单宠物无碍；**多宠物时**一个全局规则可能引用 A 宠物有、B 宠物无的动作。
该映射关系（规则动作 → per-pet 动作，或规则 per-pet 化）**属 Step 4+**，记为 **O5-a**。

---

## 九、O6 — 队列与抢占边界

**裁决：Phase 1 = FIFO 队列 + 上限 3 + 满丢最旧；不实现 priority 抢占。**

### 9.1 队列归属与状态机

| 项 | 裁决 |
|----|------|
| 队列归谁 | **ActionEngine**（C3） |
| 状态集合 | 对外 `{idle, playing}`；`return_idle` 为**过渡动作**（非持久状态，不对外暴露） |
| `get_state` 返回值 | `idle` / `playing`（与 `system_architecture.md:303` 一致） |

### 9.2 队列上限与满时策略

| 项 | 裁决 | 依据 |
|----|------|------|
| 上限 | **3** | `phase1_design.md:234`（Phase 1 专项） |
| 满时 | **丢弃队首（最旧），保留最新到达** | `system_architecture.md:312`「超出丢弃最旧项」 |

**为何「丢最旧」而非「丢最新」**：核心价值是「我操作，它会回应」（§十五产品定位）。
若丢最新，用户刚点的礼物**没有反应** —— 恰好破坏最关键的因果感知（验收 S1/S2）。
丢最旧则保证**最近一次互动一定被回应**。两文档在此互补而非冲突：
`phase1_design.md` 只写「满则丢弃」（未指明丢哪个），`system_architecture.md` 给出了具体项。

### 9.3 为什么不实现 priority 抢占（关键裁决）

`phase1_design.md:234` 有「新动作优先级更高 → 抢占」一行，但：

1. **比较依据已不存在**：`ActionCommand` 被冻结为**不含 `priority`**（C1），
   ActionEngine **无从得知**当前动作与新动作谁优先级高。
2. **rules.json 的 `priority` 语义不同**：那里的 `priority` 是**规则仲裁**（同一事件命中多条规则时取谁），
   一旦被 `evaluate` 消费即完成使命，**不随指令下传**（`step3_action_command_decision.md` §四）。
   把「规则优先级」当「动作优先级」是**语义错配**。
3. **抢占非 MVP 核心**：Phase 1 验证命题是「一个事件能否驱动一次完整反馈」，抢占不在其中
   （§一 Phase 1 目标）；且 Phase 1 单用户顺序交互，抢占收益低。

⇒ **Phase 1：新动作一律入队（有空位时），不比较优先级、不抢占当前动作。**
状态机的 `playing → playing`（抢占）转移**保留定义但不触发**。

### 9.4 动作优先级（若将来启用）的来源 —— 挂起

若 Step 4 要启用抢占，**动作优先级**需要独立来源（**不得**塞回 `ActionCommand`，C1 不可破）。
候选：per-pet `config.json` 增加 `action_priorities` 映射。
该取舍记为 **O6-a → Step 4**（与 C9、O5-a 同批）。

### 9.5 冷却（cooldown）—— 明确不实现

**任何既有文档均未定义动作冷却**。Phase 1 **不引入冷却机制**
（避免「发明需求」）；若后续需要，走 §七需求变更流程。

### 9.6 并发安全边界

ActionEngine 是**有状态模块**（唯一的）。Phase 1 采用：

- **假设**：单宠物、非并发写入（本地 Demo，单用户顺序交互）。
- **实现**：**不加锁**（避免为未验证的并发需求引入复杂度）。
- **已知限制（记录，非缺陷）**：多请求并发下状态机/队列存在竞态，属**线上化 / Step 4+** 议题。
- 若后续 FastAPI 并发暴露此问题，再按需引入锁或串行化，**不提前优化**。

---

## 十、数据流与类型边界（冻结）

```
Platform Adapter
      │  raw dict
      v
Event Gateway ──normalize──▶ Event
                              │
                              v
Interaction Engine ──evaluate──▶ ActionCommand | None ──执行上下文 pet_id──┐
                                   │                                       │
                                   v                                       v
                             ActionEngine ──execute(command, pet_id)──▶ bool
                                   │
                                   ├──▶ PlaybackCommand{pet_id, action_type} ──▶ 播放端口（Step 4）
                                   └──▶ (状态机 / 队列 / 存在性校验，内部)

调用方 ──▶ DataManager（一条 events 明细；动作计数聚合派生）        （C5 + O4）
```

| 边界 | 类型 | 冻结来源 |
|------|------|----------|
| Gateway → Engine | `Event` | `step2_event_gateway.md` |
| Engine → ActionEngine | `ActionCommand` **或 `None`** | `step3_interaction_engine.md` |
| 调用方 → ActionEngine | `pet_id`（执行上下文） | 本文档 §四 |
| ActionEngine → 调用方 | `bool` | 本文档 §五 |
| ActionEngine → 播放层 | `PlaybackCommand{pet_id, action_type}` | 本文档 §六 |
| 调用方 → DataManager | `event` + `action_name`（触发才非空） | 本文档 §七 |

`None`（无动作）与 `False`（未接受）都是**正常结果**，**不得用异常表达**。

---

## 十一、禁止项

**ActionEngine 不允许**（承 C3 + 本步新增）：

- ❌ 接收 / 依赖 `Event`（只认识 `ActionCommand`）
- ❌ 读取 `rules.json` / 解析 JSON / 读文件
- ❌ 做规则匹配 / 条件求值 / 优先级仲裁（属 Interaction Engine）
- ❌ **内建动作名枚举 / 硬编码动作清单**（属 per-pet `config.json`，见 O5）
- ❌ 直接操作播放器（产 `PlaybackCommand` 交播放端口）
- ❌ 写数据库 / 做聚合统计（属 DataManager）
- ❌ 平台接入 / 平台字段判断
- ❌ `ActionCommand` 上新增 `pet_id` / `priority`（执行上下文用参数传，见 O1/O6）

**本 Step（3.2-B）不允许**：创建 `action_engine.py` / `playback_command.py` / `playback_manager.py` /
`data_manager.py`，修改 `backend/` 与 `assets/`，修改 `rules.json`。

---

## 十二、实现约束提醒（Step 3.2-B 实现必读）

| 约束 | 来源 | 状态 |
|------|------|------|
| **单文件 ≤ 300 行** | `PROJECT_RULES.md` §一 | ⚠️ **现存违反**：`rule_loader.py` **376 行**、`event.py` **308 行** |
| 日志走 `logging`，禁止 `print` | `PROJECT_RULES.md` §十 | — |
| 类型提示 + 函数说明 | `PROJECT_RULES.md` §八 | — |
| 异常不影响主流程 | `PROJECT_RULES.md` §十一 | — |

> **⚠️ 必须处理的历史遗留（E0，本步禁改）**：`rule_loader.py`（376 行）、`event.py`（308 行）
> 超限。须在专门的重构 Step 拆分（如把规则数据结构 / schema 常量从 `rule_loader.py` 拆出）。

> **⚠️ 实现前置条件**：`rules.json` 的 `dance` 越域（§8.4 / E16）**必须先行修正**，
> 否则 ActionEngine 一落地，`like` 互动即静默失效。

---

## 十三、与既有文档的对齐清单（记录，本步不修改）

| # | 位置 | 不一致内容 | 建议处理 |
|---|------|------------|----------|
| **E0** | `backend/app/services/rule_loader.py`（376 行）<br>`backend/app/models/event.py`（308 行） | 超出 300 行上限 | 专门重构 Step |
| **E10** | `system_architecture.md:565-567` | 依赖图含 `ActionEngine ──→ DataManager` | 与 C5 不一致（调用方发起）→ 对齐 |
| **E11** | `system_architecture.md:302` | `trigger(pet_id, action, priority) -> bool` | 对齐为 `execute(command, pet_id) -> bool`（priority 删除） |
| **E12** | `system_architecture.md:299` | 路径 `backend/app/engine/action_engine.py` | 对齐为 `services/action_engine.py` |
| **E13** | `system_architecture.md:394` | 路径 `backend/app/assets/asset_manager.py` | 实际为 `services/asset_manager.py` |
| **E14** | `system_architecture.md:438` | `events.event_type` 注释含 `follow` | 应为 `gift/comment/like/system`（A8） |
| **E15** | `system_architecture.md:250-257` | 规则映射含 `follow`、动作名 `*_animation` | 阶段归属标注（E3 / C9） |
| **E16** | `backend/app/config/rules.json:24` | 产出动作 `dance` **越域**（无宠物声明、无素材目录） | **优先修正**（§8.4），仅改 `rules.json` |
| **E17** | `phase1_design.md:299` | 「事件记录：网关接收事件后」早于 `evaluate`，无法承载 `action_name` | 对齐为「`execute` 后一次写」（C5 + O4） |
| **E18** | `phase1_design.md:234` / `system_architecture.md:312` | 队列满策略表述不一（「满则丢弃」vs「丢弃最旧项」） | 已裁决为**丢最旧**（O6 §9.2）；文档对齐 |
| **E19** | `system_architecture.md:314-316` | 「预留 `generate_action(prompt)`」「register_action」 | Phase 1 不实现，标注阶段归属 |
| **E20** | `PROJECT_RULES.md` §二（示例 `idle/heart/dance/angry/special`）<br>`PROJECT_RULES.md` §三（目录 `idle/heart/happy/sad/surprise`） | **同一文件内动作集自相矛盾**；实际磁盘为后者 | **E16 的根因**：统一为 `idle/heart/happy/sad/surprise`（与各 `config.json`、Step 1 冻结集一致） |

> **处理原则**：与 `step2_event_schema.md` §6.4 相同 —— 后续修正既有文档时
> **必须在提交信息中说明，不得无声改写**。

---

## 十四、未冻结事项（禁止在 Step 3.2-B 实现中自行扩大）

| # | 项目 | 挂起原因 | 处理 |
|---|------|----------|------|
| **C9** | 动作名文字拼写（`heart` vs `heart_animation`） | `step2_event_schema.md` C9 | **Step 4** |
| **O5-a** | 全局规则动作 → per-pet 动作域的映射（多宠物） | 单宠物无碍 | **Step 4+** |
| **O6-a** | 动作优先级来源（启用抢占时） | 单宠物、非并发，抢占无收益 | **Step 4** |
| **O3-b** | `PlaybackCommand` 完整字段集（`duration` / `loop` / `audio`） | 消费者属播放层 | **Step 4** |
| **O6-b** | idle 恢复回调入口命名（`on_playback_complete` 等） | 随 `PlaybackManager` 一起冻结 | **Step 4** |

---

## 十五、变更管理

本文档冻结后，以下属**破坏性约束** —— 变更会使动作执行链上下游同时失效：

- `execute(command, pet_id) -> bool`（入口签名 + 返回值）
- `PlaybackCommand{pet_id, action_type}` 最小字段集
- 「调用方一次写 `events`」的记录模型
- 「动作名取值域 = per-pet `config.json`」+「越域降级 idle」

任何变更必须走 `PROJECT_RULES.md` §七「需求变更管理」，变更后本文档**版本号递增**，
并在第十六节记录变更历史。

**禁止**在实现代码中「顺手」：把 `pet_id` 塞进 `ActionCommand`、让 ActionEngine 内建动作枚举、
或在 ActionEngine 内直接写库 —— 那正是本文档要防止的边界腐化。

---

## 十六、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 O1–O6；发现并记录 E16（`rules.json` 动作越域缺陷）。 |
