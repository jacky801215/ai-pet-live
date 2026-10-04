# CR-7：SQLite 写入性能修复（`journal_mode=WAL`）

> **类型**：性能修复 / 数据层连接配置
> **状态**：**已完成（COMPLETE）**（2026-10-04）—— 交付与验收记录见 §八
> **日期**：2026-10-03
> **提出背景**：Phase 2 任务 **2-7（性能验收）** 实测发现
> **依据**：`PROJECT_RULES.md` §七（需求变更管理）
> **关联契约**：`docs/development/step4_data_layer_decision.md`（v1.0 FROZEN）—— **本 CR 不修改其任何条款**（该文档未冻结连接级 PRAGMA）

---

## 一、需求描述

把数据层 SQLite 连接从默认的 **回滚日志（`journal_mode=delete`）+ `synchronous=FULL`** 改为
**`journal_mode=WAL` + `synchronous=NORMAL`**，消除「每次提交多次 fsync」带来的写延迟。

**实测证据（只读实验，2026-10-03，同盘 D:）**：

| 模式 | 单行 `INSERT`+`commit` p50 | p95 |
|---|---|---|
| 现状 `delete + FULL` | **202.4 ms** | 319.0 ms |
| WAL + FULL | 45.7 ms | 120.9 ms |
| **WAL + NORMAL（本 CR 采用）** | **0.0 ms** | 0.0 ms |

实验脚本：工作区 `p2_7_wal_probe.py`（只读、零仓库改动）。

---

## 二、为什么需要

1. **2-7 性能验收被此项阻塞**：owner 本机复测（`out.json`，n=100 @100ms）显示
   发送→事件帧延迟 p50 **15421.7 ms**（判据 <500 ms），100 条仅落库 **43** 条。
   环境自校准 commit p50 = **233.4 ms** ⇒ 延迟判据因环境不达标而 **SKIP**，**2-7 无法判定为通过**。
   ⇒ 修复写延迟后，2-7 的延迟判据才可被真正断言。
2. **demo 手感**：事件落库在请求路径上，~200 ms/commit 使「连续触发」明显堆积（动作队列容量仅 3，
   满则丢弃最旧）⇒ 观众操作与画面反馈出现可感知滞后。
3. **根因定位明确**：`app/repositories/db.py::Database.connect()` 使用**裸 `sqlite3.connect()`**，
   未做任何 PRAGMA 调优；`delete` journal 每次提交需 **多次 fsync**（写/同步 journal → 写/同步 db → 删 journal → 同步目录），
   在慢 fsync 的磁盘上被放大到数百毫秒。

---

## 三、影响模块

| 模块 | 影响 |
|---|---|
| `backend/app/repositories/db.py` | **改动点**：`Database.connect()` 增加 2 条连接级 PRAGMA |
| `backend/tests/test_data_manager.py` | **新增 1 个测试**（断言连接为 `wal` + `synchronous=NORMAL`） |
| 数据层契约 `step4_data_layer_decision.md` | **不改动**；其冻结内容为表结构与 DataManager 边界，不含连接级 PRAGMA |
| `database/schema.sql` | **不改动**（表结构零变更） |
| 运行产物 | 新增 `*.db-wal` / `*.db-shm` 侧文件；`.gitignore` **已预置**对应规则（第 46–47 行）⇒ 不入库、不污染工作树 |
| API / 前端 / 播放链路 | **零影响**（仅底层写延迟下降） |

**架构合规**：SQLite 配置属 `app/repositories/**`（SQL / DB 的唯一归属层，见 `PROJECT_RULES.md` §十四）⇒ 不越层。

---

## 四、修改方案

`Database.connect()` 在建连后、进入事务前设置：

```python
conn = sqlite3.connect(str(self._db_path))
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")      # 写前日志：去掉回滚日志的多次 fsync
conn.execute("PRAGMA synchronous=NORMAL")    # WAL 下的推荐档位
```

**语义与权衡**：
- `journal_mode` 为**库级持久**属性（首次设置后写入库头），重复设置幂等；
- `synchronous` 为**连接级**属性 ⇒ 每次建连都设置；
- **`NORMAL` 档位在「主机断电 / OS 崩溃」时可能丢失最近若干次已提交事务，但不会损坏数据库**
  （与 `delete+FULL` 的「不丢」相比是持久性降级）。**判定**：本库是本地 demo 的**统计 / 明细载体**，
  非关键账务数据，丢最后一次提交无业务后果 ⇒ **可接受**；
- 两条 PRAGMA 必须在**任何事务之前**执行（SQLite 规定 `journal_mode` 不能在事务内切换）。

**不做**：不改表结构 / 不写 `schema.sql` / 不引入迁移框架（Alembic 等）/ 不改 DataManager 边界 / 不改 API。

---

## 五、是否影响 MVP 范围

**不影响**。本 CR 仅调整数据层**连接参数**，不新增/删除任何功能、不改任何对外契约
（事件四字段、`PlaybackState` 7 字段、API 错误码、event_type 白名单等均不变）。

---

## 六、验证方案

1. **静态守卫**：`tmp/cr6_guard_check.py`（后端静态守卫，全 `ok: true`）。
2. **后端全量回归（提交前）**：判据 `592 passed / 0 failed / 0 errors` + `safe_delete=False`
   （基线 591 → 新增 1 = 592）。
