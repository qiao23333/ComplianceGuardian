#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设置页面 — v2.2 现代仪表盘风

升级内容：
1. GlassCard Ollama 状态区
2. 精致信息表格
3. 暗色模式说明
4. 暗色模式支持
"""
import threading
import customtkinter as ctk
from tkinter import messagebox

from ui.theme import (
    get_colors, font_safe, font_typo, SPACING, CORNER_RADIUS,
    primary_button_style, secondary_button_style, card_frame_style,
    glass_card_style, gradient_button_style,
)
from ui.widgets import GradientCard, GlassCard, ToastNotification
from core.detector import ComplianceDetector


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)  # app.py 也传了 fg_color，避免重复
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        colors = get_colors()

        # 标题区
        ctk.CTkLabel(self, text="设置", font=font_typo("h1"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xxl"], pady=(SPACING["xl"], SPACING["xs"]))
        ctk.CTkLabel(self, text="AI模型配置与系统信息",
                     font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(anchor="w", padx=SPACING["xxl"], pady=(0, SPACING["lg"]))

        # Ollama 状态卡片 — GlassCard
        ollama_card = GlassCard(self)
        ollama_card.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["md"]))

        header = ctk.CTkFrame(ollama_card, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["xs"]))
        ctk.CTkLabel(header, text="🤖 Ollama 本地AI模型", font=font_typo("h2"),
                     text_color=colors["glass_text"]).pack(side="left")
        self.ollama_status_btn = ctk.CTkButton(header, text="检查状态", width=80, height=28,
                                               corner_radius=CORNER_RADIUS["sm"],
                                               font=font_typo("caption"),
                                               fg_color=colors["glass_border"],
                                               hover_color=colors["hover"],
                                               text_color=colors["glass_text"],
                                               border_width=0,
                                               command=self._check_ollama)
        self.ollama_status_btn.pack(side="right")

        ctk.CTkLabel(ollama_card, text="使用本地大模型（qwen2.5:7b）进行语义层面的深度合规检测。\n核心关键词检测无需AI即可运行，AI深度检测为增强功能。",
                     font=font_typo("caption"),
                     text_color=colors["text_secondary"], justify="left").pack(anchor="w", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        # 状态显示区
        self.ollama_status_frame = ctk.CTkFrame(ollama_card, fg_color=colors["bg"], corner_radius=CORNER_RADIUS["md"])
        self.ollama_status_frame.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["lg"]))

        self.ollama_status_label = ctk.CTkLabel(self.ollama_status_frame, text="点击「检查状态」检测Ollama运行情况",
                                                font=font_typo("caption"),
                                                text_color=colors["text_secondary"])
        self.ollama_status_label.pack(anchor="w", padx=SPACING["md"], pady=SPACING["sm"])

        self.ollama_models_label = ctk.CTkLabel(self.ollama_status_frame, text="",
                                                font=font_typo("micro"),
                                                text_color=colors["text"])
        self.ollama_models_label.pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["sm"]))

        # 关于卡片 — GradientCard 样式
        about_card = ctk.CTkFrame(self, **card_frame_style())
        about_card.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["md"]))

        # 顶部渐变条
        gradient_bar = ctk.CTkFrame(about_card, height=4, fg_color=colors["gradient_card_purple_top"],
                                    corner_radius=0)
        gradient_bar.pack(fill="x")

        ctk.CTkLabel(about_card, text="关于", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["md"], SPACING["sm"]))

        detector = ComplianceDetector.get_instance()
        rules_summary = detector.get_rules_summary()

        info_items = [
            ("应用名称", "多平台内容合规检测工具"),
            ("版本", "v2.3 优化版"),
            ("技术栈", "Python + CustomTkinter + Ollama"),
            ("广告法词库", f"{rules_summary['广告法违禁词']} 条"),
            ("正则模式", f"{rules_summary.get('正则模式', 0)} 组"),
            ("平台规则", " · ".join(f"{k} {v}条" for k, v in rules_summary["平台规则"].items())),
            ("蓝V限制", f"{rules_summary['蓝V专属限制']} 条"),
            ("行业红线", f"{rules_summary['行业红线']} 条"),
            ("支持平台", "小红书 · 抖音 · 微信视频号"),
            ("检测维度", "关键词 + 正则模式 + AI语义增强"),
            ("外观模式", "浅色 / 暗色（侧栏底部切换）"),
        ]

        for label, value in info_items:
            row = ctk.CTkFrame(about_card, fg_color="transparent")
            row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
            ctk.CTkLabel(row, text=label, font=font_typo("micro"),
                         text_color=colors["text_tertiary"]).pack(side="left")
            ctk.CTkLabel(row, text=value, font=font_typo("caption_bold"),
                         text_color=colors["text"]).pack(side="right")

        ctk.CTkLabel(about_card, text="核心检测完全本地运行，数据不上传。AI检测使用本地Ollama，数据不出设备。",
                     font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["xs"], SPACING["lg"]))

        # 数据管理卡片
        data_card = ctk.CTkFrame(self, **card_frame_style())
        data_card.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["xxl"]))

        # 顶部渐变条
        gradient_bar2 = ctk.CTkFrame(data_card, height=4, fg_color=colors["gradient_card_orange_top"],
                                     corner_radius=0)
        gradient_bar2.pack(fill="x")

        ctk.CTkLabel(data_card, text="数据管理", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["md"], SPACING["sm"]))

        stats_row = ctk.CTkFrame(data_card, fg_color="transparent")
        stats_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["md"]))

        total_checks = self.app.config_manager.get("total_checks", 0)
        total_violations = self.app.config_manager.get("total_violations", 0)

        ctk.CTkLabel(stats_row, text=f"累计检测：{total_checks} 次",
                     font=font_typo("caption"), text_color=colors["text"]).pack(side="left", padx=(0, SPACING["xl"]))
        ctk.CTkLabel(stats_row, text=f"累计违规：{total_violations} 条",
                     font=font_typo("caption"), text_color=colors["text"]).pack(side="left")

        ctk.CTkButton(data_card, text="重置检测统计", width=120,
                      command=self._reset_stats, **secondary_button_style()).pack(anchor="w", padx=SPACING["xl"], pady=(0, SPACING["lg"]))

    def _check_ollama(self):
        """检查Ollama状态（后台线程）"""
        colors = get_colors()
        self.ollama_status_btn.configure(state="disabled", text="检测中...")
        self.ollama_status_label.configure(text="正在检测Ollama服务...", text_color=colors["text_secondary"])
        self.ollama_models_label.configure(text="")

        def worker():
            available, models = ComplianceDetector.check_ollama_available()
            self.after(0, lambda: self._show_ollama_status(available, models))

        threading.Thread(target=worker, daemon=True).start()

    def _show_ollama_status(self, available, models):
        """显示Ollama状态"""
        colors = get_colors()
        self.ollama_status_btn.configure(state="normal", text="检查状态")

        if available:
            self.ollama_status_label.configure(text="✅ Ollama 服务运行中", text_color=colors["success"])
            if models:
                model_text = "已安装模型：\n" + "\n".join(f"  • {m}" for m in models)
                has_qwen = any("qwen2.5" in m for m in models)
                if has_qwen:
                    model_text += "\n\n✅ 已找到 qwen2.5 模型，可使用AI深度检测"
                else:
                    model_text += "\n\n⚠️ 未找到 qwen2.5 模型，请运行：ollama pull qwen2.5:7b"
                self.ollama_models_label.configure(text=model_text)
        else:
            self.ollama_status_label.configure(text="❌ Ollama 服务未运行", text_color=colors["danger"])
            self.ollama_models_label.configure(text="请安装并启动 Ollama：\n  1. 下载：https://ollama.com\n  2. 启动：ollama serve\n  3. 拉取模型：ollama pull qwen2.5:7b")

    def _reset_stats(self):
        if messagebox.askyesno("确认", "确定重置检测统计数据？"):
            self.app.config_manager.set("total_checks", 0)
            self.app.config_manager.set("total_violations", 0)
            messagebox.showinfo("成功", "统计数据已重置")

    def refresh(self):
        pass

    def apply_theme(self):
        """暗色模式切换时重建UI"""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
