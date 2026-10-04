"""SQLite 连接与初始化封装。

职责边界：
- 只负责建表、连接、事务
- 不含任何业务规则（业务规则属于 services 层）
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """轻量 SQLite 封装。"""

    def __init__(self, db_path: Path | str, schema_path: Path | str | None = None) -> None:
        """初始化。

        Args:
            db_path: SQLite 文件路径。
            schema_path: 建表脚本路径，为 None 时跳过建表。
        """
        self._db_path = Path(db_path)
        self._schema_path = Path(schema_path) if schema_path is not None else None

    @property
    def db_path(self) -> Path:
        """数据库文件路径。"""
        return self._db_path

    def initialize(self) -> None:
        """创建父目录并执行建表脚本（幂等，可重复调用）。"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        if self._schema_path is None or not self._schema_path.exists():
            logger.warning("建表脚本不存在，跳过初始化: %s", self._schema_path)
            return

        sql = self._schema_path.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(sql)
        logger.info("数据库初始化完成: %s", self._db_path.name)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """提供事务化连接。

        正常退出自动提交；发生异常自动回滚后重新抛出。

        连接级 PRAGMA（**CR-7**，见 ``docs/change_request/cr-7_sqlite_wal_journal.md``）：

        - ``journal_mode=WAL``：写前日志模式，替代默认回滚日志；
          后者每次提交需多次 fsync（写/同步 journal → 写/同步 db → 删 journal → 同步目录），
          在慢 fsync 磁盘上可放大到数百毫秒。该属性**库级持久**，重复设置幂等。
        - ``synchronous=NORMAL``：WAL 下的推荐档位。相对 ``FULL`` 的代价是
          「主机断电 / OS 崩溃可能丢最近数次已提交事务」，但**不会损坏数据库**；
          本库为本地 demo 的统计载体，判定可接受。

        两条 PRAGMA 必须在**任何事务之前**执行（SQLite 规定 ``journal_mode`` 不能在事务内切换）。
        """
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("数据库事务回滚: %s", self._db_path.name)
            raise
        finally:
            conn.close()
