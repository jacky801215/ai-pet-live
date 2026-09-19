# Phase 1 Event Gateway 契约（入口边界冻结）

| 项 | 内容 |
|----|------|
| **文档版本** | v1.0 |
| **状态** | **FROZEN（已冻结）** |
| **冻结日期** | 2026-09-19 |
| **所属阶段** | Phase 1 / Step 2.2 |
| **基线提交** | `607435c feat: implement event model` |
| **上游契约** | `docs/development/step2_event_schema.md` **v1.1** |
| **本文档作用** | 冻结 Event Gateway 的**职责边界**与**接口契约**。本文档不实现代码。 |
| **唯一性** | 与本文档冲突的 Gateway 接口描述，一律以本文档为准。 |

---

## 一、Gateway 定位

Event Gateway 是**原始事件进入核心业务的入口边界**：

```
raw event
   ↓
EventGateway        ← 本 Step 冻结的边界
   ↓
Event
   ↓
Interaction Engine
```

### 它是什么

- **一个转换器**：把「形态不确定的原始 dict」变成「形态确定的统一 `Event`」
- **一道校验闸**：调用 Event Model 的校验，非法输入在此止步
- **一个错误翻译点**：把模型层异常原样透传为统一错误结构

### 它不是什么

Gateway **不是**一个"薄壳转发器"，也**不是**一个业务层。它的存在意义只有一个：

> **让核心业务层永远收不到一个未校验、未归一化的原始事件。**

如果去掉它，`Event.from_dict()` 的调用会散落在 Interaction Engine、Action Engine、API 层——校验规则就有多份，必然漂移。Gateway 的价值在于把这条**唯一性**固定下来。

---

## 二、输入输出冻结

### 2.1 签名

| 项 | 冻结值 |
|----|--------|
| **输入** | `dict`（原始事件字典） |
| **输出** | `Event`（统一事件对象） |

```python
def normalize(raw_event: dict) -> Event: ...
```

**输入是 `dict`，不是 `Event`，不是平台对象，不是 `Adapter` 实例。**

### 2.2 示例

输入：

```json
{
    "event_type": "comment",
    "user_id": "1001",
    "user_name": "jack",
    "payload": {"content": "hello"}
}
```

输出：

```python
Event(
    event_type="comment",
    user_id="1001",
    user_name="jack",
    payload={"content": "hello"},
)
```

### 2.3 三种输入形态的预期结果

| 输入 | 结果 |
|------|------|
| 合法 dict | 返回 `Event`，且 `event.to_dict()` 与输入语义一致（缺失字段按契约补齐） |
| 非法 dict（如 `follow`、`payload: null`、顶层多余字段） | **抛异常**，不返回 `None`，不返回"错误事件对象" |
| 非 dict（`list` / `str` / `None`） | **抛异常**（`EVENT_SCHEMA_INVALID`） |

**冻结要点**：失败一律以**异常**表达，不得用 `None` 或哨兵值表达失败。理由见第四节。

---

## 三、职责

### 3.1 允许（Gateway 只做这四件事）

| # | 职责 | 说明 |
|---|------|------|
| 1 | **接收统一事件输入** | 接收 `dict`，不做平台识别 |
| 2 | **调用 Event Model 校验** | 唯一动作是调用 `Event.from_dict()` |
| 3 | **返回标准 `Event`** | 原样返回模型层产出的对象 |
| 4 | **转换异常为统一错误** | 透传 `code` / `message` / `context` |

### 3.2 不允许

| # | 禁止行为 | 为什么 |
|---|----------|--------|
| 1 | 判断评论规则 | 规则匹配属 Interaction Engine |
| 2 | 执行动作 | 动作执行属 Action Engine |
| 3 | 调用播放器 | 播放控制属 Playback Manager |
| 4 | 保存数据库 | 数据落库属 Data Manager |
| 5 | 访问平台 API | 平台连接属 Platform Adapter |

### 3.3 关键约束：**禁止在 Gateway 重复实现字段补齐逻辑**

这是本契约中最容易被违反、后果最隐蔽的一条。

字段补齐（`payload` 缺失 → `{}`、`user_name` 缺失 → `""`、`user_id` 缺失 → `None`）**已经由 `Event.from_dict()` 实现**。

Gateway **必须**写成：

```python
def normalize(raw_event: dict) -> Event:
    return Event.from_dict(raw_event)
```

**不得**写成：

```python
# ❌ 禁止：在 Gateway 里再写一遍补齐与分支
def normalize(raw_event):
    data = dict(raw_event)
    data.setdefault("payload", {})
    data.setdefault("user_name", "")
    if "user_id" not in data:
        data["user_id"] = None
    # ... 再手动挑字段构造 Event
```

