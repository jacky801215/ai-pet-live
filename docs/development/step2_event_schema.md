# Phase 1 Event Schema（事件契约冻结）

| 项 | 内容 |
|----|------|
| **文档版本** | v1.1 |
| **状态** | **FROZEN（已冻结）** |
| **冻结日期** | 2026-09-19（v1.0） |
| **修订日期** | 2026-09-19（v1.1） |
| **所属阶段** | Phase 1 / Step 2.0（v1.0）→ Step 2.1-A（v1.1） |
| **基线提交** | `f6b9eb7 docs: freeze event schema`（v1.1 起） |
| **唯一性** | 本文档是 Phase 1 Event Layer 的**唯一事件契约**。任何与之冲突的表述，以本文档为准。 |
| **本次修订** | 收窄 Phase 1 白名单为最小闭环集合（移除 `follow`）；明确 `user_name` 缺失与显式 `null` 的处理差异 |

---

## 一、Event Layer 目标

### 负责

事件层只做三件事：

1. **接收外部行为描述** —— 接收来自各来源的原始行为数据
2. **标准化事件格式** —— 把形态各异的输入归一化为统一事件
3. **提供给规则引擎消费** —— 输出稳定契约供下游读取

### 不负责

事件层**明确不做**以下事情。这些是其他层的职责，混入事件层会造成职责塌陷：

| 不做的事 | 归属层 |
|----------|--------|
| 播放动作 | Playback Manager |
| 判断情绪 | Interaction Engine |
| 平台连接 | Platform Adapter |
| 用户管理 | Data Manager |

### 核心问题

> **一个外部行为，如何被系统描述，并在后续模块之间稳定传递？**

本 Step 只解决这一条链路：

```
外部事件
   ↓
统一事件模型
   ↓
后续模块消费
```

---

## 二、核心事件结构（冻结）

### 2.1 冻结结构

```json
{
    "event_type": "",
    "user_id": "",
    "user_name": "",
    "payload": {}
}
```

**顶层字段仅此 4 个。** 新增、删除或重命名顶层字段属于**破坏性变更**，必须走 `change_request` 流程（见 `PROJECT_RULES.md` 第七节）。

### 2.2 字段语义

| 字段 | 类型 | 键是否必须存在 | 值可否为 null | 用途 |
|------|------|----------------|---------------|------|
| `event_type` | `string` | 是 | 否 | 描述发生的事件类别 |
| `user_id` | `string \| null` | 是 | **可** | 事件来源用户的唯一标识 |
| `user_name` | `string \| null` | 是 | **可** | 展示名称 |
| `payload` | `object` | 是 | 否 | 平台扩展字段载体 |

### 2.3 逐字段细则

#### `event_type`

- **类型**：`string`
- **用途**：描述发生的事件类别。
- **Phase 1 事件类型（最小闭环集合）**：

| event_type | 语义 | Phase 1 是否配触发规则 |
|------------|------|------------------------|
| `gift` | 赠送礼物 | ✅ |
| `comment` | 发送评论 | ✅ |
| `like` | 点赞 | ✅ |
| `system` | 系统事件 | ✅（仅 startup 类） |

> **注意**：本节只定义**语义**，不实现平台接入。任何平台 SDK、协议解析、连接管理均不在事件层范围内。

**「最小闭环集合」原则**：Phase 1 的 `event_type` 白名单**只包含验证互动闭环所必需的事件类型**，不提前扩展平台事件全集。

- **不追求收全**：平台额外事件（例如 `follow`、`share` 等）**当前不属于**统一事件契约。理由：Phase 1 的验证命题是「一个标准事件能否驱动完整宠物反馈」。增加不触发任何动作的事件类型，不会让该命题更成立，只会多出一条永远走不通的代码路径。此外，「真实存在就应收录」这一理由**没有边界**——进场、连击、分享、加粉丝团等同理，会无限扩张，与 MVP 优先原则直接抵触。
- **扩展有路径**：平台额外事件**必须经过 Change Request** 后方可进入统一事件契约（见第十节）。扩展的正确时点是 Phase 3——那时才有真实平台的原始事件样本可作为收录依据。

