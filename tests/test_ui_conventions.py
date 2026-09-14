#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""customtkinter 布局约定守卫。

为什么需要这个文件
------------------
2026-09-14 排查界面问题时，同一个坑在**同一天内被踩了两次**：

    # 违规列表左侧色条
    ctk.CTkFrame(row, width=3)          # → 整行被撑到 200px 高

    # 仪表盘条形图左侧文字列
    ctk.CTkFrame(row, width=170)        # → 每一行都被撑到 200px 高

根因：``CTkFrame`` 的 ``height`` 默认值是 **200**，而它的内部实现是
``canvas + 内部 frame``。只给 ``width`` 不给 ``height`` 时，canvas 会请求
200px 高度，Tk 的几何计算取"canvas 请求"与"子控件请求"的较大值 —— 于是
一个只有两行文字的行高变成 200px：一屏只放得下两条违规，其余全是空白，
看起来像"没数据"。

现象和"布局没写对"很像，但其实是**组件默认值**问题，肉眼审代码看不出来，
只有截图或量 ``winfo_height()`` 才会暴露。所以这里把它固化成自动化检查。

判定规则
--------
``ctk.CTkFrame(...)`` 调用里若出现 ``width=`` 而**没有** ``height=``，
即视为隐患。两种正确写法：

* 需要内容自适应 → 显式写 ``height=1``（取 max(1, 内容高度)）；
* 需要固定高度   → 显式写 ``height=<具体值>``；
* 纯装饰条      → 改用 ``tk.Frame``（高度完全由 fill 决定）。

例外：``corner_radius=0`` 之类的纯背景块若确实要 200 高度，请显式写
``height=200`` 说明意图，而不是依赖默认值。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parent.parent / "apps" / "desktop" / "ui"

#: 匹配 ctk.CTkFrame( ... ) 的完整调用（含跨行括号）
_CTKFRAME_CALL = re.compile(
    r"ctk\.CTkFrame\((?P<args>(?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)",
    re.DOTALL,
)

#: 只匹配独立的 width= / height=，避免把 border_width= 之类误当成尺寸参数
#: （第一版守卫就栽在这：把 ``border_width=1`` 当成了 width）
_WIDTH_ARG = re.compile(r"(?<![_A-Za-z])width\s*=")
_HEIGHT_ARG = re.compile(r"(?<![_A-Za-z])height\s*=")


def _ui_files() -> list[Path]:
    return sorted(p for p in UI_DIR.glob("*.py") if p.name != "__init__.py")


def find_risky_frames() -> list[tuple[str, int, str]]:
    """返回 [(文件名, 行号, 调用片段), ...]。"""
    risky: list[tuple[str, int, str]] = []
    for path in _ui_files():
        source = path.read_text(encoding="utf-8")
        for m in _CTKFRAME_CALL.finditer(source):
            args = m.group("args")
            if not _WIDTH_ARG.search(args):
                continue
            if _HEIGHT_ARG.search(args):
                continue
            line_no = source[: m.start()].count("\n") + 1
            snippet = " ".join(args.split())[:110]
            risky.append((path.name, line_no, snippet))
    return risky


def test_ui_files_found():
    """守卫本身要确保扫到了文件（防止路径写错导致"永远通过"）。"""
    files = _ui_files()
    assert len(files) >= 5, f"未扫到 UI 文件：{files}"


def test_no_ctkframe_with_width_but_no_height():
    """禁止 CTkFrame 只写 width 不写 height（会被默认 200px 高度撑爆布局）。"""
    risky = find_risky_frames()
    detail = "\n".join(f"  {name}:{line}  ctk.CTkFrame({snip})" for name, line, snip in risky)
    assert not risky, (
        "发现只指定 width 未指定 height 的 CTkFrame，会被默认 200px 高度撑开：\n"
        + detail
        + "\n修法：内容自适应加 height=1；固定高度写明确值；纯装饰条改用 tk.Frame。"
    )


# ============================================================ 组件默认值备忘


def test_ctkframe_default_height_is_still_200():
    """把"CTkFrame 默认高 200"这个事实本身钉住。

    将来若 customtkinter 换了默认值，上面的规则可能需要重新评估 ——
    这条测试会先失败并提醒我们，而不是让守卫静默失效。
    """
    import customtkinter as ctk

    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        frame = ctk.CTkFrame(root, width=100)
        root.update_idletasks()
        assert frame.winfo_reqheight() == 200, (
            "customtkinter 的 CTkFrame 默认高度已变化"
            f"（当前 {frame.winfo_reqheight()}），请复核布局约定守卫是否仍然必要"
        )
    finally:
        root.destroy()
