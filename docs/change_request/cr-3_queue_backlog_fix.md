# CR-3：修复 ActionEngine 队列堆积

> 变更请求（第三份正式 CR）。契约来源：`PROJECT_RULES.md` §七（CR 流程）· §十四。
> 前置：**阶段 B** 已先腾行数（`34f9f6e`，`pipeline.py` 298 → 267，余量 +2 → +33）。

## 一、现象

- 连续点按钮后**刷新页面**，动作错乱 —— 典型表现：`comment` 回显**上一次**动作（如 `happy`）；
  点 `gift` 也可能回显上一个动作而非 `heart`。
- 后端日志出现 `队列已满(3)，丢弃最旧`（被丢动作**静默消失**，UI 无任何痕迹）。
- **只有重启后端进程能清**：刷新浏览器无效。

## 二、根因（三个叠加 + 一个契约破坏）

| # | 根因 | 位置 | 影响 |
|---|---|---|---|
| **R1** | `apply_event` 在**仅入队（未 emit）**时也用新动作时长 `arm()` | `pipeline.py:148-153` | 覆盖当前动作**已到期**的窗口 ⇒ 头部动作滞留；且 `_record` 已按新动作写 `events.action` ⇒ **记录与画面不一致** |
| **R2** | `on_finished=None` ⇒ 出队**只**由 `snapshot()` 轮询驱动 | `runtime_factory.py:148`（刻意留空）· `pipeline.py:169` | 队列是进程内单例内存态 ⇒ 残留**跨刷新存活**，无 reset 通道；且 `_rearm_from_current()` 每步 arm 满时长 ⇒ **每次状态读最多推进 1 步** |
| **R2b** | `play` 两处早退直接 `return False`，**不经 `_fail()`** | `playback_manager.py:106-108` / `109-115` | 违反 **D3+D4**「成功与失败均触发 `on_finished`」；当前被「`on_finished` 恒为 None」掩盖，但一旦接线会让状态机**永久卡在 `playing`** |
| R3 | `comment` 无规则、`defaults` 仅 `{"gift": "heart"}` ⇒ `evaluate` 返 `None` | `interaction_engine.py:160-167` | **设计行为（F-2 已裁决：comment 只计数不触发动作），本 CR 不改** |

**R1 的关键细节（易误判，必须先钉死）**：`ActionEngine.execute()` 的返回值是**双语义** ——
「`True` = 指令已被接受（**已播放 或 已入队**）」（`action_engine.py:111-112`；实现见 L151-155，
仅 `_state == idle` 时才 `_emit`）。因此**不能**用 `execute()` 的返回值判断「是否真正 emit」；
**必须**在 `execute` **之前**读既有授权只读遥测 `engine_state(...)` 取 `was_idle`。

## 三、修复方案

### ① `pipeline.apply_event`：先 expire 再 execute，且**仅在真正 emit 时 arm**

```python
runtime = self._runtime
self._expire_if_due()                       # 新增：先推进已到期动作
command = runtime.interaction_engine.evaluate(event)

action_name: Optional[str] = None
was_idle = engine_state(runtime.action_engine) == STATE_IDLE   # 新增：只读预读
if command is not None and runtime.action_engine.execute(command, runtime.pet_id):
    accepted = str(getattr(command, "action_type", "") or "")
    if accepted:
        action_name = accepted
        if was_idle:                        # 新增：仅真正 emit 时才（重）备窗口
            self._playback_clock.arm(playback_duration_seconds(runtime, accepted))
```

- 「仅真正 emit 时 arm」治 **R1**：仅入队时**保留当前窗口**，不再抹掉到期时刻。
- 「先 expire 再 execute」治 **R2 的可观测面**：受理事件前先把到期动作出队，
  使 `was_idle` 反映**推进后**的真实状态 ⇒ 响应显示**本次**点击对应的动作，而非滞留的旧动作。
- 零新增 import（`engine_state` / `STATE_IDLE` / `playback_duration_seconds` 均已在 `pipeline.py` 的
  import 块内）。**净增 +7 行**（267 → **274**；余量 +33 → **+26**，仍 < 300）。

### ② `playback_manager.play`：两处早退改走 `_fail()`

- L106-108（`pet_id` 非法）、L109-115（`action_type` 非法）由 `return False`
  改为 `return self._fail(pet_id, action_type, "<原因>")`（`_fail` 签名 `(pet_id, action_type, reason) -> bool`，
  内含 `_notify(pet_id)`）。