> **v1.1 变更提示**：v1.0 曾采用「事件层收全、规则层收窄」原则，将 `follow` 纳入白名单。该裁决已在 v1.1 **撤销**，理由见 6.5 节。

#### `user_id`

- **类型**：`string | null`
- **用途**：事件来源用户唯一标识。
- **允许为 null 的两种情形**：
  - **匿名事件** —— 来源平台不提供用户标识
  - **系统事件** —— 事件不来自任何用户（如 `system`）
- **强制约束**：**禁止用常量填充代替 null。**
  例：`user_id` 缺失时**不得**补 `"anonymous"`。
  **原因**：所有匿名用户若共享同一个常量，Data Manager 统计独立用户数时会把 N 个匿名用户坍缩为 1 个，产生**系统性数据失真**。这是数据污染，不是便利。

#### `user_name`

- **类型**：`string | null`
- **用途**：展示名称。
- **强约束**：**不能作为唯一身份依据。**
  昵称可重复、可修改、可为空。任何身份判定、去重、限流逻辑只允许使用 `user_id`。使用 `user_name` 做身份判定属于缺陷。
- **缺失与显式 null 的处理规则**（v1.1 明确）：

| 输入 | 处理 | 用途 |
|------|------|------|
| 字段缺失 | 补 `""` | **字段存在性保证** —— 展示层可直接取值渲染，无需判空 |
| 显式 `null` | **保留 `null`** | **无用户事件** —— 如 `system`，表示「确实没有用户」，而非「不知道昵称」 |

  两者语义不同，因此**不得互相替换**：不得把缺失补成 `null`，也不得把显式 `null` 改写为 `""`。

#### `payload`

- **类型**：`object`
- **用途**：平台扩展字段载体。
- **规则**：平台特有字段**必须**进入 `payload`。
- **禁止**：把平台字段提升到顶层。

### 2.4 契约的作用对象（关键约定）

本节澄清一个容易误读的点——**契约约束的是「统一事件」，不是「原始事件」**。

| 阶段 | 数据形态 | 约束强度 |
|------|----------|----------|
| Adapter / Simulator 产出前 | **原始事件** | 允许缺字段。Adapter 负责补齐 |
| Event Gateway 输出后 | **统一事件** | **4 个键必须全部存在且类型正确** |

由此得出的归一化责任划分：

- **原始事件缺 `user_id`** → Adapter 归一化时补 `null`（不得补常量）
- **原始事件缺 `user_name`** → Adapter 归一化时补 `""`（字段存在性保证）
- **原始事件缺 `payload`** → Adapter 归一化时补 `{}`
- **统一事件中 4 键任一缺失** → 属于缺陷，由校验层拒绝
- **显式传入 `payload: null`** → **拒绝**，不静默修正为 `{}`

**「缺失」与「显式 null」必须区分处理**：

| 情形 | 含义 | 处理 |
|------|------|------|
| 字段缺失 | 调用方未提供，可能是设计如此 | 补默认值（`user_id`→`null`／`user_name`→`""`／`payload`→`{}`） |
| 显式传 `payload: null` | 调用方明确提供了**非法类型** | **拒绝**，暴露上游缺陷 |
| 显式传 `user_id: null`／`user_name: null` | 调用方明确表示**无用户** | **合法，保留 `null`** |

静默修正显式 null 会掩盖上游 bug，使问题在更远处以更难排查的形态出现。注意区分：`user_id` / `user_name` 的 `null` 是**合法契约形态**，`payload` 的 `null` 是**非法类型**——前者表示「无用户」，后者表示「桶缺失」，语义完全不同。

---

## 三、Schema 示例

以下示例均为**统一事件**（Gateway 输出形态），可直接用于单元测试夹具。

### 3.1 礼物事件

```json
{
    "event_type": "gift",
    "user_id": "u1001",
    "user_name": "Jack",
    "payload": {
        "gift_name": "flower",
        "gift_count": 1,
        "platform": "simulator"
    }
}
```

> **字段命名裁决**：礼物数量字段取 **`gift_count`**，非 `count`。理由见第六节 C2。

### 3.2 评论事件

