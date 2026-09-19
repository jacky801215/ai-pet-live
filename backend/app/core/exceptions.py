"""业务异常定义。

约定：
- 所有业务异常继承 PetLiveError
- 每个异常携带稳定的 ``code``，供 API 层与前端识别
- 异常不得导致进程退出（对应 PROJECT_RULES 第十一条）
"""

from __future__ import annotations

from typing import Any


class PetLiveError(Exception):
    """项目基础异常。"""

    code: str = "PET_LIVE_ERROR"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message: str = message
        self.context: dict[str, Any] = context

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的错误结构。"""
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = self.context
        return payload

    def __str__(self) -> str:  # pragma: no cover - 常规字符串输出
        return f"[{self.code}] {self.message}"


class InvalidRequestError(PetLiveError):
    """请求参数非法（缺失、类型错误、格式不合法）。"""

    code = "INVALID_REQUEST"


class AssetNotFoundError(PetLiveError):
    """资产未在元数据中登记。

    注意：此错误**不允许**通过自动拼接路径来兜底，
    必须显式失败（Step 1 验收标准 A2）。
    """

    code = "ASSET_NOT_FOUND"


class AssetFileMissingError(PetLiveError):
    """资产已登记，但物理文件不存在或不可读。"""

    code = "ASSET_FILE_MISSING"


class AssetMetadataError(PetLiveError):
    """无法从媒体文件读取元数据。

    触发场景：
    - 文件不存在
    - ffprobe 执行失败
    - 输出无法解析出 duration
    """

    code = "ASSET_METADATA_ERROR"


# ---------------------------------------------------------------------------
# 事件模型异常（Step 2.1-B）
#
# 语义分工明确，三者不得混用：
#   EVENT_TYPE_INVALID    event_type 缺失 / 空 / 非 str / 不在 Phase 1 白名单
#   EVENT_PAYLOAD_INVALID payload 类型错误（显式 null 等），或事件级 payload 字段不合规
#   EVENT_SCHEMA_INVALID  其余顶层结构问题（多余字段、user_id / user_name 类型错误）
# ---------------------------------------------------------------------------


class EventTypeInvalidError(PetLiveError):
    """``event_type`` 非法。

    依据：``docs/development/step2_event_schema.md`` v1.1 §五 情形 1–4。
    Phase 1 白名单为最小闭环集合：``comment`` / ``gift`` / ``like`` / ``system``。
    平台额外事件（``follow`` / ``share`` 等）须经 Change Request 进入契约后方为合法。
    """

    code = "EVENT_TYPE_INVALID"


class EventPayloadInvalidError(PetLiveError):
    """``payload`` 非法。

    触发场景：
    - 显式传入 ``payload: null``（空值必须传 ``{}``，不得静默修正）
    - ``payload`` 不是 ``object``
    - 事件级必填字段缺失（如 ``comment`` 缺 ``content``）
    - 出现该事件类型禁止的字段（如 ``comment`` 用 ``text``、``gift`` 用 ``count``）
    """

    code = "EVENT_PAYLOAD_INVALID"


class EventSchemaInvalidError(PetLiveError):
    """事件顶层结构非法。

    触发场景：
    - 顶层出现 4 个冻结字段之外的字段（平台字段上浮的兜底拦截）
    - ``user_id`` / ``user_name`` 类型既不是 ``str`` 也不是 ``None``
    """

    code = "EVENT_SCHEMA_INVALID"
