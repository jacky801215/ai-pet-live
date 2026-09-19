"""Event Gateway（事件网关）—— 原始事件进入核心业务的唯一入口。

契约来源：

    - ``docs/development/step2_event_gateway.md``（v1.0 FROZEN）
    - ``docs/development/step2_event_schema.md``（v1.1 FROZEN）

职责：把「形态不确定的原始 dict」变成「形态确定的统一 Event」::

    raw dict  ->  EventGateway  ->  Event  ->  Interaction Engine

本模块**只做一件事** —— 调用 Event Model 完成校验::

    return Event.from_dict(raw_event)

本模块**不做**（越界即破坏分层）：

    - 字段补齐 / 字段转换 —— 唯一来源是 ``backend/app/models/event.py``
    - 平台判断           —— 平台差异只允许存在于 Adapter 内部
    - 规则判断           —— 属 Interaction Engine
    - 动作派发           —— 属 Action Engine
    - 数据保存           —— 属 Data Manager
    - 平台连接           —— 属 Platform Adapter
    - 任何 IO（文件 / 数据库 / 网络 / 线程）

.. note::
   **方法命名说明**：网关契约 v1.0 §2.1 将唯一入口方法冻结为 ``normalize``；
   Step 2.3 指令将其定义为 ``process``。本实现按 **Step 2.3 指令**命名为
   :meth:`EventGateway.process`。两者的对齐须走契约 §十二 变更管理流程
   （``change_request`` + 版本号递增），不得在本 Step 内静默改写已冻结文档。
"""

from __future__ import annotations

from app.models.event import Event

__all__ = ["EventGateway"]


class EventGateway:
    """事件网关：``raw dict`` → :class:`~app.models.event.Event`。

    **无状态（stateless）**：不缓存、不计数、不留上次输入。
    因此单例或每请求实例均可，行为完全一致。

    本类**不定义 ``__init__``** —— 不持有任何资源。
    禁止在此添加文件读取、网络连接、数据库连接或线程创建：
    测试必须能在零外部依赖的前提下构造网关。
    """

    def process(self, raw_event: dict) -> Event:
        """把原始事件 dict 转换为已校验的统一事件对象。

        本方法**等价于** ``Event.from_dict(raw_event)``。
        所有字段补齐（``payload`` → ``{}``、``user_name`` → ``""``、
        ``user_id`` → ``None``）与校验规则**全部归属于 Event Model**，
        此处不得重复实现 —— 补齐逻辑一旦出现两份必然漂移，
        且漂移表现为「网关放行的事件引擎认为非法」，不报错、极难排查。

        Args:
            raw_event: 原始事件字典（形态由 Adapter 产出，平台无关）。

        Returns:
            校验通过的统一事件对象。

        Raises:
            EventTypeInvalidError: ``EVENT_TYPE_INVALID``
            EventPayloadInvalidError: ``EVENT_PAYLOAD_INVALID``
            EventSchemaInvalidError: ``EVENT_SCHEMA_INVALID``

        异常**原样传播**：不改写 ``code``、不包装、不更换类型、不吞掉。
        调用方需要按 ``code`` 分流，因此网关不得引入任何新错误码。
        """
        return Event.from_dict(raw_event)
