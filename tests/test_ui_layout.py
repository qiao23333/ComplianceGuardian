#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""页面布局可达性门禁（运行期实测，不是看代码）。

为什么需要这个文件
------------------
``CTkFrame`` 装不下内容时**不会**报错、也不会自动加滚动条。Tk 的 pack
会把超出的部分**压扁靠后的子控件**，一路压到 0~8px —— 控件还在、数据还在，
但用户在界面上看不见，也没有任何办法拖出来。

这种 bug 用肉眼审代码发现不了（代码里每张卡片都写得没错），静态检查也
发现不了（不涉及 ``CTkFrame(width=N)`` 那类默认值问题），只有**真的把页面
建出来量一遍**才会暴露。2026-09-15 就是这么发现的：

* 设置页内容需 1567px，窗口最小 740px → 「关于」「数据管理」两张卡片
  实际高度 0px，等于不存在；
* 仪表盘内容需 900px，默认窗口 880px → 词库概览 BarChart 的末尾几行
  被压到 8px。

判定规则
--------
对每个页面递归遍历：某控件的"请求高度"明显大于"实际分配高度"，说明它被
压缩了。此时它必须**够得着**，即自身或祖先是一个滚动容器（``ScrollBody``
/ ``CTkScrollableFrame``），或者子孙里有自带滚动能力的控件（``Treeview``
等）。否则判失败 —— 那部分内容用户永远看不到。

