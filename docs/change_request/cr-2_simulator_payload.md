# CR-2：前端模拟器补最小测试 payload

> 流程依据：`PROJECT_RULES.md` **§七「需求变更管理」**（任何新增需求必须创建 `docs/change_request/需求名称.md`）。
> 本文件是**本仓第二份正式 CR 文件**（编号空间 **CR-***；`CR-1` 见 `cr-1_idle_loop.md`）。

| 项 | 值 |
|---|---|
| 编号 | **CR-2** |
| 提出日期 | 2026-09-24 |
| 状态 | **待确认**（owner 已就方向与 payload 取值裁决，见 §六） |
| 关联契约 | `step4_frontend_event_simulator_decision.md`（**ES-2** / **ES-3**）· 事件契约 `step2_event_schema.md`（事件级 payload 必填规则） |
| 关联裁决 | `phase1_completion.md` **F-2**（comment 只计数 —— 本 CR **不变更**该裁决） |

---

## 一、需求描述

**前端模拟器的三个按钮，两个直接报错、一个无动画。**

实测现状（只读核查，逐层可复核）：

| 按钮 | 当前请求体 | 后端实际结果 |
|---|---|---|
| `gift` | `{ event_type: "gift", payload: {} }` | **400 INVALID_REQUEST**（`EVENT_PAYLOAD_INVALID`：缺 `gift_name`、`gift_count`） |
| `comment` | `{ event_type: "comment", payload: {} }` | **400 INVALID_REQUEST**（缺 `content`） |
| `like` | `{ event_type: "like", payload: {} }` | **200**，但 `action = null` ⇒ 回落待机素材（`<video src>` 仍 `idle.mp4`） |

证据链：

- **事件级必填 payload 表**：`backend/app/models/event.py` 的 `_PAYLOAD_RULES`
  —— `comment` 必填 `content`（禁 `text` / `message`）；`gift` 必填 `gift_name` + `gift_count`
  （禁 `count` / `number`）；`like` **无必填**；`system` 必填 `command`；
- **校验发生在规则层之前**：`EventGateway.normalize(raw)` 即 `Event.from_dict(raw)`，
  其 `__post_init__` 调 `_check_payload` ⇒ 空 payload 在**网关**就被拒，
  **根本到不了 Interaction Engine**（因此 `rules.json` 的 `defaults` 兜底**也不会生效**）；
- **锁定测试**：`backend/tests/test_event_model.py::test_comment_missing_content_is_rejected`
  （`payload: {}` → `EVENT_PAYLOAD_INVALID`）；
- **前端恒发空 payload**：`frontend/src/hooks/usePetRuntime.ts` 的 `submitRuntimeEvent`
  → `simulateEvent({ event_type, payload: {} })`；
- **契约来源**：`step4_frontend_event_simulator_decision.md` **ES-2**（触发链路内写死
  `simulateEvent({ event_type, payload: {} })`）与 **ES-3**（「请求体**固定**：`{ event_type, payload: {} }`」）。

**本 CR 目标**：让模拟器三个按钮都能发出**最小合法 payload**，
真正走通「事件 → 规则 → 动作 → 素材」全链路（`gift` → `heart`、`like` → `happy`）。

---

## 二、为什么需要

1. **本地验证能力被破坏**：模拟器是 Phase 1 唯一的事件入口（`development_plan.md` 任务 **1-16**，P0）。
   当前 3 个按钮里 **2 个直接 400**、1 个恒无动画 ⇒ 无法验证 gift / like 的触发链路。
2. **真实场景本就有 payload**：平台回调携带 `gift_name` / `like_count` / `content` 等字段。
   模拟器作为本地替代应发送**最小合法 payload**；空 payload 不是「真实的最小」，而是**契约非法**。
3. **规则依赖 payload**：`rules.json` 的 `gift_heart`（`payload.gift_name == "小心心"`）与
   `like_dance`（`payload.like_count >= 3`）**只能**由带 payload 的事件命中
   ⇒ 空 payload 下这两条规则**永不执行**，等于「有代码、无验证」。

---

## 三、影响模块

### 3.1 契约与治理（授权：owner 2026-09-24）

| 文件 | 改动 |
|---|---|
| `step4_frontend_event_simulator_decision.md` | **ES-2** 触发链路中的 `payload: {}` 改为按事件类型取预设 payload；**ES-3**「请求体固定」修订为「按事件类型提供**最小测试 payload**」；文档 **v1.1 → v1.2**；变更历史 +1 行 |
| `PROJECT_RULES.md` §十四 `### Frontend Event Simulator Boundary` | **ES-2** / **ES-3** 两处摘要同步（登记 2026-09-24） |

### 3.2 生产代码

