"""合规卫士内核包：桌面端与 Web 端共享的检测引擎。

本包严禁 import tkinter / customtkinter / fastapi 等 UI 框架。
"""

# 唯一版本来源。Web 端 rules.json 的 meta.engine 也从这里读——
# 这个号原先手写在导出脚本里，结果页面长期显示旧版本，
# 属于典型的"一份事实存了两处"，早晚会对不上。
__version__ = "3.4.0"
