"""Log ra stdout (cả log của uvicorn). Không log nội dung file người dùng tải lên."""

from __future__ import annotations

import logging.config


def setup_logging(level: str = "INFO") -> None:
    handler = {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "default"}
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s"}},
            "handlers": {"stdout": handler},
            "root": {"level": level.upper(), "handlers": ["stdout"]},
            "loggers": {
                name: {"level": level.upper(), "handlers": ["stdout"], "propagate": False}
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
            },
        }
    )