```json
{
    "event_type": "comment",
    "user_id": "u2001",
    "user_name": "Amy",
    "payload": {
        "content": "hello",
        "platform": "simulator"
    }
}
```

> **字段命名裁决**：评论文本字段取 **`content`**，非 `text`。理由见第六节 C1。

### 3.3 点赞事件

```json
{
    "event_type": "like",
    "user_id": "u3001",
    "user_name": "小明",
    "payload": {
        "like_count": 5,
        "platform": "simulator"
    }
}
```

### 3.4 系统事件

```json
{
    "event_type": "system",
    "user_id": null,
    "user_name": null,
    "payload": {
        "command": "startup"
    }
}
```

> **字段命名裁决**：系统命令字段取 **`command`**，非 `action`。理由见第六节 C7。

### 3.5 匿名事件

```json
{
    "event_type": "like",
    "user_id": null,
    "user_name": null,
    "payload": {
        "like_count": 1,
        "platform": "simulator"
    }
}
```

---

## 四、扩展原则

### 4.1 顶层字段稳定原则

**顶层字段**：

```
event_type
user_id
user_name
payload
```

- 这 4 个字段在 **Phase 1 之后不随平台变化**。
- 接入抖音、YY 等任何平台，**不得**增加、删除或重命名顶层字段。
- 顶层字段变更 = **破坏性变更**，必须走 `change_request` 流程并同步本文档版本号。

### 4.2 payload 开放原则

**允许**：

```json
{
    "payload": {
        "platform_specific_data": "..."
    }
}
```

各平台特有字段一律放入 `payload`，包括但不限于：等级、粉丝牌、进场特效、连击计数、平台内礼物 ID。

**禁止**：

```json
{
    "event_type": "comment",
    "user_id": "u1",
    "user_name": "A",
    "payload": {},
    "douyin_user_level": 5
}
```

`douyin_user_level` 被提升到顶层 —— **必须拒绝**。

**为什么这是硬约束**：平台字段上浮顶层，会让顶层字段集随平台数量线性膨胀，最终使「统一事件」退化为「所有平台字段的并集」。到那时核心业务无法避免平台判断分支，Adapter 隔离设计随之失效。**这是本项目架构防线中最靠外的一环，一旦破口后面全部失守。**

### 4.3 payload 字段命名规范

由第六节裁决推导出的通用规则：

- payload 字段名必须**领域化**，避免与顶层概念或通用词撞名
- 禁止使用已被项目占用的词作为 payload 字段名（如 `action` 已表示「动作名」）
- 禁止使用语义过泛的词（如 `count`、`data`、`value`）而不加领域前缀

### 4.4 payload 约定字段

以下字段跨事件类型通用，约定如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `platform` | `string` | 来源标识，如 `simulator` / `douyin` / `yy`。用于溯源，**禁止**用于业务分支判断 |
| `raw` | `object` | 平台原始报文留存，可选。用于问题排查，**禁止**业务逻辑依赖其内部结构 |

---

## 五、校验规则

### 5.1 必填项

| 字段 | 要求 |
|------|------|
| `event_type` | 键必须存在，且为非空 `string` |
| `payload` | 键必须存在，且为 `object`（**显式 `null` 视为非法**） |

### 5.2 可空项

| 字段 | 要求 |
|------|------|
| `user_id` | 键必须存在；值可为 `null` 或 `string`。缺失时补 `null` |
| `user_name` | 键必须存在；值可为 `null` 或 `string`。缺失时补 `""`；显式 `null` 保留 |

### 5.3 非法情形与处理

| # | 情形 | 判定 | 处理 |
|---|------|------|------|
| 1 | `event_type` 缺失 | 非法 | 拒绝 |
| 2 | `event_type` 为空串 | 非法 | 拒绝 |
| 3 | `event_type` 非 `string` | 非法 | 拒绝 |
| 4 | `event_type` 不在白名单 | 非法 | 拒绝 + 记录日志 |
| 5 | `payload` 缺失 | 非法（统一事件层面） | 拒绝 |
| 6 | `payload` 显式 `null` | 非法 | 拒绝 |
| 7 | `payload` 非 `object` | 非法 | 拒绝 |
| 8 | `user_id` 类型非 `string` / `null` | 非法 | 拒绝 |
| 9 | `user_name` 类型非 `string` / `null` | 非法 | 拒绝 |
| 10 | 顶层出现 4 字段之外的扩展字段 | 非法 | **拒绝** |
| 11 | 平台特有字段出现在顶层 | 非法 | **拒绝** |

