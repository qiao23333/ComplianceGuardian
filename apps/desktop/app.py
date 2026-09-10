#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多平台内容合规检测工具 v2.3
现代仪表盘风格桌面应用，侧栏导航、合规检测、词库管理、暗色模式。
检测维度：广告法违禁词 + 平台规则 + 蓝V/非蓝V + 用户自定义行业红线
性能优化：页面懒加载、Aho-Corasick检测引擎
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
    apply_root_theme, sidebar_button_style, sidebar_button_active_style,
    gradient_button_style,
)
from apps.desktop.ui.dashboard import DashboardPage
from apps.desktop.ui.checker import CheckerPage
from apps.desktop.ui.history import HistoryPage
from apps.desktop.ui.batch import BatchPage
from apps.desktop.ui.rules_manager import RulesManagerPage
from apps.desktop.ui.settings import SettingsPage


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

        # 读取初始外观模式
        initial_mode = self.config_manager.get("appearance_mode", "Light")
        ctk.set_appearance_mode(initial_mode)

        self._center_window()
        self._build_ui()
        self.show_page("dashboard")

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
        ctk.CTkLabel(logo_frame, text="桥的合规卫士", font=font_safe(22, "bold"),
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
        """切换浅色/暗色模式"""
        current = ctk.get_appearance_mode()
        new_mode = "Dark" if current == "Light" else "Light"
        ctk.set_appearance_mode(new_mode)
        self.config_manager.set("appearance_mode", new_mode)

        # 更新切换按钮文字
        colors = get_colors()
        self.mode_btn.configure(
            text="☀️  浅色模式" if new_mode == "Light" else "🌙  暗色模式",
            fg_color=colors["hover"],
            hover_color=colors["pressed"],
            text_color=colors["text_secondary"],
        )

        # 刷新所有页面
        self._refresh_all_pages()

    def _refresh_all_pages(self):
        """暗色模式切换后刷新所有已创建的页面"""
        colors = get_colors()

        # 刷新侧栏样式
        self.sidebar.configure(fg_color=colors["sidebar"])
        self.container.configure(fg_color=colors["bg"])
        self.content_frame.configure(fg_color=colors["bg"])

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
        """延迟创建页面（只创建一次）"""
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
        self.pages[page_key] = page_class(self.content_frame, self, fg_color=colors["bg"])
        self.pages[page_key].pack_forget()

    def show_page(self, page_key):
        if page_key not in ["dashboard", "checker", "batch", "history",
                            "rules", "settings"]:
            return

        self._create_page(page_key)

        if self.current_page:
            self.pages[self.current_page].pack_forget()
            self.nav_buttons[self.current_page].configure(**sidebar_button_style())

        colors = get_colors()
        self.pages[page_key].configure(fg_color=colors["bg"])
        self.pages[page_key].pack(fill="both", expand=True)
        self.current_page = page_key

        self.nav_buttons[page_key].configure(**sidebar_button_active_style())

        if hasattr(self.pages[page_key], "refresh"):
            self.pages[page_key].refresh()


def main():
    root = ctk.CTk()
    app = ComplianceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
