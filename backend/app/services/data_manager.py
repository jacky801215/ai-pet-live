"""互动数据记录与统计聚合（Data Layer）。

契约：``docs/development/step4_data_layer_decision.md``（v1.0 FROZEN）—— D1 / D2 / D4。

职责边界（D4）：
- **只收基本类型参数**（``str`` / ``int`` / ``dict``），**不接收** ``Event`` /
  ``ActionCommand`` / ``PlaybackCommand`` 等模型对象，也不订阅任何事件流；
- **只做写入与聚合**，不做规则匹配（InteractionEngine）、动作执行（ActionEngine）、
  播放控制（PlaybackManager）—— 本模块对上游模型**零依赖**；
- 不承担 ``pet_id -> pet_type`` 映射（该职责归 ``AssetManager``，D2）；
- 写库失败必须记录 error 日志并**吞掉异常**，绝不中断播放与事件主流程（红线 C4）。

公开 API **只有三个**（指令 §五）::

    write_event(event_type, payload, action_name=None)   # 写 events 明细
    record_action(action_name)                            # 动作计数 +1
    aggregate_counter(stat_type, stat_key, value)          # 通用聚合（创建 / 累加）

统计口径（D2 / D6）：``interactions`` 是全项目唯一统计载体，
``stat_type`` 只允许 ``'event'``（事件计数）与 ``'action'``（动作计数）。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from app.core.logging_config import get_logger
from app.repositories.db import Database

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 私有常量（本 Step 不可修改 constants.py，故表名在此本地定义）
# ---------------------------------------------------------------------------
TABLE_EVENTS: str = "events"
TABLE_INTERACTIONS: str = "interactions"

#: interactions.stat_type 的允许取值（D2：关闭 E22 后的唯一口径）
STAT_TYPE_EVENT: str = "event"
STAT_TYPE_ACTION: str = "action"
_ALLOWED_STAT_TYPES: frozenset[str] = frozenset({STAT_TYPE_EVENT, STAT_TYPE_ACTION})

#: 写 events 明细
_SQL_INSERT_EVENT = (
    f"INSERT INTO {TABLE_EVENTS} (event_type, payload, action_name, created_at) "
    "VALUES (?, ?, ?, CURRENT_TIMESTAMP)"
)

#: 查聚合行是否存在（Phase 1 单宠物：pet_id 恒为 NULL，用 IS NULL 精确匹配）
_SQL_FIND_COUNTER = (
    f"SELECT id FROM {TABLE_INTERACTIONS} "
    "WHERE stat_type = ? AND stat_key = ? AND pet_id IS NULL LIMIT 1"
)

#: 首次创建聚合行（created_at 与 last_time 同时落库）
_SQL_INSERT_COUNTER = (
    f"INSERT INTO {TABLE_INTERACTIONS} (stat_type, stat_key, value, created_at, last_time) "
    "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)

#: 已存在的聚合行累加数值并刷新 last_time（created_at 保持不变）
_SQL_UPDATE_COUNTER = (
    f"UPDATE {TABLE_INTERACTIONS} "
    "SET value = value + ?, last_time = CURRENT_TIMESTAMP WHERE id = ?"
)


def _is_non_empty_str(value: Any) -> bool:
    """判断是否为非空（去空白后）字符串。"""
    return isinstance(value, str) and bool(value.strip())


def _is_int(value: Any) -> bool:
    """判断是否为整数（显式排除 bool —— bool 是 int 的子类）。"""
    return isinstance(value, int) and not isinstance(value, bool)


class DataManager:
    """互动数据写入与统计聚合。

    构造只依赖 ``Database``（不依赖任何上游模型 / 规则层）。
    """

    def __init__(self, database: Database) -> None:
        """初始化。

        Args:
            database: 已初始化的 ``Database`` 实例（负责连接与事务）。
        """
        self._db = database

    # -- 公开 API（仅此三个） ------------------------------------------------
    def write_event(
        self,
        event_type: str,
        payload: dict,
        action_name: str | None = None,
    ) -> None:
        """写一条 ``events`` 明细。

        Args:
            event_type: 事件类型（``gift`` / ``comment`` / ``like`` / ``system``）。
            payload: 原始数据（序列化为 JSON 字符串后入库）。
            action_name: 已执行的动作名；``None`` 表示未命中动作（可空，D5）。

        Returns:
            None。参数非法或写库失败时只记日志并返回，不抛异常。
        """
        if not _is_non_empty_str(event_type):
            logger.warning("write_event 忽略：event_type 非法 (%r)", event_type)
            return
        if not isinstance(payload, Mapping):
            logger.warning(
                "write_event 忽略：payload 不是映射 (%s)", type(payload).__name__
            )
            return
        if action_name is not None and not _is_non_empty_str(action_name):
            logger.warning("write_event 忽略：action_name 非法 (%r)", action_name)
            return

        try:
            payload_json = json.dumps(dict(payload), ensure_ascii=False)
        except (TypeError, ValueError):
            logger.exception("write_event 忽略：payload 无法序列化为 JSON")
            return

        self._safe_write(
            "write_event",
            _SQL_INSERT_EVENT,
            (event_type, payload_json, action_name),
        )

    def record_action(self, action_name: str) -> None:
        """记录一次动作触发（动作计数 +1）。

        语义等价于 ``aggregate_counter('action', action_name, 1)``（D4）——
        动作**只记聚合、不记明细**，本方法是与动作相关的**唯一**写入动作。

        Args:
            action_name: 动作名（``heart`` / ``happy`` / ``idle`` / ``sad`` / ``surprise``）。

        Returns:
            None。
        """
        if not _is_non_empty_str(action_name):
            logger.warning("record_action 忽略：action_name 非法 (%r)", action_name)
            return
        self.aggregate_counter(STAT_TYPE_ACTION, action_name, 1)

    def aggregate_counter(self, stat_type: str, stat_key: str, value: int) -> None:
        """更新 ``interactions`` 聚合行：不存在则创建，存在则累加（D2 / 指令 §六）。

        Args:
            stat_type: ``'event'`` 或 ``'action'``；其他取值一律拒绝。
            stat_key: 事件类型或动作名。
            value: 累加量（首次创建时即为该行的初值）。

        Returns:
            None。参数非法或写库失败时只记日志并返回，不抛异常。
        """
        if stat_type not in _ALLOWED_STAT_TYPES:
            logger.warning("aggregate_counter 忽略：stat_type 非法 (%r)", stat_type)
            return
        if not _is_non_empty_str(stat_key):
            logger.warning("aggregate_counter 忽略：stat_key 非法 (%r)", stat_key)
            return
        if not _is_int(value):
            logger.warning("aggregate_counter 忽略：value 非整数 (%r)", value)
            return

        try:
            with self._db.connect() as conn:
                row = conn.execute(_SQL_FIND_COUNTER, (stat_type, stat_key)).fetchone()
                if row is None:
                    conn.execute(_SQL_INSERT_COUNTER, (stat_type, stat_key, value))
                else:
                    conn.execute(_SQL_UPDATE_COUNTER, (value, row["id"]))
        except Exception:  # noqa: BLE001 - D4：写库失败不得中断主流程
            logger.exception(
                "aggregate_counter 写库失败（已忽略，不中断主流程）: %s/%s",
                stat_type,
                stat_key,
            )

    # -- 内部实现 -----------------------------------------------------------
    def _safe_write(self, where: str, sql: str, params: tuple) -> None:
        """执行单条写入语句并吞掉异常（D4：不得中断主流程）。"""
        try:
            with self._db.connect() as conn:
                conn.execute(sql, params)
        except Exception:  # noqa: BLE001 - D4：写库失败不得中断主流程
            logger.exception("%s 写库失败（已忽略，不中断主流程）", where)


__all__ = ["DataManager", "STAT_TYPE_EVENT", "STAT_TYPE_ACTION"]
