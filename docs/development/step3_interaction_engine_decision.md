# Step 3 Interaction Engine 契约裁决

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 3.0-A
> **定位**：Step 3（Interaction Engine 实现）及其后**所有 Step 的唯一输入**。
> **上游冻结**：`docs/development/step2_event_schema.md`（v1.1）、`docs/development/step2_event_gateway.md`（v1.0）
> **来源**：Step 3.0 在设计前扫描既有文档时触发 **STOP（§三 A 类硬冲突）**，本文档为其裁决产出。

---

## 一、本文档存在的理由

Step 3.0 在冻结 Interaction Engine 契约前，按规程扫描既有文档，发现：

- `docs/development/phase1_design.md`（Step 1 产出）**已经完整定义过规则结构与 `rules.json` 格式**；
- `docs/architecture/system_architecture.md`（Step 1 产出）**定义了另一版规则匹配语义与引擎接口**；
- 两者互相冲突，且都与 Step 3.0 指令要求冲突。

若不作裁决直接写契约文档，会产出**第三套规则方言**。

后果与 `step2_event_schema.md` §6.1 记载的完全同类：**不报错，只是静默失效**——规则永远不命中，系统无任何异常，表现为「评论没反应」。这类缺陷排查成本极高。

**因此本文档是冻结动作的必要组成部分，不是附加说明。**

本文档只做**裁决与冻结**，不含任何代码。Interaction Engine 的实现属 Step 3 后续步骤。

---

## 二、冲突记录与裁决（H1–H7）

| ID | 冲突 | 来源 | **裁决** |
|----|------|------|----------|
| **H1** | 规则字段集 | `phase1_design.md:153-177`：`id` / `event_type` / `match{field,op,value}` / `action` / `priority`＋顶层 `defaults`<br>Step 3.0 §四.3：`id` / `event_type` / `condition` / `action` / `enabled` | **采用 `match`，保留 `priority`，新增 `enabled`**<br>最终字段集：`id` / `event_type` / `match` / `action` / `priority` / `enabled` |
| **H2** | 触发条件术语 | `phase1_design.md:162` → `match`<br>`step2_event_gateway.md:243` → `trigger`（描述性用词）<br>Step 3.0 §四.3 → `condition` | **`match`**（结构化对象） |
| **H3** | 操作符命名 | `phase1_design.md:180`：`eq` / `contains` / `gte` / `lte`<br>Step 3.0 §四.4：`==` / `>=` / `contains` | **`eq` / `contains` / `gte` / `lte`**（沿用既有，禁止符号形式） |
| **H4** | 优先级归属 | `phase1_design.md:164`：规则级 `priority`<br>`system_architecture.md:265`：`get_priority(action) -> int`（动作级）<br>Step 3.0 §四.3 字段表未列 `priority` | **保留规则级 `priority`**；不采用动作级 `get_priority` |
| **H5** | 兜底规则 | `phase1_design.md:174-176`：顶层 `defaults: {"gift": "heart"}`<br>Step 3.0 §四.3 字段表无处安放 | **保留 `defaults`**（rules.json 顶层段），并把 `match` 定为**必填** |
| **H6** | 规则加载职责 | `phase1_design.md:861`：`rule_loader` 与 Interaction Engine **分列两项**<br>`system_architecture.md:263`：`load_rules` **挂在 Engine 上** | **独立 RuleLoader**；Engine 不读文件、不解析 JSON |
| **H7** | `like` 触发阈值 | `phase1_design.md:150` → **3**<br>`system_architecture.md:256` → **10**<br>`step2_event_schema.md:429`（C8/A6：**挂起，指向 Step 3**） | **3**（详见第七节） |

### 2.1 逐条理由

**H1｜为什么保留 `match` 而不是改用 `condition`**
`phase1_design.md:169` 的 `match.field = "payload.content"` 是 `step2_event_schema.md` 裁决 **C1**（评论文本字段名取 `content` 而非 `text`）的直接依据之一。改名会动摇一条**已冻结**的结论链。`condition` 作为字段名同样要装一个结构化对象，语义上无增益，代价是让契约与既有文档不一致。