> 第 10、11 条是 4.2 节「禁止平台字段上浮」的**执行手段**。没有校验兜底的原则等于没有原则。

> **Phase 1 白名单**（情形 4 的判定依据）：`gift` / `comment` / `like` / `system`。**不含 `follow`**（v1.1 裁决，见 6.5 节）。

### 5.4 校验示例

**应拒绝** —— 指令给定的非法样例：

```json
{
    "event_type": "",
    "payload": null
}
```

判定依据：`event_type` 为空串（命中情形 2）；`payload` 为显式 `null`（命中情形 6）。**两处均非法，拒绝。**

**应拒绝** —— 平台字段上浮：

```json
{
    "event_type": "gift",
    "user_id": "u1",
    "user_name": "A",
    "payload": {},
    "douyin_user_level": 5
}
```

判定依据：顶层出现第 5 个字段（命中情形 10 + 11）。

**应拒绝** —— `event_type` 不在 Phase 1 白名单：

```json
{
    "event_type": "follow",
    "user_id": "u4001",
    "user_name": "路人甲",
    "payload": { "platform": "simulator" }
}
```

判定依据：`follow` 不在白名单（命中情形 4）。Phase 1 白名单为 `gift` / `comment` / `like` / `system`。平台额外事件需经 Change Request 进入契约后方为合法。

**应通过** —— 系统事件，值为 null 但键存在：

```json
{
    "event_type": "system",
    "user_id": null,
    "user_name": null,
    "payload": { "command": "startup" }
}
```

> 注意：拒绝的是「键缺失」或「非法类型」，**不是** `null` 值本身。`user_id: null` 是合法契约形态。

### 5.5 校验失败的行为约定

- **拒绝 = 不向下游转发**。非法事件不得进入 Interaction Engine。
- 拒绝必须**记录日志**（级别、原因、原始报文），不得静默丢弃。
- 单个非法事件**不得导致进程崩溃**。网关对非法输入必须容错。

---

## 六、与既有文档的冲突与裁决

### 6.1 为什么必须有这一节

冻结前扫描发现：`docs/development/phase1_design.md`（Step 1 产出）与 `docs/architecture/system_architecture.md`（Step 1 产出）**在本 Step 之前已经定义过统一事件格式**，且与 Step 2.0 指令存在多处实质冲突。

若不作裁决直接写新文档，会产生**第三套方言**。后果不是报错，而是**静默失效**：Step 2.1 按本文档写出 Event Model（字段名 `content`），Step 2.2 按指令示例写出 `rules.json`（字段名 `text`），规则匹配永远不命中，而系统不报任何错误——表现为「评论没反应」，排查成本极高。

**因此本节是冻结动作的必要组成部分，不是附加说明。**

### 6.2 裁决表