**为什么这是硬约束**：一旦补齐逻辑出现两份，两份就会漂移。而漂移的表现形式是——**Gateway 通过的事件，Interaction Engine 却认为是非法的**；或者反过来，某条路径下的 `Event` 从未被校验过。这类缺陷不报错，只会让"某些评论没反应"，排查成本极高。

> 「单一事实来源」优先于「就近方便」。补齐规则的唯一位置是 `backend/app/models/event.py`。

---

## 四、错误传播规则（冻结）

### 4.1 异常集合

Gateway 只可能出现以下三种异常，**全部来自 Event Model**：

| code | 触发面 | 来源 |
|------|--------|------|
| `EVENT_TYPE_INVALID` | `event_type` 缺失 / 空 / 非 `str` / 不在白名单 | `Event.from_dict()` |
| `EVENT_PAYLOAD_INVALID` | `payload` 非 `object`（含显式 `null`）/ 事件级必填缺失 / 含禁用字段 | `Event.from_dict()` |
| `EVENT_SCHEMA_INVALID` | 顶层多余字段 / `user_id`、`user_name` 类型错误 / 入参非 mapping | `Event.from_dict()` |

三者均继承 `PetLiveError`，输出结构统一为：

```
{ "code": ..., "message": ..., "context": ... }
```

### 4.2 传播规则（冻结）

1. **保持原 `code`** —— Gateway **不得**改写、包装或映射为别的 `code`。
2. **禁止创建新异常** —— Gateway **不得**定义任何新异常类，也不得引入除此之外的错误码。
3. **禁止吞掉异常** —— 不得 `try/except` 后返回 `None` 或空 `Event`。
4. **禁止改变异常类型** —— 不得把 `EventTypeInvalidError` 转成 `InvalidRequestError` 之类的通用错误。

**理由**：调用方（Interaction Engine / API 层）需要**按 `code` 分流**。例如 `EVENT_TYPE_INVALID` 是"上游给错了"（应记日志并拒绝），`EVENT_PAYLOAD_INVALID` 是"上游字段名用错"（应告警并检查 Adapter）。一旦 Gateway 把两者都压成 `INVALID_REQUEST`，这个区分能力就没了。

### 4.3 一项可选包装（需在 Step 2.3 明确取舍）

若未来需要给异常补充网关上下文（如收到时间、来源适配器名），**允许**以 `context` 追加字段的方式补充，但：

- `code` **不得**改变
- 异常**类型**不得改变
- 不得为此新增异常类

Phase 1 **默认不补**（上下文为零）。保持 Gateway 无状态。

---

## 五、生命周期与状态约定（冻结）

| 项 | 约定 |
|----|------|
| **状态** | **无状态（stateless）**。不缓存、不计数、不留上次输入 |
| **实例** | 单例或每请求实例均可 —— 因为无状态，两者行为一致 |
| **构造** | `__init__` **禁止**任何 IO（文件 / 数据库 / 网络 / 环境探测） |
| **线程** | 不创建线程、不定时器、不启后台任务 |
| **连接** | 不持有任何长连接（WebSocket / 平台 SDK / 消息队列） |
| **幂等性** | 同一输入多次调用，结果必须完全一致 |

### 为什么冻结这些

这些都是"顺手加一下"就再也拿不掉的复杂度：一旦 Gateway 带了缓存，就必须回答缓存失效与并发安全问题；一旦它起了线程，就必须回答关闭顺序问题。**Phase 1 的验证命题是"互动链路是否成立"，不是"网关性能"**，这些都无收益。

`__init__` 不做 IO 还有一条独立理由：**测试必须能在不启任何外部依赖的前提下构造 Gateway**。带 IO 的构造函数会让每个测试都要搭环境。

---

## 六、与 Adapter 的边界

两个环节，**不要合并**：

```
Adapter：平台事件 → 统一 dict
Gateway：统一 dict → Event
```

| 边界 | Adapter | Gateway |
|------|---------|---------|
| **输入** | 平台原始报文（抖音/YY 结构） | 统一 dict（平台无关） |
| **输出** | 统一 dict | `Event` |
| **平台知识** | **有**（且只在这里有） | **无** |
| **知道 `Event` 类吗** | 否 | 是 |
| **做校验吗** | 否（产出合法 dict 即可） | **是** |

### 冻结规则

1. **Gateway 不持有 Adapter 引用。** 禁止 `register_adapter(adapter)` 这类接口 —— 一旦持有，Gateway 就必须回答"用哪个 Adapter 解析"，也就等于它开始做平台识别。
2. **Gateway 不认识平台名。** 不得出现 `if platform == "douyin"` 之类的分支。
3. **Adapter 不认识 `Event`。** Adapter 只产出符合契约字段的 dict；`Event` 的构造是 Gateway 的事。
4. **合并的后果**：若两者合一，平台差异会与核心业务绑定，新增平台必然修改核心代码——违反 `PROJECT_RULES.md` §十四「新增平台不得修改核心业务代码」。