- 补齐 **D3+D4**「成功与失败两条路径均触发 `on_finished`」。
- 附带：`api/playback.py:111` 已引用的语义不受影响；本项**不改**播放窗口架构。

### ③ 契约修订（**受权增量**，对应提交 4）

- `PROJECT_RULES.md` §十四 **WC-3** → **v1.1**：把「到期推进」的所有权由「**仅**读路径副作用」
  扩展为「**读路径 + 事件受理路径**」，同时**保留原禁令不变** —— 到期推进**仍不作为 push trigger**
  （无对应 WM-1 事件类型），推送节拍与可见性口径仍由既有 HTTP pull 承担（RF-1/RF-2 不变）。
- `docs/development/phase2_websocket_commit_point_decision.md` 同步 v1.1（WC-2 补注：
  `apply_event` 起始处的 `_expire_if_due()` 是**推进**而非新增 mutation 步骤；commit point 定义不变）。
- `docs/development/phase2_websocket_event_coverage_boundary_decision.md` 的 **E7** 标签校准：
  「snapshot expire」→「expire (read path + intake path)」，其**传输排除**结论不变。

## 四、不做的

- ❌ **不接线** `on_finished = ActionEngine.restore_idle` —— 会使 `execute()` 在**同一次调用内同步递归排空**
  队列 ⇒ 快照恒 `idle`，与 **API-2** 直接矛盾。本 CR **不改变「轮询驱动」架构**（只修 R2b 的契约破坏）。
- ❌ **不改 R3**（`comment` 无规则是 F-2 裁决的设计行为）。如需消歧，另立 UI 提示 / 契约澄清项。
- ❌ **不加 reset 入口**（原方案 ③）—— 触 `MP-5` 写侧未授权 + `QP-1` 只读白名单，须另裁 scope。
- ❌ 不新增依赖、不改 `database/schema.sql`、不改 `app/platform/**`、不改 `api/ws.py`。

## 五、影响模块

| 文件 | 变更 |
|---|---|
| `backend/app/services/pipeline.py` | ① + 注释同步（L77「只在状态查询时推进」随 ① 失效需更新）。**余量 +33，净增 ≤ +30** |
| `backend/app/services/playback_manager.py` | ② |
| `backend/tests/` | 同步 1 处锁定用例 + 新增用例（见下） |
| `PROJECT_RULES.md` §十四 | WC-3 → v1.1 |
| `docs/development/phase2_websocket_commit_point_decision.md` | WC-2/WC-3 同步 v1.1 |
| `docs/development/phase2_websocket_event_coverage_boundary_decision.md` | E7 标签校准 |

**测试同步（唯一锁定项）**：`backend/tests/test_playback_manager.py:163`
`test_invalid_command_does_not_notify` 断言 `finished.pet_ids == []`，② 后为 `[None]` ⇒ **必 FAIL**。
按裁决改写为**新语义**：失败路径同样通知（D4），`pet_id` 是否可用由**回调侧**裁定
（`ActionEngine.restore_idle` 对非法 `pet_id` 幂等忽略）。

**新增用例**：
1. **R1**：窗口已过期时入队 ⇒ 先 expire、本次点击动作为响应结果（连续两次 `simulate` + 推进时钟）；
2. **R1 反例**：窗口**未**过期时仅入队 ⇒ **窗口不被重置**（`deadline()` 不变）；
3. **R2b**：非法 `pet_id` / 非法 `action_type` ⇒ `on_finished` **均被触发**一次。

## 六、是否影响 MVP

**是** —— 直接影响用户体验（点击与画面不一致、刷新后动作错乱、动作静默丢失）。

## 七、回滚

```bash
git revert <实现提交> <测试提交> <契约修订提交>
```

## 八、落地授权记录（owner 裁决）

| # | 裁决点 | 结论 |
|---|---|---|
| **q-0** | ① 触冻结的 WC-3 | **纳入**，并**追加第 4 笔**契约修订提交（WC-3 → v1.1） |
| **q-1** | R1 的 emit 判据 | 按 **`was_idle` 预读**实现（不加 ActionEngine 公开信号，不破「公开 API 恰 execute + restore_idle」） |
| **q-2** | 既有锁定用例 | **改写** `test_invalid_command_does_not_notify` 为新语义 |
| 前序 | 阶段 B 腾行数 | 已完成并提交 `34f9f6e`（`pipeline.py` 298 → 267） |

## 九、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-24 | 首次提出（CR-3 立项 + 阶段 B 前置完成 + owner 3 项裁决落地） |