| 编号 | 冲突点 | 既有文档 | Step 2.0 指令 | **裁决** | 依据 |
|------|--------|----------|---------------|----------|------|
| **C1** | 评论文本字段名 | `payload.content`<br>`phase1_design.md:77,169`<br>`system_architecture.md:217` | `payload.text` | **`content`** | 两份既有文档一致；且 `rules.json` 规则已绑定 `payload.content`（`phase1_design.md:169`）。`text` 语义更泛，未来出现「弹幕原文 / 翻译文本」时无法区分 |
| **C2** | 礼物数量字段名 | `payload.gift_count`<br>`phase1_design.md:76,106`<br>`system_architecture.md:216` | `payload.count` | **`gift_count`** | 同上，三处一致。`count` 过泛，会占用通用词位，稀释 payload 命名空间 |
| **C3** | 顶层 `timestamp` | 存在，网关缺失时补当前时间<br>`phase1_design.md:109,120`<br>`system_architecture.md:208` | 未列入 4 个冻结字段 | **Phase 1 冻结为 4 字段** | `payload` 的定义是「平台扩展字段桶」，而时间戳是**跨平台稳定语义**，按 4.2 节规则它也不该进 `payload`。共 4 处候选位（顶层 / payload / 不要 / 显式扩展）中，顶层会破坏指令冻结的字段集，payload 违反其自身语义定义。Demo 阶段事件发生时刻 ≈ 处理时刻，区分无收益。DB 已有 `created_at` 覆盖 |
| **C4** | `user_id` 缺失处理 | 补默认值 `"anonymous"`<br>`phase1_design.md:118` | 允许 `null` | **保留 `null`，禁止补常量** | 补同一常量会让所有匿名用户坍缩为 1 个 `user_id`，独立用户数统计**系统性失真**。这是数据污染，不是便利。指令的 `null` 更正确 |
| **C5** | `payload` 缺失 / 为 null | 可空，默认 `{}`，补默认值<br>`phase1_design.md:119` | `payload: null` 应拒绝 | **区分二者**：字段缺失→补 `{}`；显式 `null`→拒绝 | 缺失 = 调用方未提供；显式 `null` = 调用方明确给了非法类型。静默修正后者会掩盖上游 bug。见 2.4 节 |
| **C6** | `follow` 是否在 Phase 1 白名单 | `phase1_design.md:122` 明确排除<br>`system_architecture.md:219` 包含 | 包含 | ~~事件层收全，规则层收窄~~<br>→ **不含 `follow`**（v1.1） | **v1.0 裁决已撤销。** 原理由「`follow` 是真实直播行为、事件层应收全」不成立：该理由没有边界，会无差别要求收录进场/连击/分享/加粉丝团，与 MVP 优先原则抵触。`phase1_design.md:122` 原本就是对的。详见 6.5 节 |
| **C7** | `system` 载荷字段名 | `payload.action`<br>`system_architecture.md:220` | `payload.command` | **`command`** | `action` 在本项目已被「动作名」占用（`"action": "heart"`）。再用 `action` 表示系统命令会造成**同名异义**，属真实语义碰撞 |
| **C8** | `like` 触发阈值 | `3`（`phase1_design.md:150`）<br>`10`（`system_architecture.md:256`） | 不在本步范围 | **挂起** | 属 Interaction Engine 规则层，Step 3 处理 |
| **C9** | 动作命名 | `heart` / `special`<br>`phase1_design.md:144,145` | `heart_animation` / `special_animation`<br>`system_architecture.md:252,253` | **挂起** | 属 Action Engine 动作字典，Step 4 处理 |

### 6.3 裁决原则说明

所有裁决遵循同一优先级：

1. **消除歧义优先于保持原样** —— 宁可显式裁决，不留两可
2. **数据正确性优先于便利性** —— C4 是典型：补常量更省事，但污染数据
3. **单一事实来源优先于就近修改** —— 冲突集中在本文档裁决，不在多处散改
4. **不扩大本 Step 范围** —— 属其他层的冲突（C8/C9）只记录，不裁决

### 6.4 待对齐清单（本次不允许修改，留给后续 Step）

本 Step 的执行范围**仅允许**新增本文档、修改 `PROJECT_RULES.md`。以下不一致**已知且有意保留**，必须在后续 Step 处理：

| # | 位置 | 不一致内容 | 建议处理 Step |
|---|------|------------|---------------|
| A1 | `phase1_design.md:118` | `user_id` 补 `"anonymous"` | Step 2.1 同步修正 |
| A2 | `phase1_design.md:119` | `payload` 可空默认 `{}`（未区分显式 null） | Step 2.1 同步修正 |
| A3 | `phase1_design.md:109,120`<br>`system_architecture.md:208` | 顶层 `timestamp` 字段 | Step 2.1 同步修正 |
| A4 | `phase1_design.md:77,169` | `payload.content` —— **与裁决一致**，无需修改 | 无需处理 |
| A5 | `phase1_design.md:122` | 「Phase 1 不含 follow」—— **与 v1.1 裁决一致，无需澄清**（v1.0 曾误判为需改为「规则层不含」，已撤销） | Step 2.1 仅需补充一句：Phase 1 事件白名单不包含 `follow`；后续平台事件扩展需通过 Change Request |
| A6 | `phase1_design.md:150` vs `system_architecture.md:256` | `like` 阈值 3 / 10 | Step 3 |
| A7 | `phase1_design.md:144` vs `system_architecture.md:252` | 动作命名 | Step 4 |
| A8 | `phase1_design.md:483` | 事件表 `event_type` 注释只列 `gift/comment/like` | Step 2.x 数据库设计时同步 |

