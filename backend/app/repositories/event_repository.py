"""``events`` 表**只读**仓储（读路径）。

契约来源：

    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-1 = B**
    - ``docs/development/step4_api_contract_decision.md``（v1.0 FROZEN）**API-3**
    - ``docs/development/step4_data_layer_decision.md``（v1.0 FROZEN）**D1**

分层（DA-1 冻结）::

    API 层（app/api/**）
       ├─ 写路径 ─▶ DataManager（app/services/data_manager.py）── 唯一写入出口
       └─ 读路径 ─▶ EventRepository / StatRepository（app/repositories/**）
                         └─▶ Database（app/repositories/db.py）

职责边界：

- **只读**：本模块**只**提供 ``SELECT``；**禁止**写 ``events`` / ``interactions``。
  一切写入的**唯一出口**是 ``DataManager``（Step 4.2-B 冻结）。
- **基本类型**：返回 ``list[dict]``，**不引入新模型类**（DA-1 冻结）；
  ``payload`` 保持库内 JSON **字符串**形态，「字符串 → 对象」的反序列化由
  **API 层**完成（D1）。
- **不校验、不判断**：参数合法性（如 ``limit`` 越界）由调用方（API 层）负责 ——
  仓储只做 SQL 与行映射，与 ``asset_repository.py`` 同一定位。

.. note::
   表名在本模块**本地定义**（``constants.py`` 本 Step 不可修改，与
   ``data_manager.py`` 的处理方式一致）。两处是否会漂移，由
   ``tests/test_api_contract.py`` 的「DataManager 写入 → 仓储读取」往返用例守住。
"""

from __future__ import annotations

import sqlite3

from app.core.logging_config import get_logger
from app.repositories.db import Database

__all__ = ["EventRepository", "TABLE_EVENTS"]

logger = get_logger(__name__)

#: 表名（与 ``database/schema.sql`` 一致）
TABLE_EVENTS: str = "events"

#: 对外字段顺序（与 API-3 的 ``<EventItem>`` 9 字段一致）
_COLUMNS: str = (
    "id, event_type, user_id, user_name, pet_id, action_name, platform, payload, created_at"
)

#: 最近事件：``created_at DESC, id DESC``（API-3 冻结；同秒内按 ``id`` 兜底）
_SQL_LIST_RECENT: str = (
    f"SELECT {_COLUMNS} FROM {TABLE_EVENTS} ORDER BY created_at DESC, id DESC LIMIT ?"
)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """将数据库行映射为基本类型容器（不引入模型类，DA-1 冻结）。"""
    return dict(row)


class EventRepository:
    """``events`` 表的数据访问对象（只读）。"""

    def __init__(self, database: Database) -> None:
        """初始化。

        Args:
            database: 已初始化的 ``Database`` 实例（负责连接与事务）。
        """
        self._db = database

    def list_recent(self, limit: int) -> list[dict]:
        """查询最近 ``limit`` 条事件明细。

        Args:
            limit: 返回条数上限。**调用方**负责保证其合法性
                （API-3 冻结范围 ``1..200``）；本方法不做业务校验。

        Returns:
            事件行列表（每行为 ``dict``），按 ``created_at DESC, id DESC`` 排序；
            ``payload`` 为库内 JSON 字符串。
        """
        with self._db.connect() as conn:
            rows = conn.execute(_SQL_LIST_RECENT, (int(limit),)).fetchall()
        logger.debug("查询最近事件: limit=%s -> %d 条", limit, len(rows))
        return [_row_to_dict(row) for row in rows]
