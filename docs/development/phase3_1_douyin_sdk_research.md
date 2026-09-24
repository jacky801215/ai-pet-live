# Phase 3-1 抖音开放平台 SDK 调研

> 状态：**调研稿（web 调研）**
> 日期：**2026-09-24**
> 性质：**只读调研产物** —— **非冻结契约、非 decision doc、不入 §十四、不授权任何实现**（不引入新编号前缀；引用既有 `PB-*` / `MP-*` / `QP-*` / `API-*` / `MB-*`）
> 方法：公开资料检索（官方文档站 + 开发者社区 + 第三方 SDK 文档）。**未经任何真实 SDK 调用验证**，未申请任何开放平台应用，未接真实回调
> ⚠️ **本报告不构成实现依据**：所有结论须在 Phase 3-4 真正落地前由官方文档/实测复核；第六节列出全部未确认项
> 关联：`docs/development/phase3_2b_b_live_evaluation.md`（B-live 立项评估 · owner 已确认「事件源 = 抖音开放平台 → HTTP 回调」）

---

## 一、接入方式

### 1.1 官方支持的接入形态

| 形态 | 是否官方支持 | 说明 |
|---|---|---|
| **直播小玩法 / 直播互动插件** | ✅ 官方 | 面向直播间互动的官方能力，事件经**数据推送任务**下发 |
| **开放平台数据推送（HTTP 回调 / webhook）** | ✅ 官方 | 官方推荐的服务端事件接收方式 |
| **长连接（WebSocket / TCP 自建通道）** | ❌ **官方明确不支持** | 直播互动事件**不提供**长连接推送；第三方长连接实现均为**逆向**产物 |
| **`Webcast*Message` protobuf 消息族** | ❌ 非官方 | 常见于第三方 SDK，属**逆向**所得，非官方契约、随时可能失效 |

**结论（入口口径）**：B-live 的事件入口**只能**是 **HTTP 回调（webhook）**，与 owner 裁决一致。
→ 这同时与 **PB-4** 相容：任何外部通道**必须**以 **adapter** 形态落在 platform 层，**禁止**在 `api/**` / `services/**` / 前端业务组件中直连外部协议。

### 1.2 接入前置步骤（官方口径）

1. 在抖音开放平台创建应用（直播小玩法 / 互动插件类目），取得 `app_id` / `app_secret`。
2. 配置**事件推送地址**（回调 URL）与**签名密钥**。
3. 调用 **`start_task`** 显式**开启数据推送任务** —— ⚠️ **不调用则不会推送**（易踩坑）。
4. 订阅所需事件类型（见第二节）。
5. 服务端实现回调接收 + 签名校验 + 幂等去重 + 超时快速响应。

> ⚠️ 本节为流程性描述，具体接口名/参数需以官方原文复核（见第六节 U-1）。

---

## 二、事件类型表格

### 2.1 官方事件名（与第三方命名对照）

| 业务事件 | **官方事件名** | 第三方逆向名（**勿用**） | 本项目 `event_type` 可映射 | 备注 |
|---|---|---|---|---|
| 评论 | `live_comment` | `WebcastChatMessage` | ✅ `comment` | 需 `content` |
| 礼物 | `live_gift` | `WebcastGiftMessage` | ✅ `gift` | ⚠️ 字段为 `sec_gift_id`（非 `gift_id`） |
| 点赞 | `live_like` | `WebcastLikeMessage` | ✅ `like` | ⚠️ `like_num` 为 **2 秒合并的累计值** |
| 粉丝团 | `live_fansclub` | `WebcastFansclubMessage` | ❌ **无槽位** | 现有白名单无对应类型 |
| 关注 | （服务端事件，**待核实**） | `WebcastSocialMessage` | ❌ **无槽位** | 是否发服务端推送**未确认**（U-2） |
| 进入直播间 | **未检索到官方事件** | `WebcastMemberMessage` | ❌ 无槽位 | 未确认（U-3） |

> ⛔ **关键事实**：本项目 `event_type` 白名单**恰 4** = `comment` / `gift` / `like` / `system`（`backend/app/models/event.py::ALLOWED_EVENT_TYPES`，**不含 `follow`**）。
> ⇒ `live_fansclub` / 关注 / 进入直播间**当前无落点**，只能**丢弃**或**走 CR 扩展白名单**（本报告不裁决）。

### 2.2 事件字段（调研所得，**待官方复核**）

| 官方字段 | 用途 | 陷阱 |
|---|---|---|
| `msg_id` | 消息唯一 ID | ⚠️ 是**幂等去重**主键；但事件契约**顶层仅 4 字段**，**禁止**新增 `id` 字段 ⇒ 去重**不能**依赖 `Event` 对象承载 |
| `room_id` | 直播间 ID | 冻结契约禁止顶层 `room_id` ⇒ 只能入 `payload` 或丢弃 |
| `test` | 测试标记 | ⚠️ `test: true` 的推送**必须过滤**，否则脏数据入链路 |
| `sec_gift_id` | 礼物 ID | ⚠️ **不是** `gift_id`；礼物「名称」需另行解析（U-4） |
| `like_num` | 点赞数 | ⚠️ **2 秒合并累计值**，语义 ≠「单次点赞数」 |
| `content` | 评论文本 | 直接映射 `comment.payload.content` |
| `fansclub_reason_type` | 粉丝团原因 | ⚠️ **服务端与客户端取值不一致** |

