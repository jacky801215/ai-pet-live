# Step 3 Interaction Engine 契约

> **版本**：v1.0（FROZEN）
> **日期**：2026-09-19
> **产出 Step**：Step 3.0-B
> **上游依据**：
> - `docs/development/step2_event_schema.md`（v1.1 FROZEN）—— 事件契约
> - `docs/development/step2_event_gateway.md`（v1.0 FROZEN）—— 事件入口契约
> - `docs/development/step3_interaction_engine_decision.md`（v1.0 FROZEN）—— **冲突裁决与规则契约**
> **定位**：`InteractionEngine` 与 `RuleLoader` 的实现（Step 3.1+）**唯一接口准绳**。
> **本文档只冻结接口与职责，不含任何实现代码。**

---

## 一、模块定位

### 1.1 在数据流中的位置

```
EventGateway
      │  Event            （已冻结：4 顶层字段；唯一构造点）
      v
InteractionEngine
      │  ActionCommand | None
      v
ActionEngine
```

### 1.2 一句话定位

> **EventGateway 知道「事件合法吗」；InteractionEngine 知道「事件该做什么」。**
> 两者之间只传递 `Event`。

### 1.3 负责 / 不负责

| | 内容 |
|---|---|
| ✅ **负责** | 规则匹配（rule matching）<br>条件计算（condition evaluation）<br>动作选择（action selection，含优先级仲裁） |
| ❌ **不负责** | 平台事件接入（属 Adapter）<br>`Event` 校验（属 Event Model / Event Gateway）<br>播放执行（属 Playback Manager）<br>数据库存储（属 Data Manager）<br>文件读取（属 RuleLoader） |

---

## 二、输入输出契约

| 项 | 冻结值 |
|---|---|
| **输入** | `Event`（已校验的统一事件对象，4 个顶层字段） |
| **输出** | `ActionCommand` \| `None` |

**`None` 是正常业务结果，不是异常。**

- 「没有任何规则命中，且 `defaults` 也没有对应项」→ 返回 `None`。
- 这是**预期内**的日常情况（例如一条不含「跳舞」的普通评论）。
- 因此：**禁止用异常表达「无动作」**，**禁止在无动作时记录 ERROR 级日志**（可为 DEBUG/INFO）。

| 输入情形 | 行为 |
|---|---|
| 合法 `Event`，有规则命中 | 返回 `ActionCommand` |
| 合法 `Event`，无规则命中但有 `defaults` | 返回 `ActionCommand` |
| 合法 `Event`，无规则命中且无 `defaults` | 返回 `None` |

> Engine **不再校验** `Event`。若入参不是合法 `Event`，属上游破口，不是 Engine 的责任（唯一构造点见 `PROJECT_RULES.md` §十四「事件入口边界」）。

---

## 三、Rule Schema

### 3.1 完整示例

```json
{
    "id": "gift_heart",
    "event_type": "gift",
    "match": { "field": "payload.gift_name", "op": "eq", "value": "小心心" },
    "action": "heart",
    "priority": 50,
    "enabled": true
}
```

### 3.2 字段说明（规则对象）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | **规则唯一标识**。用于日志、排障与按规则统计；同一文件内不得重复。 |
| `event_type` | string | ✅ | **精确匹配**事件类型，取值必须是事件契约白名单：`comment` / `gift` / `like` / `system`。 |
| `match` | object | ✅ | 触发条件，子结构 `{field, op, value}`。**必填**（「无条件生效」唯一走 `defaults`）。 |
| `action` | string | ✅ | **输出动作类型**。命中即作为 `ActionCommand.action_type`。取值域属 Step 4。 |
| `priority` | int | ✅ | **冲突排序**：**数字越大越优先**。用于多条规则同时命中时的仲裁。 |
| `enabled` | bool | ✅ | **规则开关**：`false` 表示该规则**不参与匹配**。 |

### 3.3 `match` 子结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `field` | string | 取值路径，点号分隔，**根为事件顶层**。例：`payload.gift_name`、`payload.content`、`payload.like_count`。 |
| `op` | string | 操作符，白名单见第五节。 |
| `value` | any | 比较值。 |

