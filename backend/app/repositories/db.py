"""SQLite 连接与初始化封装。

职责边界：
- 只负责建表、连接、事务
- 不含任何业务规则（业务规则属于 services 层）

连接生命周期（**CR-8**「连接复用」）：
- **按线程复用**一条长连接（``threading.local``），替代原先「每次操作 open + close」；
  后者在关闭时触发 WAL ``checkpoint`` 并删除 ``-wal``，在慢盘上使单次写入退化到数百毫秒。
- **跨线程不共享**：每个线程各自持有独立连接 —— 与 SQLite 默认
  ``check_same_thread=True`` 的线程约束一致，**不需要** ``check_same_thread=False``。
- 连接由 :meth:`Database.dispose`（测试 teardown）关闭，或随线程结束回收。
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """轻量 SQLite 封装（**CR-8**：线程内连接复用）。"""

    def __init__(self, db_path: Path | str, schema_path: Path | str | None = None) -> None:
        """初始化。

        Args:
            db_path: SQLite 文件路径。
            schema_path: 建表脚本路径，为 None 时跳过建表。
        """
        self._db_path = Path(db_path)
        self._schema_path = Path(schema_path) if schema_path is not None else None
        #: 线程私有连接缓存（``threading.local().connection``）。
        #: 每个线程首次 :meth:`connect` 时惰性创建，之后复用同一连接；
        #: 连接**不在**每次操作后关闭，由 :meth:`dispose` 或线程结束回收。
        self._local = threading.local()

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

    def _acquire(self) -> sqlite3.Connection:
        """返回**当前线程**的长连接；首次调用时创建并应用连接级 PRAGMA。

        连接级 PRAGMA（**CR-7**，见 ``docs/change_request/cr-7_sqlite_wal_journal.md``）：

        - ``journal_mode=WAL``：写前日志模式，替代默认回滚日志；
          后者每次提交需多次 fsync（写/同步 journal → 写/同步 db → 删 journal → 同步目录），
          在慢 fsync 磁盘上可放大到数百毫秒。该属性**库级持久**，重复设置幂等。
        - ``synchronous=NORMAL``：WAL 下的推荐档位。相对 ``FULL`` 的代价是
          「主机断电 / OS 崩溃可能丢最近数次已提交事务」，但**不会损坏数据库**；
          本库为本地 demo 的统计载体，判定可接受。

        两条 PRAGMA 必须在**任何事务之前**执行（SQLite 规定 ``journal_mode`` 不能在事务内切换），
        故放在连接**创建点**（首次获取）而非每次事务控制点。
        """
        conn: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.connection = conn
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """提供事务化连接（**CR-8**：线程内复用同一连接）。

        正常退出自动提交；发生异常自动回滚后重新抛出。

        与 CR-8 前的差异：**退出时不关闭连接** —— 连接被当前线程缓存复用，
        由 :meth:`dispose` 或线程结束回收。这样消除了「每操作 open + close」的固定开销，
        以及关闭连接触发的 WAL ``checkpoint``（其在慢盘上使单次写入退化到数百毫秒）。
        """
        conn = self._acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("数据库事务回滚: %s", self._db_path.name)
            raise

    def dispose(self) -> None:
        """关闭**当前线程**持有的连接并清除其缓存（幂等，可安全重复调用）。

        仅影响调用线程：其它线程的连接在各自线程结束、连接对象被回收时释放。
        生产入口（``main.py``）无应用生命周期钩子，故本方法主要供测试 teardown 调用，
        以避免长连接在 Windows 上占用临时库文件句柄。
        """
        conn: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if conn is not None:
            self._local.connection = None
            conn.close()
