# CR-6：动作播完自动回待机（服务端定时推进 + 状态帧推送）

> 变更请求（**第六份正式 CR**）。契约来源：`PROJECT_RULES.md` §七（CR 流程）· §十四（边界登记）。
> 前置：**CR-1**（`loop` 下发，已交付）· **CR-3**（队列堆积 / 到期推进时机，已交付 `0769a3b`）。
> 根因取证：`phase3_trial_acceptance_report.md` **§7**（工作区报告，2026-09-28，源码级证据链）。
> owner 授权：**2026-09-28**，Q3 = **A（本地展示 / demo）**；P0 修法选定 **① 服务端定时推进 + 推送状态快照**。
> 状态：**已确认（2026-09-28，owner 裁决见 §八）· 尚未实现**（先提交本 CR 文档；实现另按 §十 分笔授权）。
> 性质：本 CR **含冻结契约修订**（**WP-3** / **WC-3** / **PC-2·PC-4** / **FS-3**）；
> 并且**本 CR 即** `phase2_websocket_push_boundary_decision.md` §Step 3 明文预留的
> **"另出修订文档"**（原文见 §五 K1）——**不是**绕过冻结，而是**行使其明文的修订程序**。

## 一、需求描述

「动作播放**结束 → 画面自动回到该宠物的待机动画（循环）**」——**无需用户再次点击**。

**现状（2026-09-28 实测）**：`heart` / `happy` 等一次性动作（`loop=false`）播完后，`<video>`
**停在末帧**；要回 idle 只能**再点一次任意按钮**或**点「刷新」**。CR-1 只解决了「idle 能循环」，
**未解决「动作播完谁把状态推回 idle」**。

| 项 | 口径 |
|---|---|
| 触发 | 一次性动作的播放窗口**到期**（`playback_duration_seconds()` 给出的时长） |
| 结果 | 前端 `playback` 切片被**整份替换**为该时刻的服务端快照（通常 `state=idle`、`loop=true`、`action=null`） |
| 用户可见 | 无需任何交互，画面回到循环待机动画 |
| 队列情形 | 有排队动作时，到期后按既有队列语义续播下一动作（`restore_idle` ⇒ 下一动作；快照如实反映） |

## 二、为什么需要

1. **属 Phase 1 P0 验收项（`phase1_design.md` F5 / P4）的闭合** —— CR-1 + 本 CR 合起来才构成
   「待机动画持续可见 + 动作播完回落」的完整验收项；**缺失即未达标**。
2. **根因 = 系统里不存在「时间驱动」的事件源**（报告 §7.1，逐条源码级证据）：

| # | 事实 | 源码位置 |
|---|---|---|
| 1 | 状态机只接受两种推进：**读路径**与**事件受理路径**（**WC-3 v1.1**，CR-3 授权）。`_expire_if_due()` 全仓**仅两处**调用 | `services/pipeline.py:150` / `:176` / `:233` |
| 2 | 队列出队**只由到期推进驱动**：`on_finished` **刻意留空**（注释原文："播放何时结束由编排层按时长判定"） | `services/runtime_factory.py:147` |
| 3 | 前端**零定时器**：`src/**` 无 `setInterval` / `setTimeout` / `requestAnimationFrame`；**9 个测试文件**断言禁止 | `frontend/tests/**` |
| 4 | 前端**零媒体事件回写**：`PetPlayer` 无 `useState`/`useEffect`/`ref`/`currentTime`/`progress`/`onEnded`（**FP-4**） | `components/player/PetPlayer.tsx` |
| 5 | 前端**唯一**回读 = `triggerEvent()` 内 + 人工刷新 + 挂载一次 ⇒ **无周期性回读** | `hooks/usePetRuntime.ts:70-92` |
| 6 | 推送救不了场：`api/ws.py` 的推送是**该连接入站消息的"回声"**（前端走 HTTP ⇒ 0 帧）；且 `applyPushEvent` **只写 `last_event`**，**结构上改不了画面** | `api/ws.py` / `stores/usePetStore.ts:86-107` |
| 7 | `snapshot()` docstring 自陈："状态机由**状态查询**驱动推进——**Phase 1 无 push 通道**" | `services/pipeline.py:174-175` |

3. **为什么时间源必须落在服务端**：Q3 = A（demo），但「客户端拥有时间」会**推翻**本项目
   「服务端唯一状态所有者」的主轴（RS / RF / FS / FP 系列），须逐条解 **9 处守卫** ⇒ 属**架构倒退**；
   且"播放时序"一旦进前端，后续每次动作语义变更都要同步前端判断（违 FP-1「禁止业务判断」）。