| 层 | 文件 | 改动 |
|---|---|---|
| 前端 · 编排 | `src/hooks/usePetRuntime.ts` | 新增 `SIMULATOR_PAYLOADS` 常量；`submitRuntimeEvent` 按事件类型取 payload |

### 3.3 测试

`frontend/tests/event-simulator/EventSimulator.test.tsx` —— 4 处「payload 恒空」锁定点同步 + 新增 payload 映射用例。

### 3.4 明确不受影响

- **后端全部不动**：`rules.json` · `app/models/event.py` · `app/services/**` · `app/api/**` ·
  `app/platform/**` · `api/ws.py` · `database/schema.sql`；
- **组合根三件套**（`pipeline.py` 余量 **+2**，**禁止触碰**）；
- **`ALLOWED_EVENT_TYPES` / 动作域 / Rule Schema / `SimulateEventRequest` 4 键结构** 逐字不变；
- **ES-1**（组件位置与「只渲染三按钮」）**零改动**；**ES-4 / ES-5 逐字不变**
  —— 尤其 ES-3 的其余禁止项（自由文本输入 / payload 编辑器 / 批量触发 / 去抖策略）与
  **ES-5「不实现自定义 payload、事件编辑器」** 原样有效：本 CR 加的是**代码内固定的预设值**，
  **不是**用户可编辑的自定义 payload；
- `PlaybackState`（7 字段）· `PlaybackSnapshot`（6 字段）· **FP-3** `<video>` 白名单 ·
  API-1 / API-2 / API-3 均不变。

---

## 四、修改方案

1. **契约松绑（仅一条）**：ES-2 / ES-3 由「请求体**固定** `payload: {}`」
   改为「请求体**按事件类型**提供**预设的最小测试 payload**」；
   该值**不代表业务规则**，仅为本地验证提供可触发后端规则的输入；真实场景下 payload 由平台回调提供。
2. **前端预设表**（`usePetRuntime.ts`）：

   | 事件类型 | payload | 依据 |
   |---|---|---|
   | `gift` | `{ gift_name: "小心心", gift_count: 1 }` | 事件契约必填两字段；且命中 `rules.json` 的 `gift_heart` → `heart` |
   | `like` | `{ like_count: 3 }` | `like` 无必填；`3` 满足 `rules.json` 的 `like_dance` 阈值 → `happy` |
   | `comment` | `{ content: "好可爱" }` | 事件契约必填 `content`（修掉 400；**不产生动画**，见 §四.4） |

3. **取值口径**：未列入上表的 `event_type` **回落 `{}`**（保持既有默认，**不臆造**）。
4. **明确边界（F-2 不变）**：`comment` 补 payload **只把 400 修回 200**；
   **comment 不触发动作**系既有 owner 裁决 **F-2（comment 只计数，方案 B）**
   （`phase1_completion.md` §六 已知限制 1），**本 CR 不变更该裁决**。
   若后续要使 comment 产生动画，须**另行裁决修改 `rules.json`**（不在本 CR 授权范围）。

---

## 五、是否影响 MVP 范围

**是 —— 属本地验证的核心能力（任务 1-16，P0）。**

不扩范围：不改后端任何文件、不改 `rules.json`、不新增事件类型、不扩 Rule Schema、
不新增依赖、不改文件尺寸（组合根 `pipeline.py` 余量 **+2** 保持不动）。

---

## 六、落地授权记录（owner 裁决，2026-09-24）

| 裁决 | 内容 |
|---|---|
| **方案 A** | 前端模拟器**按事件类型发送最小测试 payload**（不改后端规则） |
| **`gift` 取值** | `{ gift_name: "小心心", gift_count: 1 }` —— 修正草案中的 `{}`（实测 `{}` 必然 400：payload 校验先于 `defaults`） |
| **`comment` 目标** | **接受 F-2 不变**：补 `content` 只为把 400 修回 200；**不改 `rules.json`** |
| **§十四 同步** | **授权**同步 `ES-2` / `ES-3` 两处摘要 |
| **提交门槛** | 工作树既有 `M frontend/vite.config.ts`（owner 未提交改动）**保留不提交**；只 `git add` 授权路径，提交前校验「**无未跟踪文件**」 |

---

## 七、附：音轨登记（沿用 CR-1 §七，本次**不处理**）

`PetPlayer` 的 `<video>` **硬编码 `muted`** ⇒ 素材 AAC 音轨**惰性不播**（登记见 `cr-1_idle_loop.md` §七）。本次仅**沿用登记**，不改动。

---

## 八、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-24 | 首版；owner 已裁决方向（方案 A）、`gift` 取值修正、`comment` 维持 F-2、§十四 授权与提交门槛口径 |
