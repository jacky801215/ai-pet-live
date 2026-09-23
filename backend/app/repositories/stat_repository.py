"""``interactions`` 表**只读**仓储（统计聚合读路径）。

契约来源：

    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 = B**
    - ``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-3**
    - ``docs/development/step4_data_layer_decision.md``（v1.0 FROZEN）**D2 / D6**
    - ``docs/development/phase3_pet_scoped_http_api_decision.md``（v1.0 FROZEN）**MB-2 / MB-3**（pet 作用域**读侧**）

职责边界：

- **只读**：**只**提供 ``SELECT``；写入（``UPSERT value`` / ``last_time``）的
  **唯一出口**是 ``DataManager.aggregate_counter``（Step 4.2-B 冻结）。
- **口径冻结**（D6）：``interactions`` 是**全项目唯一统计载体**，
  ``stat_type`` 只允许 ``'event'``（事件计数）与 ``'action'``（动作计数）；
  ``stat_key`` 为事件类型或动作名。
  两个维度**必须**能直接从表结构派生 —— 因此本模块**不得**引入第二套统计口径，
  更**不得**改用固定 ``event_type`` 列。
- **Phase 1 单宠物**：``pet_id`` 恒为 ``NULL``（``aggregate_counter`` 不接收 ``pet_id``），
  故**默认查询条件**为 ``pet_id IS NULL``，与写入侧语义严格对齐。
- **Phase 3.2-B（pet 作用域读侧，`MB-2` / `MB-3`）**：``stats()`` 新增**可选** ``pet_id`` 形参 ——
  ``None``（默认 / 无 query）⇒ **逐字沿用** ``pet_id IS NULL`` 分支；非 ``None`` ⇒ ``pet_id = ?``，
  读**单一 canonical 桶**（**不聚合 alias**，P-1 = ①）。⛔ 写入路径**零变更**；WS 写侧**未**归一化。

.. note::
   表名与 ``stat_type`` 取值在本模块**本地定义**（``constants.py`` 本 Step 不可修改，
   与 ``data_manager.py`` 的处理方式一致）。漂移由 ``tests/test_api_contract.py``
   的「``aggregate_counter`` 写入 → ``stats()`` 读取」往返用例守住。
"""

from __future__ import annotations

from app.core.logging_config import get_logger
from app.repositories.db import Database

__all__ = ["StatRepository", "TABLE_INTERACTIONS", "STAT_TYPE_EVENT", "STAT_TYPE_ACTION"]

logger = get_logger(__name__)

#: 表名（与 ``database/schema.sql`` 一致）
TABLE_INTERACTIONS: str = "interactions"

#: ``stat_type`` 的两个合法取值（D6）
STAT_TYPE_EVENT: str = "event"
STAT_TYPE_ACTION: str = "action"

#: Phase 1 单宠物：聚合行 ``pet_id`` 恒为 ``NULL``（与写入侧一致）
_SQL_SELECT_COUNTERS: str = (
    f"SELECT stat_type, stat_key, value FROM {TABLE_INTERACTIONS} "
    "WHERE pet_id IS NULL ORDER BY stat_type, stat_key"
)

#: Phase 3.2-B（读侧）：显式 pet 作用域，读**单一 canonical 桶**（`MB-3`；绑定 ``(pet_id,)``）
_SQL_SELECT_COUNTERS_BY_PET: str = (
    f"SELECT stat_type, stat_key, value FROM {TABLE_INTERACTIONS} "
    "WHERE pet_id = ? ORDER BY stat_type, stat_key"
)


class StatRepository:
    """``interactions`` 表的数据访问对象（只读）。"""

    def __init__(self, database: Database) -> None:
        """初始化。

        Args:
            database: 已初始化的 ``Database`` 实例（负责连接与事务）。
        """
        self._db = database

    def stats(self, pet_id: str | None = None) -> dict:
        """读取互动统计（API-3 冻结结构）。

        Args:
            pet_id: **canonical** pet 作用域键；``None``（默认）= 原有 ``pet_id IS NULL`` 口径。
                ⚠️ 归一化（``cat → cat_001``）由 API 层完成，本层**只接收已归一化的键**
                （仓储不校验、不判断，与 ``event_repository`` 同一定位）。

        Returns:
            ``{"events": {event_type: int}, "actions": {action: int}, "total": int}``。

            - ``events`` / ``actions`` 由 ``interactions`` 的 ``stat_type`` 分流派生（D6）；
            - ``total`` = **事件计数之和**（``phase1_design.md`` §4.4 与 API-3 示例中，
              ``events`` 之和为 10、``total`` 亦为 10；动作是事件的**派生结果**，
              不计入 ``total``，否则同一互动会被重复计数）；
            - ``pet_id is None`` ⇒ 结果与 Phase 1 **逐字一致**（默认作用域不变量）。
        """
        events: dict[str, int] = {}
        actions: dict[str, int] = {}

        with self._db.connect() as conn:
            if pet_id is None:
                # 默认作用域：调用形态与 SQL 均**逐字保留**（A2=W / A3=S-1）
                rows = conn.execute(_SQL_SELECT_COUNTERS).fetchall()
            else:
                rows = conn.execute(_SQL_SELECT_COUNTERS_BY_PET, (pet_id,)).fetchall()

        for row in rows:
            stat_type = row["stat_type"]
            stat_key = row["stat_key"]
            value = int(row["value"] or 0)
            if stat_type == STAT_TYPE_EVENT:
                events[str(stat_key)] = value
            elif stat_type == STAT_TYPE_ACTION:
                actions[str(stat_key)] = value

        logger.debug("统计读取: %d 类事件 / %d 类动作", len(events), len(actions))
        return {"events": events, "actions": actions, "total": sum(events.values())}