> 注：Phase 1 的 `SimulatorAdapter` **不在本 Step 范围**。本契约只冻结"dict 从哪来"与"Event 由谁造"的分界。

---

## 七、与 Interaction Engine 的边界

### 7.1 Gateway 不知道的事

Gateway **不得**接触、读取或推断：

- `rules.json`
- `trigger`（触发条件）
- `action`（动作名）
- `cooldown`（冷却）

Gateway 对"这个事件该不该有反应"**完全无知**。它既不知道规则表存在，也不关心某个事件会不会命中。**一个永远不触发任何动作的事件（如 Phase 1 未配规则的输入），对 Gateway 而言与其它合法事件没有区别。**

### 7.2 Engine 不知道的事

Interaction Engine **不得**接触：

- 抖音字段（如 `douyin_user_level`）
- YY 字段
- 平台用户对象（等级 / 粉丝牌 / 进场特效等）

Engine 只认识 `Event` 的 4 个顶层字段与 `payload` 内的契约字段。**任何平台字段都必须已被 Adapter 收进 `payload`**，Engine 不区分它来自哪个平台。

### 7.3 边界一句话

> **Gateway 知道"事件合法吗"；Engine 知道"事件该做什么"。**
> 两者之间只传递 `Event`，不传递任何判断结果。

---

## 八、流程图

```
+---------------------------+
|        Platform           |   （Phase 1：不接入，仅保留位置）
+---------------------------+
              |
              v
+---------------------------+
|         Adapter           |   平台报文 -> 统一 dict
+---------------------------+   平台差异只允许存在于此
              |
              |  raw dict
              v
+---------------------------+
|      EventGateway         |   本 Step 冻结的边界
|   normalize(raw) -> Event |
+---------------------------+
              |                    |
              | 调用                | 失败时
              v                    v
+---------------------------+   +---------------------+
|       Event Model         |   |  PetLiveError       |
|     from_dict() 校验       |   |  code 原样透传       |
+---------------------------+   +---------------------+
              |
              |  Event
              v
+---------------------------+
|    Interaction Engine     |   规则匹配 -> 动作指令
+---------------------------+
              |
              v
+---------------------------+
|       Action Engine       |
+---------------------------+
```

**图中要点**：

- `raw dict` → `Event` 的转换**只发生在一个位置**（EventGateway）
- 失败路径**不进入** Interaction Engine（拒绝 = 不向下游转发，见 schema 契约 §5.5）
- 图下方的 Engine / Action 属后续 Step，本契约只冻结到 `Event` 为止

---

## 九、与既有文档的冲突与待对齐

### 9.1 冲突（本 Step 不修改既有文档，仅记录）

`docs/architecture/system_architecture.md:222-230` 定义了另一个版本的 Gateway 接口：

```python
# backend/app/gateway/event_gateway.py
class EventGateway:
    def register_adapter(self, adapter: PlatformAdapter) -> None
    def ingest(self, raw_event: dict) -> None        # 接收原始事件
    def normalize(self, raw_event: dict) -> dict     # 转换为统一格式
    def subscribe(self, handler: Callable) -> None   # 下游订阅
```

与本文档存在 **4 处冲突**：

| 编号 | 冲突点 | 既有文档 | 本文档 v1.0 | 依据 |
|------|--------|----------|-------------|------|
| **D1** | 模块路径 | `backend/app/gateway/event_gateway.py` | `backend/app/services/event_gateway.py` | `PROJECT_RULES.md` §三「分层约定（Backend）」只允许 `core / models / repositories / services / api / config`，且明确「事件网关层」实现为 `services/event_gateway.py`。Step 2.2 亦禁止创建 `gateway/` 目录 |
| **D2** | `normalize` 返回类型 | `-> dict` | **`-> Event`** | 返回 `dict` 等于放弃了类型约束——`dict` 无法表达"已校验"。Step 2.2 §四.2 冻结输出为 `Event` |
| **D3** | `register_adapter` | 持有 Adapter 引用 | **禁止** | 与第六节「不要合并」冲突：持有 Adapter 即意味着 Gateway 做平台识别 |
| **D4** | `ingest -> None` + `subscribe(handler)` | 推送（observer）模型 | **未冻结**（本文档只冻结返回值形态） | Step 2.2 §四.3 只要求"返回标准 Event"。推送模型会引入订阅者生命周期与线程安全议题，Phase 1 无收益 |

### 9.2 D4 的取舍说明

- **本文档冻结的**：`normalize(raw_event: dict) -> Event`，纯函数式，无副作用。
- **本文档未冻结的**：`ingest` / `subscribe` 这一层推送机制。
- **判断**：Phase 1 的调用方（Interaction Engine）与 Gateway **同进程且同步**，直接拿返回值即可；引入 observer 属于为不存在的场景付复杂度成本。
- **但这不是本 Step 能单方面决定的** —— 它改变了 Gateway 的对外形态。**Step 2.3 必须以本契约为准实现 `normalize`，若要额外提供 `ingest` / `subscribe`，须先在报告中说明理由，不得默默遵循 `system_architecture.md`。**

