#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一日志：滚动文件日志 + 可选控制台输出。

要点
----
* 日志文件写在**系统应用数据目录**（见 `guardian.paths`），不污染项目目录，
  也不受打包后程序目录只读的影响。
* 滚动保留：单文件 500KB，最多留 3 个历史文件，避免长期运行撑爆磁盘。
* 幂等：重复调用 `get_logger()` 不会重复添加 handler。

用法::

    from guardian.logging_setup import get_logger
    log = get_logger(__name__)
    log.info("检测到 %d 处风险", len(findings))
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from guardian.paths import PATHS

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 500 * 1024   # 单文件 500KB
_BACKUP_COUNT = 3

_configured = False
_log_file = None


def get_logger(name: str = "guardian", level: int = logging.INFO) -> logging.Logger:
    """获取已配置好的 logger。

    Args:
        name: logger 名称，通常用 `__name__`
        level: 日志级别

    Returns:
        配置完成的 Logger 实例
    """
    global _configured, _log_file

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not _configured:
        try:
            PATHS.logs.mkdir(parents=True, exist_ok=True)
            _log_file = PATHS.logs / "guardian.log"

            file_handler = RotatingFileHandler(
                _log_file,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
            file_handler.setLevel(level)

            root = logging.getLogger()
            root.setLevel(level)
            root.addHandler(file_handler)

            # 开发环境下同时输出到控制台，方便调试
            # （打包后 sys.frozen 为 True，此时不输出控制台避免弹黑框）
            if not getattr(sys, "frozen", False):
                console = logging.StreamHandler(sys.stderr)
                console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
                console.setLevel(logging.WARNING)  # 控制台只显示警告及以上，避免刷屏
                root.addHandler(console)

            _configured = True
        except Exception:
            # 日志初始化失败绝不能影响主程序运行
            _configured = True

    # 避免向上传播导致重复输出
    logger.propagate = False
    if not logger.handlers:
        root = logging.getLogger()
        for h in root.handlers:
            logger.addHandler(h)

    return logger


def log_path():
    """返回当前日志文件路径（未初始化则返回 None）。"""
    return _log_file


def set_level(level: int) -> None:
    """运行时调整日志级别。"""
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers:
        h.setLevel(level)
