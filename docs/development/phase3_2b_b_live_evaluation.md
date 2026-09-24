# Phase 3.2-B B-live 立项评估

> 状态：**草案 · 待 owner 拍板**
> 前置：B-read 已完成（CR-1）；B-live 现状不可行（已证）
> 性质：**评估草案** —— **不冻结、不授权实现、未新铸任何契约编号**（本文件**不是** decision doc，不入 §十四）
> owner 已确认（2026-09-24）：① 事件源 = **抖音开放平台 → HTTP 回调**；② 范围 = **含写侧**（pet-scoped 写侧授权）；③ 先出本草案
> 编号空间：本文件**未**引入新编号前缀（沿用既有 `MP-*` / `MB-*` / `QP-*` / `API-*` / `PB-*` 引用）

---

## 一、产品需求梳理

### 1.1 真实场景事件源（owner 已确认）

- ✅ **抖音开放平台 → HTTP 回调**（webhook 推送到我方服务器）。**B-live 为必需**。
- ⚠️ 与 **PB-4** 的关系：PB-4 已冻结「任何外部通道（WebSocket、OBS 集成、**抖音/YY/Bilibili**、本地调试工具）接入本系统，
  **必须**以 **adapter 形态**落在 platform 层，**禁止**在 `api/**`、`services/**`、前端业务组件中直连外部协议」
  ⇒ HTTP 入站**仍须**包成 platform 层 adapter；**webhook 端点只是 transport，不是事件语义的归属地**。
- 本轮排除：前端 WS 直连、第三方工具本地回调（可后续另议）。

### 1.2 需求定义

| 项 | 内容 | 状态 |
|---|---|---|
| 用户期望 | 观众打赏 → **对应宠物**做动作；且该宠物的播放态**可被前端读回** | 确认 |
| 事件入口 | 抖音 webhook（HTTP 入站）→（PB-4）platform 层 adapter → 内部 `Event` | 确认 |
| 延迟要求 | **待 owner 明确**（决定是否需要队列 / 批处理 / 背压） | ⏳ 待定 |
| 多宠物同时在线 | **待 owner 明确** —— 这是路径选择的**第一决定变量**（见 2.4） | ⏳ 待定 |
| 范围 | **含写侧**（pet-scoped 写侧授权） | 确认 |

**需求的既有证据（非本步新增）**：前端 `useRuntimePush(petId)` 已能经 WS 收该宠物 push 帧，但其**刷新 / 轮询路径**是
`GET /api/playback/state`（恒走默认单例）⇒ **选中宠物的播放态经 HTTP 读不回来**（读到的是默认 `cat_001`）。
这就是既有遗留项 **B2**；连带风险 **R-10**（若只上 B-read，UI 会出现「计数随选中宠物变、播放态不变」的**新不一致**）。

---

## 二、技术路径评估

### 2.0 问题的真内核（本步核查所得判据）

**PB-1 / PB-3 / PB-4** 合起来意味着：**无论何种传输形态**，adapter 的产物都是**事件契约 v1.1 的统一内部 `Event`**。
而内部 `Event` 要驱动动画，就**必须**落到**某个具体 pet 的 runtime**（= `SimulationPipeline.apply_event()` 的接收者）。

⇒ **真内核 = 「一条 `Event` → 哪个 pet 的 runtime」的寻址与生命周期**，**不是**「HTTP 还是 WS」。
B-live 只是它在「HTTP 入站」形态下的一个切面。

**现状（实测）**：`apply_event` 的接收者**只有两种**：

| 接收者 | 来源 | 生命周期 | pet 作用域 |
|---|---|---|---|
| `_default_pipeline`（`get_pipeline()`） | **全部 4 个 HTTP 端点**（`events.py:56` · `playback.py:137` · `stats.py:170,196` · `ws.py:82,122`） | **进程级单例** | ❌ `pet_id=None` ⇒ 派生 `cat_001`，**不承载 pet 上下文** |
| `build_pipeline_for_pet(key, settings)` | **唯一**：`api/ws.py:149` `?pet_id=<key>` | **连接级**（连接结束即丢弃） | ✅ 该 key |

### 2.1 路径 A：per-request 新建 runtime

- 实现：每个 HTTP 请求 `build_pipeline_for_pet(key, settings)` 新建 runtime，用完即弃。
- **是否违 MP-2**：⚠️ **不违字面** —— MP-2 禁的是「全局 current_pet · 共享 active runtime · 进程级 pet 态 · 后台 pet registry」，
  per-request 临时物件图不在其枚举内。
