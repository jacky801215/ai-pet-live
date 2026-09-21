# Phase 2.2-9-3 — WebSocket Production Hardening Gap Resolution Boundary (FROZEN)

> 版本：v1.0 FROZEN
> 来源：9-2 设计草案（`HR-1~HR-6`）原样升级冻结，编号不变。
> 性质：**仅边界冻结，不实现**。本文件不修改 runtime / frontend / 测试逻辑，不授权任何实现。
> 依赖冻结文档（均 v1.0 FROZEN）：WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR / OB / PH
> 编号空间：**HR-\***（9-2 引入，本阶段冻结；不与 PH-\* 混淆）

---

## 0. 地位与范围

- **HR-\*** = production hardening **gap resolution boundary**（生产加固缺口划界清单）：把 PH-4（G-R1~G-R4）/ PH-5（T-G1~T-G5）已登记但未解决的缺口**逐条划清边界**，而非解决或实现。
- **非** feature spec、**非**授权文件；**不授权**任何实现（实现授权在 9-4 另行裁决）。
- 本决策**只追加**边界条款，**不修改** WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR / OB / PH 任何上游冻结。
- 保持不变的冻结不变式：**WM-1 unchanged · event schema unchanged · transport behavior unchanged · frontend protocol unchanged · lifecycle ownership unchanged**。

---

## 1. HR-1 Exception Boundary（G-R1 Unexpected Exception）

> 调查证据：`backend/app/api/ws.py` L103–L120（内层 `try` 仅包 `adapter.handle()`；`receive_text`/`apply_event`/`send_event` 不在 try；唯一 `except WebSocketDisconnect`）。

- **冻结**：非 disconnect 异常（接收 / 编排 / 发送阶段）的 containment 归属 **transport robustness** 范畴（PH-1 类别），由 transport 端点层就地收敛为「干净断连」。
- **不改变** lifecycle ownership（WL-1：连接仍由 transport endpoint 协程栈帧独占）。
- **不改变** event schema（WM-1：不新增事件类型 / 不新增出站帧）。
- **显式记录（≠ 关系）**：
  - unexpected exception **≠** reconnect
  - unexpected exception **≠** retry
  - unexpected exception **≠** heartbeat
- 允许的最小 containment 方向（**仅方向**，实现属 9-4 授权范围）：端点 `while` 外层 `except WebSocketDisconnect` 之后追加 `except Exception: logger.warning + return`（不重连 / 不回滚已提交 mutation / 不向客户端发帧）。

---

## 2. HR-2 Mutation Atomicity Boundary（G-R2 Partial Mutation）

> 调查证据：`pipeline.apply_event`（L109–L143）内存态变更（`execute` L128 / `arm` L132 / `_last_event` L142）全在 `_record`（L134）之前；`DataManager` 三公开写入（`write_event` L117 / `record_action` L181 / `aggregate_counter` L198）经 `_safe_write`（L234）/ `try/except`（L219–L231）**全部吞异常**（D4 红线 C4）→ `_record` 永不抛、DB 失败静默丢写。

- **冻结**：partial mutation 作为**已登记问题**，**不解决**。
- 语义边界：运行时内存态（队列 / 状态机 / 时钟 / last_event）是权威源，DB 是 best-effort 持久化副作用，二者不保持事务一致（= PH-4 G-R2 runtime transaction scope）。
- **禁止**：
  - transaction rollback（在 `apply_event` 内加回滚内存态的 try/except）
  - atomic commit（两阶段提交 / 同步阻塞提交）
  - database redesign（为一致性改 `DataManager` / `events` / `interactions` schema）

---

## 3. HR-3 Client Disconnect Visibility Boundary（G-R3 Frontend Disconnect Awareness）

> 调查证据：`frontend/src/services/websocketClient.ts`（`connect()` 仅订阅 `message`，无 `close`/`error` 监听）；`useRuntimePush.ts`（`writeEnvelope` → `applyPushEvent`，无 try/catch）。

- **冻结**：frontend 断线感知是 **visibility gap（可见性缺口），不是 protocol gap（协议缺口）**。
- 语义边界：push 是 HTTP pull（RF-1 / RF-2）之上的 fire-and-forget 增强通道；断线时客户端回退到 pull，不要求前端感知 WebSocket 生命周期（= PH-4 G-R3 design-intentional，依赖 PC-3 push≠refresh）。
- **禁止**：
  - reconnect
  - heartbeat
  - connection state machine（在 store 引入连接状态字段 / 状态机）

---

## 4. HR-4 Logging Visibility Boundary（G-R4 Logging，继承 OB）

> 调查证据：传输层裸 `logging.getLogger(__name__)`；`setup_logging` 不配置 root ⇒ INFO 级传输日志被静默吞掉。

