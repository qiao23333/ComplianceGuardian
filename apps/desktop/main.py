#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规卫士 · 桌面端启动入口。

用法（项目根目录下执行）：

    python -m apps.desktop.main

打包后由 PyInstaller 直接调用本文件。
"""
import sys
from pathlib import Path

# apps/desktop/main.py → desktop → apps → 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.desktop.app import main

if __name__ == "__main__":
    main()