**H1｜为什么保留 `priority`**
`InteractionEngine` 的既定职责包含**优先级仲裁**（`system_architecture.md:240`）。`priority` 是该职责的唯一数据载体；删掉它就必须另造机制，属无收益的复杂度。

**H1｜为什么新增 `enabled`**
既有两份文档都没有规则开关，只能通过「注释掉 JSON」或「物理删除」来停用规则。`enabled` 提供**不改动规则内容即可停用**的能力，是规则可配置的前提。属**纯新增**，不覆盖任何既有语义。

**H2｜为什么 `trigger` 不算字段冻结**
`step2_event_gateway.md:242-245` 的原文是「Gateway **不得**接触：`rules.json` / `trigger`（触发条件） / `action`（动作名） / `cooldown`（冷却）」——该句在陈述**网关的禁知范围**，不是在定义规则字段。其 `trigger` 应理解为「触发条件」这一概念的代称。本文档统一使用 `match` 作为字段名，`trigger` 不再作为字段名出现。

**H3｜为什么禁止 `==` / `>=` / `<=`**
操作符在 `rules.json` 中是**字符串字面量**。符号形式与「字符串」组合后，可读性、转义、以及与 `contains`（本就无符号形式）的混用都会制造不一致。更重要的是：**已有一套词形在文档中，新增第二套即双语法**——而双语法正是 Step 3.0 STOP 要防止的情况。

**H4｜为什么不做动作级优先级**
若同时存在「规则级 `priority`」与「动作级 `get_priority(action)`」，同一动作经不同规则触发时优先级可能不同，系统出现**两个优先级事实来源**，仲裁结果不可预测。保留单一来源：规则级。

**H5｜为什么 `match` 定为必填**
若既允许「无 `match` 的规则」又保留 `defaults`，则「无条件匹配某 `event_type`」有**两种表达方式**——又一处双语法。取舍为：**无条件 / 兜底一律走 `defaults`；每条规则必须写明条件**。这与 `phase1_design.md` 的实际写法一致（其 `rules[]` 每条都有 `match`，「其他礼物 → heart」正是通过 `defaults` 表达）。

**H6｜为什么 Loader 与 Engine 分离**
`phase1_design.md:861` 已把 `rule_loader`（加载＋校验＋容错）与 Interaction Engine（规则匹配＋优先级）列为**两个任务**。分离后 Engine 的输入是**已校验的规则集**，其可实现为纯函数（无 IO），可被单测完全覆盖——符合 `PROJECT_RULES.md` §一.5「所有模块可测试」。

**H7｜为什么取 3**
见第七节。

---

## 三、最终 Rule Schema 冻结

### 3.1 文件结构

```json
{
    "version": "1.0",
    "rules": [
        {
            "id": "gift_heart",
            "event_type": "gift",
            "match": { "field": "payload.gift_name", "op": "eq", "value": "小心心" },
            "action": "heart",
            "priority": 50,
            "enabled": true
        }
    ],
    "defaults": {
        "gift": "heart"
    }
}
```

### 3.2 字段含义（规则对象内）

| 字段 | 类型 | 必填 | 含义 |
|------|------|------|------|
| `id` | string | ✅ | 规则唯一标识。用于日志、排障、后续按规则统计。**同一文件内必须唯一**。 |
| `event_type` | string | ✅ | 该规则适用的 `event_type`。取值必须是事件契约白名单：`comment` / `gift` / `like` / `system`。 |
| `match` | object | ✅ | 触发条件。结构 `{field, op, value}`，语义见第四节。**必填**（H5）。 |
| `action` | string | ✅ | 命中后要执行的动作名。**取值域（动作字典）属 Action Engine，Step 4 冻结**（见 `step2_event_schema.md` C9）。 |
| `priority` | int | ✅ | 规则优先级。数值越大优先级越高。用于命中多条规则时的仲裁。 |
| `enabled` | bool | ✅ | 规则开关。`false` 表示该规则**不参与匹配**。 |