3. **行为验证**：新增测试断言 `PRAGMA journal_mode == "wal"` 且 `PRAGMA synchronous == 1`（NORMAL）。
4. **性能复验（owner 本机，可选但建议）**：重跑 `p2_7_local_acceptance.py`
   —— 期望 `env_calibration` 的 commit p50 降至毫秒级，且 **C5 延迟判据由 SKIP 转为 PASS**。

> **实际结果见 §八** —— 2026-10-04 最终验收：2-7 `overall = PASS`（C1–C5 全 PASS）。
> 注：本节为**立档时的验证计划**（原文逐字保留）；实施期新增的两项前置条件（连接生命周期、验收口径）见 §八。

---

## 七、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-03 | 首次立档。基于 2-7 性能验收实测（`journal_mode=delete`+`synchronous=FULL` ⇒ commit p50 202–233 ms）提出：`db.py` 连接改为 `WAL` + `synchronous=NORMAL`。裁决：3 文件 · NORMAL 档 · 2 笔提交。 |
| v1.1 | 2026-10-04 | **状态同步为「已完成（COMPLETE）」**；追加 **§八 交付与验收记录**（交付链 · 失败复跑记录 · 最终验收）；§六 追加指向 §八 的结果注记。**§一–§六 原文逐字保留**（初始问题 / WAL 设计背景 / 失败复跑记录一律不删）。 |

---

## 八、交付与验收记录（2026-10-04）

### 8.1 交付链（问题 → 修复 → 验证 → 完成）

| # | 阶段 | 提交 | 内容 |
|---|---|---|---|
| ① | 立档 | `080283b` | 本 CR 文档（裁决：3 文件 · NORMAL 档 · 2 笔提交） |
| ② | 修复 | `f4eae37` | `db.py` 加 `PRAGMA journal_mode=WAL` + `synchronous=NORMAL`；`test_data_manager.py` +1 测试 |
| ③ | 复跑 | — | ⚠️ **未达目标**（`overall=PASS_未含延迟`）⇒ 根因纠正见 8.2 |
| ④ | 补齐连接生命周期 | `fded328` | 连接复用（`Database` 改 thread-local 持久连接）。**独立提交**；按 owner 裁决不并入本 CR 的提交面 |
| ⑤ | 验收口径对齐 | `9ba2469` | `p2_7_local_acceptance.py` 的 `env_calibration` 由「原始 fsync」改为 **app 真实写入路径** |
| ⑥ | 完成 | — | 2-7 **`overall = PASS`**（C1–C5 全 PASS） |

### 8.2 失败复跑记录（2026-10-04，**保留**）

CR-7 单独交付后首次复跑 `p2_7_local_acceptance.py` **未达目标**：
`overall = PASS_未含延迟`（事件帧 **28/100**、延迟 p50 **15842 ms**、`env_calibration` p50 **222.5 ms** ⇒ C5 SKIP）。

**根因纠正**：瓶颈**不在** journal fsync，而在 **「每操作新建连接」** —— `Database.connect()` 原先每次操作
`open` + `close`，**关闭时触发 WAL `checkpoint` 并删除 `-wal`**。同盘（D:）实测：

| 形态 | commit p50 |
|---|---|
| 单连接**持久** + WAL/NORMAL | **0.0 ms** |
| 每操作**新建连接** + WAL/NORMAL | 221–234 ms |
| 每操作**新建连接** + delete（= 本 CR 前） | 155–168 ms |
| 纯 `open`+`close`（无写） | 0.6 ms |

⇒ WAL 在**旧的「每操作新建连接」访问模式**下反而比 `delete` 慢约 66 ms。
**本 CR 的 journal / synchronous 配置本身正确且必要**（0 ms 优势需在连接复用后才显现）；
缺失的一环是**连接生命周期**（建连/断连频率），由 `fded328` 补上。

### 8.3 最终验收（2026-10-04）

- **验收工具**：`backend/scripts/p2_7_local_acceptance.py`（修订后入库于 `9ba2469`）；
  其 `env_calibration` 已对齐 **app 真实写入路径**（直接调用项目 `Database.connect()`）。
- **app 写入路径实测**：`journal_mode=WAL` + `synchronous=NORMAL` + **thread-local 连接复用**
  ⇒ commit **p50 = 0.0 ms**（对照诊断：raw fsync 单连接 `delete/FULL` p50 = **260.8 ms**，仅作环境画像保留）。
- **2-7 验收结果：`overall = PASS`（rc = 0）** —— **C1–C5 全 PASS**：

| 项 | 实测 |
|---|---|
| 事件帧 | **100 / 100**（丢帧 0，drain_ratio 1.0） |
| 落库增量 | **100 / 100** |
| 延迟 | **p50 = 1.0 ms / p95 = 2.0 ms** |
| RSS delta | **−3140 KB**（无泄漏） |
| 排空后 `/api/stats` | 17.6 ms（baseline 45.7 ms） |
| 到期→idle | 4720.2 ms |

- **回归**：后端全量 **596 passed / 0 failed / 0 errors / `safe_delete=False`**；静态守卫全 `ok: true`。

> ⚠️ **登记（待裁）**：完成判定由 **CR-7（配置）** + **`fded328`（连接生命周期）** + **`9ba2469`（验收口径）** 三者共同达成；
> 其中连接复用一笔**无独立 CR 文档**（当时按指令直接实现，仅以提交承载）。是否补立 CR 文档，待 owner 裁决。