### 3.4 文件级结构

```json
{ "version": "1.0", "rules": [ ... ], "defaults": { ... } }
```

`defaults` 为 `event_type` → `action` 的映射，兜底语义见第六节 6.4。

### 3.5 不可变点

规则对象的字段集固定为 **6 个**，**不得增删改名**（`enabled` 为 Step 3.0-A 新增，`match` / `priority` 为沿用既有）。任何变更必须走第十一节的变更流程。

---

## 四、匹配流程

### 4.1 冻结顺序

```
receive Event
      │
      v
filter enabled = true
      │
      v
match event_type
      │
      v
evaluate match
      │
      v
select highest priority
      │
      v
create ActionCommand
```

**无命中 → `return None`。**

### 4.2 逐步语义

1. **receive Event** —— 接收已校验的 `Event`。
2. **filter enabled = true** —— 剔除 `enabled = false` 的规则。
3. **match event_type** —— 保留 `event_type` 与事件**完全相等**的规则，构成候选集。
   - `event_type` 是**精确匹配**，不做前缀 / 包含 / 模糊匹配。
4. **evaluate match** —— 逐条求值 `match` 表达式，求出**命中集**。
5. **select highest priority** —— 命中集中取 `priority` **最大**者。
   - **同优先级 → 取 `rules[]` 中声明顺序靠前者**（确定性优先；不得依赖字典序、文件系统顺序或随机）。
6. **create ActionCommand** —— 产出 `{action_type: <rule.action>, payload: {}}`。

### 4.3 无命中时的兜底

命中集为空 → 查 `defaults[event_type]`：

- 存在 → 以该动作产出 `ActionCommand`（**走与普通规则完全相同的路径**）。
- 不存在 → **`return None`**。

### 4.4 流程不变量

- 全过程**不抛异常**。「未命中」是正常结果，不是错误。
- 单条规则求值失败（字段缺失 / 类型不匹配）**不得中断**流程，只影响该条规则（见第五节 5.3）。

---

## 五、Match 语义

### 5.1 白名单（**只允许**这 4 个）

| `op` | 含义 | `value` 类型 |
|------|------|--------------|
| `eq` | 等于 | 任意可比较类型 |
| `contains` | 包含（string → 子串；list → 成员存在） | string / list |
| `gte` | 大于等于 | number（或同类型可比较值） |
| `lte` | 小于等于 | number（或同类型可比较值） |

### 5.2 禁止项

- ❌ **符号形式**：`==` / `>` / `<` / `>=` / `<=` / `!=`
- ❌ **正则**（regex）
- ❌ **脚本 / 表达式求值**（任何可执行语法）
- ❌ **复合条件**（`and` / `or` / 嵌套逻辑树）

多条件需求的正确做法是**拆成多条规则**，不是在 `match` 里引入逻辑树。

> 说明：操作符在 `rules.json` 中是**字符串字面量**。若同时允许 `eq` 与 `==` 两套词形，即形成**双语法**——这正是 Step 3.0 触发 STOP 要防止的情形。详见 `step3_interaction_engine_decision.md` H3。

### 5.3 边界行为（冻结，**禁止崩溃**）

| 情形 | 行为 |
|------|------|
| `field` 路径不存在（如 `like` 事件无 `payload.like_count`） | 求值为 **false**（不命中），**不报错** |
| `op` 所需类型不匹配（如对 string 用 `gte`） | 求值为 **false**，**记录告警日志** |
| `op` 不在白名单 / `match` 结构非法 | **由 RuleLoader 在加载期拒绝**，不得进入 Engine |

> 原则：**规则问题不得导致主流程异常**。加载期拒绝非法规则，运行期把「不匹配」当作正常结果。

---

## 六、RuleLoader 边界

### 6.1 职责划分

```
rules.json  →  RuleLoader  →  validated rules  →  InteractionEngine
                  │
                  └─ 加载 / 校验 / 容错（失败不崩溃）
```