### 9.3 待对齐清单

| # | 位置 | 不一致内容 | 建议处理 |
|---|------|------------|----------|
| G1 | `system_architecture.md:224` | `backend/app/gateway/event_gateway.py` | 对齐为 `backend/app/services/event_gateway.py`（Step 2.3 或文档专项） |
| G2 | `system_architecture.md:228` | `normalize(...) -> dict` | 对齐为 `-> Event` |
| G3 | `system_architecture.md:226,229` | `register_adapter` / `subscribe` | 与 D3/D4 一并裁决后对齐 |
| G4 | `system_architecture.md:261` | `backend/app/engine/interaction_engine.py` | 同类路径问题，Step 3 一并对齐 |
| G5 | `phase1_design.md:122` | 白名单 `gift/comment/like`（无 `system`） | schema 契约 §6.4 A8 已记录，Step 2.x 数据库设计时同步 |
| G6 | `phase1_design.md:88-94` | Event Gateway 职责描述为"格式归一化与校验" | **与本契约一致**，无需修改 |

> **处理原则**：与 schema 契约 §6.4 相同 —— 后续 Step 修正既有文档时，**必须在提交信息中说明，不得无声改写**。

---

## 十、设计禁止项（Phase 1 明确不进入）

本 Step 及 Phase 1 的 Gateway 实现中**不得出现**：

- ❌ WebSocket
- ❌ 平台 Adapter 实现（抖音 / YY）
- ❌ `gateway/` 目录或 package
- ❌ FastAPI endpoint / 路由
- ❌ 消息队列
- ❌ 数据库访问
- ❌ 缓存层
- ❌ 订阅者注册机制（未冻结，见 D4）
- ❌ 定时任务 / 后台线程

### 为什么列出来

这些每一项都能找到"看起来很合理"的引入理由，但它们全部属于**其他阶段或其他层**：

| 禁止项 | 归属 | 引入后果 |
|--------|------|----------|
| WebSocket | Phase 4 | 提前引入实时通道，Demo 无收益 |
| 平台 Adapter | Phase 3/4 | 违反第六节边界，且当前无授权 |
| `gateway/` 目录 | —— | 违反 `PROJECT_RULES.md` §三 分层约定 |
| FastAPI endpoint | Step 2.3 之后的 API 层 | 路由与出入参校验属 `api/`，混入即破坏分层 |
| 数据库访问 | Data Manager | Gateway 落库 = 职责塌陷 |
| 缓存层 | —— | 破坏无状态约定（第五节） |

**本清单的作用**：在实现阶段抵挡"顺手加一下"。任何引入必须走 `change_request`，不得在 Step 2.3 内顺手实现。

---

## 十一、验收标准

| 项 | 要求 | 状态 |
|----|------|------|
| Gateway 定位 | 已冻结（入口边界，非业务层） | ✅ |
| 输入输出 | 已冻结（`dict` → `Event`） | ✅ |
| 职责 | 已冻结（允许 4 项 / 不允许 5 项） | ✅ |
| 错误传播 | 已冻结（保留原 `code`，禁止新建异常） | ✅ |
| 生命周期 | 已冻结（无状态、无 IO 构造、无线程） | ✅ |
| Adapter 边界 | 已冻结（不合并、不持有、不认识平台） | ✅ |
| Engine 边界 | 已冻结（Gateway 不知规则 / Engine 不知平台字段） | ✅ |
| 流程图 | 已提供（含失败路径） | ✅ |
| 既有文档冲突 | 已记录（D1–D4 + 待对齐清单 G1–G6） | ✅ |
| 代码变化 | **0** | ✅ |

---

## 十二、变更管理

本文档已冻结。任何修改必须：

1. 创建 `docs/change_request/<需求名称>.md`
2. 说明：改什么、为什么必须改、影响哪些下游模块
3. 更新本文档版本号（当前 v1.0 → 下次 v1.1）
4. 在文档末尾追加变更记录

**接口变更属破坏性变更**：`normalize` 的输入输出形态一旦变更，Interaction Engine 与所有测试夹具都受影响，必须走上述流程。

### 变更记录

| 版本 | 日期 | 变更内容 | 触发原因 |
|------|------|----------|----------|
| v1.0 | 2026-09-19 | 初始冻结：定位、输入输出、职责、错误传播、生命周期、Adapter/Engine 边界、流程图、设计禁止项；记录 D1–D4 与待对齐清单 G1–G6 | Step 2.2 Event Gateway 前置设计与接口冻结 |