### 3.3 `match` 子结构

| 字段 | 类型 | 含义 |
|------|------|------|
| `field` | string | 取值路径，点号分隔，**根为事件顶层**。例：`payload.content`、`payload.gift_name`、`payload.like_count`。 |
| `op` | string | 操作符，白名单见第四节。 |
| `value` | any | 比较值。类型随 `op` 而定。 |

### 3.4 顶层 `defaults`

`event_type` → `action` 的映射，用于**无规则命中**时的兜底。语义与边界见第五节。

### 3.5 规则求值语义（冻结）

1. 取 `enabled = true` 且 `event_type` 与事件**完全相等**的规则，作为候选集。
2. 逐条求值 `match`；在候选集中，`match` 为真的规则构成**命中集**。
3. 命中集非空 → 取 `priority` **最大**者。**同优先级 → 取 `rules[]` 中声明顺序靠前者**（确定性优先，不依赖字典序或随机）。
4. 命中集为空 → 查 `defaults[event_type]`：存在则该动作生效；不存在则**返回 `None`**。
5. 全过程**不抛异常**。未命中是正常结果，不是错误。

### 3.6 不可变点

- 规则对象的字段集固定为 3.2 的 6 个，**不得增删改名**。
- 新增字段必须走第十二节的变更流程。

---

## 四、Match Operator 冻结

### 4.1 白名单（**只允许**以下 4 个）

| `op` | 语义 | `value` 类型 |
|------|------|--------------|
| `eq` | 相等 | 任意可比较类型 |
| `contains` | 包含。string → 子串；list → 成员存在 | string / list |
| `gte` | 大于等于 | number（或同类型可比较值） |
| `lte` | 小于等于 | number（或同类型可比较值） |

### 4.2 禁止项

- ❌ `==` / `>=` / `<=` / `!=` / `>` / `<` —— **禁止符号形式**，理由见 H3。
- ❌ 正则、脚本表达式、函数调用等任何可执行语法。
- ❌ 复合条件（`and` / `or` / 嵌套）。Phase 1 每条规则**单条件**。多条件需求的正确做法是**拆成多条规则**，而不是在 `match` 里引入逻辑树。

### 4.3 边界行为（冻结，禁止崩溃）

| 情形 | 行为 |
|------|------|
| `field` 路径不存在（如 `like` 事件无 `payload.like_count`） | 求值为 **false**（不命中），**不报错** |
| `op` 所需类型不匹配（如对 string 用 `gte`） | 求值为 **false**，并**记录告警日志** |
| `op` 不在白名单 / `match` 结构非法 | **由 RuleLoader 在加载期拒绝**（见第六节），不得进入 Engine |

> 原则：**规则问题不得导致主流程异常**。加载期拒绝非法规则，运行期把「不匹配」当作正常结果。这与 `phase1_design.md:193`「rules.json 解析失败时使用内置空规则 + 告警日志，不影响启动」一致。

---

## 五、`defaults` 裁决

### 5.1 结论：**保留**

`phase1_design.md:146` 的规则表包含「`gift` / 其他礼物 / `heart`（默认礼物动作）」——这是一条**真实的 Phase 1 行为**，不是可选项。`defaults` 是它的唯一载体（H5 已排除「无 `match` 规则」这一替代表达）。

### 5.2 语义

```
命中集为空 → defaults[event_type]
```
- 键为 `event_type`，值为 `action`。
- 无该 `event_type` 键 → 该事件返回 `None`（不产生动作）。
- `defaults` 是 **per-event_type 单一动作**；`like` 的正例（`like_count >= 3`）走普通规则，反例（`< 3`）通过**不配置** `defaults["like"]` 自然得到「无动作」。