4. **为什么这是"补齐 Phase 1 的既定设计"而非新特性**：`snapshot()` 的自我陈词「Phase 1 无 push 通道」
   已明示 push 通道是**既定缺口**；`WP-6` 当初禁 heartbeat ≠ 禁状态推送（见 §五 K1/K2）。

## 三、影响模块

| 文件 | 变更 | 层 |
|---|---|---|
| `backend/app/api/ws.py` | 连接循环改为**常驻收帧任务 + 非取消式观察**（**A-1′**，见 §4.2）+ 变化检测 + 状态帧推送 | transport |
| `backend/app/platform/websocket_dispatcher.py` | **新增** `send_state_frame(...)`（与 `send_event` 并列）；头部禁令第 25 行口径同步 | platform |
| `frontend/src/services/websocketClient.ts` | 入站帧**按帧型分流**（状态帧 / 事件帧） | transport |
| `frontend/src/types/push.ts` | 新增状态帧类型定义 | 契约类型 |
| `frontend/src/stores/usePetStore.ts` | **新增写出口** `applyPlaybackSnapshot` | store |
| `frontend/src/hooks/useRuntimePush.ts` | 仍是**唯一**接线点（PC-1 归属不变），接上新写出口 | hook |
| `docs/development/phase2_websocket_push_boundary_decision.md` | ⛔ **冻结契约修订**：**WP-3** v1.0 → v1.1 + §Step 3 登记 | 契约 |
| `docs/development/phase2_websocket_commit_point_decision.md` | ⛔ **冻结契约修订**：**WC-3** v1.1 → v1.2 | 契约 |
| `docs/development/phase2_websocket_boundary_decision.md` | **WS-4** 口径同步（登记） | 契约 |
| `docs/development/phase2_frontend_push_channel_decision.md` | ⛔ **冻结契约修订**：**PC-2** / **PC-4** | 契约 |
| `docs/development/step4_frontend_state_decision.md` | ⛔ **冻结契约修订**：**FS-3**（写出口增项） | 契约 |
| `PROJECT_RULES.md` §十四 | 摘要同步（**块内就地**：版本指针 + 相关条目） | 治理 |
| 后端 / 前端测试 | 新增用例 + **同步既有守卫清单** | 测试 |

**不涉及**：`services/pipeline.py` · `services/playback_state.py` · `services/runtime_factory.py` ·
`services/data_manager.py` · `repositories/**` · `models/**` · `database/schema.sql` ·
`PlaybackState` 字段集（仍 **7 字段**）· `package.json` / `requirements`（**零新增依赖**）·
`FP-3` / `FP-4` / `UB-*` / `RB-*` / `API-*` / `QP-*`（**逐字不变**）。

> ✅ **后端改动被刻意压在 transport + platform 两层**：不触 `pipeline.py` ⇒ **保住 AS-4 的
> 「组合根三件套各 < 300 行」预算**（`pipeline.py` 现 **274**，仅余 **+26**）。

## 四、修改方案

### 4.1 总览（一句话）

**在 WS 连接内补一个「到点就去读一次」的定时循环**；读到的快照**仅在与上次推送不同时**
作为**状态帧**推给该连接；前端把状态帧**整份写入 `playback`**。

### 4.2 后端 · 到期观察（**F1 = A-1** → 实现层经 owner **E1** 追认为 **A-1′**）

`api/ws.py` 的连接循环由「纯阻塞收帧」改为「**常驻收帧任务 + 非取消式观察**」：

| 事件 | 处理 |
|---|---|
| 收到帧 | 走**既有** `adapter.handle(raw)` → `pipeline.apply_event(...)` → `dispatcher.send_event(...)` 推 **WM-1 事件帧**（**逐字不变**）→ 随后按 **C1** 做一次 compare-and-push（见下） |
| **观察到期**（无入站消息） | 调**既有公开方法** `pipeline.snapshot()`（其内部已含 `_expire_if_due()`）⇒ 与「**上一条已成功推送的状态帧**」比对 ⇒ **仅在变化时**调 `dispatcher.send_state_frame(...)` |

- `TICK` 集中声明为**模块级常量**、**可注入**（monkeypatch）以便测试固定时序。
  ⛔ **TICK 数值与计时器实现类别属「实现参数」**，**不进契约**（见 §五 K7 / K8）。
- ✅ **零改动** `pipeline.py` / `playback_state.py` ⇒ **不新增推进逻辑**，只是**服务端自己触发一次既有读路径**。
- ✅ **不需要** connection registry / 后台任务 / 连接集合 ⇒ **WP-4 / WP-6 / WS-6 逐字不变**
  （本循环**不发送** ping/pong、**不重连**、**不 buffer**）。