| 模块 | 负责 | 不负责 |
|------|------|--------|
| **RuleLoader** | 文件读取；JSON 解析；schema 检查；**非法规则拒绝**；过滤 `enabled = false`；容错降级 | 规则匹配；条件求值；动作选择；优先级仲裁 |
| **InteractionEngine** | 规则匹配；条件计算；动作选择；产出 `ActionCommand` | 文件读取；JSON 解析；schema 校验 |

### 6.2 RuleLoader 负责（冻结）

- **文件读取**：读取 `rules.json`。
- **JSON 解析**：解析为结构化对象。
- **schema 检查**：字段完备性、类型正确性、`op` 在白名单内、`id` 不重复、`event_type` 在白名单内。
- **非法规则拒绝**：任一检查失败 → 拒绝该规则（并按 6.3 决定整体策略）。

### 6.3 容错策略（冻结）

`rules.json` 解析 / 校验失败时：**使用内置空规则集 + 告警日志，不影响启动。**

- 单个规则非法 → 拒绝该规则，**其余规则继续加载**（记录告警）。
- 文件级失败（不存在 / 非法 JSON）→ **空规则集**，记录告警。

依据：`phase1_design.md:193`（「不影响启动」）、`PROJECT_RULES.md` §十一（异常处理）。

### 6.4 RuleLoader 与 `defaults`

`RuleLoader` **同时读取并交付 `defaults`**，与 `rules` 一并构成「validated rules」。

| 环节 | 归属 |
|------|------|
| **谁读取** | RuleLoader |
| **谁解释** | InteractionEngine（命中集为空时按 `event_type` 查） |
| **谁执行** | ActionEngine（**对 `defaults` 完全无感知**） |

> 关键不变量：`defaults` **不产生第二条执行路径**。它只影响「是否产生指令」，不影响「指令如何被执行」。

### 6.5 InteractionEngine 明确禁止

- ❌ `open()` —— 不得读取任何文件
- ❌ `json.load()` —— 不得解析 JSON
- ❌ 读取 `rules.json` —— 不得感知规则文件的**存在**

> 理由：Engine 的输入必须是**已校验的规则集**，使其成为**纯函数式、可完全单测**的模块。一旦 Engine 自己读文件，单测就必须准备真实文件或 mock IO，可测试性下降——与 `PROJECT_RULES.md` §一.5「所有模块可测试」冲突。

---

## 七、ActionCommand 冻结

### 7.1 最小结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `action_type` | string | 要执行的动作名（来自命中的规则或 `defaults`）。**取值域属 Step 4。** |
| `payload` | object | 动作参数桶。**Phase 1 允许为空 `{}`**，为后续参数化动作预留。 |

```json
{ "action_type": "heart", "payload": {} }
```

### 7.2 当前**不包含**的字段

| 字段 | 是否包含 | 原因（引用 Step 3.0-A 决策） |
|------|----------|------------------------------|
| `event_id` | ❌ | 事件契约的 4 个顶层字段中**没有 `id`**。凭空生成 ID 会制造「可追溯」的假象——它无法与任何上游记录对应，排障时反而误导。 |
| `user_id` | ❌ | `ActionCommand` 的职责是表达**「做什么」**，不是携带**「谁触发的」**。互动次数 / 独立用户统计所需的 `user_id`，由**持有 `Event` 的调用方**直接交给 Data Manager。指令一旦携带 `user_id`，会逐步演变为「`Event` 的副本」，`Event` 与 `ActionCommand` 的边界随之消失。 |
| `priority` | ❌（本步） | 优先级由 Engine 仲裁得出，但其消费者是 Action Engine，契约属 **Step 4**。本步**不单方面扩字段**（见第九节 O1）。 |

> **关键不变量**：`ActionCommand` 是**指令**，不是事件的投影。
> **推翻条件**：若未来 `ActionCommand` 需**跨进程 / 经队列**传递，应引入**统一的 `correlation_id`**，而非单独塞入 `user_id`。

### 7.3 不实现声明

本步不创建 `ActionCommand` 的任何代码实体、不创建 `class`、不创建数据类型文件。

