"""Structured logging configuration."""
import logging
import sys


class StructuredLogger(logging.Logger):
    def info(self, msg, *args, **kwargs):
        if kwargs:
            parts = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg = f"{msg} | {parts}"
        super().info(msg, *args)

    def error(self, msg, *args, **kwargs):
        if kwargs:
            parts = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            msg = f"{msg} | {parts}"
        super().error(msg, *args)


def setup_logging(level: str = "INFO") -> StructuredLogger:
    logger = StructuredLogger("syncguard")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = setup_logging()