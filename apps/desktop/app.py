#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多平台内容合规检测工具 v3.0
现代仪表盘风格桌面应用：侧栏导航、合规检测、批量检测、历史记录、词库管理、设置。
检测维度：广告法违禁词 + 平台规则 + 蓝V/非蓝V + 用户自定义行业红线 + 正则兜底 + 变体抗规避
性能优化：页面懒加载、Aho-Corasick 引擎、系统托盘常驻
"""
import sys
from pathlib import Path

import customtkinter as ctk

# apps/desktop/app.py → 上溯三级到项目根（apps/desktop/app.py → desktop → apps → 根）
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from guardian.config import ConfigManager
from apps.desktop.ui.theme import (
    get_colors, font_safe, font_typo, SPACING, CORNER_RADIUS,
    apply_root_theme, apply_dark_titlebar,
    sidebar_button_style, sidebar_button_active_style,
    gradient_button_style,
)
from apps.desktop.ui.dashboard import DashboardPage
from apps.desktop.ui.checker import CheckerPage
from apps.desktop.ui.history import HistoryPage
from apps.desktop.ui.batch import BatchPage
from apps.desktop.ui.rules_manager import RulesManagerPage
from apps.desktop.ui.settings import SettingsPage
from apps.desktop.tray import TrayController, available as tray_available


class ComplianceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("合规卫士 · 内容合规检测工具 v3.0")
        self.root.geometry("1320x880")
        self.root.minsize(1100, 740)

        self.config_manager = ConfigManager()
        self.current_page = None
        self.pages = {}
        self.nav_buttons = {}
        self._overlay = None  # 大规模重建时盖在整窗上的提示层

        # 读取初始外观模式
        initial_mode = self.config_manager.get("appearance_mode", "Light")
        ctk.set_appearance_mode(initial_mode)

        self._center_window()
        self._build_ui()
        self.show_page("dashboard")

        # 系统托盘（可选，失败静默降级）
        self.tray = None
        self._setup_tray()

    # ------------------------------------------------ 系统托盘

    def _setup_tray(self):
        """初始化系统托盘：关闭窗口→最小化到托盘；右键菜单可显示/快检/退出。"""
        if not tray_available():
            return
        try:
            self.tray = TrayController(self)
            started = self.tray.start()
            if started:
                self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            self.tray = None

    def _on_close(self):
        """窗口关闭按钮：有托盘则隐藏到托盘，否则真正退出。"""
        keep_in_tray = bool(self.config_manager.get("minimize_to_tray", True))
        if self.tray is not None and keep_in_tray:
            self.tray.hide_window()
        else:
            self.quit_app()

    def quit_app(self):
        """彻底退出：停托盘 + 销毁窗口。"""
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _center_window(self):
        self.root.update_idletasks()
        w, h = 1320, 880
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        colors = get_colors()
        apply_root_theme(self.root)

        # 主容器
        self.container = ctk.CTkFrame(self.root, fg_color=colors["bg"], corner_radius=0)
        self.container.pack(fill="both", expand=True)

        # 侧边栏 — 加渐变顶条
        self.sidebar = ctk.CTkFrame(self.container, width=240, fg_color=colors["sidebar"],
                                     corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # 侧栏顶部渐变色条
        gradient_bar = ctk.CTkFrame(self.sidebar, height=6,
                                    fg_color=colors["sidebar_gradient_top"],
                                    corner_radius=0)
        gradient_bar.pack(fill="x", pady=0)

        # Logo 区
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=80)
        logo_frame.pack(fill="x", padx=SPACING["xl"], pady=(SPACING["lg"], SPACING["md"]))
        logo_frame.pack_propagate(False)
        ctk.CTkLabel(logo_frame, text="合规卫士", font=font_safe(22, "bold"),
                     text_color=colors["primary"]).pack(anchor="w")
        ctk.CTkLabel(logo_frame, text="多平台内容合规检测", font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(anchor="w")

        # 导航按钮
        nav_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_container.pack(fill="x", padx=SPACING["md"], pady=(SPACING["sm"], 0))

        nav_items = [
            ("dashboard", "📊", "仪表盘"),
            ("checker", "🔍", "合规检测"),
            ("batch", "📁", "批量检测"),
            ("history", "🕘", "历史记录"),
            ("rules", "📚", "词库管理"),
            ("settings", "⚙️", "设置"),
        ]

        for page_key, icon, label in nav_items:
            btn = ctk.CTkButton(nav_container, text=f" {icon}  {label}",
                                command=lambda k=page_key: self.show_page(k),
                                **sidebar_button_style())
            btn.pack(fill="x", pady=(0, SPACING["xs"]))
            self.nav_buttons[page_key] = btn

        # 底部区域
        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=SPACING["lg"], pady=SPACING["lg"])

        # 暗色模式切换
        self.mode_btn = ctk.CTkButton(
            footer,
            text="☀️  浅色模式" if ctk.get_appearance_mode() == "Light" else "🌙  暗色模式",
            command=self._toggle_dark_mode,
            width=200, height=32,
            corner_radius=CORNER_RADIUS["md"],
            fg_color=colors["hover"],
            hover_color=colors["pressed"],
            text_color=colors["text_secondary"],
            font=font_typo("caption"),
            anchor="w",
        )
        self.mode_btn.pack(fill="x", pady=(0, SPACING["sm"]))

        ctk.CTkLabel(footer, text="本地检测 · 隐私安全",
                     font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(anchor="w")
        ctk.CTkLabel(footer, text="v3.0",
                     font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(anchor="w")

        # 内容区
        self.content_frame = ctk.CTkFrame(self.container, fg_color=colors["bg"], corner_radius=0)
        self.content_frame.pack(side="left", fill="both", expand=True)

    def _toggle_dark_mode(self):
        """切换浅色/暗色模式。

        主题色是控件构造时写进参数里的（customtkinter 没有批量改色的 API），
        所以切换主题必须重建页面 —— 仪表盘 214 个控件的重建实测约 1.2 秒。
        直接重建的话，用户看到的是界面逐块变色、闪一下，像是卡住或花屏。

        这里改成"遮罩 + 延后一帧"：先盖一层明确的提示，等遮罩真正画出来
        之后再执行重建，完成后撤掉 —— 把 1.2 秒的视觉混乱换成一次
        有反馈的等待。
        """
        current = ctk.get_appearance_mode()
        new_mode = "Dark" if current == "Light" else "Light"
        ctk.set_appearance_mode(new_mode)
        self.config_manager.set("appearance_mode", new_mode)

        colors = get_colors()
        self.mode_btn.configure(
            text="☀️  浅色模式" if new_mode == "Light" else "🌙  暗色模式",
            fg_color=colors["hover"],
            hover_color=colors["pressed"],
            text_color=colors["text_secondary"],
        )

        self._show_busy_overlay("正在切换主题…")
        # 延后一帧执行：确保遮罩先渲染出来，再开始重建
        self.root.after(30, self._finish_theme_switch)

    def _finish_theme_switch(self):
        try:
            self._refresh_all_pages()
        finally:
            self._hide_busy_overlay()

    def _show_busy_overlay(self, text: str = "加载中…"):
        """在整窗之上盖一层半透明提示，用于遮住大规模重建过程。"""
        if getattr(self, "_overlay", None) is not None:
            return
        colors = get_colors()
        overlay = ctk.CTkFrame(self.container, fg_color=colors["bg"], corner_radius=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        ctk.CTkLabel(overlay, text=text, font=font_typo("h2"),
                     text_color=colors["text_secondary"]).place(relx=0.5, rely=0.5, anchor="center")
        overlay.lift()
        self._overlay = overlay
        self.root.update_idletasks()

    def _hide_busy_overlay(self):
        overlay = getattr(self, "_overlay", None)
        if overlay is not None:
            overlay.destroy()
            self._overlay = None

    def _refresh_all_pages(self):
        """暗色模式切换后刷新所有已创建的页面"""
        colors = get_colors()

        # 刷新侧栏样式
        self.sidebar.configure(fg_color=colors["sidebar"])
        self.container.configure(fg_color=colors["bg"])
        self.content_frame.configure(fg_color=colors["bg"])
        # 让 Windows 原生标题栏跟随深浅色（否则深色界面顶着白标题栏）
        apply_dark_titlebar(self.root)

        # 刷新导航按钮样式
        for page_key, btn in self.nav_buttons.items():
            if page_key == self.current_page:
                btn.configure(**sidebar_button_active_style())
            else:
                btn.configure(**sidebar_button_style())

        # 刷新所有页面
        for page_key, page in self.pages.items():
            if hasattr(page, "apply_theme"):
                page.apply_theme()

    def _create_page(self, page_key):
        """延迟创建页面（只创建一次）。

        布局用 ``place`` 让所有页面**重叠**在内容区的同一位置，而不是
        用 pack 依次排列。这样做是为了让切页变成一次 ``lift()``：
        pack_forget + pack 会触发 Tk 对整个页面树重新做几何计算
        （仪表盘 160 个控件实测 ~540ms），而 lift 只改 z 序，几乎零成本。

        新建页面先 ``lower()`` 压到最底层，确保它还不可见 —— 随后
        show_page 里先 refresh 再 lift，用户看不到构建过程。
        """
        if page_key in self.pages:
            return
        page_classes = {
            "dashboard": DashboardPage,
            "checker": CheckerPage,
            "batch": BatchPage,
            "history": HistoryPage,
            "rules": RulesManagerPage,
            "settings": SettingsPage,
        }
        page_class = page_classes[page_key]
        colors = get_colors()
        page = page_class(self.content_frame, self, fg_color=colors["bg"])
        page.place(x=0, y=0, relwidth=1, relheight=1)
        page.lower()
        self.pages[page_key] = page

    def show_page(self, page_key):
        if page_key not in ["dashboard", "checker", "batch", "history",
                            "rules", "settings"]:
            return

        self._create_page(page_key)

        if self.current_page:
            self.nav_buttons[self.current_page].configure(**sidebar_button_style())

        colors = get_colors()
        page = self.pages[page_key]
        page.configure(fg_color=colors["bg"])

        # ── 顺序很关键：先刷新内容，再提升到最上层 ──
        #
        # 这里曾把 refresh() 放在"页面上屏之后"，结果是：用户先看到页面
        # 出现（内容是上一轮的旧布局/空白），随后 refresh() 开始 destroy 并
        # 重建子控件 —— 于是组件一个接一个"从黑变正常"地画出来，
        # 在仪表盘（160 个控件）上尤其明显。
        #
        # 现在页面切换只是 lift()，而 lift 放在 refresh() 之后，
        # 所有重建都发生在不可见状态，上屏即完整。
        if hasattr(page, "refresh"):
            page.refresh()

        page.lift()
        self.current_page = page_key

        self.nav_buttons[page_key].configure(**sidebar_button_active_style())


def main():
    root = ctk.CTk()
    # 构建期间先隐藏窗口。
    # customtkinter 的每个控件都是"canvas + 子控件"的组合，创建耗时叠加起来
    # 首屏约 1.2 秒；若窗口此时已经映射到屏幕，用户会看到标题、统计卡、图
    # 表一个接一个"长出来"，像是加载失败在闪。先 withdraw 再构建，最后
    # 一次性 deiconify，观感上是"开窗即完整"。
    root.withdraw()
    app = ComplianceApp(root)
    root.deiconify()
    root.lift()
    try:
        root.mainloop()
    finally:
        # 主循环退出后收尾托盘线程
        if getattr(app, "tray", None) is not None:
            try:
                app.tray.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
