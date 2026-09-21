# Phase 2.2-9-1 —— WebSocket Production Hardening Boundary（v1.0 FROZEN）

> **状态**：v1.0 FROZEN。本文件**只冻结边界，不授权任何实现**。
> 前置审计：`phase2_websocket_production_hardening_audit_draft.md`（Phase 2.2-9-0，只读 + 草案）。
> 前置冻结（均 v1.0 FROZEN）：WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR / OB。
> 编号空间：`PH-1 ~ PH-6`（由 9-0 草案原样保留；本步仅升级为正式冻结，编号不变）。
> 纪律：本阶段**不实现 hardening / 不修改 runtime / 不修改 frontend / 不修改测试逻辑**。

---

## 0. 冻结范围与纪律

本步仅将 9-0 审计结论**冻结为边界清单**。所有「缺口」均按 **Deferred / runtime-transaction-scope / design-intentional / 继承 OB-6** 四类状态登记，**本步不实现、不修代码**。

---

## 1. PH-1 ~ PH-6 边界条款

### PH-1 Production Hardening Ownership Boundary
Production Hardening 归属三类能力：
- **transport robustness**（传输健壮性）：连接接收 / 发送 / 异常处理的稳健性，归属 `api/ws.py` 与 `platform/websocket_dispatcher.py`；
- **dispatcher reliability**（推送可靠性）：出站帧组装与发送失败的收敛，归属 `websocket_dispatcher.py`；
- **client lifecycle resilience**（前端生命周期韧性）：连接启停 / 断线处理的稳健性，归属 `frontend/src/services/websocketClient.ts` + `hooks/useRuntimePush.ts`。

**不改变**既有所有权边界：
- **WC**（commit point）不变 —— `apply_event()` 返回前即提交的定义仍归编排内核；
- **WP**（dispatcher ownership）不变 —— 出站推送仍归 platform transport；
- **WL**（connection ownership）不变 —— 连接生命周期仍归 transport endpoint；
- **LI**（object ownership）不变 —— 连接对象仍为协程栈帧借参、dispatcher 仍中性。

### PH-2 Failure Classification Boundary
失败模式**冻结为四类**，每类归属明确、**禁止混合 ownership**：

1. **Transport Failure**（归属 transport）：`disconnect` · `receive failure` · `send failure`。
2. **Adapter Failure**（归属 adapter）：`reject` · `malformed input`（envelope 形状 / event_type 白名单 / payload 结构）。
3. **Runtime Failure**（归属 runtime）：`apply_event exception` · `mutation exception`（动作执行 / 数据记录期间的异常）。
4. **Client Failure**（归属 client）：`malformed envelope`（前端解析）· `store update failure`（applyPushEvent 失败）。

各类失败**只由归属层处理与记录**；**禁止**跨层 ownership 混合（例：transport 不得擅自改写 runtime 的失败语义，client 不得擅自接管 transport 的重连）。

### PH-3 Resource Safety Boundary
**冻结当前资源模型**：
- **connection = coroutine scoped**（连接 = 协程栈帧局部，随 endpoint 协程生灭）；
- **socket = borrowed reference**（socket 仅逐次借参传入，dispatcher / adapter 不持有）；
- **dispatcher = stateless**（仅持注入时钟与 logger，无连接态）。

**禁止**引入以下结构：
- connection **registry** / **ConnectionManager** / **broadcast manager**；
- **global socket state**（全局连接集合）；
- **hidden buffer**（消息缓冲队列）；
- **background lifecycle task**（后台连接管理 / 心跳 / 回收协程）。

### PH-4 Reliability Gap Boundary（登记但不实现）
已知可靠性缺口，按状态分类登记；**本步不实现**：

- **G-R1 · unexpected exception（Deferred）**：`apply_event()` 运行期异常原样传播 → 连接 abrupt 关闭（端点层无 `except Exception` 兜底、无日志）。
  状态：**Deferred**（修复须新增端点级捕获 + 日志，属 hardening 实现，须单独授权）。
- **G-R2 · partial mutation risk（runtime transaction scope）**：`mutation ↓ DataManager failure` 可能导致部分状态（内存态已变、写库丢失）。
  状态：**runtime transaction scope**（属 Phase 1 运行期事务边界关注，继承 WE-4 / GR Option A logged-not-solved；非 WS hardening 范围）。
