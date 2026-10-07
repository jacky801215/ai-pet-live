"""资产元数据仓储。

职责边界：
- 只做数据存取（SQL 与对象映射）
- 不做参数校验、不做业务判断（属于 services 层）
"""

from __future__ import annotations

import sqlite3

from app.core.constants import TABLE_ASSETS
from app.core.logging_config import get_logger
from app.models.asset import AssetRecord
from app.repositories.db import Database

logger = get_logger(__name__)

_COLUMNS = "id, pet_type, action, path, duration, audio_path"


def _row_to_record(row: sqlite3.Row) -> AssetRecord:
    """将数据库行映射为 AssetRecord。"""
    return AssetRecord(
        id=row["id"],
        pet_type=row["pet_type"],
        action=row["action"],
        path=row["path"],
        duration=row["duration"],
        audio_path=row["audio_path"],
    )


class AssetRepository:
    """assets 表的数据访问对象。"""

    def __init__(self, database: Database) -> None:
        """初始化。

        Args:
            database: 已初始化的 Database 实例。
        """
        self._db = database

    def find(self, pet_type: str, action: str) -> AssetRecord | None:
        """按 (pet_type, action) 精确查找。

        Returns:
            命中返回 AssetRecord，未命中返回 None。
        """
        sql = (
            f"SELECT {_COLUMNS} FROM {TABLE_ASSETS} "
            "WHERE pet_type = ? AND action = ? LIMIT 1"
        )
        with self._db.connect() as conn:
            row = conn.execute(sql, (pet_type, action)).fetchone()
        return _row_to_record(row) if row is not None else None

    def list_by_pet(self, pet_type: str) -> list[AssetRecord]:
        """列出某个角色的全部资产。"""
        sql = (
            f"SELECT {_COLUMNS} FROM {TABLE_ASSETS} "
            "WHERE pet_type = ? ORDER BY action"
        )
        with self._db.connect() as conn:
            rows = conn.execute(sql, (pet_type,)).fetchall()
        return [_row_to_record(r) for r in rows]

    def list_all(self) -> list[AssetRecord]:
        """列出全部资产。"""
        sql = f"SELECT {_COLUMNS} FROM {TABLE_ASSETS} ORDER BY pet_type, action"
        with self._db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [_row_to_record(r) for r in rows]

    def upsert(self, record: AssetRecord) -> None:
        """插入或更新一条资产记录。

        这是验收 A3 的关键支撑：新增动作只需写入数据，无需改代码。

        **CR-11**：``audio_path`` 采用**全量覆盖**（``excluded.audio_path``）——
        本次未提供（``None``）即写 ``NULL``，**不**保留旧值（COALESCE）。
        理由：与「显式映射即事实」一致、可预测、``seed`` 结果 == 文件系统；
        且避免 ``--reset`` 与普通运行出现**不一致的清空语义**，或留下指向
        磁盘上已不存在音频的陈旧引用。契约见
        ``docs/change_request/cr-11_audio_feedback_design.md`` §4.1。
        """
        sql = (
            f"INSERT INTO {TABLE_ASSETS} "
            "(pet_type, action, path, duration, audio_path) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (pet_type, action) DO UPDATE SET "
            "path = excluded.path, duration = excluded.duration, "
            "audio_path = excluded.audio_path"
        )
        with self._db.connect() as conn:
            conn.execute(
                sql,
                (
                    record.pet_type,
                    record.action,
                    record.path,
                    record.duration,
                    record.audio_path,
                ),
            )
        logger.debug("资产已登记: %s/%s", record.pet_type, record.action)

    def upsert_many(self, records: list[AssetRecord]) -> int:
        """批量插入或更新。

        Returns:
            写入的记录条数。
        """
        for record in records:
            self.upsert(record)
        return len(records)

    def count(self, pet_type: str | None = None) -> int:
        """统计记录数，可按角色过滤。"""
        if pet_type is None:
            sql = f"SELECT COUNT(*) AS n FROM {TABLE_ASSETS}"
            params: tuple = ()
        else:
            sql = f"SELECT COUNT(*) AS n FROM {TABLE_ASSETS} WHERE pet_type = ?"
            params = (pet_type,)

        with self._db.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["n"]) if row is not None else 0

    def delete_all(self) -> int:
        """清空 assets 表。

        仅用于初始化脚本的 ``--reset`` 场景（重建元数据，不涉及素材文件）。

        Returns:
            被删除的记录条数。
        """
        sql = f"DELETE FROM {TABLE_ASSETS}"
        with self._db.connect() as conn:
            cursor = conn.execute(sql)
            removed = cursor.rowcount
        logger.warning("已清空 assets 表: %d 条记录", removed)
        return int(removed)