---

## 八、Phase 1 行为规则

> 以下为 Phase 1 的**行为约定**（供 `rules.json` 编写与测试夹具使用）。
> **动作名的最终取值域属 Step 4（`step2_event_schema.md` C9）**，此处记录的是**规则结构与字段路径**。

### 8.1 Gift（礼物）

| 规则 | 条件 | 输出动作 |
|------|------|----------|
| 指定礼物 | `gift_name = 小心心` | `heart` |
| 其他礼物 | —— | `heart`（经 `defaults: {"gift": "heart"}` 兜底） |

字段路径依据：`payload.gift_name`、`payload.gift_count`（事件契约 C2 已冻结字段名）。

### 8.2 Like（点赞）

| 规则 | 条件 | 输出动作 |
|------|------|----------|
| 达标 | `payload.like_count >= 3` | 对应 action |
| 未达标 | `payload.like_count < 3` | **不配置 `defaults["like"]`** → 返回 `None`（无动作） |

- **阈值 3 的裁决依据**：`step3_interaction_engine_decision.md` 第七节（来源差异 `phase1_design.md:150` = 3 vs `system_architecture.md:256` = 10）。
- 字段路径 `payload.like_count` **已在事件契约的规范示例中出现**（`step2_event_schema.md:208`、`:237`）。
- ⚠️ 该字段的**单事件 / 累计语义**未冻结，见第九节 O4。

### 8.3 Comment（评论）—— **预留**

- 条件字段路径已冻结：`payload.content`（事件契约 C1）。
- 具体规则（如「含『跳舞』→ dance」）**本步不冻结**：其动作名属 Step 4（C9）。

### 8.4 System（系统）—— **预留**

- 条件字段路径已冻结：`payload.command`（事件契约 C7）。
- 具体规则**本步不冻结**。

---

## 九、未冻结事项

以下项目**显式挂起**，**禁止在 Step 3.1 实现中自行决定**：

| # | 项目 | 挂起原因 | 后续处理 |
|---|------|----------|----------|
| **O1** | `ActionCommand.priority` 是否传递 | 消费者是 Action Engine | **Step 4** |
| **O2** | 动作名称最终表（`heart` vs `heart_animation` 等） | `step2_event_schema.md` C9 | **Step 4** |
| **O3** | Engine 入口方法名 | 旧文档（`system_architecture.md:264`）用 `process`；须与契约统一后再定，**不得长期并存两个入口名**（参照 Step 2.3-A 教训） | **Step 3.1 实现步** |
| **O4** | `payload.like_count` 单事件 / 累计语义 | 事件契约未明示 | 真实平台接入前（Phase 3） |

---

## 十、禁止项

InteractionEngine **不允许**：

- ❌ 创建 `Event`（唯一构造点是 Event Gateway，见 `PROJECT_RULES.md` §十四「事件入口边界」）
- ❌ 调用 Adapter
- ❌ 读取平台字段（只认识事件的 4 个顶层字段与 `payload` 内的契约字段）
- ❌ 播放资源
- ❌ 操作数据库
- ❌ 读取文件 / 解析 JSON（属 RuleLoader）

本 Step（3.0-B）**不允许**：创建 `InteractionEngine`、创建 `RuleLoader`、创建 `rules.json`、创建 `ActionCommand` 类、修改 `backend` 代码。

---

## 十一、变更管理

本文档冻结后：

- **`ActionCommand` 最小结构**、**Rule Schema 字段集**、**操作符白名单**属**破坏性约束**——变更会使既有 `rules.json`、测试夹具与下游（Action Engine）失效。
- 任何变更必须走 `PROJECT_RULES.md` §七「需求变更管理」流程（`docs/change_request/需求名称.md`）。
- 变更后本文档**版本号递增**，并在第十二节记录变更历史。
- **禁止**在实现代码中「顺手」新增字段或操作符——那正是本契约要防止的方言漂移。

---

## 十二、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-19 | 首次冻结。基于 `step3_interaction_engine_decision.md` v1.0 产出。 |