- **冻结**：logging 可见性缺口**继承 OB-6** 禁令。
- 语义边界：日志可见性修复被 OB-6（禁 logger framework / namespace 改造）明确禁止，须单独裁决，不在本阶段授权（= PH-4 G-R4 继承 OB-6）。
- **禁止**：
  - logger migration（迁移到统一 logger 体系）
  - framework change（改 `setup_logging` / 引入 `pet_live` 命名空间）
  - telemetry system（加 metrics / tracing / OpenTelemetry / connection id / delivery receipt）

---

## 5. HR-5 Test Gap Matrix（对应 PH-5 T-G1~T-G5）

> 调查证据：`tests/platform` 共 44 例，覆盖 reject / dispatcher 成功失败 / commit 后推送 / disconnect 无推送 / ws 驱动 runtime；缺口 T-G1~T-G5 仅登记。

- **冻结**：测试缺口划界如下。
- **允许未来（9-4 实现授权后，且不得改变任何冻结不变式）**：
  - **T-G1** network interruption → 服务端 abrupt 关闭行为（验证 HR-1：连接关闭、不崩溃、不回滚已提交 mutation）
  - **T-G3** malformed transport frame → 连接存活（验证 WA-4 / WC 拒收路径保活：经 `/api/ws` 发非法帧，断言连接继续、无出站帧）
- **不包含（被 PH-6 禁止或 out-of-scope）**：
  - T-G2 reconnect（PH-6 禁 reconnect）
  - T-G4 multi-client（PH-6 禁 multi-client / registry）
  - T-G5 soak / long session（PH-6 禁 retry/timeout，无 soak 框架）
- 新增测试（若 9-4 授权）不得改变 WM-1 / 事件 schema / transport 行为 / frontend 协议 / 生命周期所有权。

---

## 6. HR-6 Scope Freeze

- 本决策（HR-\*）**仅划界、不实现**；不修改 backend / frontend / 测试逻辑。
- **禁止**（逐项复述并强化既有冻结）：
  - WM-1 change（envelope 恰 4 字段）
  - event envelope change（出站帧 WM-1 形态不变）
  - lifecycle ownership change（连接 = transport endpoint 协程栈帧，WL-1）
  - frontend protocol change（push ≠ refresh，UI 只经 store，PC-2/PC-3/PC-5）
  - new dependency（后端 / 前端不引入新依赖）
  - metrics / tracing（OB-6 / PH-6 禁止）
- 继承并复述 PH-6 全部禁止项：reconnect / heartbeat / retry / timeout / auth / multi-client / logger framework change / protocol change / WM-1 change / envelope change / frontend telemetry。

---

## 7. Resolution Record

- **R-HR-1**：HR-\* 由 9-2 草案（`HR-1~HR-6`）原样升级为 FROZEN，编号不变（不复用 PH-\*）。
- **R-HR-2**：HR 只冻边界、不解决缺口、不实现；缺口补救（含 HR-1 端点 `except Exception` 兜底）须 9-4 单独授权。
- **R-HR-3**：HR 不修改 WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR / OB / PH；纯追加，不删不重排。
- **R-HR-4**（HR-1 专属）：HR-1 允许的最小 containment 方向（端点 `except Exception: log + return`）属 9-4 授权范围，但**不得**引入 reconnect / retry / heartbeat，且**不得**改变 WL-1 lifecycle ownership 与 WM-1 event schema。

---

## 8. 冲突矩阵（冻结时复核）

| 维度 | 结论 |
|------|------|
| HR ↔ PH | ✅ 互补：HR-1~HR-4 解决 PH-4（G-R1~G-R4），HR-5 解决 PH-5，HR-6 复述 PH-6 |
| HR ↔ OB | ✅ HR-4 继承 OB-6 禁令（logger migration / framework change / telemetry 全禁） |
| HR ↔ GR | ✅ G-R3 设计意图依赖 GR（HTTP pull 兜底）；HR-2 与 GR Option A 一致 |
| HR ↔ WE | ✅ HR-1 异常不新增事件源；WE「1 msg=1 commit=1 frame」不变 |
| HR ↔ WC / WP / WL / LI | ✅ 保持 WC-1 commit point、WC-4 per-message、WP-1/3/5 出站=WM-1/fail log、WL-1 生命周期=transport endpoint、LI-1/3 中性 dispatcher |
| 不变式 | ✅ WM-1 / 事件 schema / transport 行为 / frontend 协议 / 生命周期所有权 全部不变 |

> 本文件为 v1.0 FROZEN。实现授权在 9-4 阶段另行裁决；本阶段 STOP。
