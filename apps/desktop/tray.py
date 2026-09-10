#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统托盘（Windows 可用，pystray + Pillow）。

职责
----
* 主窗口"关闭"时**最小化到托盘**而不是退出（可在设置里关掉）；
* 托盘右键菜单：显示主窗口 / 快速检测剪贴板 / 退出；
* 快速检测：读剪贴板 → 规则引擎判定 → 托盘气泡提示风险等级。

设计约束
--------
* pystray 未安装 / 无托盘环境时**整体降级为空操作**，绝不拖垮主程序。
* pystray 的事件循环跑在后台线程，任何 Tk 操作都经 ``root.after(0, ...)``
  切回主线程（Tk 非线程安全）。
* 图标用 Pillow 现画，不依赖任何图片资源（打包 exe 少一个坑）。
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:  # pystray 可选依赖
    import pystray
    _PYSTRAY_OK = True
except Exception:  # pragma: no cover - 环境缺失
    pystray = None
    _PYSTRAY_OK = False

try:
    from PIL import Image, ImageDraw
    _PIL_OK = True
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None
    _PIL_OK = False


def available() -> bool:
    """托盘能力是否可用（pystray + Pillow 均在）。"""
    return _PYSTRAY_OK and _PIL_OK


def create_icon_image(size: int = 64):
    """用 Pillow 现画一个盾牌 + 对勾图标（返回 PIL.Image，失败返回 None）。"""
    if not _PIL_OK:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size * 0.08
    # 盾牌主体
    d.polygon(
        [(size / 2, m),
         (size - m, m + size * 0.16),
         (size - m, size * 0.58),
         (size / 2, size - m),
         (m, size * 0.58),
         (m, m + size * 0.16)],
        fill=(79, 110, 247, 255),
    )
    # 对勾
    lw = max(2, int(size * 0.10))
    d.line([(size * 0.32, size * 0.50),
            (size * 0.45, size * 0.63),
            (size * 0.70, size * 0.36)],
           fill=(255, 255, 255, 255), width=lw, joint="curve")
    return img


class TrayController:
    """托盘控制器。``start()`` 后由后台线程驱动图标事件循环。"""

    def __init__(self, app, on_show: Optional[Callable] = None,
                 on_quit: Optional[Callable] = None,
                 on_quick_check: Optional[Callable] = None):
        self.app = app
        self._on_show = on_show or self._default_show
        self._on_quit = on_quit or self._default_quit
        self._on_quick_check = on_quick_check or self._default_quick_check
        self._icon = None
        self._thread: Optional[threading.Thread] = None
        self.enabled = available()

    # ------------------------------------------------ 线程安全封装

    def _ui(self, fn, *args):
        """把回调切回 Tk 主线程执行。"""
        root = getattr(self.app, "root", None)
        if root is not None:
            try:
                root.after(0, lambda: fn(*args))
                return
            except Exception:
                pass
        fn(*args)

    def _default_show(self):
        self.show_window()

    def _default_quit(self):
        self.quit()

    def _default_quick_check(self):
        self.quick_check()

    # ------------------------------------------------ 生命周期

    def start(self) -> bool:
        """启动托盘（后台线程）。返回是否成功启动。"""
        if not self.enabled:
            return False
        img = create_icon_image(64)
        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", lambda *a: self._ui(self._on_show), default=True),
            pystray.MenuItem("快速检测剪贴板", lambda *a: self._ui(self._on_quick_check)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda *a: self._ui(self._on_quit)),
        )
        self._icon = pystray.Icon("ComplianceGuardian", img,
                                  "合规卫士 · 内容合规检测", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def notify(self, title: str, message: str) -> None:
        """弹托盘气泡（不支持时静默）。"""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            pass

    # ------------------------------------------------ 动作

    def show_window(self) -> None:
        root = getattr(self.app, "root", None)
        if root is None:
            return
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except Exception:
            pass

    def hide_window(self) -> None:
        root = getattr(self.app, "root", None)
        if root is None:
            return
        try:
            root.withdraw()
        except Exception:
            pass

    def quit(self) -> None:
        self.stop()
        root = getattr(self.app, "root", None)
        if root is not None:
            try:
                root.quit()
                root.destroy()
            except Exception:
                pass

    def quick_check(self) -> Optional[dict]:
        """读剪贴板 → 规则引擎检测 → 托盘提示。返回结果 dict 或 None。"""
        root = getattr(self.app, "root", None)
        text = ""
        if root is not None:
            try:
                text = root.clipboard_get()
            except Exception:
                text = ""
        if not text or not text.strip():
            self.notify("合规卫士", "剪贴板没有可用文本")
            return None
        try:
            from guardian.detector import ComplianceDetector
            res = ComplianceDetector.get_instance().detect(text)
        except Exception as e:  # pragma: no cover
            self.notify("合规卫士", f"检测失败：{e}")
            return None

        summary = res.get("summary", {})
        risk = summary.get("risk_level", "未知")
        n = summary.get("violations", 0) + summary.get("warnings", 0)
        self.notify("合规卫士 · 检测完成", f"{risk} · 命中 {n} 处")
        return res