- **G-R3 · frontend disconnect awareness（design intentional）**：前端无 `close`/`error` 监听 → 无法感知断线、`isConnected()` 在 socket 死后仍 `true`。
  状态：**design intentional**（PC-6 禁止重连；属可观测性缺口，非正确性问题）。
- **G-R4 · logger namespace / INFO visibility（继承 OB-6）**：传输 / 引擎模块用裸 `logging.getLogger(__name__)`（非 `pet_live` 命名空间）→ INFO 级日志被 root `lastResort` 吞。
  状态：**继承 OB-6**（observability 冻结已划出范围，**不进入本阶段**；修复须另行裁决）。

### PH-5 Testing Boundary
**冻结测试边界**：
- 回归基线：**backend 全量 511 passed**（当前基准，不得因本冻结步回退）。
- 已有覆盖（tests/platform，44 例）：dispatcher **success** · dispatcher **failure** · **reject** · **disconnect** · push **ordering**（commit 后推送 / 多消息顺序 / reject 不推送 / disconnect 不推送）。
- **缺口登记**（仅登记、本步不写测试）：**network interruption**（半包 / TCP reset / 非 disconnect 接收错误）· **reconnect**（反向不变量：PC-6 禁止，应断言幂等）· **concurrent clients**（多客户端隔离 / 无 registry 断言）· **malformed transport frame**（非文本 / 超大 / 控制帧）· **soak testing**（长会话 / 持续压入 / 经 WS 队列溢出 / 过期推进 / 内存增长）。

### PH-6 Scope Freeze
**禁止**以下实现（均须单独授权、另立决策文档）：
- **reconnect implementation** · **heartbeat implementation** · **retry implementation** · **timeout implementation**；
- **auth** · **multi-client**；
- **metrics** · **tracing**；
- **logger framework change**（含 namespace 修复，见 G-R4 / OB-6）；
- **protocol change** · **WM-1 change** · **envelope change** · **frontend telemetry**。

---

## 2. 冲突检查（PH ↔ 12 frozen spaces）

| PH 条款 | 触及 frozen | 判定 |
|---|---|---|
| PH-1 | WC-1/2、WP-1/2、WL-1/4、LI-1/3 | ✅ 一致（仅重申既有所有权，未扩张） |
| PH-2 | WA-4、WS-5/6、WP-5、WC-5、PC-2 | ✅ 一致（四类失败归属与既有处理层吻合） |
| PH-3 | WL-1、LI-1/3、WA-6、WS-6、WG-5 | ✅ 一致（冻结当前无状态模型，禁引入 registry/timer） |
| PH-4 G-R1 | WS-5/6、WP-5 | ✅ 一致（登记为 Deferred 缺口，未改代码） |
| PH-4 G-R2 | WE-4、GR-2/3/5 | ✅ 一致（runtime-transaction-scope，继承 logged-not-solved） |
| PH-4 G-R3 | PC-6、OB-2/6 | ✅ 一致（design-intentional，非正确性缺陷） |
| PH-4 G-R4 | OB-6 | ✅ 一致（继承 OB-6 范围，本步不修） |
| PH-5 | PC-6、WL-1、WS-6 | ✅ 一致（纯测试边界登记，未写测试、未实现多客户端） |
| PH-6 | 全部 12 + WM-1 | ✅ 一致（禁止项与既有冻结不冲突） |

**结论**：`PH-*` 不与任何已冻结条款矛盾；所有缺口显式标记为 Deferred / runtime-transaction-scope / design-intentional / 继承 OB-6，**未触发任何实现或语义修改**。

---

## 3. Resolution Record

- **R-PH-1**：9-0 草案 `PH-*` 原样保留、编号不变升级为 v1.0 FROZEN；草案内容全量并入本 decision。
- **R-PH-2**：PH = **production hardening boundary**（生产加固边界清单），**非** feature spec、**非**授权文件；**不授权**任何实现。
- **R-PH-3**：不修改 WS / WM / WA / WG / WP / WC / WL / LI / PC / WE / GR / OB；纯追加，不删不重排。
- **R-PH-4**：所有 hardening 实现（reconnect / heartbeat / retry / timeout / auth / multi-client / metrics / tracing / logger 修复）**必须**由单独、显式授权的决策文档承接。