### 5.3 谁读取 / 谁解释 / 谁执行

| 环节 | 归属 | 说明 |
|------|------|------|
| **谁读取** | **RuleLoader** | 解析 `rules.json`，把 `rules` 与 `defaults` 一并纳入「已校验规则集」。 |
| **谁解释** | **InteractionEngine** | 在命中集为空时按 `event_type` 查 `defaults`，决定是否产出指令。 |
| **谁执行** | **ActionEngine** | 只接收 `ActionCommand`。**ActionEngine 对 `defaults` 完全无感知**——兜底动作与普通动作走**完全相同**的指令路径。 |

> 关键不变量：`defaults` **不产生第二条执行路径**。它只影响「是否产生指令」，不影响「指令如何被执行」。若未来 ActionEngine 需要区别对待兜底动作，说明分层已破口。

### 5.4 与 `match` 必填的关系

`match` 必填（H5）＋ `defaults` 保留 ⇒ **「无条件生效」只有一种表达：`defaults`**。

---

## 六、Rule Loader 边界

### 6.1 数据流

```
rules.json  →  RuleLoader  →  validated rules  →  InteractionEngine
                  │
                  └─ 加载 / 校验 / 容错（失败不崩溃）
```

### 6.2 职责划分

| 模块 | 负责 | 不负责 |
|------|------|--------|
| **RuleLoader** | 文件读取；JSON 解析；结构校验（字段完备、类型正确、`op` 在白名单内、`id` 不重复、`event_type` 在白名单内）；过滤 `enabled = false`；容错（失败降级为空规则集 + 告警日志） | 规则匹配；条件求值；动作决策；优先级仲裁 |
| **InteractionEngine** | 规则匹配；条件求值；优先级仲裁；产出 `ActionCommand` | 文件读取；JSON 解析；平台字段转换 |

### 6.3 Interaction Engine 明确**不负责**

- ❌ 文件读取（含 `rules.json`）
- ❌ JSON 解析
- ❌ 平台字段转换（平台差异只允许存在于 Adapter 内）

> 理由：Engine 的输入必须是**已校验的规则集**，使其成为**纯函数式、可完全单测**的模块（H6）。一旦 Engine 自己读文件，单测就必须准备真实文件或 mock IO，可测试性下降。

---

## 七、`like` 触发阈值裁决

### 7.1 最终值：**3**

### 7.2 来源差异记录

| 来源 | 值 | 文档性质 |
|------|----|----------|
| `phase1_design.md:150` | **3** | Phase 1 专项设计 |
| `system_architecture.md:256` | **10** | 架构长期形态 |
| `step2_event_schema.md:429`（C8 / A6） | 挂起 | 原文：「属 Interaction Engine 规则层，**Step 3 处理**」 |

### 7.3 理由

1. **验证命题要求可达。** Phase 1 的命题是「一个标准事件能否驱动完整宠物反馈」。`10` 在本地模拟器 / Demo 单次会话中几乎不可达，等于该规则路径**永不执行**——即「有代码、无验证」。`3` 可被模拟器稳定触达。
2. **文档性质对齐。** `phase1_design.md` 是 Phase 1 专项设计，`system_architecture.md` 描述的是长期形态。Phase 1 的取值应以 Phase 1 文档为准。
3. **阈值不是架构常量。** 它是运营参数，属规则配置（`rules.json`），**改值不需要改代码**。取 `3` 不构成对架构的否定。

### 7.4 字段路径与语义

- 规则形式：`{"field": "payload.like_count", "op": "gte", "value": 3}`。
- `payload.like_count` **已在事件契约的规范示例中出现**（`step2_event_schema.md:208`、`:237`），因此该路径**有契约依据**，不是本文档新造的字段。
- 缺失 `payload.like_count` 时按第四节 4.3：求值为 false（不命中），不报错。

