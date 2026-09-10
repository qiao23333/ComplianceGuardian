#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台数据目录定位。

为什么需要这个模块
------------------
打包成 exe 之后，程序所在目录通常是只读的（例如装在 `Program Files` 下），
把日志、配置、历史数据库写进项目目录会导致：

* 权限不足直接崩溃
* 用户重装 / 升级时数据被覆盖丢失

因此用户数据一律写到操作系统的**应用数据目录**：

| 系统   | 路径                                            |
|--------|-------------------------------------------------|
| Windows| `%LOCALAPPDATA%\\ComplianceGuardian`             |
| macOS  | `~/Library/Application Support/ComplianceGuardian` |
| Linux  | `~/.local/share/ComplianceGuardian`             |

设计约束：本模块属于内核层，只依赖标准库。
（实现参考了同工作区 SnapSort 项目的 `core/platform_paths.py`）
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ComplianceGuardian"

#: 数据目录覆盖开关。
#:
#: 默认写入操作系统标准应用数据目录（Windows 是 `%LOCALAPPDATA%`，位于 C 盘）。
#: 若你希望**所有数据都不落在 C 盘**，设置此环境变量指向 D 盘路径即可：:
#:
#:     setx GUARDIAN_DATA_DIR "D:\\ai产物\\ComplianceGuardian_data"
#:
#: 设置后，日志 / 配置 / 检测历史 / 用户自定义规则全部改写到该目录下。
DATA_DIR_ENV = "GUARDIAN_DATA_DIR"


@dataclass(frozen=True)
class AppPaths:
    """应用数据目录集合（全部位于系统应用数据目录下，不在项目目录内）。"""

    root: Path        # 数据根目录
    db: Path          # SQLite 检测历史数据库
    config: Path      # 用户配置
    logs: Path        # 日志
    cache: Path       # 缓存（如分享链接、LLM 结果缓存）
    user_rules: Path  # 用户自定义规则 / 白名单（与内置词库分离，升级不被覆盖）

    @classmethod
    def for_system(
        cls,
        system: str,
        home: Path,
        local_app_data: str | None,
    ) -> "AppPaths":
        if system == "Windows":
            base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
            root = base / APP_NAME
        elif system == "Darwin":
            root = home / "Library" / "Application Support" / APP_NAME
        else:
            root = home / ".local" / "share" / APP_NAME

        return cls(
            root=root,
            db=root / "history.sqlite3",
            config=root / "config.json",
            logs=root / "logs",
            cache=root / "cache",
            user_rules=root / "rules",
        )

    @classmethod
    def current(cls) -> "AppPaths":
        """按当前运行平台返回数据目录。

        若设置了环境变量 `GUARDIAN_DATA_DIR`，则优先使用该目录
        （方便把数据全部放到 D 盘，避免写入 C 盘）。
        """
        override = os.getenv(DATA_DIR_ENV)
        if override:
            root = Path(override)
            return cls(
                root=root,
                db=root / "history.sqlite3",
                config=root / "config.json",
                logs=root / "logs",
                cache=root / "cache",
                user_rules=root / "rules",
            )
        return cls.for_system(platform.system(), Path.home(), os.getenv("LOCALAPPDATA"))

    def ensure(self) -> "AppPaths":
        """创建所有目录（已存在则跳过），返回自身便于链式调用。"""
        for path in (self.root, self.logs, self.cache, self.user_rules):
            path.mkdir(parents=True, exist_ok=True)
        return self


# 模块级便捷入口
PATHS = AppPaths.current()


def project_root() -> Path:
    """返回项目根目录（guardian/paths.py → guardian → 项目根）。

    用于定位仓库内的**只读资源**，例如 `rules/` 内置词库。
    注意：可写数据请用 AppPaths，不要写在项目目录里。
    """
    return Path(__file__).resolve().parent.parent


def builtin_rules_dir() -> Path:
    """内置词库目录（仓库内，只读）。"""
    return project_root() / "rules"


def log_dir() -> Path:
    """日志目录，确保已创建。"""
    PATHS.logs.mkdir(parents=True, exist_ok=True)
    return PATHS.logs
