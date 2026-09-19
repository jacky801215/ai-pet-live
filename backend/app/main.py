"""ASGI 入口（**全项目唯一**）。

契约来源：

    - ``docs/development/step4_api_runtime_decision.md``（v1.0 FROZEN）**DB-2 / DB-3 / DB-6**
    - ``docs/development/step4_api_implementation_boundary.md``（v1.0 FROZEN）**DA-3 / DA-5**

职责**仅此四项**（DB-3）::

    1. 构造 FastAPI 应用
    2. 注册 CORS 中间件（DB-6：白名单式放行本机 dev 源）
    3. 注册全局异常处理器（DA-3：PetLiveError 映射 + INTERNAL_ERROR 兜底）
    4. ``include_router``（路由本体在 ``app/api/**``）+ 静态素材挂载（DA-5）

**禁止**（越界即破坏分层）：

    - ❌ 业务逻辑（规则匹配 / 动作决策）
    - ❌ SQL 或任何 ``sqlite3`` 使用（SQL 只允许在 ``app/repositories/**``
      与 ``app/services/data_manager.py``）
    - ❌ 直接调用 ``ActionEngine`` / ``InteractionEngine`` / ``PlaybackManager``
      （引擎装配在 ``app/services/pipeline.py``，本模块**不 import 引擎**）
    - ❌ 直接持有 ``Database`` / 建表 / 初始化数据
    - ❌ 定义路由处理函数（路由属 ``app/api/**``）

启动::

    uvicorn app.main:app --reload

.. note::
   ``openapi_url`` / ``docs_url`` / ``redoc_url`` 一律关闭：本 Step 的边界明确
   「**不进入 OpenAPI 自动生成**」。如后续需要交互式文档，应由独立 Step 显式开启。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core import constants
from app.core.exceptions import (
    AssetFileMissingError,
    AssetNotFoundError,
    EventPayloadInvalidError,
    EventSchemaInvalidError,
    EventTypeInvalidError,
    InvalidRequestError,
    PetLiveError,
)
from app.core.logging_config import get_logger

__all__ = ["app", "create_app"]

logger = get_logger(__name__)

#: 应用元信息
APP_TITLE: str = "AI Pet Live API"
APP_VERSION: str = "0.1.0"

# ---------------------------------------------------------------------------
# 错误契约（API-4 冻结：只有 3 个 API 码）
# ---------------------------------------------------------------------------
CODE_INVALID_REQUEST: str = "INVALID_REQUEST"
CODE_ASSET_NOT_FOUND: str = "ASSET_NOT_FOUND"
CODE_INTERNAL_ERROR: str = "INTERNAL_ERROR"

_STATUS_BY_CODE: dict[str, int] = {
    CODE_INVALID_REQUEST: 400,
    CODE_ASSET_NOT_FOUND: 404,
    CODE_INTERNAL_ERROR: 500,
}

#: 业务细码 → API 契约码的**折叠表**（4.3-A API-4）
_INVALID_REQUEST_CODES: frozenset[str] = frozenset(
    {
        InvalidRequestError.code,
        EventTypeInvalidError.code,
        EventPayloadInvalidError.code,
        EventSchemaInvalidError.code,
    }
)
_ASSET_NOT_FOUND_CODES: frozenset[str] = frozenset(
    {AssetNotFoundError.code, AssetFileMissingError.code}
)
# 其余（AssetMetadataError / PetLiveError 基类 / 任意未捕获异常）→ INTERNAL_ERROR

# ---------------------------------------------------------------------------
# CORS（DB-6 = A：仅本机 dev 源，禁用 "*"）
# ---------------------------------------------------------------------------
CORS_ALLOW_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
CORS_ALLOW_METHODS: tuple[str, ...] = ("GET", "POST")
CORS_ALLOW_HEADERS: tuple[str, ...] = ("Content-Type",)

#: 静态素材挂载名（挂载点唯一，且**只**挂 ``assets/pets``）
STATIC_MOUNT_NAME: str = "assets"


def _fold_code(biz_code: str) -> str:
    """业务细码 → API 契约码（4.3-A API-4 折叠表；UI 不得依赖细码）。"""
    if biz_code in _INVALID_REQUEST_CODES:
        return CODE_INVALID_REQUEST
    if biz_code in _ASSET_NOT_FOUND_CODES:
        return CODE_ASSET_NOT_FOUND
    return CODE_INTERNAL_ERROR


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """统一错误体 ``{"code","message"}``（禁止堆栈 / 物理路径 / SQL 片段）。"""
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def _validation_message(exc: RequestValidationError) -> str:
    """把校验错误压缩为一行**不含内部路径**的说明。"""
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(
            str(item) for item in err.get("loc", ()) if item != "body"
        )
        parts.append(f"{loc or 'request'}: {err.get('msg', 'invalid')}")
    if not parts:
        return "请求参数非法"
    return "请求参数非法: " + "; ".join(parts)


def _register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理（DA-3）。

    - ``RequestValidationError`` → ``400 INVALID_REQUEST``（含 DA-7 未知字段、
      ``limit`` 越界 —— FastAPI 默认的 422 不在契约内，必须折叠）；
    - ``PetLiveError`` → 按折叠表映射状态码；
    - 其余未捕获 ``Exception`` → ``500 INTERNAL_ERROR``（堆栈**只进日志**）。
    """

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            400, CODE_INVALID_REQUEST, _validation_message(exc)
        )

    @app.exception_handler(PetLiveError)
    async def _on_pet_live_error(_request: Request, exc: PetLiveError) -> JSONResponse:
        code = _fold_code(getattr(exc, "code", "") or "")
        status = _STATUS_BY_CODE[code]
        if status >= 500:
            logger.exception("API 捕获业务异常: %s", getattr(exc, "code", ""))
        return _error_response(status, code, str(exc.message))

    @app.exception_handler(Exception)
    async def _on_unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("API 未捕获异常，已折叠为 INTERNAL_ERROR")
        return _error_response(500, CODE_INTERNAL_ERROR, "服务器内部错误")