> **处理原则**：A1–A3、A5 将在 Step 2.1 以「按 `step2_event_schema.md` 对齐」为名修正，届时**必须**在提交信息中说明，不得无声改写既有设计文档。

### 6.5 C6 裁决撤销记录（v1.1）

**撤销对象**：v1.0 的 C6 裁决 —— 「事件层收全、规则层收窄」，将 `follow` 纳入 Phase 1 白名单。

**撤销理由**：

1. **原论证没有边界。** 原理由是「`follow` 是真实直播行为，事件层应标准化外部行为，故应收全」。但真实存在的直播行为不止 `follow`——进场、连击、分享、加粉丝团、直播间累计点赞……按同一逻辑都应收录。**一个会无限扩张的原则不是原则，是范围失控。**
2. **与 MVP 优先原则直接抵触。** Phase 1 的验证命题是「一个标准事件能否驱动完整宠物反馈」。增加一个**永不触发任何动作**的事件类型，不会让该命题更成立，只会多出一条永远走不通的代码路径和一条测试。
3. **扩展时点判断错误。** 「收全」的正确时点是 **Phase 3**——那时手里才有真实平台的原始事件样本，才知道应当收录哪些类型。Phase 1 若「收全」，收的是**猜想的集合**，价值近似为零。
4. **`phase1_design.md:122` 原本就是对的。** v1.0 把它标为「待对齐」，属误判。

**新裁决**：Phase 1 `event_type` 白名单为 `gift` / `comment` / `like` / `system`，即**最小闭环集合**。平台额外事件必须经 Change Request 进入契约。

**影响**：

- `system_architecture.md:219` 的事件类型枚举包含 `follow` —— 该枚举描述的是**架构长期形态**，非 Phase 1 白名单，**不构成冲突**，无需修改。
- `system_architecture.md:257` 的 `follow → heart_animation` 规则映射 —— 属 Phase 3+ 内容，不在 Phase 1 范围。
- 本契约 §3 已删除「关注事件」示例；§5.4 新增 `follow` 应拒绝的校验示例。

---

## 七、与后续模块关系

### 7.1 数据流位置

```
Platform Adapter
      ↓
 Event Gateway
      ↓
 Event Schema          ← Step 2.0 冻结的就是这一层
      ↓
Interaction Engine
      ↓
 Action Engine
```

### 7.2 一个必须澄清的读法

**Event Schema 不是一个运行时模块，它是模块间传递的数据契约。**

上图中它出现在管线上，容易误读为「需要实现一个 Schema 模块」。实际含义是：

- **Event Gateway 是模块** —— 它会接收、校验、归一化、转发
- **Event Schema 是契约** —— 它约束 Gateway 的输出形态，本身没有代码实体

因此 Step 2.1 实现 Event Model 时，产出的是**数据结构定义**（`backend/app/models/`），不是「Schema 处理器」。把契约误实现为模块，会凭空多出一层无职责的中间件。

### 7.3 各模块与契约的关系

| 模块 | 与契约的关系 | 职责边界 |
|------|--------------|----------|
| Platform Adapter | 产出**原始事件**，负责归一化补齐 | 平台差异只允许存在于 Adapter 内部 |
| Event Gateway | 产出**统一事件**，强制执行校验规则 | 只做格式校验与归一化，不做业务判断 |
| Event Schema | **契约本身**，无代码实体 | 被 Gateway 引用，被 Engine 消费 |
| Interaction Engine | 消费统一事件，输出动作指令 | 只决定「该播什么」，不管「怎么播」 |
| Action Engine | 消费动作指令 | 不管事件从哪来 |

### 7.4 边界声明

**Step 2.0 只冻结中间契约。**

本次冻结：

