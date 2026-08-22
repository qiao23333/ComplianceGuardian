#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仪表盘页面 — v2.2 现代仪表盘风

升级内容：
1. GradientCard 统计卡片（各带不同色渐变）
2. BarChart 迷你图（词库统计）
3. 渐变按钮组（快速操作）
4. 跨平台检测入口
5. 暗色模式支持
"""
import customtkinter as ctk

from ui.theme import (
    get_colors, font_safe, font_typo, SPACING, CORNER_RADIUS,
    primary_button_style, secondary_button_style, card_frame_style,
    gradient_button_style, glass_card_style,
)
from ui.widgets import (
    GradientCard, BarChart, StatCard, SegmentedControl,
)
from core.detector import ComplianceDetector


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)  # app.py 也传了 fg_color，避免重复
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        colors = get_colors()

        # 标题区
        ctk.CTkLabel(self, text="仪表盘", font=font_typo("h1"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xxl"], pady=(SPACING["xl"], SPACING["xs"]))
        ctk.CTkLabel(self, text="多平台内容合规检测中心 · 一站式管理你的内容安全",
                     font=font_typo("body"),
                     text_color=colors["text_secondary"]).pack(anchor="w", padx=SPACING["xxl"], pady=(0, SPACING["xl"]))

        # 统计卡片 — GradientCard 样式
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["xl"]))
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_checks = GradientCard(
            cards_frame, title="累计检测", value="0", subtitle="次",
            icon="📊", gradient_key="gradient_card_blue_top")
        self.stat_checks.grid(row=0, column=0, padx=(0, SPACING["lg"]), sticky="nsew")

        self.stat_violations = GradientCard(
            cards_frame, title="发现违规", value="0", subtitle="条",
            icon="🔴", gradient_key="gradient_card_red_top")
        self.stat_violations.grid(row=0, column=1, padx=(0, SPACING["lg"]), sticky="nsew")

        detector = ComplianceDetector.get_instance()
        rules_summary = detector.get_rules_summary()

        self.stat_rules = GradientCard(
            cards_frame, title="规则词库", value=str(rules_summary["总计"]), subtitle="条规则",
            icon="📚", gradient_key="gradient_card_orange_top")
        self.stat_rules.grid(row=0, column=2, padx=(0, SPACING["lg"]), sticky="nsew")

        self.stat_platforms = GradientCard(
            cards_frame, title="覆盖平台", value="3", subtitle="小红书·抖音·视频号",
            icon="🎯", gradient_key="gradient_card_green_top")
        self.stat_platforms.grid(row=0, column=3, sticky="nsew")

        # 快速操作 — 渐变按钮组
        action_card = ctk.CTkFrame(self, **card_frame_style())
        action_card.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["xl"]))

        ctk.CTkLabel(action_card, text="快速操作", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["lg"], SPACING["md"]))

        btn_frame = ctk.CTkFrame(action_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["lg"]))

        ctk.CTkButton(btn_frame, text="🔍 开始合规检测",
                      command=lambda: self.app.show_page("checker"),
                      **gradient_button_style()).pack(side="left", padx=(0, SPACING["md"]))

        # 跨平台检测入口
        ctk.CTkButton(btn_frame, text="📊 跨平台对比检测", width=160,
                      command=lambda: self._go_to_cross_platform(),
                      fg_color=colors["primary_light"], hover_color=colors["hover"],
                      text_color=colors["primary"],
                      border_width=1, border_color=colors["primary"],
                      font=font_typo("caption_bold"), height=38,
                      corner_radius=CORNER_RADIUS["md"]).pack(side="left", padx=(0, SPACING["md"]))

        ctk.CTkButton(btn_frame, text="📚 管理词库",
                      command=lambda: self.app.show_page("rules"),
                      **secondary_button_style()).pack(side="left", padx=(0, SPACING["md"]))
        ctk.CTkButton(btn_frame, text="⚙️ 设置",
                      command=lambda: self.app.show_page("settings"),
                      **secondary_button_style()).pack(side="left")

        # 词库概览 — BarChart
        overview_card = ctk.CTkFrame(self, **card_frame_style())
        overview_card.pack(fill="both", expand=True, padx=SPACING["xxl"], pady=(0, SPACING["xxl"]))

        ctk.CTkLabel(overview_card, text="词库概览", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["lg"], SPACING["md"]))

        # BarChart 数据
        bar_data = []
        for name, count in rules_summary.items():
            if name == "总计":
                continue
            if isinstance(count, dict):
                total = sum(count.values())
            else:
                total = count
            color_key = {
                "广告法违禁词": "primary",
                "平台规则": "info",
                "蓝V专属限制": "warning",
                "行业红线": "danger",
                "正则模式": "success",
            }.get(name, "primary")
            bar_data.append((name, total, color_key))

        if bar_data:
            max_val = max(v for _, v, _ in bar_data)
            chart = BarChart(overview_card, bar_data, max_value=max_val)
            chart.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["md"]))

        # 词库详细列表（保留兼容）
        for name, count in rules_summary.items():
            if name == "总计":
                continue
            row = ctk.CTkFrame(overview_card, fg_color=colors["hover"], corner_radius=CORNER_RADIUS["md"], height=48)
            row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
            row.pack_propagate(False)

            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="y", padx=SPACING["md"])

            if isinstance(count, dict):
                detail = " · ".join(f"{k}: {v}" for k, v in count.items())
                ctk.CTkLabel(left, text=name, font=font_typo("caption_bold"),
                             text_color=colors["text"]).pack(anchor="w")
                ctk.CTkLabel(left, text=detail, font=font_typo("micro"),
                             text_color=colors["text_secondary"]).pack(anchor="w")
                total = sum(count.values())
            else:
                ctk.CTkLabel(left, text=name, font=font_typo("caption_bold"),
                             text_color=colors["text"]).pack(anchor="w")
                ctk.CTkLabel(left, text=f"{count} 条规则", font=font_typo("micro"),
                             text_color=colors["text_secondary"]).pack(anchor="w")
                total = count

            ctk.CTkLabel(row, text=str(total), font=font_safe(22, "bold"),
                         text_color=colors["primary"]).pack(side="right", padx=SPACING["md"])

    def _go_to_cross_platform(self):
        """跳转到检测页面的跨平台对比模式"""
        self.app.show_page("checker")
        checker_page = self.app.pages.get("checker")
        if checker_page:
            checker_page.platform_var.set("cross_platform")
            # 重新构建平台选择器，选中"对比"项
            segments = [("小红书", "小红书"), ("抖音", "抖音"), ("视频号", "微信视频号"), ("通用", "all"), ("对比", "cross_platform")]
            checker_page.platform_control._segments = segments
            checker_page.platform_control._selected_idx = 4
            checker_page.platform_control._build_buttons()

    def refresh(self):
        total_checks = self.app.config_manager.get("total_checks", 0)
        total_violations = self.app.config_manager.get("total_violations", 0)
        self.stat_checks.update_value(value=str(total_checks))
        self.stat_violations.update_value(value=str(total_violations))

    def apply_theme(self):
        """暗色模式切换时重建UI"""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