---

## 三、回调机制

| 项 | 调研结论 | 备注 |
|---|---|---|
| **签名头** | **`x-signature`** | 算法：`Base64(MD5(排序后的 header 拼接 + body + secret))` |
| ⚠️ 易错对照 | **不是** `X-Douyin-Signature`（SHA1） | 后者属**生活服务 / 抖店**体系，勿混用 |
| **挑战/握手** | **未检索到** `challenge` / `verify_webhook` 机制 | 与微信/飞书回调不同（U-5） |
| **响应超时** | **2 秒**（礼物事件 3 秒） | ⇒ 必须**先 ACK、后异步处理** |
| **熔断** | 连续 **10 次**失败 ⇒ 平台**熔断**（停止推送） | 生产环境必须做本地持久化 + 补偿 |
| **幂等** | 按 **`msg_id`** 去重 | 平台**允许重推** |
| **回查** | 礼物 / 粉丝团事件支持 **24 小时回查** | 可作对账兜底 |

> ⚠️ 签名算法与超时阈值均来自公开资料，**须以官方原文复核**（U-6）。

---

## 四、鉴权与限流

| 项 | 调研结论 | 备注 |
|---|---|---|
| **事件回调鉴权** | 请求头签名校验（见第三节） | 无 OAuth、无用户态 token |
| **OpenAPI 鉴权** | **应用级 `access_token`** | 获取方式：**`client_credential`** 模式 |
| `expires_in` | **7200 秒** | ⚠️ **重新获取会使旧 token 缩短至 5 分钟后失效** ⇒ 需单例刷新 + 提前续期 |
| **OpenAPI 请求签名** | **SHA256-RSA2048** | 头部：`Byte-Authorization` |
| **限流（任务级）** | **10 次 / 秒** | 调用类接口 |
| **限流（推送 QPS）** | 约 **100 QPS** | 回调下发侧 |
| **任务生命周期** | 必须显式 **`start_task`** | ⚠️ 不调用 → 零推送 |

> ⚠️ 限流口径与 token 续期细节**须以官方原文复核**（U-7 / U-8）。

---

## 五、与现有架构映射

### 5.1 落点（PB-4 口径）

```
抖音回调(HTTP)  →  [platform 层 adapter：新建 DouyinAdapter]  →  EventGateway.normalize(dict)  →  Event  →  （B-live 未落地，暂时止步）
```

- ✅ **入口归属**：`backend/app/platform/`（现有 `websocket_adapter.py` / `websocket_dispatcher.py` 的同类）。**新建 `douyin_adapter.py` 属实现，本报告不授权**。
- ✅ **唯一入网关**：adapter 产物**必须**是 `EventGateway.normalize(dict) -> Event`（HTTP / WS 同门），**禁止**绕过网关直接构造 `Event`。
- ✅ **双门面**：现状只有 `simulate(raw)`（HTTP）与 `apply_event(event, *, platform)`（WS）。抖音事件到「哪个 pet 的 runtime」的寻址，是 **B-live 的核心难点**（见 `phase3_2b_b_live_evaluation.md` §2.0；owner 已裁 **C3**）。

### 5.2 事件映射表（逐事件）

| 抖音事件 | 内部 `event_type` | 建议 `payload` | 冲突/缺口 |
|---|---|---|---|
| `live_comment` | `comment` | `{"content": <评论文本>}` | 必填 `content` 满足 |
| `live_gift` | `gift` | `{"gift_name": <名称>, "gift_count": <数量>}` | ⚠️ 官方只给 `sec_gift_id`，`gift_name` 需自建**映射表**（U-4）；现有规则 `gift_heart` 要求 `gift_name == "小心心"` |
| `live_like` | `like` | `{"like_count": <数>}` | ⚠️ `like_num` 是 **2s 合并累计值**，语义与规则 `like_dance`（`like_count >= 3`）**不同构** ⇒ 直接透传会产生**语义错误**（U-9） |
| `live_fansclub` | ❌ 无 | — | 白名单无槽位（U-10） |
| 关注 | ❌ 无 | — | 白名单无槽位（U-10） |
| 进入直播间 | ❌ 无 | — | 官方事件**未检索到**（U-3） |

### 5.3 与冻结契约的交点（**只登记，不裁决**）