- 代价：❌ **语义退化** —— 请求返回后状态被丢弃 ⇒ `/api/playback/state` **恒返回 `idle`**，
  `simulate` 的效果**无法被后续请求观察到** ⇒ **不满足 1.2 的「播放态可被读回」**；
  且每请求新建 SQLite 句柄 + 素材扫描，成本高。
- 适用：单次事件、**无需状态连续**（与本项目需求不符）。

### 2.2 路径 B：加 runtime registry

- 实现：进程级 `pet_id → runtime` 映射（缓存 / 注册表）。
- **是否违 MP-2**：⛔ **直接违反** —— MP-2 逐字禁「**后台 pet registry**」「进程级 pet 态」「共享 active runtime」。
  ⇒ 不可行，**除非先修订 MP-2**。
- 代价：技术成本中等，但**须动 3.2-A 的冻结基石**（MP-2 是 per-connection 隔离的根基），治理成本高。
- 适用：多宠物并发、需状态连续。

### 2.3 路径 C：混合模型（第三条路径，探索）

> 目标：是否存在**不违 MP-2** 的「事件 → 某 pet runtime」机制。以下为**候选子方案**，均需 owner 裁决（本文件不代裁）。

| # | 子方案 | 机制 | 与 MP-2 的关系 | 主要缺口 |
|---|---|---|---|---|
| **C1** | **runtime 池 + 借用/归还（lease）** | 预建 N 个 per-pet runtime，池化复用 | ⛔ **仍违** —— 池本身即「进程级 pet 态」+「后台 registry」 | 无（除非修 MP-2） |
| **C2** | **单例 + pet 上下文参数化** | 把 `pet_id` 从 `Runtime` 的**构造期定值**改为**事件级 / 请求级参数**；状态机按 `pet_id` 分区 | ❓ **待裁** —— 单例不承载 pet 态（不落入 MP-2 枚举），但**改了 MP-2 的前提**（per-connection 独立物件图）与 `ActionEngine` 的 pet_id 不变量 | ① `Runtime` 为 `frozen`、`pet_id` **构造期定值**（Phase 3.2-A1 结构守卫已锁「禁后置赋值」）；② `ActionEngine` 单例内**单一** `_state` / `_pending` ⇒ 需按 pet 分片；③ 触 AS-4 行数（`pipeline.py` 余量 **+26**） |
| **C3** | **事件队列 + 单一消费者（单宠物在线）** | 明确**只支持单宠物在线**：默认单例消费队列，事件里带 `pet_id` 仅作校验 | ✅ **不违**（不引入任何进程级 pet 态 / registry） | ① **不支持多宠物并存**（若 1.2 答「不需要」则成立）；② 写侧仍须解除 MP-5；③ `/state` 读侧仍须 CR |
| **C4** | **adapter 直投 + 合法状态持有者** | DouyinAdapter 产出 `Event` 后**直接**交给某 pet 的 runtime | ❓ **待裁** —— 关键缺口：**PB-1 明令 platform「不持有业务状态、不做缓存决策」** ⇒ adapter 自身**不能**持有 pet→runtime 映射，也**不能** import `services/**`（PB-2） | 需要一个介于 adapter 与 runtime 之间的**合法持有者**；该持有者本质上就是 registry ⇒ **回到 MP-2** |

**结论 C**：绕开 MP-2 的唯一**不违**子方案是 **C3（单宠物在线）**；其余子方案（C1 / C2 / C4）**要么违 MP-2、要么须修订 MP-2 的前提**。

### 2.4 第一决定变量：单宠物 vs 多宠物并存

- **单宠物在线** ⇒ **C3 可行且不触 MP-2**（治理成本最低）。
- **多宠物并存** ⇒ 只剩 **A（语义退化，可能不满足需求）** 或 **B / C1 / C2（须修订 MP-2）**。
- ⛔ **本文件不代裁** —— 请 owner 就 1.2 的「多宠物是否并存」给出明确口径，推荐路径才能定（第五节）。

### 2.5 与路径无关的**共性前置**（任一方案都必须做）

