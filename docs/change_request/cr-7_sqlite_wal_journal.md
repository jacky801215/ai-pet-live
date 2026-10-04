# CR-7：SQLite 写入性能修复（`journal_mode=WAL`）

> **类型**：性能修复 / 数据层连接配置
> **状态**：待实现
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

---

## 七、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-03 | 首次立档。基于 2-7 性能验收实测（`journal_mode=delete`+`synchronous=FULL` ⇒ commit p50 202–233 ms）提出：`db.py` 连接改为 `WAL` + `synchronous=NORMAL`。裁决：3 文件 · NORMAL 档 · 2 笔提交。 |