| 契约 | 交点 | 影响 |
|---|---|---|
| **event schema v1.1** | 顶层**恰 4 字段**，禁 `id/timestamp/source/platform/room_id` | `msg_id` / `room_id` / `timestamp` **不能进顶层** ⇒ 幂等去重必须发生在 adapter 层（**不能**靠 `Event`），或塞入 `payload` |
| **event schema v1.1** | `test: true` 必须过滤 | adapter 层职责（**不是**规则层） |
| **PB-1 / PB-3 / PB-4** | adapter 无业务状态；产物 = 事件契约 | 抖音「当前推送任务 / token 缓存」等**不得**落到业务层 |
| **MP-5** | pet-scoped HTTP **写侧未授权** | 抖音事件要落到指定 pet ⇒ 需 **MP-5 写侧解除 CR**（B-live 前置） |
| **QP-1 / QP-4** | `/state` query 白名单 = **空集** | 前端无法传 `pet_id` 读回播发态 ⇒ 需 **`/state` 白名单 CR**（B-live 前置） |
| **MP-2** | 禁「后台 pet registry」 | 若选路径 B/C1（registry）须**先修订 MP-2** |
| **GR**（scope freeze） | 禁 reconnect / heartbeat / retry / timeout / **metrics** / tracing | ⚠️ 抖音机制**内含**重推、熔断、超时 —— 这些属**平台侧**行为，**不得**被理解为授权本项目新增 heartbeat/retry 机制 |

---

## 六、关键风险与待确认项

### 6.1 风险

| 风险 | 说明 | 严重度 |
|---|---|---|
| **官方 vs 逆向命名** | `Webcast*Message` 普遍流传但**非官方**，据此实现会埋长期失效风险 | 🔴 |
| **`gift_name` 需自建映射** | 官方只给 `sec_gift_id`，而规则层按 **名称**（`"小心心"`）匹配 | 🟠 |
| **`like_num` 语义不同构** | 2s 合并累计 vs 单次计数 ⇒ 可能**误触发** `like_dance` | 🟠 |
| **无 `challenge` 握手** | 与既有 WS/微信回调心智不同，易误实现校验流程 | 🟠 |
| **签名头易混用** | `x-signature`(MD5) vs `X-Douyin-Signature`(SHA1，生活服务/抖店) | 🟠 |
| **2s 超时 + 10 次熔断** | 处理慢 ⇒ 熔断 ⇒ 整条链路静默失效 | 🔴 |
| **`test: true` 未过滤** | 测试数据入链路，污染数据与动作 | 🟡 |
| **token 续期陷阱** | 重复获取会**缩短旧 token 至 5 分钟**，多实例/多 worker 易互相踢 | 🟠 |

### 6.2 未确认项清单（**12 项**，落地前必须逐项复核）

| # | 未确认项 |
|---|---|
| U-1 | 创建应用 / 配置推送地址 / `start_task` 的**准确接口名与参数** |
| U-2 | **关注**事件是否有服务端推送 |
| U-3 | **进入直播间**事件是否存在（官方未检索到） |
| U-4 | `sec_gift_id` → 礼物**名称**的官方解析接口 / 字典 |
| U-5 | 回调**是否**存在 challenge / 校验握手 |
| U-6 | **签名算法与超时阈值**的官方原文 |
| U-7 | 限流（10/s、100 QPS）的官方原文与适用范围 |
| U-8 | `access_token` 续期与多实例并发刷新的官方约束 |
| U-9 | `like_num` 的**精确语义**与是否可换算为「单次点赞」 |
| U-10 | `live_fansclub` / 关注 在本项目**是否需要**落点（决定是否走 CR 扩白名单） |
| U-11 | 事件**重推策略**与 24h 回查接口形态 |
| U-12 | 应用类目（直播小玩法 / 互动插件）的**资质与准入**要求 |

---

## 七、证据来源

> ⚠️ 以下为检索时点（2026-09-24）的公开资料，**未做实时可用性复核**；URL 仅为线索，**须以官方原文为准**。

| # | 来源 | 用途 |
|---|---|---|
| 1 | 抖音开放平台 · 直播小玩法文档（developer.open-douyin.com） | 接入形态、事件名、`start_task` |
| 2 | 抖音开放平台 · 数据推送 / 事件回调文档 | 签名 `x-signature`、超时、熔断、重推 |
| 3 | 抖音开放平台 · 鉴权（`client_credential` / `access_token`） | 鉴权与续期 |
| 4 | 抖音开放平台 · OpenAPI 签名（SHA256-RSA2048） | `Byte-Authorization` |
| 5 | 抖音开放平台 · 限流说明 | 10/s、100 QPS 口径 |
| 6 | 第三方开源 SDK（如 `douyin-live` 类 Python 实现） | ⚠️ **仅作字段线索**，命名与字段属逆向，**不作契约** |
| 7 | 开发者社区帖子（各事件字段实测） | `like_num` 合并、`test` 过滤、`fansclub_reason_type` 差异 |
| 8 | 生活服务 / 抖店 `X-Douyin-Signature` 文档 | ⚠️ **反例对照**，说明与直播互动的签名不同 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1 | 2026-09-24 | 初稿（web 调研，七节） |
