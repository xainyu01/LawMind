"""结构化日志配置 — 基于 structlog 输出 JSON 格式日志。"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """初始化 structlog，配置 JSON 渲染器和时间戳。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取绑定了模块名称的 logger 实例。"""
    return structlog.get_logger(name)