- **实现层方案 A-1′（owner E1 追认，2026-09-29）**：
  **常驻收帧任务 + `asyncio.wait({task}, timeout=T)`**（超时**只观察**、**绝不取消在途收帧**）；
  `task.result()` 重新抛出 `WebSocketDisconnect`；`finally` 中显式 `cancel()` 回收。
  ⚠️ **不是** `wait_for(receive_text)`、**不是** background scheduler（**A-3 仍否决**）。
  - ⛔ **U-6a 实测结论（本 CR 原推荐值被推翻）**：原设计 `asyncio.wait_for(receive_text(), timeout)` **实测丢帧** ——
    超时**取消在途 `receive_text()`** 时，**已送达 ASGI 队列但尚未返回**的消息被吞
    （10 ms 节拍连发 20 条 ⇒ **19/20**，丢的恰是第 1 条）。
     ⇒ 故**未**退 A-2（无需暴露 `PlaybackClock` 访问器、**不动行预算**），而是改为 **A-1′**。
  - **A-2 的适用性**：仍然有效、仍**不是**本次选择（本 CR §九 U-6a 原「若不安全 ⇒ 退 A-2」**已由 E1 取代**）。

### 4.3 后端 · 状态帧（**推荐 F2 = B-1：原样复用 `PlaybackState`**）

```json
{"type": "playback_state",
 "snapshot": {"pet_id": "cat_001", "state": "idle", "action": null,
              "asset_url": "/assets/pets/cat/actions/idle/idle.mp4",
              "queue_size": 0, "last_event": "gift", "loop": true}}
```

- **载荷 = API-2 的 `PlaybackState` 7 字段原样**（不新造口径、不加任何派生字段）。
- ✅ **满足 WP-3 的存活禁止项**：`duration` / `progress` / `video_state` / `queue` **一律不发送**。
- 由 `websocket_dispatcher.py` **新增一个** `send_state_frame(snapshot, websocket)`；
  仍**不持有 socket**（逐次传入）、**无业务状态**、**失败只 log** —— **WP-1 / WP-4 / WP-5 保持不变**。
- **帧型判别规则**：`type` 字段**仅存在于状态帧**；**事件帧（WM-1）逐字不变**（仍**恰 4 字段**）。

### 4.4 前端 · 分流 + 写口径（**推荐 F3 = C-1**）

- `services/websocketClient.ts`：入站帧**先判帧型** ——
  - 含 `type === "playback_state"` + `snapshot` 对象 ⇒ **状态帧**（校验 7 字段形状齐全）→ 交**状态写通道**；
  - 否则 ⇒ 既有 **WM-1 事件帧**路径（`parsePushEnvelope` + 非法拒收，**逐字不变**）。
- `stores/usePetStore.ts`：**新增**写出口 `applyPlaybackSnapshot(snapshot)` ——
  **整份替换** `playback`（与 `setPlayback` 同语义、来源不同）；**天然幂等**（重复帧无副作用）。
- `hooks/useRuntimePush.ts`：仍是**唯一**接线点（PC-1 归属不变），仅多接一路。
- ⛔ **不在组件内做任何判定**（UB-3 / FCM）；**App 不新增 import**（RF-3 与两处
  App import 白名单守卫**不受影响**）。

### 4.5 待裁 fork

| # | fork | 选项 | 我的建议 |
|---|---|---|---|
| **F0** | **出站帧形态** | **a** 新增「状态帧」为**第二类**出站帧（须修订 WP-3）· **b** 保持"唯一 WM-1"，把状态塞进 `system` 事件的 `payload`（**否决**：前端须解读 payload = 触 PC-3「禁业务判定」，且 `applyPushEvent` 只写 `last_event`） | **a** |
| **F1** | **到期观察位置** | **A-1** `ws.py` 内 `asyncio.wait_for` 超时（原推荐）· **A-2** `PlaybackClock.deadline()` 精确唤醒（更"事件驱动"，但需暴露访问器 / 动行预算）· **A-3** 组合根后台任务（**否决**：需连接集合 ⇒ 破 WP-4 / WS-6） | **A-1**（原裁决）；**实现层 = A-1′**（见 §4.2，owner **E1** 追认） |
| **F2** | **状态帧载荷** | **B-1** 原样复用 `PlaybackState` 7 字段（**推荐**）· **B-2** 另造"精简状态"（新口径，前端须映射 ⇒ 更易漂移） | **B-1** |
| **F3** | **store 写口径** | **C-1** 新增独立写出口 `applyPlaybackSnapshot`（**推荐**）· **C-2** 复用 `setPlayback`（语义混淆：既有调用方是 `loadRuntimeData`） | **C-1** |
| **F4** | **「驱动 / 观察同源」范围** | **α** 本 CR **一并**把前端**触发**由 HTTP `/simulate` 改走 **WS 发送**（入站格式同为 WM-1 envelope，`adapter` **已支持**）⇒ **任意宠物**下均成立 · **β** 本 CR **限定默认宠物路径**（`selectedPetId = null` ⇒ WS 与 HTTP **共用单例**，成立；**显式选宠物**时 WS 连 per-connection 实例而驱动仍在单例 ⇒ **仍然冻结**，登记 U-6c） | **α** |

