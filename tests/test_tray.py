#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统托盘模块测试（不启动真实托盘图标）。

覆盖：
* 图标图像生成（Pillow 纯代码绘制）
* 能力探测与降级（pystray 缺失时 available()/start() 不炸）
* 快速检测：剪贴板读取 → 引擎检测 → 返回结果
* 线程安全封装 _ui：无 root 时直接同步执行
"""

from __future__ import annotations

import apps.desktop.tray as tray


class _FakeRoot:
    def __init__(self, clip: str = ""):
        self._clip = clip
        self.withdrawn = False

    def clipboard_get(self):
        if self._clip == "":
            raise RuntimeError("no clipboard")
        return self._clip

    def deiconify(self):
        self.withdrawn = False

    def withdraw(self):
        self.withdrawn = True


class _FakeApp:
    def __init__(self, clip: str = ""):
        self.root = _FakeRoot(clip)


# ---------------------------------------------------------------- 图标


def test_create_icon_image():
    img = tray.create_icon_image(64)
    assert img is not None
    assert img.size == (64, 64)
    # 盾牌区域应当有非透明像素
    assert img.getextrema()[3][1] > 0


def test_available_returns_bool():
    assert isinstance(tray.available(), bool)


# ---------------------------------------------------------------- 降级


def test_start_returns_false_when_unavailable(monkeypatch):
    monkeypatch.setattr(tray, "_PYSTRAY_OK", False)
    ctl = tray.TrayController(_FakeApp())
    assert ctl.enabled is False
    assert ctl.start() is False
    # 停止 / 通知在未启动时也必须安全
    ctl.stop()
    ctl.notify("t", "m")


# ---------------------------------------------------------------- 快速检测


def test_quick_check_empty_clipboard():
    ctl = tray.TrayController(_FakeApp(clip=""))
    assert ctl.quick_check() is None


def test_quick_check_detects_text():
    ctl = tray.TrayController(_FakeApp(clip="这是最好的产品，加我微信"))
    res = ctl.quick_check()
    assert res is not None
    assert "summary" in res
    assert res["summary"]["risk_level"]


def test_ui_runs_inline_without_root():
    """无 root 时 _ui 直接同步调用（不抛异常）。"""
    ctl = tray.TrayController(_FakeApp())
    ctl.app.root = None
    called = {}
    ctl._ui(lambda: called.setdefault("ok", True))
    assert called.get("ok") is True


# ---------------------------------------------------------------- 显示/隐藏


def test_hide_and_show_window():
    app = _FakeApp()
    ctl = tray.TrayController(app)
    ctl.hide_window()
    assert app.root.withdrawn is True
    ctl.show_window()
    assert app.root.withdrawn is False