> ⚠️ **待确认项（不阻塞 Step 3）**：`payload.like_count` 的语义是**单事件携带的计数**还是**累计计数**，事件契约未明示。本文档按**单事件比较**处理（模拟器与 Adapter 负责决定携带何种数值）。若 Phase 3 接入真实平台时需要累计语义，属 Adapter 职责，不在规则层解决。

---

## 八、ActionCommand 初步冻结

> 本步**只定义接口，不实现**。ActionCommand 的完整契约（含 `priority` 传递）以 Step 4（Action Engine）契约为准，本文档只冻结 Step 3 必须依赖的最小部分。

### 8.1 最小字段（冻结）

| 字段 | 类型 | 含义 |
|------|------|------|
| `action_type` | string | 要执行的动作名。取值来自命中的规则（或 `defaults`）。**取值域本身属 Step 4**。 |
| `payload` | object | 动作参数桶。**Phase 1 允许为空 `{}`**，为后续参数化动作预留。 |

### 8.2 是否包含 `event_id` / `user_id`

**结论：均不包含。**

| 候选 | 裁决 | 理由 |
|------|------|------|
| `event_id` | ❌ **不包含** | 事件契约的 4 个顶层字段中**没有 `id`**（`step2_event_schema.md` §二）。凭空生成一个 ID 会制造「可追溯」的假象——它无法与任何上游记录对应，排障时反而误导。 |
| `user_id` | ❌ **不包含** | `ActionCommand` 的职责是表达**「做什么」**，不是携带**「谁触发的」**。互动次数 / 独立用户统计所需的 `user_id`，由**持有 `Event` 的调用方**直接交给 Data Manager；`ActionCommand` 一旦携带 `user_id`，就会逐步演变成「Event 的副本」，`Event` 与 `ActionCommand` 的边界随之消失。 |

**关键不变量**：`ActionCommand` 是**指令**，不是事件的投影。同一条调用链上 `Event` 仍然存活，身份与溯源信息不需要在指令里复制一份。

> **推翻条件（诚实标注边界）**：若未来 `ActionCommand` 需要**跨进程 / 经队列**传递（调用方不再持有 `Event`），则需要引入关联标识。届时应当引入**统一的 `correlation_id`**，而**不是**把 `user_id` 单个字段塞进指令——后者只会解决一部分场景，留下不一致的半套方案。

### 8.3 挂起项：`priority` 是否进入 ActionCommand

- `system_architecture.md:302` 的 `trigger(pet_id, action, priority)` 显示 Action Engine **接收优先级**；而优先级由 Interaction Engine 仲裁得出。
- 若 ActionCommand 不携带 `priority`，仲裁结果**无法传递**给 Action Engine。
- 但 `priority` 的消费者是 Action Engine，其契约属 **Step 4**。
- ⇒ **本文档不单方面扩字段**。该项与 Action Engine 契约一并在 Step 4 冻结，并记录在第十一节。

### 8.4 不实现声明

本步不创建 ActionCommand 的任何代码实体、不创建 `class`、不创建数据类型文件。

---

## 九、数据流与类型边界

```
Platform Adapter
      │  raw dict          （平台差异只允许存在于此）
      v
Event Gateway
      │  Event             （已冻结：4 顶层字段；唯一构造点）
      v
InteractionEngine
      │  ActionCommand | None
      v
Action Engine
```

| 边界 | 类型 | 冻结来源 |
|------|------|----------|
| Adapter → Gateway | `dict` | `step2_event_gateway.md` |
| Gateway → Engine | **`Event`** | `step2_event_gateway.md`；`step2_event_schema.md` §7.3 |
| Engine → Action Engine | `ActionCommand` **或 `None`** | 本文档第八节 |

`None` 是**正常返回值**，表示「无动作」，**不是错误**，不得用异常表达。

---

## 十、禁止项

Interaction Engine **不允许**：

