"""
Structured Logging for Lapwing
JSON-formatted logs for better analysis and monitoring.
"""

import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pythonjsonlogger import jsonlogger


class StructuredLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging"""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ):
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record["timestamp"] = datetime.utcnow().isoformat()

        # Add log level
        log_record["level"] = record.levelname

        # Add source
        log_record["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add service info
        log_record["service"] = "lapwing"

        # Rename 'message' to 'msg' to avoid conflict
        if "message" in log_record:
            log_record["msg"] = log_record.pop("message")


class LapwingLogger:
    """
    Structured logger for Lapwing.

    Usage:
        from lapwing.utils.structured_logging import LapwingLogger
        logger = LapwingLogger()
        logger.info("Server started", extra={"port": 8000})
        logger.error("API failed", extra={"error": str(e), "latency": 0.5})
    """

    def __init__(self, name: str = "lapwing"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Clear existing handlers
        self.logger.handlers.clear()

        # JSON formatter
        formatter = StructuredLogFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _log(self, level: str, message: str, extra: Dict[str, Any] = None):
        """Internal log method with structured data"""
        extra = extra or {}

        # Add context
        log_data = {"event": message, **extra}

        getattr(self.logger, level)(message, extra=log_data)

    def debug(self, message: str, **kwargs):
        self._log("debug", message, kwargs)

    def info(self, message: str, **kwargs):
        self._log("info", message, kwargs)

    def warning(self, message: str, **kwargs):
        self._log("warning", message, kwargs)

    def error(self, message: str, **kwargs):
        self._log("error", message, kwargs)

    def critical(self, message: str, **kwargs):
        self._log("critical", message, kwargs)


# Convenience functions

_lapwing_logger: Optional[LapwingLogger] = None


def get_logger() -> LapwingLogger:
    """Get or create global logger"""
    global _lapwing_logger
    if _lapwing_logger is None:
        _lapwing_logger = LapwingLogger()
    return _lapwing_logger


# Structured logging helpers


def log_api_request(method: str, path: str, latency: float, status: int, **kwargs):
    """Log API request"""
    get_logger().info(
        "api_request",
        method=method,
        path=path,
        latency_ms=round(latency * 1000, 2),
        status=status,
        **kwargs,
    )


def log_llm_call(
    provider: str, model: str, latency: float, tokens_in: int, tokens_out: int, **kwargs
):
    """Log LLM API call"""
    get_logger().info(
        "llm_call",
        provider=provider,
        model=model,
        latency_ms=round(latency * 1000, 2),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        **kwargs,
    )


def log_memory_operation(operation: str, memory_id: str, **kwargs):
    """Log memory operation"""
    get_logger().info(
        "memory_operation", operation=operation, memory_id=memory_id, **kwargs
    )


def log_emotion_change(old_eii: float, new_eii: float, trigger: str, **kwargs):
    """Log emotion change"""
    get_logger().info(
        "emotion_change",
        old_eii=old_eii,
        new_eii=new_eii,
        delta=round(new_eii - old_eii, 2),
        trigger=trigger,
        **kwargs,
    )


def log_proactive_trigger(intent_type: str, message: str, boredom: float, **kwargs):
    """Log proactive behavior trigger"""
    get_logger().info(
        "proactive_trigger",
        intent_type=intent_type,
        message_preview=message[:50],
        boredom=round(boredom, 2),
        **kwargs,
    )