- ✅ 事件顶层结构
- ✅ 字段语义与类型
- ✅ 扩展原则
- ✅ 校验规则
- ✅ 模块边界

本次**未**冻结（留给后续 Step）：

- ❌ Event Model 的代码实现（Step 2.1）
- ❌ Event Gateway 的校验器实现（Step 2.2）
- ❌ 各平台字段 → `payload` 的映射表（Phase 3）
- ❌ 规则表结构与动作字典（Step 3 / 4）

---

## 八、设计禁止项

**Phase 1 Event Layer 不包含：**

- ❌ WebSocket
- ❌ 抖音 SDK
- ❌ YY SDK
- ❌ 消息队列
- ❌ 用户数据库
- ❌ 播放控制

### 为什么明确列出

这些技术每一项都「看起来很合理」，且都能找到引入理由。但它们全部属于**其他阶段或其他层**：

| 禁止项 | 归属 | 引入后果 |
|--------|------|----------|
| WebSocket | Phase 1 前端用 HTTP 轮询/请求即可 | 提前引入实时通道，复杂度上升但 Demo 无收益 |
| 抖音 SDK | Phase 4 | 违反平台接入原则，且当前无授权 |
| YY SDK | Phase 4 | 同上 |
| 消息队列 | 当前规模不需要 | 单机 Demo 引入 MQ 是纯粹的复杂度负担 |
| 用户数据库 | Data Manager | 事件层管用户 = 职责塌陷 |
| 播放控制 | Playback Manager | 事件层管播放 = 破坏分层 |

**本清单的作用**：在实现阶段抵挡「顺手加一下」的冲动。任何对上述项的引入，必须走 `change_request` 流程，不得在 Step 2.x 内顺手实现。

---

## 九、验收标准

| 项 | 要求 | 状态 |
|----|------|------|
| Event 顶层结构 | 已冻结（4 字段） | ✅ |
| 字段语义 | 已定义（类型 / 可空性 / 用途 / 约束 / 缺失与 null 处理） | ✅ |
| 事件类型白名单 | 已冻结为最小闭环集合（4 类：`gift`/`comment`/`like`/`system`） | ✅ |
| 示例事件 | ≥ 3 个（实际 5 个） | ✅ |
| payload 扩展策略 | 已定义（开放原则 + 命名规范 + 约定字段） | ✅ |
| 校验规则 | 已定义（必填 / 可空 / 11 条非法情形 / 4 个示例） | ✅ |
| 后续模块边界 | 已定义（含 7.2 节契约 vs 模块澄清） | ✅ |
| 代码变化 | 0 | ✅ |
| 既有文档冲突 | 已裁决（C1–C7，其中 C6 于 v1.1 撤销并重裁）并列出待对齐清单 | ✅ |
| 文档版本 | v1.1（Step 2.1-A 修订） | ✅ |

---

## 十、变更管理

本文档已冻结。任何修改必须：

1. 创建 `docs/change_request/<需求名称>.md`
2. 说明：改什么、为什么必须改、影响哪些下游模块
3. 更新本文档版本号（当前 v1.1 → 下次 v1.2；版本号在头部表格与本节变更记录中同步）
4. 在文档末尾追加变更记录

**事件类型白名单的扩展**同属契约修改，必须走上述流程。禁止在实现 Step 中顺手新增 `event_type`。

### 变更记录

| 版本 | 日期 | 变更内容 | 触发原因 |
|------|------|----------|----------|
| v1.0 | 2026-09-19 | 初始冻结：顶层 4 字段、字段语义、扩展原则、校验规则、模块边界；裁决 C1–C9 | Step 2.0 Event Schema Freeze |
| v1.1 | 2026-09-19 | ①`event_type` 白名单收窄为最小闭环集合，**移除 `follow`**（C6 撤销并重裁，新增 6.5 节）；②明确 `user_name` 缺失补 `""`、显式 `null` 保留（§2.3 / §2.4 / §5.2）；③删除「关注事件」示例（原 §3.4），示例数 6 → 5；④新增 `follow` 应拒绝的校验示例（§5.4）；⑤修正 A5 待对齐项 | Step 2.1-A 冲突裁决与契约修订 |
