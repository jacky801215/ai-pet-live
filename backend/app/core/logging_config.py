"""统一日志配置。

对应 PROJECT_RULES 第十条：
- 所有核心模块必须记录日志
- 禁止使用 print 作为正式日志
- 统一使用 logging 模块
"""

from __future__ import annotations

import logging
import sys

LOGGER_NAMESPACE = "pet_live"

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level: int = logging.INFO, force: bool = False) -> None:
    """初始化根日志器。重复调用不会重复添加 handler。

    Args:
        level: 日志级别，默认 INFO。
        force: 为 True 时强制重建 handler（测试用）。
    """
    global _configured
    if _configured and not force:
        return

    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取带命名空间的日志器。

    Args:
        name: 模块名，通常传 ``__name__``（如 ``app.services.asset_manager``）。

    Returns:
        形如 ``pet_live.app.services.asset_manager`` 的 Logger。
        若传入的名称已带命名空间前缀，则不重复添加。
    """
    setup_logging()
    if name.startswith(f"{LOGGER_NAMESPACE}.") or name == LOGGER_NAMESPACE:
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")
