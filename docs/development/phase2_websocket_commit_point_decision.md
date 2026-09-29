# Phase 2.2-7B-1 WebSocket Runtime Commit Point Decision v1.2（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-7B-1 指令；**CR-3** 修订 v1.1 = 2026-09-24：仅 WC-2 补注 + WC-3 触发路径扩张，push 侧禁令 / commit point 定义 / RF-1·RF-2 均不变；**CR-6** 修订 **v1.2** = 2026-09-29：**WC-3 / WC-4 / WC-6 追加受权增量**（出站帧**第二类 = 状态帧** + **连接作用域观察**），**commit point 定义 / WC-1 / WC-2 / WC-5 / RF-1·RF-2 均不变**，**WS-3 逐字不变**）
> 性质：**纯架构设计 / 冻结**——零代码、零依赖、零测试改动
> （**不**实现 notifier，**不**改 `pipeline.py`，**不**改 `ws.py`，**不**增加 `websocket.send`，**不**做 dispatcher）。
> 输入：`phase2_websocket_boundary_decision.md`（WS-*）、
> `phase2_websocket_event_model_decision.md`（WM-*）、
> `phase2_websocket_adapter_boundary_decision.md`（WA-*）、
> `phase2_websocket_runtime_integration_decision.md`（WG-*）、
> `phase2_frontend_push_channel_decision.md`（PC-*）、
> `phase2_websocket_push_boundary_decision.md`（WP-*，v1.0 FROZEN）。
> 编号空间声明：本文档使用 **`WC-*`**（创建前核查：全仓 `WC-` **0 命中**，无撞车；
> 与 WS/WM/WA/WG/PC/PB/RB/**WP** 互不重叠）。

## Input

- 指令：Phase 2.2-7B-1 —— 解决 Phase 2.2-7B-0 已识别的核心缺口：
  - **G-1** runtime state 无通知点；
  - **G-2** commit point 未精确化（`apply_event()` 与 `snapshot()` 读取路径存在差异）；
  - **G-3** pipeline 与 transport 无通知连接；
  - **G-4** push trigger 生命周期未定义。
- 前置检查：branch = `phase1-step1-foundation`，HEAD = **`dca8574`**，working tree **clean**；
  `WC-` 全仓 0 命中；8 份既有冻结文档齐备；目标文件不存在。

## Step 1 已核读冻结（关键条款）

| 来源 | 与本步相关的冻结要点 |
|---|---|
| **WS-2** | 消息必须转统一事件；唯一入口 `EventGateway.normalize()` |
| **WS-3** | **推送 ≠ refresh**；禁 WS 内 refresh 循环（**禁以推送之名行轮询之实**） |
| **WS-4** | PlaybackState **7 字段（CR-1）冻结**；推送不能增加派生字段 |
| **WG-1** | WS 事件唯一入口 = `normalize()`（与 HTTP 同一扇门） |
| **WG-3** | `normalize` 之后下一跳 = **`SimulationPipeline` 编排入口**；**责任方 = transport**；禁 adapter 调 pipeline；禁第二条编排入口 |
| **WG-5 / WG-6** | 单连接独立语义；scope freeze |
| **WP-1** | push 归 **platform websocket transport boundary**；禁 `ActionEngine` / `PlaybackManager` / `EventGateway` / **`SimulationPipeline`** 持 socket；**禁 `WebSocketAdapter.send()`**（adapter = inbound only） |
| **WP-2** | 触发点**必须位于 runtime state commit point 之后**；禁 `ActionEngine.execute()` 直连 `send()`；禁 `PlaybackManager` 持 socket 引用；**commit point 的精确定义归本步** |
| **WP-3** | 出站帧**唯一形式 = WM-1 envelope**（4 字段，事件形态） |
| **WP-4 / WP-5 / WP-6** | 单活动连接 + transport owns；失败只 log；scope freeze |
| **PC-2 / PC-4** | 前端消费 = **WM-1 envelope 逐字段保持**（4 字段）；由 envelope 派生 `EventItem` + 同步 `playback.last_event` |

## Step 1 只读调查（Q1 / Q2 / Q3）

### Q1 —— 事件型 commit point：runtime mutation 在哪一步完成

链路（`pipeline.apply_event()`，`pipeline.py:109-143`）：

```
EventGateway.normalize()                     ← WG-1 唯一入口（唯一事件入口）
  ↓ SimulationPipeline.apply_event()
    ├─ interaction_engine.evaluate(event)                     (pipeline.py:125)
    ├─ action_engine.execute(command, pet_id)                 (pipeline.py:128)  ← ① 状态机变更
    ├─ self._playback_clock.arm(...)                          (pipeline.py:132)
    ├─ self._record(...)  → DataManager 写入                   (pipeline.py:134-141)  ← ② 落库
    ├─ self._last_event = event.event_type                    (pipeline.py:142)  ← ③ 投影更新
    └─ return self.snapshot()                                 (pipeline.py:143)
```

| 子问题 | 回答 | 依据 |
|---|---|---|
| **哪一步代表 runtime mutation 完成？** | **`apply_event()` 返回前**（`pipeline.py:142` 为最后一次 mutation，随即 `return`） | ①②③ 全在该函数同步栈内完成 |
| **`ActionEngine` 状态变化何时稳定？** | **`action_engine.execute()` 返回时即稳定** | `execute()`（`action_engine.py:93-155`）为**同步**方法：置 `_state`(`151-152`) + `_pending.append`(`149`) + `_emit`(`153`) 全在返回前完成；`_emit`(`231-247`) 同步调 `playback_port`，而 `playback_port = playback_manager.play`（`runtime_factory.py:134`）**不会回调**引擎（`on_finished` 生产留空，`runtime_factory.py:133`）⇒ 无重入 |
| **Playback enqueue 何时稳定？** | 同上 —— **`execute()` 返回即稳定** | `_pending.append(playback)`（`action_engine.py:149`）同步完成；无异步/线程 |

> **结论 Q1**：runtime mutation 在 **`SimulationPipeline.apply_event()` 返回前**全部完成且稳定
> （无异步、无线程、无重入）。该函数返回点即**事件型 commit point**。

### Q2 —— 读取型变化是否属于 push source

- `snapshot()`（`pipeline.py:145-168`）在 `148` 行调用 `_expire_if_due()`（`205-232`），后者可能调用
  `ActionEngine.restore_idle(pet_id)`（`220`）⇒ **确实会变更 runtime state**（`playing→idle`、弹队首、续发）。
- 该 mutation 属于 **read-path side effect**：`snapshot()` **同时**是
  `GET /api/playback/state` 的读取入口（`api/playback.py:101`）与 `apply_event()` 的尾调用（`pipeline.py:143`）。

| 子问题 | 回答 |
|---|---|
| **是否属于 runtime mutation？** | **是**（技术上确实改变 `_state` / `_pending`） |
| **是否允许触发 outbound push？** | **否**（冻结为**不作为 push trigger**） |

**理由（三条）**：

1. **与 WP-3 冲突**：出站帧唯一形式 = **WM-1 envelope**（事件形态，`event_type` ∈
   `{comment,gift,like,system}`，WM-1）。到期回落**不是事件** —— 没有任何白名单内的 `event_type`
   能表达「播放结束」；要推送它就必须**新增事件类型** ⇒ 需修订 **WM-1（FROZEN）** 与前端白名单
   （`PUSH_EVENT_TYPES`，PC-2）⇒ 超出本步 scope；
2. **与 WS-3 冲突**：`snapshot()` 是**读路径**（含 HTTP GET）。读路径触发推送 = 让 transport 变成
   HTTP 读操作的副作用 ⇒ 正是 WS-3 所禁的「以推送之名行轮询之实」；
3. **不确定的推送节拍**：触发时机取决于**谁在何时读**，推送节奏不可定义、不可测试。

> **结论 Q2（预期冻结项）**：**`snapshot()` side effect 不作为 push trigger**（见 WC-3）。
> 到期回落仍是**合法 runtime mutation**，只是**不产生**出站帧。

### Q3 —— commit point 定义候选（裁决）

| 候选 | 内容 | 裁决 |
|---|---|---|
| **Candidate A** | `apply_event()` **返回前**作为 commit point | ✅ **采纳** |
| **Candidate B** | 引入 runtime mutation observer（`ActionEngine → RuntimeCommitNotifier → Transport`） | ❌ **否决** |
| **Candidate C** | 只监听 `DataManager` 写入 | ❌ **否决** |

**A 采纳理由**：
1. **单一事件入口**，与 **WG-1 / WG-3** 一致（编排入口唯一）；
2. **与 WS inbound 生命周期天然对应**：`receive_text → adapter → normalize → apply_event → commit`
   一个**每消息（per-message）**周期，无独立长生命周期机制；
3. **与 WP-3 的形式约束一致**：outbound frame = 事件 envelope ⇒ commit point 必须是**事件**提交点；
4. **零新增机制**：不需要 observer / 订阅 / 注册表。

**A 的已知取舍（须明示）**：**不覆盖** `snapshot()` 到期推进（Q2）—— 该变化不进推送。
其可见性由既有 **HTTP refresh（RF-1/RF-2）** 承担（pull 与 push 长期并存，WS-3）。

**B 否决理由**：① **超出本阶段 scope**（指令明示「风险：超出当前 scope 需要新增生命周期机制」）；
② 会触碰 **`ActionEngine` 已冻结的依赖契约**（`step3_action_engine_decision.md`：外部依赖**恰两个**
`asset_manager` / `playback_port`，且「唯一指令入口 = `execute`」）⇒ 属 Step 4 的
「**修改既有冻结**」STOP 条件；③ 与 **WP-1**（ActionEngine 不得参与 push 侧）相悖。

**C 否决理由**：① `DataManager` 是**写出口**而非 runtime state owner，用它当 commit point 造成
「事件已落库」与「状态已提交」语义错位；② `_record()`（`pipeline.py:134`）在 **`_last_event` 更新之前**
（`pipeline.py:142`）⇒ 会**提前**提交；③ **遗漏**播放态变化（`restore_idle` 不写库）。

## Step 2 Decision（冻结总表 WC-1 ~ WC-6）

### WC-1 —— Runtime Commit Point Ownership（冻结）

- **Runtime commit point = `SimulationPipeline.apply_event()` 返回前**（受理一条事件后的最终提交点）；
- **所有权归编排层（pipeline）**——即「何时算提交完成」由 `apply_event()` 定义；
- **推送所有权仍归 transport**（WP-1 不变）：pipeline **不**持有 socket、**不**发送；
- **禁**：任何第二 commit point 定义（不得以 `snapshot()` / `DataManager` 写入 / 引擎内部为提交点，Q3 已否决 B/C）。

### WC-2 —— Event Mutation Boundary（冻结）

- runtime mutation 的**完整集合**（全部发生在 `apply_event()` 返回前、**同步栈内**）：
  1. `ActionEngine.execute()` 返回 ⇒ **状态机（`_state`）与动作队列（`_pending`）稳定**；
  2. `DataManager` 写入完成（`write_event` / `aggregate_counter` / 可选 `record_action`）；
  3. `_last_event` 更新；
- **commit point = 上述三者全部完成之后**（即 `apply_event()` 返回点）；
- **禁**：在 ① / ② / ③ 任一步骤**之前**触发推送；**禁**将 `ActionEngine` / `PlaybackManager` 的
  内部实现细节当作 commit 信号（WP-1/WP-2 重申）。
- **CR-3 补注（v1.1）**：`apply_event()` **起始处**的到期推进（`_expire_if_due()`，见 WC-3）
  发生在 ① / ② / ③ **之前**，属**复用既有 mutation**（WC-3 授权），**不新增** commit 步骤、
  **不改变** commit point 定义（仍为 `apply_event()` 返回前）、**不产生**出站帧。

### WC-3 —— Snapshot Side Effect Boundary（**v1.2**，CR-3 + CR-6）

- `_expire_if_due() → ActionEngine.restore_idle()`（含 `_rearm_from_current()` 续发）是**合法 runtime mutation**；
- **触发路径 = 读路径 + 事件受理路径**（**CR-3** 增量）：
  - **读路径**：`snapshot()`（`GET /api/playback/state` 的读取入口，亦为 `apply_event()` 的尾调用）；
  - **事件受理路径**：`apply_event()` **起始处** —— 受理新事件前先推进**已到期**动作，
    使响应反映**本次**事件对应的动作，而非滞留的旧动作；
- **冻结不变（push 侧）**：该 side effect **不作为 push trigger** —— 不得触发任何 outbound push；
  原因：无对应 WM-1 事件类型（会迫使修订 WM-1 / PC-2）、读路径副作用违反 WS-3、推送节拍不可定义；
  事件受理路径的同一次 `apply_event()` 只推送**该次受理事件**的 WM-1 envelope（WC-4），到期推进**不产生帧**；
- 其可见性由**既有 HTTP pull**（RF-1/RF-2）承担；**本冻结不改变** RF-1/RF-2。

> **受权增量（CR-6 / 2026-09-29）—— WC-3 v1.1 → v1.2**：
> 以上冻结文字**逐字保留**；本节**只追加**「服务端**何时**去读」的**触发时机**，
> **不新增推进实现**、**不新增状态机**、**不构成第三类推进路径**
> —— 观察所调用的仍是**既有读路径** `pipeline.snapshot()`（其内部已含既有 `_expire_if_due()`）。
>
> 1. **新增触发时机 = 连接作用域观察（connection-scoped observation）**：
>    连接处理协程在**有界等待**（bounded await with timeout）到期、**该连接尚无入站消息**时，
>    调用**既有读路径**；**推进实现唯一**（与原文两路径复用同一个 `_expire_if_due()`），
>    **每次读最多推进 1 步**（不变）。
> 2. ⚠️ **限缩式修订（①）**：原文「该 side effect **不作为 push trigger** —— 不得触发任何 outbound push」
>    经 CR-6 明确为**限缩式** —— 该 side effect **不得**触发**事件帧**、
>    **不得**触发任何**播放控制**语义（**未**成为播放驱动通道）；
>    **但允许**：observer 读取快照 → 与**上一条已成功推送的状态帧**比对 →
>    **仅在该比对发生变化时**推送**状态帧**（状态帧 = **WP-3 v1.1** 的第二类出站帧；
>    性质 = **状态同步，非播放驱动**，见 §CR-6 修订记录）。
> 3. ⚠️ **限缩式修订（②）**：原文「事件受理路径的同一次 `apply_event()` **只推送该次受理事件的 WM-1 envelope**（WC-4），
>    到期推进**不产生帧**」经 CR-6 明确为**限缩式**：到期推进**不产生事件帧**；
>    其**状态变化**可由 observer 经**状态帧**对外同步。
>    ⇒ **状态帧触发集 = 事件受理（event accepted）+ 到期观察（expiry observed）**；
>    **比较基准 = 上一条已成功推送的状态帧**（**不是**「上一次 `snapshot()` 读值」）。
> 4. **原文三条理由的逐条回应（CR-6）**：
>    1. 「**无对应 WM-1 事件类型**（会迫使修订 WM-1 / PC-2）」⇒ **理由仍成立**：本增量
>       **不新增事件类型**、**不改 WM-1**、**不改 PC-2 的事件帧校验与拒收口径** ——
>       状态同步走**独立状态帧**，与事件帧**并存**而非扩张；
>    2. 「读路径副作用**违反 WS-3**」⇒ **理由仍成立，且已回避**：**WS-3**（「推送 ≠ refresh；
>       **禁以推送之名行轮询之实**」）**逐字不变**。本增量**不构成** refresh 循环 ——
>       观察是**连接处理协程内的有界等待**（**非**独立轮询循环、**非**客户端拉取），
>       且**仅变化时**才产生出站帧 ⇒ **不产生心跳流量**、**不做周期全量下发**；
>    3. 「**推送节拍不可定义**」⇒ **理由已消解**：契约只要求「**有界等待 + 变化才推**」，
>       **具体节拍数值属实现参数、不进契约**（**禁止**把毫秒值或计时器类别写入冻结条款）。
> 5. **不变项**：`_expire_if_due()` 的**推进实现** · **commit point 定义**（仍 = `apply_event()` 返回前）·
>    **每次读最多推进 1 步** · **RF-1 / RF-2 可见性路径**（HTTP pull **仍长期并存**，**不删除、不降级**）。
>    ⚠️ **本节未修改** `phase2_websocket_push_boundary_decision.md`；该文档 §三 / §五 的
>    「**本笔不修订 WC-3**」为该文档落笔时点（CR-6 第 2 笔）的结论，
>    **其版本指针与「不修订」表述已由本笔（v1.2）取代** ⇒ 已登记、**待后续授权笔追加更正注记**
>    （见 §CR-6 修订记录 §六 · 变更记录）。

### WC-4 —— Transport Notification Boundary（冻结）

- **通知路径**：`apply_event()` 返回 → **transport 层**（`api/ws.py`，位于 `receive_text()` 循环内）
  取得该次受理结果 → 组装 **WM-1 envelope** → （**7B-2 实现**）发送；
- **禁**：pipeline 内发送、`SimulationPipeline` 持 socket、`WebSocketAdapter.send()`（WP-1 重申）；
- **触发生命周期 = per-message（每消息）**，**位于既有 inbound 处理周期之内**：
  `receive_text()` → adapter → `apply_event()` → commit → （7B-2）push；
  - **不引入**独立订阅、长生命周期监听机制、后台任务（asyncio）、定时器；
- transport **只**在其**自身**处理的 `apply_event()` 返回后推送（**当前单连接**，WP-4）；
  **不**为其它来源（如 HTTP `simulate`）的提交推送（本阶段无跨来源广播）。

> **受权增量（CR-6 / 2026-09-29）—— WC-4 边界澄清（解除历史冲突，保持边界）**：
> 以上冻结文字**逐字保留**；本节**只澄清允许的实现形态**，
> **不扩张**通知路径的**所有权**（仍 = transport，WP-1 不变）、**不放宽**失败策略（WC-5 不变）。
>
> - ✅ **允许（connection-scoped observer + await-timeout observation）**：
>   **连接作用域**的观察者 —— 位于**该连接自身**的 `receive_text()` 处理周期内、
>   **生命周期不超过该连接**的**有界等待**（bounded await with timeout）到期观察；
>   观察者**不持 socket**（出站仍由 transport 侧 dispatcher 承担，**WP-1 / WP-4 不变**）。
> - ⛔ **禁止（逐项，本增量明确列举）**：
>   **global scheduler** · **background timer service** · **cross-connection task** ·
>   **connection registry** · **broadcast manager**；
>   并**禁止**任何**跨连接存活**、可被**独立调度或取消**的计时对象 / 后台任务。
> - **绑定判据（可判定）**：观察者的生命周期**严格 ⊂ 单条连接的处理协程** ——
>   **连接终止即终止**、**无**跨连接共享状态、**无**可枚举连接的全局注册表。
> - ⚠️ **原文四项禁令的「限缩式保留」**（逐项对照，**均未整体删除**）：
>   1. 「**不引入**独立订阅」⇒ **逐字保留**（本增量**不新增**订阅机制；连接自身处理协程内的观察**不是**订阅）；
>   2. 「**不引入**长生命周期监听机制」⇒ **逐字保留**（观察者生命周期 **⊂ 单条连接**，**非**长生命周期）；
>   3. 「**不引入**后台任务（asyncio）」⇒ **限缩式为**「**禁脱离连接生命周期的后台任务**」；
>      **允许**连接处理协程内、**不超过该连接**的收帧等待所需的**协程任务**（生命周期 ⊂ 连接，**显式回收**）；
>   4. 「**不引入**定时器」⇒ **限缩式为**「**禁独立计时服务 / 全局定时器**」；
>      **允许**连接内的**有界等待超时**（**非**独立计时器对象）。
> - ⛔ **实现参数不入契约**：**具体节拍数值**与**所用计时器实现类别**均属**实现笔参数**，
>   **禁止**写入本条冻结条款；本条只约束**形态与边界**。
> - **追加而非替换**：原文「触发生命周期 = **per-message**」**不变**；
>   本增量**追加**「**或无入站消息时的连接内到期观察**」这一**连接内**触发时机。

### WC-5 —— Failure Isolation（冻结）

- **推送失败不得影响 runtime mutation**：`apply_event()` 的状态变更 / 返回快照 / 落库结果
  均**不因**推送失败而改变（推送位于提交**之后**，失败不回滚、不重试）；
- 失败**只 log**（**WP-5 重申**）；**禁** retry / reconnect / buffer / ack / replay；
- **禁**把推送异常向上抛入 inbound 处理循环（不得使 WS 连接因推送失败而中断语义改变）。

### WC-6 —— Scope Freeze（冻结）

本阶段（7B-1）**禁止**：

- ❌ 实现任何 notifier / observer / 订阅机制；
- ❌ 修改 `pipeline.py` / `ws.py` / 任何 `backend/**/*.py`；
- ❌ 增加 `websocket.send()` 或 dispatcher；
- ❌ 修改 `frontend/**`（`.ts` / `.tsx`）/ `package.json`；
- ❌ 新依赖；
- ❌ 把 `snapshot()` 读路径纳入推送（WC-3 已正相反冻结）。

> **阶段冻结记录保留 + CR-6 授权解除注记（2026-09-29）**：
> 以上 WC-6 **全文逐字保留**（含其中「（WC-3 已正相反冻结）」这一**历史时点引用**），
> **不作任何改写** —— 篡改历史阶段结论会同时破坏本清单的**可追溯性**。
>
> - **时效限定语（原文即含）**：本条首句限定为「**本阶段（7B-1）禁止**」⇒
>   本清单是 **Phase 2.2-7B-1 阶段**的 scope freeze，**不是跨阶段永久禁令**。
> - **时效说明**：该阶段已结束；其绝大多数条目已由**后续已授权笔**逐条解除
>   （7B-2 实现笔已修改 `ws.py` 并新增 dispatcher；**CR-1 ~ CR-6** 各笔已依 `PROJECT_RULES.md` §七
>   逐笔授权修改 backend / frontend）。⇒ 引用本清单时**须以「本阶段」限定语为准**，
>   **不得**据其**跨阶段**主张禁止；各项的**现行**约束**以各自正式契约的当前版本为准**。
> - ✅ **CR-6 显式解除（仅第 6 条）**：「❌ 把 `snapshot()` 读路径纳入推送」一条**经 CR-6 解除** ——
>   允许 observer 读取快照后**仅在变化时**推送**状态帧**（见 WC-3 受权增量）。
> - ⛔ **与解除同时保留的边界**：**禁止**改变 `snapshot()` 的 **API 语义** ——
>   **签名 / 返回结构 / 推进语义**（`_expire_if_due()` 复用与「每次读最多推进 1 步」）**一律不变**；
>   状态帧**只消费**其返回值，**不为其新增参数、不新增返回字段**（**API-2 仍 7 字段**）。
> - **本节未解除**其余 5 条：它们**原有**的正式契约挂点（`WP-3` / `WS-4` / `WP-1` / `API-2` 等）
>   继续以其**现行版本**生效。

## Step 4 冲突检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| **WC ↔ WG** | ✅ **无冲突** | WC-1/2 = WG-1/3 编排入口的**提交侧**落位；WC-4「责任方 = transport」= WG-3 逐字；WC-3 的「读路径非触发源」与 WG-3「编排入口唯一」一致 |
| **WC ↔ WP** | ✅ **无冲突（且为 WP-2 的必要补全）** | WC-1/2 **精确化** WP-2 的「runtime state commit point」；WC-4 遵守 WP-1（push 归 transport、禁 pipeline 持 socket / 禁 adapter.send）；WC-5 = WP-5 重申 |
| **WC ↔ PC** | ✅ **无冲突** | WC-4 产出帧 = WM-1 envelope（4 字段）= PC-2 消费契约；WC-3 使 push 仅沿事件路径 ⇒ 与 PC-4 的写入语义（envelope 派生 `EventItem`）一致 |
| **WC ↔ PlaybackState** | ✅ **无冲突** | 本决策不改变 PlaybackState 字段（**CR-1** 起为 **7 字段**）；WC-3 明确不新增事件类型/字段 |
| 是否修改既有冻结 | **否** | WS/WM/WA/WG/PC/WP 全部保持原样 |
| 是否编号冲突 | **否** | `WC-*` 全仓 0 命中（创建前核查） |
| 是否 scope 扩张 | **否** | 仅定义 commit point 与通知边界；不引入任何机制 |
| **WC ↔ CR-6（2026-09-29）** | ⚠️ **本笔修订点** | **WC-3 / WC-4 / WC-6 追加受权增量**（出站帧**第二类 = 状态帧** + **连接作用域观察**）；**WC-1 / WC-2 / WC-5 逐字不变**；**commit point 定义不变** |
| **WC ↔ WS-3** | ✅ **无冲突（CR-6 逐条回应）** | **WS-3**（「推送 ≠ refresh；**禁以推送之名行轮询之实**」）**逐字不变**：观察 = **连接内有界等待**（**非**独立轮询循环、**非**客户端拉取），且**仅变化时**推 ⇒ **无心跳流量**、**无周期全量下发** |
| **WC ↔ WP-3（跨文档）** | ✅ **无冲突** | 状态帧 = **WP-3 v1.1** 的第二类出站帧（已于 CR-6 第 2 笔 `b9666bb` 修订；见 `phase2_websocket_push_boundary_decision.md` §CR-6 修订记录）；**WM-1 事件帧逐字不变** |
| **修改既有冻结（CR-6 范围更正）** | ⚠️ **是（限 WC-3 / WC-4 / WC-6）** | 上表「是否修改既有冻结 = **否**」为 **7B-1 / CR-3 时点**的结论，**逐字保留**；**CR-6 起**以本行**更正**：WS / WM / WA / WG / PC 仍**全部原样**，**WP-3 已于第 2 笔升 v1.1** |

**结论：本次冻结不需要修改任何既有冻结规则。**

## 设计验证清单（零代码变更，仅冻结）

| 检查项 | 结果 |
|---|---|
| `WC-*` 编号空间全仓 0 撞车 | ✅ |
| WC-1 commit point 唯一、所有权明确（pipeline 定义 / transport 发送） | ✅ |
| WC-2 mutation 三步全在 `apply_event()` 返回前（同步栈） | ✅ |
| WC-3 snapshot side effect **不**作为 push trigger（附三条理由） | ✅ |
| WC-4 通知路径 per-message、无新增生命周期机制 | ✅ |
| WC-5 推送失败不影响 mutation 结果、只 log | ✅ |
| WC-6 scope 清单完整（5 项禁止） | ✅ |
| 全部既有编号空间 0 修改 | ✅ |
| **CR-6**：状态帧触发集 = **事件受理 + 到期观察**，比较基准 = **上一条已成功推送的状态帧** | ✅ |
| **CR-6**：observer 生命周期 **⊂ 单条连接**（无 global scheduler / registry / broadcast） | ✅ |
| **CR-6**：`snapshot()` **API 语义不变**（签名 / 返回结构 / 每次读最多推进 1 步） | ✅ |
| **CR-6**：**WS-3 / WM-1 / WC-1 / WC-2 / WC-5 / RF-1 / RF-2** 逐字不变 | ✅ |

## 落地项（归 Phase 2.2-7B-2，须另行授权）

- **Runtime Commit Notification / Push Dispatcher 实现**：`apply_event()` → transport 组装 → `send()`；
- **envelope `timestamp` / `source` 取值口径**（**本步未冻结**）：
  adapter 已按 WM-1 在 normalize 时**丢弃** `timestamp`/`source`
  （`websocket_adapter.py:87-94`）⇒ 内部 `Event` **不含**二者。推送帧的 `timestamp`/`source`
  必须由 transport 侧定义（选项：回填原帧 / 以提交时刻 + `"ws"` 合成）—— **归 7B-2 裁决**；
- **推送帧与入库事件的对应关系**（是否复用接收到的 envelope）—— **归 7B-2**。

## CR-6 修订记录 —— idle return push（状态帧 + 连接作用域观察）（2026-09-29，受权增量）

> **依据（变更请求）**：`docs/change_request/cr-6_idle_return_push.md`（**CR-6**）§五
> **K3**（WC-3 v1.1 → **v1.2**）· **K7**（WC-4 修订登记）· **K8**（WC-6 修订登记）。
> **owner 裁决（2026-09-29）**：契约修订范围**含**本文件 **+** `PROJECT_RULES.md` §十四 摘要（**A1**）；
> **授权新增 K7 / K8**（**A2**）；**E1** 追认实现层方案 **A-1′**；**C1** 状态推送语义冻结为**双触发**。
> **性质**：**零代码**（本笔仅文档；代码归后续实现笔）。

### 一、允许项（本增量新增）

1. **出站帧第二类 = 状态帧** —— 由 transport 侧 dispatcher 组装/发送；
   载荷 = **API-2 `PlaybackState` 7 字段原样**（形态归 **WP-3 v1.1**，本文件不重复定义）；
2. **连接作用域观察**（connection-scoped observer）作为到期推进的**触发时机**（**非**第三类推进路径）；
3. **observer 读快照 → 与上一条已成功推送的状态帧比对 → 仅变化时推送状态帧**。

### 二、禁止项（本增量明确列举，逐条可判定）

1. **禁止**改变 **commit point** 定义（仍 = `apply_event()` 返回前）；
2. **禁止**改变 `snapshot()` 的 **API 语义**（签名 / 返回结构 / 推进语义）；
3. **禁止**新增推进实现 / 状态机 / 独立订阅 / 长生命周期监听机制；
4. **禁止** global scheduler · background timer service · cross-connection task ·
   connection registry · broadcast manager；
5. **禁止**由推送触发 `apply_event()` / `ActionEngine.execute()` / 队列变更
   （**推送仍是出站同步，非播放驱动通道**）；
6. **禁止**事件帧承载任何 `PlaybackState` 字段（**WM-1 恰 4 字段，逐字不变**）；
7. **禁止**把**实现参数**（节拍数值、计时器实现类别）写入冻结条款。

### 三、状态帧边界（**性质定义**）

**WS idle return push：**

> 是**状态同步机制**，**不是**播放驱动机制。

**状态来源**：`pipeline.snapshot()`（**而不是** new playback state machine）。
**载荷**：API-2 **7 字段原样**；`duration` / `progress` / `video_state` / `queue` **不发送**。

### 四、状态帧触发集与比较基准（**C1 冻结**）

| 项 | 冻结值 |
|---|---|
| **触发集** | **事件受理（event accepted）** + **到期观察（expiry observed）** |
| **比较基准** | **上一条已成功推送的状态帧**（**不是**「上一次 `snapshot()` 读值」） |
| **发送条件** | **仅变化时发送**（**禁**每 tick heartbeat / **禁**周期全量下发） |
| **推送失败** | **只 log**、**不回滚**、**不重试**（**WC-5 重申**） |
| **连接首帧** | **不推** —— 由**既有 HTTP `/state`** 承担初始化（登记 **`initial_state_frame = deferred`**，归前端笔处理前端状态入口） |

### 五、WS-4 / WG-4 与既有条款重申

| 条款 | 本增量后 |
|---|---|
| **WC-1 / WC-2** | ✅ **逐字不变**（commit point 与 mutation 三步同步） |
| **WC-5** | ✅ **逐字不变**（失败隔离：只 log、不重试、不上抛） |
| **WS-3** | ✅ **逐字不变**（本增量**不构成** refresh 循环；见 WC-3 受权增量理由 ②） |
| **WM-1** | ✅ **不变**（约束**仅**事件帧） |
| **RF-1 / RF-2** | ✅ **不变**（HTTP pull **仍长期并存**，**不删除、不降级**） |
| **API-2** | ✅ **不变**（仍 **7 字段**，**不扩张**，**不新增** `snapshot()` 参数） |
| **WP-1 / WP-2 / WP-4 / WP-5 / WP-6** | ✅ **不变**（push 归 transport；禁 registry / broadcast / 多连接） |

### 六、本笔**未触及**（登记，供后续笔核对）

| 项 | 状态 |
|---|---|
| `phase2_websocket_push_boundary_decision.md` §三 / §五 的「**本笔不修订 WC-3**」 | ⚠️ **已陈旧**（版本指针 + 「不修订」表述被本笔 v1.2 取代）⇒ **待后续授权笔追加更正注记**（**本笔未获该文件修改授权，故只在此外登记**） |
| `phase2_websocket_boundary_decision.md` 的 **WS-4 重申行** | **未修改**（**未获授权**）；其只约束**字段数**与「推送载荷与 API-2 同构」，与本增量**一致** |
| **PC-2 / PC-4**（前端推送通道：按帧型分流 + 状态写出口） | **未修订** —— 归 CR-6 **前端笔** |
| **FS-3 / FS-1**（store 写出口增项） | **未修订** —— 归 **前端笔** |
| **W-3-1（`apply_event()` 后不再刷新基线、改为 compare-and-push）** | ⚠️ **代码侧变更**（归**实现笔**；见本记录 §四 **C1** 冻结口径） |

### 七、变更记录

| 项 | 内容 |
|---|---|
| **原冻结约束** | ① **WC-3 v1.1**：到期推进 = 读路径 + 事件受理路径；该 side effect **不作为 push trigger**、**不得触发任何 outbound push**；**到期推进不产生帧**；② **WC-4**：通知路径 per-message；**不引入**独立订阅 / 长生命周期监听机制 / 后台任务（asyncio）/ 定时器；③ **WC-6**：7B-1 阶段 scope freeze（含「❌ 把 `snapshot()` 读路径纳入推送」） |
| **本次授权范围** | **仅**：① WC-3 → **v1.2**（追加连接作用域观察 + 限缩式修订两处 push 侧表述）；② WC-4 追加**边界澄清**（允许 connection-scoped observer；禁 global scheduler / timer service / cross-connection task / registry / broadcast）；③ WC-6 追加**阶段冻结保留 + 解除注记**（**不改写历史条目**）。**修订落点 = 本文件 + `PROJECT_RULES.md` §十四 摘要**。**零代码** |
| **不受影响范围** | **WC-1 / WC-2 / WC-5** 逐字不变；**commit point 定义**不变；**RF-1 / RF-2** 不变；**WS-3 / WS-4 / WM-1 / API-2 / WP-1/2/4/5/6** 不变；**组合根预算**未触（`pipeline.py` 274 / `playback_state.py` 224 **未改**） |

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 首版冻结：WC-1 ~ WC-6 + Q1/Q2/Q3 调查与裁决（**commit point = `apply_event()` 返回前**，Candidate A；B/C 否决）；零代码变更 |
| v1.1 FROZEN | 2026-09-24 | **CR-3**：WC-3 触发路径由「**仅**读路径副作用」扩张为「**读路径 + 事件受理路径**」（`apply_event()` 起始处先推进到期动作）；**push 侧禁令 / commit point 定义 / RF-1·RF-2 均不变**；WC-2 加补注。见 `docs/change_request/cr-3_queue_backlog_fix.md` |
| v1.2 FROZEN | 2026-09-29 | **CR-6**：WC-3 **v1.1 → v1.2**（追加**连接作用域观察**触发时机；**限缩式**修订「不作为 push trigger / 不产生帧」两处）；WC-4 追加**边界澄清**（允许 connection-scoped observer；禁 global scheduler / timer service / cross-connection task / registry / broadcast；四项旧禁令**限缩式保留**）；WC-6 追加**阶段冻结保留 + 解除注记**（历史条目**逐字不改**）；新增 **§CR-6 修订记录**。**WC-1 / WC-2 / WC-5 / commit point / RF-1·RF-2 / WS-3 不变**；**实现参数不入契约**。见 `docs/change_request/cr-6_idle_return_push.md` §五 K3 / K7 / K8 |