> ⚠️ **F4 是本 CR 的真正范围分水岭**。`DEFAULT_SELECTED_PET_ID = null` ⇒ **不选宠物时**
> WS 与 HTTP **共用同一 `get_pipeline()` 单例**，「观察」天然看到「驱动」的结果；
> 但 UI 里点「小橘」后 `selectedPetId = "cat_001"` ⇒ WS 改用 `?pet_id=cat_001` 的
> **per-connection 实例**，而 HTTP `/simulate` **仍写单例** ⇒ **L3 复现**。
> 对 demo 而言「选小橘」几乎是必然动作 ⇒ **只选 β 大概率等于没修**。

## 五、契约修订（**受权增量**）

### K1 —— 前置说明：本 CR 即冻结文档明文预留的「另出修订文档」

`phase2_websocket_push_boundary_decision.md` §Step 3（C-WP3 Resolution Record）末尾**逐字预留**：

> 「本裁决**未回改** WS-4 / WG-4 的已冻结条款（其**禁止项**继续有效；**字段数**经 **CR-1** 由 6 → 7）；
> **如需对 WS-4 / WG-4 做正式文字澄清，须另出修订文档（待授权）**。」

且该 §Step 3 已明确：WS-4 / WG-4 的「同构」**仅约束**「禁止新增播放字段」与「不扩张 PlaybackState」，
**不作为线上 frame schema**。⇒ 本 CR 的 K2 正是**回归其原文意图** + **行使该修订程序**。

### K2 —— WP-3 v1.0 → **v1.1**（出站帧形态）

- **现状（FROZEN）**：「出站帧**唯一形式** = **WM-1 envelope**」（`WP-3`）。
- **修订口径**：出站帧**有且仅有两类** ——
  1. **事件帧** = **WM-1 envelope**（恰 4 字段：`event_type`/`payload`/`timestamp`/`source`，**逐字不变**）；
  2. **状态帧** = 本 CR §4.3 形态（**载荷 = API-2 `PlaybackState` 7 字段原样**）。
- **存活禁止项逐字不变**：**不发送** `duration` / `progress` / `video_state` / `queue`；
  **不新增** envelope 字段；**不扩张** `PlaybackState`（仍 **7 字段**，此后不再扩张）。
- **同步**：`backend/app/platform/websocket_dispatcher.py` 头部第 25 行
  （现为 `❌ 增删 envelope 字段、❌ 发送 PlaybackState 快照`）修订为
  「❌ 增删 envelope 字段、❌ 发送**播放派生字段**（`duration`/`progress`/`video_state`/`queue`）；
  状态帧**只允许** API-2 的 7 字段快照」；`WS-4`（`phase2_websocket_boundary_decision.md`）
  与 §Step 3 同步登记。

### K3 —— WC-3 v1.1 → **v1.2**（到期推进时机）✅ **已落地（2026-09-29 A 笔）**

- **现状（v1.1，CR-3 授权）**：到期推进 = **读路径 + 事件受理路径**。
- **修订口径（落地版）**：**+ 连接作用域观察（connection-scoped observation）** 这一**触发时机**；
  ⚠️ 该时机**不新增推进实现**、**不构成第三类推进路径** ——
  它只是**服务端在连接内有界等待到期后调用既有读路径**（`pipeline.snapshot()` ⇒ 内部 `_expire_if_due()`）。
  ⛔ 措辞**不写「定时路径 / 定时器」**、**不写具体节拍数值**（属**实现参数**，**不进契约**）。