- ❌ 创建 `Event`（唯一构造点是 Event Gateway，见 `PROJECT_RULES.md` §十四「事件入口边界」）
- ❌ 调用 Adapter
- ❌ 读取平台字段（Engine 只认识事件的 4 个顶层字段与 `payload` 内的契约字段）
- ❌ 播放资源
- ❌ 操作数据库
- ❌ 读取文件 / 解析 JSON（属 RuleLoader）

本 Step（3.0-A）**不允许**：创建 Interaction Engine 代码、创建 `rules.json`、创建 Rule Loader、修改 Event Model / Gateway、修改 Action Engine。

---

## 十一、与既有文档的对齐清单（B 类，待后续 Step）

本文档**不修改**任何既有文档，仅记录。后续修正时**必须在提交信息中说明，不得无声改写**（与 `step2_event_schema.md` §6.4、`step2_event_gateway.md` §9.3 同一原则）。

| # | 位置 | 不一致内容 | 建议处理 |
|---|------|------------|----------|
| **E1** | `phase1_design.md:153-180` | 规则结构缺 `enabled`；无 `match` 必填说明 | 按本文档第三节对齐 |
| **E2** | `phase1_design.md:180` | 操作符表未标注「禁止符号形式」 | 按本文档第四节对齐 |
| **E3** | `system_architecture.md:250-257` | 规则映射表含 `follow`（Phase 3+）、动作名 `*_animation`（C9 → Step 4） | 标注阶段归属 |
| **E4** | `system_architecture.md:261` | Engine 路径 `backend/app/engine/`（`PROJECT_RULES.md` 分层只允许 `services/`） | **即 `step2_event_gateway.md` §9.3 G4**，Step 3 后续对齐 |
| **E5** | `system_architecture.md:264` | 旧签名写作 `process(event: dict) -> ActionCommand \| None`：入参为 `dict`（应为 `Event`），方法与 `load_rules` / `get_priority` 绑定在 Engine | 按第九节与第六节对齐 |
| **E6** | `system_architecture.md:261` / `development_plan.md:99-100` | `rules.json` 路径为 `engine/`，与 `phase1_design.md:409` 的 `services/rules.json` 不一致 | 随 E4 一并对齐 |
| **E7** | `phase1_design.md:137` | 写作 `action_command`（小写） | 统一为 `ActionCommand` |
| **E8** | `step2_event_gateway.md:243` | 用词 `trigger` 指代触发条件 | 术语统一为 `match`（属描述性用词，非字段冻结） |
| **E9** | `step2_event_schema.md:429`（C8）/ `:452`（A6） | `like` 阈值**已挂起至 Step 3** | **本文档第七节已关闭该项** |

### 11.1 未冻结项（显式挂起，禁止在 Step 3 自行决定）

| # | 项目 | 挂起原因 | 处理 Step |
|---|------|----------|-----------|
| **O1** | `ActionCommand.priority` 是否传递 | 消费者属 Action Engine | **Step 4** |
| **O2** | 动作名取值域（`heart` vs `heart_animation`） | `step2_event_schema.md` C9 | **Step 4** |
| **O3** | Interaction Engine 入口方法名 | 旧文档用 `process`，命名须与契约一致后再定（参照 Step 2.3-A 教训：**不得长期并存两个入口名**） | **Step 3 实现步** |
| **O4** | `payload.like_count` 单事件 / 累计语义 | 事件契约未明示 | 真实平台接入前（Phase 3） |

---

## 十二、变更管理

本文档冻结后：

- **规则字段集、操作符白名单**属**破坏性约束**——变更会使既有 `rules.json` 与所有规则测试失效。
- 任何变更必须走 `PROJECT_RULES.md` §七「需求变更管理」流程：`docs/change_request/需求名称.md`。
- 变更后本文档**版本号递增**，并在第十三节记录变更历史。
- **禁止**在实现代码中「顺手」新增字段或操作符——那正是本文档要防止的方言漂移。

---

## 十三、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。裁决 H1–H7；关闭 `step2_event_schema.md` C8/A6。 |