def _register_cors(app: FastAPI) -> None:
    """注册 CORS（DB-6：白名单式，无凭证）。"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ALLOW_ORIGINS),
        allow_credentials=False,
        allow_methods=list(CORS_ALLOW_METHODS),
        allow_headers=list(CORS_ALLOW_HEADERS),
    )


def _mount_assets(app: FastAPI, static_dir: str | Path | None) -> None:
    """挂载静态素材（DA-5 = A）。

    **只**挂载 ``/assets/pets`` → ``<assets_dir>``；**禁止**挂载项目根
    （否则 ``database/pet_live.db``、``.env`` 会随 HTTP 裸露）。

    ``StaticFiles`` 要求目录存在，否则**导入即失败**。素材目录属运行所需目录，
    与 ``Settings.ensure_directories()`` 同口径：缺失时创建空目录，让应用先起得来
    （``4.3-B-0/DB-3`` 残留项 DB-R1 的落地口径）。
    """
    directory = Path(static_dir) if static_dir is not None else Path(constants.ASSETS_ROOT)
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(
        constants.ASSET_URL_PREFIX,
        StaticFiles(directory=str(directory)),
        name=STATIC_MOUNT_NAME,
    )


def create_app(*, static_dir: str | Path | None = None) -> FastAPI:
    """构造 ASGI 应用（工厂）。

    Args:
        static_dir: 静态素材根目录；``None`` 时使用项目真实目录
            ``<PROJECT_ROOT>/assets/pets``。**测试传入临时目录**以实现隔离
            （临时库 + 临时素材，绝不触碰真实 ``database/pet_live.db``）。

    Returns:
        已完成 CORS / 异常处理 / 路由 / 静态挂载配置的 ``FastAPI`` 实例。
    """
    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        # 本 Step 边界：不进入 OpenAPI 自动生成
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    _register_cors(app)
    _register_exception_handlers(app)
    app.include_router(api_router)
    _mount_assets(app, static_dir)

    logger.info(
        "FastAPI 应用已构造：%d 条路由，静态挂载 %s",
        len(app.routes),
        constants.ASSET_URL_PREFIX,
    )
    return app


#: ASGI 可调用对象（``uvicorn app.main:app``）
app = create_app()