- **同时落地的两处限缩式修订（v1.2 的实质内容）**：
  1. 原文「该 side effect **不作为 push trigger** —— 不得触发任何 outbound push」→ **限缩为**：
     **不得**触发**事件帧** / **不得**触发**播放控制**语义；**但允许** observer 读快照 → 与**上一条已成功推送的状态帧**
     比对 → **仅变化时**推**状态帧**；
  2. 原文「事件受理路径的同一次 `apply_event()` **只推送该次受理事件的 WM-1 envelope**，到期推进**不产生帧**」
     → **限缩为**：到期推进**不产生事件帧**；其状态变化可由 observer 经**状态帧**同步。
     ⇒ **状态帧触发集 = 事件受理 + 到期观察**（**C1 冻结**）；**比较基准 = 上一条已成功推送的状态帧**。
- **原文三条理由逐条回应**：①「无对应 WM-1 事件类型」**仍成立**（不新增事件类型 / 不改 WM-1）；
  ②「违反 **WS-3**」**仍成立且已回避**（WS-3 逐字不变；连接内有界等待**非**刷新循环，**变化才推** ⇒ 无心跳流量）；
  ③「**推送节拍不可定义**」**已消解**（契约只要求「有界等待 + 变化才推」）。
- **落点**：`phase2_websocket_commit_point_decision.md`（**WC-3 §受权增量 + CR-6 修订记录**，v1.2）
  + `PROJECT_RULES.md` §十四 摘要（**WC-3 补注**）。**均已于 A 笔落地**。
- ⚠️ **连带未完成项（未获授权）**：`phase2_websocket_push_boundary_decision.md` §三 / §五 的
  「**本笔不修订 WC-3**」与版本指针「（v1.1）」**已陈旧** ⇒ **待后续授权笔追加更正注记**（已在 commit_point 文档 §六 登记）。

### K4 —— PC-2 / PC-4（前端推送通道）

| 条目 | 现状 | 修订口径 |
|---|---|---|
| **PC-2** | 消息格式 = **WM-1 envelope 逐字段保持**；非法拒收 | **按帧型分流**（事件帧 / 状态帧）；**事件帧的校验与拒收口径逐字不变** |
| **PC-4** | push 只写既有切片、**schema 零变化** | **新增第 2 条 push 写通道** —— 状态帧**整份写 `playback`**（仍是**既有切片**、**schema 仍零变化**） |
| **PC-3** | socket 回调**禁止**调用 API `refresh` / `loadRuntimeData`、禁止业务处理 | ⛔ **逐字不变**（本 CR 不碰） |

**落点**：`phase2_frontend_push_channel_decision.md`。

### K5 —— FS-3 / FS-1（store 写出口）

- **现状**：`usePetStore` 写出口 = `setPlayback` / `setRecentEvents` / `setStats` / `setSelectedPet`
  + `applyPushEvent`。
- **修订口径**：**新增** `applyPlaybackSnapshot`（**第 6 个**写出口）—— 仍**单一 store**、
  **不新建切片 / 字段 / 第二 store**、**不派生业务状态**、**不进组件**。
- **落点**：`step4_frontend_state_decision.md`。

### K6 —— 其他边界影响说明（**不修订，仅登记**）

| 契约 | 是否冲突 | 说明 |
|---|---|---|
| **API-2（`PlaybackState`）** | ✅ 不冲突 | **7 字段不变**；状态帧**原样复用**，零新增/零改名 |
| **FP-3 / FP-4** | ✅ 不冲突 | 不触 `<video>` 属性白名单；**不引入** `onEnded` / 本地播放状态 |
| **RF-1 / RF-2 / RF-3** | ✅ 不冲突 | `refresh` 仍是人工按钮的唯一来源；App 仍零 `useState` / 零定时器 / 零 API import |
| **UB-3 / UB-4 / UB-5** | ✅ 不冲突 | 状态帧**写入 store**，组件仍只做展示、仍只消费 `asset_url` |
| **RB-3 / RB-5** | ✅ 不冲突 | 未新增媒体元素；**零新依赖**、不触 Canvas / 动画系统 / Live2D |
| **QP-\*** | ✅ 不冲突 | 不新增/不改任何 HTTP query 参数（Q1/Q2 已裁"不需要宠物化"） |
| **MP-1 / MP-2 / MP-3** | ⚠️ 需登记 | **F4 = β**：不改 per-connection 装配，默认路径共用单例 ⇒ 无冲突但覆盖不全；**F4 = α**：后端 per-connection 装配**不动**，只把前端触发通道改走 WS ⇒ 无冲突 |
| **WS-5 / WS-6 · WL-\*** | ✅ 不冲突 | 新增的是**接收超时**（非 heartbeat、无出站 ping/pong）；**不 reconnect / 不 buffer / 不 replay** |
| **WM-1** | ✅ 不冲突 | **事件帧逐字不变**；状态帧是**另一类帧**，不改 envelope |
| **P1（`loop` 口径）** | ✅ 不冲突 | `loop` 仍由 `AssetManager` 给出、仍由前端**纯消费**（FP-1） |
| **AS-4（组合根 < 300 行）** | ⚠️ 需守住 | 本方案**不改** `pipeline.py`（274 / 余 **+26**）；若退 F1 = A-2 须**先算预算** |