1. ⛔ **PB-4 / PB-3**：抖音 webhook **必须**包成 platform 层 adapter（输出事件契约 v1.1 统一事件，经 `EventGateway.normalize` 入核心）。
   ⇒ **不是**把抖音报文直接塞进 `POST /api/events/simulate`（后者是 `platform="simulator"` 的模拟器门面，且入站即校验）。
2. ⛔ **MP-5 写侧解除**（MB-7③）—— owner 已裁「含写侧」。
3. ⛔ **`/api/playback/state` 的 pet 作用域**须 CR（**QP-1** 该端点 query 白名单为**空集**；**QP-4** 禁为只读端点新增参数；
   CR-1 只为 `/stats` · `/events/recent` 开了 `pet_id` 例外，**未含 `/state`**）。**MB-6 逐字把 `/state` 列为 B-live 范围**。
4. ⛔ **MPF-7**：前端「pet 级 HTTP 消费」仍禁 ⇒ 前端要能读回选中宠物的播放态，须**另行授权**（否则后端做了也读不回）。
5. ⚠️ **AS-4**：任何改 `pipeline.py` 的方案，**先算行数预算**（余量 **+26**，上限 < 300）。

---

## 三、与现有冻结契约的冲突分析

| 契约 | 路径 A | 路径 B | 路径 C |
|---|---|---|---|
| **MP-2**（Runtime Isolation） | ✅ 不违**字面**（per-request 临时图不在禁令枚举） | ❌ **直接违**（进程级 pet 态 / 后台 registry） | ❓ **C1 违 · C2 待裁 · C3 不违 · C4 待裁** |
| **MP-5**（pet-scoped HTTP **写侧**） | ⛔ 须**显式解除** | ⛔ 须显式解除 | ⛔ 须显式解除 |
| **QP-1**（`/state` query 白名单 = **空集**） | ⛔ 须 CR 新增 `pet_id` | ⛔ 同 | ⛔ 同 |
| **QP-4**（禁为只读端点新增参数） | ⛔ 须 CR（CR-1 已为 `/stats`·`/recent` 开例外，`/state` **未开**） | ⛔ 同 | ⛔ 同 |
| **API-1**（`pet_id` 由后端补齐、UI 不发送） | ⛔ 若写侧复用 `simulate` 并收 `pet_id` 即破（MB-7②） | ⛔ 同 | ❓ 若写侧改由 **webhook → adapter** 产出（**不走** `simulate`），API-1 是否被破须**另裁**（属新端点输入契约） |
| **API-2**（`PlaybackState` **7 字段**） | ✅ 不改字段 | ✅ | ✅ |
| **PB-1**（platform **不持业务状态**） | ✅ runtime 在 `api/**` 层新建 | ❌ 若 registry 落 platform；✅ 若落 `api/**`/`services/**` | ❓ C4 直接受本条约束（见 2.3） |
| **PB-3 / PB-4**（外部平台**必须** adapter） | ⛔ 漏做 adapter = 把 HTTP 入站当事件源 | ⛔ 同 | ⛔ 同 —— **共性前置**，与路径无关（见 2.5-1） |
| **WM-1**（envelope 恰 4 字段） | ✅ 不变 | ✅ | ✅ |
| **AS-4**（组合根 < 300 行；`pipeline.py` 余量 **+26**） | ✅ 可不改 `pipeline.py` | ❓ 若 registry 落组合根 ⇒ **先算预算** | ❓ C2 必触 ⇒ **先算预算** |
| **MPF-7**（前端 pet 级 HTTP 消费仍禁） | ⛔ 须另行授权 | ⛔ 须另行授权 | ⛔ 须另行授权 |
| **MB-6**（B-live 未授权、registry 类结构禁） | ⛔ 须 CR 解除 | ⛔ 须 CR 解除 | ⛔ 须 CR 解除 |

> 说明：`❓` = 本评估**无权裁定**、须 owner 拍板；`✅/⛔/❌` 均按既有冻结原文逐字对照。

---

## 四、代价矩阵

