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

    write_event(event_type, payload, action_name=None, *,
                user_id=None, user_name=None, pet_id=None, platform=None)  # 写 events 明细
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

#: 写 events 明细。
#: Step 4.3-B-2-L2（AS-2 授权的 Change Request）起，``events`` **九字段可完整落库** ——
#: 身份四列（``user_id`` / ``user_name`` / ``pet_id`` / ``platform``）不再是死字段。
_SQL_INSERT_EVENT = (
    f"INSERT INTO {TABLE_EVENTS} "
    "(event_type, user_id, user_name, pet_id, action_name, platform, payload, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
)

#: 查聚合行（**多宠物模式**：显式 pet 上下文的 DataManager → ``pet_id = ?``）。
#: 3.2-A（MP-3）裁决：「仅显式 pet 连接按 pet 写」。绑定严格对应
#: ``(stat_type, stat_key, pet_id)`` —— **禁止** ``(stat_type, stat_key, stat_key)``。
_SQL_FIND_COUNTER: str = (
    f"SELECT id FROM {TABLE_INTERACTIONS} "
    "WHERE stat_type = ? AND stat_key = ? AND pet_id = ? LIMIT 1"
)

#: 查聚合行（**单宠物兼容模式**：未提供 pet 上下文 → ``pet_id IS NULL``）。
#: 与 Phase 1 逐字一致；冻结读路径 ``stat_repository._SQL_SELECT_COUNTERS`` 亦按
#: ``pet_id IS NULL`` 读，故默认 / HTTP / 旧 WS 路径必须保持本分支（否则 `/api/stats` 读空）。
_SQL_FIND_COUNTER_LEGACY: str = (
    f"SELECT id FROM {TABLE_INTERACTIONS} "
    "WHERE stat_type = ? AND stat_key = ? AND pet_id IS NULL LIMIT 1"
)

#: 首次创建聚合行（created_at 与 last_time 同时落库；``pet_id`` 为 ``None`` 时落 ``NULL``）
_SQL_INSERT_COUNTER = (
    f"INSERT INTO {TABLE_INTERACTIONS} "
    "(stat_type, stat_key, value, pet_id, created_at, last_time) "
    "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
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


def _optional_str(value: Any) -> str | None:
    """规范可空文本列（身份字段 / 平台）。

    - ``None`` → 保留 ``None``（落 ``NULL``）；
    - ``str`` → **原样保留**，含空串 ``""``（事件契约规定 ``user_name`` 缺失补 ``""``，
      故 ``""`` 是合法值，**不得**被折叠成 ``NULL``）；
    - 其它类型 → 记日志后落 ``None``。

    设计取向：身份字段是**附加元数据**，非法值不应导致整行 ``events`` 丢写
    （丢行会让事件计数与明细不一致），故降级为 ``NULL`` 而非拒绝整次写入。
    """
    if value is None or isinstance(value, str):
        return value
    logger.warning("write_event 身份字段非字符串，按 NULL 落库 (%r)", value)
    return None


class DataManager:
    """互动数据写入与统计聚合。

    构造只依赖 ``Database``（不依赖任何上游模型 / 规则层）。
    """

    def __init__(self, database: Database, *, pet_id: str | None = None) -> None:
        """初始化。

        Args:
            database: 已初始化的 ``Database`` 实例（负责连接与事务）。
            pet_id: 聚合计数的**作用域**（MP-3，Phase 3.2-A）。

                - ``None``（默认）= 单宠物兼容模式：聚合行 ``pet_id`` 写 ``NULL``，
                  与 Phase 1 及冻结读路径 ``stat_repository`` **逐字一致**；
                - 非空 = 该 pet 的独立计数命名空间：FIND / INSERT 均按 ``pet_id = ?``。

                **只由组合根在「显式 pet 上下文」时注入**（``build_runtime(pet_id=...)``）；
                默认 / HTTP / 旧 WS 路径保持 ``None``，故统计读路径不受影响。
        """
        self._db = database
        self._pet_id = pet_id

    # -- 公开 API（仅此三个） ------------------------------------------------
    def write_event(
        self,
        event_type: str,
        payload: dict,
        action_name: str | None = None,
        *,
        user_id: str | None = None,
        user_name: str | None = None,
        pet_id: str | None = None,
        platform: str | None = None,
    ) -> None:
        """写一条 ``events`` 明细（九字段完整落库）。

        Args:
            event_type: 事件类型（``gift`` / ``comment`` / ``like`` / ``system``）。
            payload: 原始数据（序列化为 JSON 字符串后入库）。
            action_name: 已执行的动作名；``None`` 表示未命中动作（可空，D5）。
            user_id: 触发用户 ID。``None`` = 未知；**禁止**由本层补常量
                （``step2_event_schema.md`` §2.3：补 ``"anonymous"`` 会让独立用户数坍缩）。
            user_name: 触发用户昵称。``""`` 是**合法值**（事件契约规定缺失补 ``""``），
                与 ``None``（显式 ``null``）语义不同，本层**原样保留**。
            pet_id: 对外主键（由组合根提供，来源 ``AssetManager``，**不是**请求参数）。
            platform: 来源平台。Phase 1 由组合根固定传 ``"simulator"``。

        Returns:
            None。参数非法或写库失败时只记日志并返回，不抛异常。

        .. note::
            **向后兼容**（Step 4.3-B-2-L2，AS-2 授权的 CR）：身份四参数均为
            **keyword-only 且可选**；省略时四列落 ``NULL`` —— 与 Step 4.3-B-1
            的旧行为逐字一致，既有调用点**零改动**。
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
            (
                event_type,
                _optional_str(user_id),
                _optional_str(user_name),
                _optional_str(pet_id),
                action_name,
                _optional_str(platform),
                payload_json,
            ),
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
                if self._pet_id is None:
                    # 单宠物兼容模式（Phase 1 口径，pet_id IS NULL）
                    row = conn.execute(
                        _SQL_FIND_COUNTER_LEGACY, (stat_type, stat_key)
                    ).fetchone()
                else:
                    # 多宠物模式（MP-3）：FIND / INSERT 的 pet 绑定取**同一来源** self._pet_id
                    row = conn.execute(
                        _SQL_FIND_COUNTER, (stat_type, stat_key, self._pet_id)
                    ).fetchone()
                if row is None:
                    conn.execute(
                        _SQL_INSERT_COUNTER,
                        (stat_type, stat_key, value, self._pet_id),
                    )
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