### K7 —— WC-4 修订登记（**owner A2 授权新增**）✅ **已落地（2026-09-29 A 笔）**

- **目标**：**解除历史冲突，但保持边界** ——
  WC-4 原文「**不引入**独立订阅、长生命周期监听机制、后台任务（asyncio）、定时器」
  与本 CR 的连接内观察**字面冲突**，须澄清，**不得**借此放松连接模型。
- **必须表达（允许）**：
  **connection-scoped observer** + **await-timeout observation**
  （连接处理协程内、生命周期**不超过该连接**的**有界等待**到期观察；观察者**不持 socket**）。
- **必须表达（禁止）**：
  **global scheduler** · **background timer service** · **cross-connection task** ·
  **connection registry** · **broadcast manager**；
  以及任何**跨连接存活**、可被**独立调度或取消**的计时对象 / 后台任务。
- **绑定判据（可判定）**：观察者生命周期**严格 ⊂ 单条连接的处理协程** → 连接终止即终止、
  **无**跨连接共享状态、**无**可枚举连接的全局注册表。
- ⛔ **不得写入契约的内容（实现参数）**：**`asyncio timer`** / **`250ms timer`** 之类的
  **计时器类别**与**节拍数值** —— 它们是**实现笔参数**，**不是契约**。
- **原文四项禁令按「限缩式保留」处理**（**不整体删除**）：独立订阅 / 长生命周期监听机制**逐字保留**；
  「后台任务（asyncio）」「定时器」限缩为**禁脱离连接生命周期者 / 禁独立计时服务**。
- **落点**：`phase2_websocket_commit_point_decision.md`（**WC-4 §受权增量**）
  + `PROJECT_RULES.md` §十四 摘要（**WC-4 补注**）。**均已于 A 笔落地**。

### K8 —— WC-6 修订登记（**owner A2 授权新增**）✅ **已落地（2026-09-29 A 笔）**

- **目标**：解除历史冲突，**同时不删除历史冻结**。
- **采用方式**：**阶段冻结记录保留 + CR-6 授权解除注记** ——
  WC-6 原文（含「❌ 把 `snapshot()` 读路径纳入推送」及其历史时点引用）**全文逐字保留**，
  **只在其后追加**解除注记。
- ⛔ **禁止**：**直接改写历史阶段结论**（会破坏该清单的可追溯性）。
- **注记须含**：① 本条属 **Phase 2.2-7B-1 阶段** scope freeze（原文限定语「本阶段」），
  **不是**跨阶段永久禁令；② 该阶段结束后，其绝大多数条目已由后续已授权笔逐条解除
  （7B-2 / CR-1 ~ CR-6）⇒ 引用时**须守「本阶段」限定语**，其余条目**以其各自正式契约的现行版本为准**；
  ③ **仅第 6 条**（`snapshot()` 读路径纳入推送）**经 CR-6 显式解除**；
  ④ 与解除**同时保留**的边界：**禁**改变 `snapshot()` 的 **API 语义**（签名 / 返回结构 / 推进语义），
  状态帧**只消费**其返回值、**不新增参数 / 不新增返回字段**。
- **落点**：`phase2_websocket_commit_point_decision.md`（**WC-6 注记**）
  + `PROJECT_RULES.md` §十四 摘要（**WC-6 注记**）。**均已于 A 笔落地**。

> ⛔ **K3 / K7 / K8 的共同红线**：三者都只**追加**受权增量与注记，**原文一律逐字保留**；
> **实现参数（节拍数值、计时器类别）一律不入契约**。

## 六、是否影响 MVP

**是** —— 闭合 **Phase 1 P0 验收项 F5 / P4**（"动作播完回落待机"），且是 Q3 = A 下
**demo 可看性的分水岭**（报告 §5-Q3 / §4-L3）。

**范围严格限定（单一目的）**：
- 本 CR **只做"到期回待机"一件事**；
- **不含**「动作**开始**也走推送」为独立目标 —— 若 F4 = **α**，仅把**触发通道**改为 WS
  （复用**既有** `apply_event` 与**本 CR 新增的状态帧**），**不新增**事件语义。

## 七、回滚