| 路径 | 实现成本 | 契约改动 | 风险 | 推荐度 |
|---|---|---|---|---|
| **A**（per-request 新建） | 低 | MP-5 写侧 + QP-1/QP-4 + （API-1） + MPF-7 | 🔴 **语义退化**：`/state` 恒 `idle` ⇒ **可能根本不满足 1.2** | ❓ 待拍板 |
| **B**（runtime registry） | 中 | 以上 + ⛔ **修订 MP-2** | 🔴 **大**：动 3.2-A 冻结基石（per-connection 隔离） | ❓ 待拍板 |
| **C3**（单例 + 单宠物在线） | 低~中 | MP-5 写侧 + QP-1/QP-4（**不触 MP-2**） | 🟡 **中**：**不支持多宠物并存**（须 1.2 确认） | ❓ 待拍板 |
| **C2**（单例 + pet 参数化） | 高 | 以上 + **修订 MP-2 前提** + API-1 + 结构守卫 | 🔴 大：`Runtime` frozen / `pet_id` 构造期定值 / `ActionEngine` 单状态机全须改 | ❓ 待拍板 |
| **C1 / C4** | 高 | 同 B（C1 违 MP-2；C4 缺合法持有者 ⇒ 回到 B） | 🔴 大 | ❓ 待拍板 |

> 共性成本（任一方案都要付）：PB-3/PB-4 的 `DouyinAdapter` + 合规审查 + 事件映射表（对应 `development_plan.md` Phase 3 任务 3-3/3-4/3-6）。

---

## 五、推荐方案（待 owner 拍板后填写）

> **占位** —— 本节须在 owner 明确 1.2 的「**多宠物是否并存**」与「**延迟要求**」后填写。
> 本评估**不代裁**（铁律 2）。

---

## 六、实施范围（草案）（待推荐方案确定后填写）

> **占位** —— 本节须在第五节推荐方案确定后填写（含：CR 清单、契约修订清单、授权文件清单、`pipeline.py` 行数预算、测试与回归口径）。
> 本评估**不代裁**。

---

## 七、证据来源

| # | 来源 | 用途 |
|---|---|---|
| 1 | `phase3_pet_scoped_http_api_decision.md`（v1.0 FROZEN）**MB-1 / MB-6 / MB-7** `:139-157` | B-live 未授权；**MB-7 三项前置** |
| 2 | `phase3_backend_multi_pet_context_decision.md`（FROZEN）**MP-1 / MP-2 / MP-3 / MP-4 / MP-5** `:62-126` | Runtime 隔离禁令；写侧仍禁；MP-4 双源不对称 |
| 3 | `phase2_platform_boundary_decision.md`（FROZEN）**PB-1 / PB-2 / PB-3 / PB-4** `:29-62` | **外部平台必须 adapter**；platform 不持业务状态；`normalize` 唯一通道 |
| 4 | `phase3_2b_route_b_decision_input.md`（非冻结）`§4.1-4.3` `:140-165`、`R-5` `:228`、`A4` `:248` | 路径 A/B 的既有分析；B2 / R-10；B-live 剥离裁决 |
| 5 | `phase3_2b_bread_execution_plan.md` `:131` `:218` | A6 解除 MP-5（**限 B-read**）；「引入 registry 须先修订 MP-2」 |
| 6 | `step4_api_query_boundary_decision.md`（FROZEN）**QP-1 / QP-4** + CR-1 条目 `:233` `:282` | `/state` 白名单空集；CR-1 例外不含 `/state` |
| 7 | `development_plan.md` `:204-265` | Phase 3（接入**准备**，含 3-1 抖音 SDK 调研、3-4 `DouyinAdapter` 骨架、3-6 合规）+ Phase 4（正式接入）；Phase 3 末 **Go/No-Go** |
| 8 | `phase1_design.md` `:344` | 抖音 SDK 接入 = Phase 4、需授权 |
| 9 | 代码实测：`pipeline.py:266-274`（单例）· `runtime_factory.py:243`（`build_pipeline_for_pet`）· `api/{events,playback,stats,ws}.py`（4 端点均 `Depends(get_pipeline)`）· `api/ws.py:149`（唯一 pet 分支）· `backend/app/platform/**`（仅 WS 两文件，`SimulatorAdapter` 0 命中） | 现状事实 |
| 10 | CR-1 交付报告 `phase3_cr1_idle_loop_delivery_report.md` / CR-3 交付报告 `phase3_cr3_queue_backlog_delivery_report.md` | 读侧既有授权边界；队列语义现状 |

---

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.1（草案） | 2026-09-24 | 首次提出（B-live 立项评估草案）。**不冻结、不授权实现、未新铸编号**。owner 已确认：事件源 = 抖音开放平台 HTTP 回调；范围 = 含写侧。第五节（推荐方案）与第六节（实施范围）**待 owner 拍板后填写** |
