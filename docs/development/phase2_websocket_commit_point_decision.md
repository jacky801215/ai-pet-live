# Phase 2.2-7B-1 WebSocket Runtime Commit Point Decision v1.0（FROZEN）

> 状态：**FROZEN**（2026-09-21，Phase 2.2-7B-1 指令）
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

### WC-3 —— Snapshot Side Effect Boundary（冻结）

- `snapshot() → _expire_if_due() → ActionEngine.restore_idle()` 是**合法 runtime mutation**，
  但属 **read-path side effect**；
- **冻结：该 side effect 不作为 push trigger** —— 不得触发任何 outbound push；
- 原因：无对应 WM-1 事件类型（会迫使修订 WM-1 / PC-2）、读路径副作用违反 WS-3、推送节拍不可定义；
- 其可见性由**既有 HTTP pull**（RF-1/RF-2）承担；**本冻结不改变** RF-1/RF-2。

### WC-4 —— Transport Notification Boundary（冻结）

- **通知路径**：`apply_event()` 返回 → **transport 层**（`api/ws.py`，位于 `receive_text()` 循环内）
  取得该次受理结果 → 组装 **WM-1 envelope** → （**7B-2 实现**）发送；
- **禁**：pipeline 内发送、`SimulationPipeline` 持 socket、`WebSocketAdapter.send()`（WP-1 重申）；
- **触发生命周期 = per-message（每消息）**，**位于既有 inbound 处理周期之内**：
  `receive_text()` → adapter → `apply_event()` → commit → （7B-2）push；
  - **不引入**独立订阅、长生命周期监听机制、后台任务（asyncio）、定时器；
- transport **只**在其**自身**处理的 `apply_event()` 返回后推送（**当前单连接**，WP-4）；
  **不**为其它来源（如 HTTP `simulate`）的提交推送（本阶段无跨来源广播）。

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

## Step 4 冲突检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| **WC ↔ WG** | ✅ **无冲突** | WC-1/2 = WG-1/3 编排入口的**提交侧**落位；WC-4「责任方 = transport」= WG-3 逐字；WC-3 的「读路径非触发源」与 WG-3「编排入口唯一」一致 |
| **WC ↔ WP** | ✅ **无冲突（且为 WP-2 的必要补全）** | WC-1/2 **精确化** WP-2 的「runtime state commit point」；WC-4 遵守 WP-1（push 归 transport、禁 pipeline 持 socket / 禁 adapter.send）；WC-5 = WP-5 重申 |
| **WC ↔ PC** | ✅ **无冲突** | WC-4 产出帧 = WM-1 envelope（4 字段）= PC-2 消费契约；WC-3 使 push 仅沿事件路径 ⇒ 与 PC-4 的写入语义（envelope 派生 `EventItem`）一致 |
| **WC ↔ PlaybackState** | ✅ **无冲突** | 本决策不改变 PlaybackState **6 字段**；WC-3 明确不新增事件类型/字段 |
| 是否修改既有冻结 | **否** | WS/WM/WA/WG/PC/WP 全部保持原样 |
| 是否编号冲突 | **否** | `WC-*` 全仓 0 命中（创建前核查） |
| 是否 scope 扩张 | **否** | 仅定义 commit point 与通知边界；不引入任何机制 |

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

## 落地项（归 Phase 2.2-7B-2，须另行授权）

- **Runtime Commit Notification / Push Dispatcher 实现**：`apply_event()` → transport 组装 → `send()`；
- **envelope `timestamp` / `source` 取值口径**（**本步未冻结**）：
  adapter 已按 WM-1 在 normalize 时**丢弃** `timestamp`/`source`
  （`websocket_adapter.py:87-94`）⇒ 内部 `Event` **不含**二者。推送帧的 `timestamp`/`source`
  必须由 transport 侧定义（选项：回填原帧 / 以提交时刻 + `"ws"` 合成）—— **归 7B-2 裁决**；
- **推送帧与入库事件的对应关系**（是否复用接收到的 envelope）—— **归 7B-2**。

## 变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 FROZEN | 2026-09-21 | 首版冻结：WC-1 ~ WC-6 + Q1/Q2/Q3 调查与裁决（**commit point = `apply_event()` 返回前**，Candidate A；B/C 否决）；零代码变更 |