```bash
git revert <CR 提交> <契约修订提交> <后端提交> <前端提交> <测试提交>
```

## 八、落地授权记录（owner 裁决，2026-09-28）

| # | 裁决点 | 结论 |
|---|---|---|
| **F1** | 到期观察位置（A-1 / A-2 / A-3） | ✅ **A-1**（`api/ws.py` 循环内带超时收帧；零改动 `pipeline.py` / `playback_state.py`）—— ⚠️ **实现层取值见下行** |
| **F1′** | **实现层方案**（owner 二次裁决 **2026-09-29**） | ✅ **A-1′**：**常驻收帧任务 + `asyncio.wait({task}, timeout=T)`**（超时**只观察、绝不取消在途收帧**；`finally` 显式回收）。**不是** `wait_for(receive_text)`、**不是** background scheduler（**A-3 仍否决**）。依据 **U-6a 实测**（见 §9）与 owner **E1 追认** |
| **F4** | 「驱动 / 观察同源」范围（α / β） | ✅ **α**（本 CR **一并**把前端事件触发由 HTTP `/simulate` 改走 **WS 发送**，使任意宠物下均成立） |
| **F0** | 出站帧形态（新增状态帧 / 塞进 `system` payload） | ⏳ **按推荐 a**（owner 未单独裁决；备选 b 已说明不可行 —— 触 PC-3 且 `applyPushEvent` 只写 `last_event`）。如有异议请指示 |
| **F2** | 状态帧载荷（B-1 / B-2） | ⏳ **按推荐 B-1**（原样复用 API-2 的 `PlaybackState` 7 字段；零新增字段）。如上 |
| **F3** | store 写口径（C-1 / C-2） | ⏳ **按推荐 C-1**（新增独立写出口 `applyPlaybackSnapshot`，整份替换、幂等）。如上 |

> ⚠️ **F0 / F2 / F3 未经 owner 单独裁决**，按 CR 内的推荐值采用；**若需改为备选，请在实现前指示**
> （三者与 F0 相关的契约修订范围（§五 K2）随之调整）。
> ⚠️ **A-3（组合根后台任务）已否决**：需连接集合 ⇒ 破 **WP-4 / WS-6**（未列入选项）。

## 九、附：待裁 / 未确认项（**本 CR 不解决**）

| # | 项 | 说明 |
|---|---|---|
| **U-6a** | ~~`asyncio.wait_for` 取消 `receive_text()` 的**丢帧 / 断线语义**~~ | ✅ **已实测并裁定（2026-09-29）**：`wait_for` **确会丢帧**（10ms 节拍连发 20 条 ⇒ **19/20**，丢第 1 条；根因 = 超时取消在途收帧吞掉**已交付 ASGI 队列但未返回**的消息）⇒ **owner E1 追认实现层改用 A-1′**（不取消在途收帧）。原「若不安全 ⇒ 退 **F1 = A-2**」**已被 E1 取代**（无需暴露 `PlaybackClock` 访问器、**不动行预算**） |
| **U-6b** | **TICK 取值**（建议 250 ms）与「服务端每连接定时读快照」的成本 | 单宠物 demo 下可忽略；**多连接**需重估（与 WP-4「单活动连接」现状一致） |
| **U-6c** | F4 = **β** 时，**显式选宠物**路径的 L3 **仍然存在** | 登记；根治须另 CR（或本 CR 直接选 α） |
| **U-6d** | 状态帧是否携带 **`seq` / 版本号**以支持乱序检测 | 本 CR 暂不加（**整份替换 + 幂等**已足够）；若后续需要另裁 |
| **U-6e** | **AI 标识 / 隐式标识** | 承接 CR-5 U-3；本 CR 不触 |
| **U-6f** | **Phase 3.2-B 人工试用（Task 1）** | `phase3_trial_acceptance_report.md` §2 仍待 owner 填写；**T1.2 的人眼现象**可为本 CR 提供直接证据 |
| **U-6g** | **`pet_selected_runtime_consistency`** | ✅ **owner 裁决（2026-09-29）：`= deferred`** —— **F4 = α 下显式选宠物路径的运行态不一致，不在 CR-6 #3（后端状态帧笔）内解决**。理由：HTTP `/simulate` 仍写 `get_pipeline()` **单例**，而 `?pet_id=` 走 **per-connection 实例** ⇒ 观察与驱动不同源。**登记备查、另行 CR** |
| **U-6h** | **文档陈旧项（一致性笔）** | ✅ **owner 裁决（2026-09-29）：`NOT NOW`** —— 暂不改 `phase2_websocket_push_boundary_decision.md`（§三 / §五 的「本笔不修订 WC-3」+ 版本指针）与 `phase2_websocket_boundary_decision.md`（**WS-4** 登记）⇒ 记入**后续「文档一致性笔」**统一处理 |

