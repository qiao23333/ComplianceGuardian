#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""界面截图工具：把任一页面渲染成 PNG，用于 UI 走查与回归比对。

为什么需要它
------------
这个项目是 CustomTkinter 桌面端，开发过程中有一个绕不开的问题：
**改动界面之后没法"看一眼"**。直接 `python apps/desktop/app.py` 起的窗口
会被其他窗口遮挡，普通截屏（``PIL.ImageGrab.grab()``）抓到的往往是别人。

本脚本用 Win32 的 ``PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)``
把窗口**自绘内容**抓到内存 DC —— 不受遮挡影响、不需要窗口置顶、
也不需要焦点，因此可以在无人值守的情况下批量出图。

用法::

    # 抓仪表盘（浅色）
    python scripts/ui_screenshot.py dashboard out.png

    # 抓检测页在有违规结果时的样子
    python scripts/ui_screenshot.py checker out.png --dark --demo-text "保证下签，成功率100%"

    # 一次抓全部页面
    python scripts/ui_screenshot.py all .tmp-shots/

注意：只支持 Windows（依赖 user32/gdi32）。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402

ALL_PAGES = ["dashboard", "checker", "batch", "history", "rules", "settings"]

#: 演示文案：覆盖虚假承诺 / 成功率宣传 / 价格宣称 / 时间承诺 / 关系暗示
DEMO_TEXT = (
    "新加坡雇主担保移民，我们保证下签，成功率100%，全网最低价，"
    "最快3个月就能获批PR，内部关系直通移民局，现成雇主资源随便挑。"
)


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


def grab_window(hwnd: int) -> Image.Image:
    """用 PrintWindow 抓取窗口内容（不受遮挡影响）。"""
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    u32.SetProcessDPIAware()

    rect = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top

    hdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, 2)  # 2 = PW_RENDERFULLCONTENT

    header = _BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    header.biWidth = w
    header.biHeight = -h  # 负值 = 自上而下
    header.biPlanes = 1
    header.biBitCount = 32

    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(header), 0)
    image = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")

    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, hdc)
    return image


def capture(page: str, out_path: Path, dark: bool = False,
            demo_text: str = "") -> Path:
    """渲染指定页面并保存截图。"""
    from apps.desktop.app import ComplianceApp

    root = ctk.CTk()
    app = ComplianceApp(root)
    if dark:
        ctk.set_appearance_mode("Dark")
        app._refresh_all_pages()
    app.show_page(page)

    def pump(times: int = 30, delay: float = 0.03) -> None:
        for _ in range(times):
            root.update()
            time.sleep(delay)

    pump()

    if demo_text and page == "checker":
        checker = app.pages["checker"]
        checker.textbox.delete("1.0", "end")
        checker.textbox.insert("1.0", demo_text)
        checker._update_char_count()
        checker._display_result(checker.detector.detect(demo_text, "xiaohongshu", "blue_v"))
        checker.toggle_btn.configure(state="normal")
        pump(25)

    hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
    ctypes.windll.user32.ShowWindow(hwnd, 5)
    pump(10)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    grab_window(hwnd).save(out_path)
    root.destroy()
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="合规卫士界面截图工具")
    parser.add_argument("page", help=f"页面名，或 all（{'/'.join(ALL_PAGES)}）")
    parser.add_argument("out", help="输出 PNG 路径；page=all 时视为输出目录")
    parser.add_argument("--dark", action="store_true", help="暗色模式")
    parser.add_argument("--demo-text", default="", help="检测页的演示文案")
    args = parser.parse_args()

    if args.page == "all":
        out_dir = Path(args.out)
        for page in ALL_PAGES:
            path = capture(page, out_dir / f"{page}.png", args.dark, args.demo_text)
            print("saved", path)
    else:
        print("saved", capture(args.page, Path(args.out), args.dark, args.demo_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