被测窗口取 **740px**（``app.py`` 里 ``minsize`` 的高度），也就是用户能
把窗口拖到的最矮状态。在这个高度下站得住，放大时只会更宽松。
"""

from __future__ import annotations

import pytest

ctk = pytest.importorskip("customtkinter")
tk = pytest.importorskip("tkinter")

from guardian.config import DEFAULT_CONFIG  # noqa: E402

#: 用户能把窗口拖到的最小高度（与 apps/desktop/app.py 的 minsize 一致）
MIN_WINDOW_HEIGHT = 740

#: 请求高度比实际高度多出多少才算"被压缩"（留出边框/字体的几像素误差）
SQUEEZE_TOLERANCE = 8


class _StubConfig(dict):
    """假配置管理器：只走内存，不碰 data/config.json。

    直接用真的 ``ConfigManager`` 会在文件缺失时**写出**默认配置 ——
    跑个测试顺手改了用户配置，是比布局 bug 更讨厌的事。
    """

    def __init__(self):
        super().__init__(DEFAULT_CONFIG)

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):  # noqa: A003 - 对齐真实接口
        self[key] = value


class _StubApp:
    """页面构造只需要 ``config_manager`` 与少量回调，其余一律吞掉。"""

    def __init__(self):
        self.config_manager = _StubConfig()
        self.pages: dict = {}
        self.root = None

    def show_page(self, *_a, **_k):
        return None

    def __getattr__(self, _name):
        return lambda *_a, **_k: None


def _page_classes():
    from apps.desktop.ui.batch import BatchPage
    from apps.desktop.ui.checker import CheckerPage
    from apps.desktop.ui.dashboard import DashboardPage
    from apps.desktop.ui.history import HistoryPage
    from apps.desktop.ui.rules_manager import RulesManagerPage
    from apps.desktop.ui.settings import SettingsPage

    return {
        "dashboard": DashboardPage,
        "checker": CheckerPage,
        "batch": BatchPage,
        "history": HistoryPage,
        "rules": RulesManagerPage,
        "settings": SettingsPage,
    }


# 根窗口由 ``tests/conftest.py`` 的会话级 ``tk_root`` fixture 提供 ——
# 不要在模块里自己建（同进程反复创建 Tcl 解释器本机必失败，详见 conftest）。


def _squeezed_unreachable(widget, inside_scroll: bool) -> list[str]:
    """返回"被压缩且够不着"的控件描述（递归）。

    Args:
        widget: 当前遍历到的容器
        inside_scroll: 当前是否已经在某个滚动容器里
    """
    bad: list[str] = []
    for child in widget.winfo_children():
        # 未显示的控件（例如按条件 pack 的那几行）不算 —— 它们本来就不该占位置
        if not child.winfo_viewable():
            continue

        scrollable = isinstance(child, ctk.CTkScrollableFrame)
        req_h, real_h = child.winfo_reqheight(), child.winfo_height()
        squeezed = (req_h - real_h) > SQUEEZE_TOLERANCE

        if squeezed and not inside_scroll and not scrollable:
            if not _carries_own_scroll(child):
                bad.append(
                    f"{type(child).__name__} 请求 {req_h}px / 实际 {real_h}px "
                    f"(y={child.winfo_y()})"
                )
        bad += _squeezed_unreachable(child, inside_scroll or scrollable)
    return bad


#: 自带滚动能力、因此"变矮"不等于"内容够不着"的控件。
#:
#: Treeview 是唯一一个真在用的：词库管理页那张表本身带竖向滚动条，容器矮
#: 一点只是视口小一点，数据照样翻得到 —— 这和"被压到 0px 的卡片"是两回事，
#: 不能算失败。
_SELF_SCROLLING_CLASSES = {"Treeview", "Listbox"}


def _carries_own_scroll(widget) -> bool:
    """自身自带滚动能力，或子孙里有滚动容器/自带滚动的控件。"""
    for child in [widget, * _descendants(widget)]:
        if child.winfo_class() in _SELF_SCROLLING_CLASSES:
            return True
        if isinstance(child, ctk.CTkScrollableFrame):
            return True
    return False


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _has_page_level_scroll_body(page) -> bool:
    """页面是否挂了页面级滚动容器。

    注意不能只看 ``page.winfo_children()``：``CTkScrollableFrame`` 自身会被
    塞进它内部的 canvas，而挂在页面下的是它外面那层包装 frame —— 直接遍历
    子控件**看不到**滚动容器本身（实测踩过）。所以这里认 ``body`` 这个约定
    属性名，见 ``widgets.ScrollBody`` 的用法说明。
    """
    body = getattr(page, "body", None)
    return isinstance(body, ctk.CTkScrollableFrame)


@pytest.mark.parametrize("page_key", sorted(_page_classes()))
def test_page_content_is_reachable_at_min_window(tk_root, page_key):
    """最小窗口下，任何一页的内容都不能"存在但够不着"。

    失败说明该页的某个区块被压扁且不在滚动容器里 —— 用户看不到它，
    也没法把它拖出来。修法：把页面内容挂到 ``widgets.ScrollBody`` 上
    （参考 ``dashboard.py`` / ``settings.py`` 的写法）。
    """
    page_cls = _page_classes()[page_key]
    page = page_cls(tk_root, _StubApp(), fg_color="#fff")
    page.place(x=0, y=0, relwidth=1, relheight=1)
    tk_root.update()
    tk_root.update_idletasks()
    try:
        bad = _squeezed_unreachable(page, inside_scroll=False)
        assert not bad, (
            f"{page_key} 页在 {MIN_WINDOW_HEIGHT}px 高度下有内容够不着：\n  "
            + "\n  ".join(bad)
            + "\n修法：把内容挂到 ScrollBody 上（apps/desktop/ui/widgets.py）。"
        )
    finally:
        page.destroy()


def test_scroll_body_is_used_by_long_pages(tk_root):
    """长页面必须用页面级滚动容器，而不是裸的 CTkFrame。

    这条防的是"改回裸 CTkFrame"的倒退：上一条会同时失败，但这条把
    **意图**写清楚 —— 不是随便找个参数糊过去，而是页面要有滚动容器。
    """
    expected = {"dashboard", "settings"}
    classes = _page_classes()
    for page_key in sorted(expected):
        page = classes[page_key](tk_root, _StubApp(), fg_color="#fff")
        page.place(x=0, y=0, relwidth=1, relheight=1)
        tk_root.update()
        tk_root.update_idletasks()
        try:
            has_body = _has_page_level_scroll_body(page)
            assert has_body, (
                f"{page_key} 页没有页面级滚动容器。"
                "该页内容实测高度超过最小窗口（dashboard 900px / "
                f"settings 1567px，最小窗口 {MIN_WINDOW_HEIGHT}px），"
                "裸 CTkFrame 会把末尾的卡片压到 0px。"
            )
        finally:
            page.destroy()