## 十、建议提交拆分（**待 owner 确认**）

| # | subject（逐字） | 文件 |
|---|---|---|
| 1 | `docs: add CR-6 for idle return push` | `docs/change_request/cr-6_idle_return_push.md` |
| 2 | `docs: revise WP-3 and WC-3 for state push` | `phase2_websocket_push_boundary_decision.md` · `phase2_websocket_commit_point_decision.md` · `phase2_websocket_boundary_decision.md` · `PROJECT_RULES.md` §十四 |
| 3 | `docs: revise push channel and store boundaries` | `phase2_frontend_push_channel_decision.md` · `step4_frontend_state_decision.md` |
| 4 | `feat: push playback state on action expiry` | `backend/app/api/ws.py` · `backend/app/platform/websocket_dispatcher.py` |
| 5 | `feat: apply pushed playback state` | `frontend/src/services/websocketClient.ts` · `frontend/src/types/push.ts` · `frontend/src/stores/usePetStore.ts` · `frontend/src/hooks/useRuntimePush.ts` |
| 6 | `test: cover idle return push` | 后端 / 前端测试（+ **同步既有守卫清单**） |
| 7 | `feat: trigger events over push channel`（**F4 = α 已裁 ⇒ 纳入范围**） | `frontend/src/hooks/usePetRuntime.ts` · `frontend/src/api/events.ts` |

> ⚠️ **笔数为预估**，须在实现前依据实际改动面核定；**守卫同步**（App import 白名单 / `COMPONENT_FILES` /
> `websocketPush` 守卫等）随实际改动追加。契约修订**独立可回滚**（§七）。

**实际执行状态（2026-09-29 更新）**：

| # | subject | 文件 | 状态 |
|---|---|---|---|
| 1 | `docs: add CR-6 for idle return push` | 本 CR 文档 | ✅ 已提交 **`10550f9`** |
| 2a | `docs: revise WP-3 for state push` | `phase2_websocket_push_boundary_decision.md` | ✅ 已提交 **`b9666bb`**（+108/−0；WP-3 v1.0 → **v1.1**） |
| 2b | **A 笔**（本笔，未提交） | `phase2_websocket_commit_point_decision.md`（v1.1 → **v1.2**）· `PROJECT_RULES.md` §十四 摘要 · **本 CR 文档**（K3 落地 + **K7 / K8** + wait_for 口径同步） | 🟡 **已完成待 commit** |
| — | `phase2_websocket_boundary_decision.md` 的 **WS-4 登记** | 同上 | ⛔ **未获授权 ⇒ 未做**（待后续授权笔） |
| 4 | `feat: push playback state on action expiry` | `backend/app/api/ws.py` · `backend/app/platform/websocket_dispatcher.py` | 🟡 已写、已过回归（**591 passed**）、**未提交** |
| 3 / 5 / 6 / 7 | 前端契约 · 前端实现 · 测试 · F4=α 触发通道 | 前端文件 | ⛔ 未开始（未授权） |

## 十一、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-28 | 首次提出（承接 `phase3_trial_acceptance_report.md` §7 根因取证与 owner「P0 = 修法 ①」授权；含 **WP-3 / WC-3 / PC-2·PC-4 / FS-3** 修订范围；5 项 fork 待裁） |
| v1.1 | 2026-09-28 | owner 裁决落地（**F1 = A-1** · **F4 = α**；F0/F2/F3 按推荐采用，标注未单独裁决）；F4 = α 使「切触发通道」由可选变为**纳入范围**；状态由「草案 · 待确认」→「已确认 · 尚未实现」 |
| v1.2 | 2026-09-29 | **二次裁决 + A 笔落地**：owner 裁 **A（CONTRACT_FIRST）· C1 · D1 · E1 · F4 = α**；新增 **§五 K7（WC-4 修订登记）/ K8（WC-6 修订登记）**；**K3 标记已落地**（WC-3 → **v1.2**，含**限缩式**修订 + 触发集 **C1**）；**§4.2 实现层改为 A-1′** 并同步 **U-6a 实测结论**（`wait_for` 丢帧 19/20）⇒ 全文 **5 处 `wait_for` 表述**与 **F1 选项表**已同步（新增 **F1′**）；新增 **§十 实际执行状态**表。**实现参数不入契约**（不写 `asyncio timer` / `250ms timer`） |
