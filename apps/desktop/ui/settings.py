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
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from apps.desktop.ui.theme import (
    get_colors, font_safe, font_typo, SPACING, CORNER_RADIUS,
    primary_button_style, secondary_button_style, card_frame_style,
    glass_card_style, gradient_button_style,
)
from apps.desktop.ui.widgets import GradientCard, GlassCard, ToastNotification
from guardian.detector import ComplianceDetector
from guardian.llm_config import LLM_DEFAULTS, load_llm_config, save_llm_config

# 常见 OpenAI 兼容端点（下拉候选，可手改）
_CLOUD_PRESETS = {
    "DeepSeek": "https://api.deepseek.com/v1",
    "OpenAI": "https://api.openai.com/v1",
    "通义千问": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "自定义": "",
}


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

        ctk.CTkLabel(ollama_card, text="使用本地大模型或云端 API 进行语义层面的深度合规检测。\n核心关键词检测无需 AI 即可运行，AI 深度检测为增强功能（可在下方配置）。",
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

        # ---------------- AI 模型配置卡片 ----------------
        cfg_card = ctk.CTkFrame(self, **card_frame_style())
        cfg_card.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["md"]))

        gradient_bar_cfg = ctk.CTkFrame(cfg_card, height=4,
                                        fg_color=colors["gradient_card_purple_top"], corner_radius=0)
        gradient_bar_cfg.pack(fill="x")

        ctk.CTkLabel(cfg_card, text="AI 模型配置", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["md"], SPACING["xs"]))
        ctk.CTkLabel(cfg_card,
                     text="启用后，「AI 深度检测」会把文案交给大模型做语义复核；未启用时仅用本地规则（完全离线）。",
                     font=font_typo("micro"), text_color=colors["text_tertiary"],
                     justify="left", wraplength=560).pack(anchor="w", padx=SPACING["xl"], pady=(0, SPACING["sm"]))

        cm = self.app.config_manager

        # 启用开关
        row_enable = ctk.CTkFrame(cfg_card, fg_color="transparent")
        row_enable.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(row_enable, text="启用 AI 增强", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_enable_var = tk.BooleanVar(value=bool(cm.get("llm_enabled", False)))
        ctk.CTkSwitch(row_enable, text="", variable=self.llm_enable_var,
                      command=self._sync_llm_fields).pack(side="right")

        # 模式选择
        row_mode = ctk.CTkFrame(cfg_card, fg_color="transparent")
        row_mode.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(row_mode, text="模式", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_mode_var = tk.StringVar(
            value="本地 Ollama" if cm.get("llm_mode", "local") == "local" else "云端 API")
        ctk.CTkSegmentedButton(row_mode, values=["本地 Ollama", "云端 API"],
                               variable=self.llm_mode_var,
                               command=lambda _v: self._sync_llm_fields(),
                               font=font_typo("caption")).pack(side="right")

        # 模型名（本地/云端共用）
        row_model = ctk.CTkFrame(cfg_card, fg_color="transparent")
        row_model.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(row_model, text="模型名", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_model_entry = ctk.CTkEntry(row_model, width=260, font=font_typo("caption"))
        self.llm_model_entry.insert(0, cm.get("llm_model") or LLM_DEFAULTS["llm_model"])
        self.llm_model_entry.pack(side="right")

        # 本地 Ollama 地址
        self.llm_local_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        ctk.CTkLabel(self.llm_local_row, text="Ollama 地址", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_local_entry = ctk.CTkEntry(self.llm_local_row, width=260, font=font_typo("caption"))
        self.llm_local_entry.insert(0, cm.get("llm_local_base") or LLM_DEFAULTS["llm_local_base"])
        self.llm_local_entry.pack(side="right")

        # 云端 API 地址
        self.llm_cloud_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        ctk.CTkLabel(self.llm_cloud_row, text="API 地址", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_cloud_entry = ctk.CTkEntry(self.llm_cloud_row, width=260, font=font_typo("caption"))
        self.llm_cloud_entry.insert(0, cm.get("llm_base_url") or LLM_DEFAULTS["llm_base_url"])
        self.llm_cloud_entry.pack(side="right")

        # 云端 API Key
        self.llm_key_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        ctk.CTkLabel(self.llm_key_row, text="API Key", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.llm_key_entry = ctk.CTkEntry(self.llm_key_row, width=260, show="•", font=font_typo("caption"))
        self.llm_key_entry.insert(0, cm.get("llm_api_key") or "")
        self.llm_key_entry.pack(side="right")

        # 云端预设快捷填入
        self.llm_preset_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        ctk.CTkLabel(self.llm_preset_row, text="快捷预设", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        ctk.CTkOptionMenu(self.llm_preset_row, values=list(_CLOUD_PRESETS.keys()),
                          width=140, font=font_typo("caption"),
                          command=self._apply_cloud_preset).pack(side="right")

        # 保存按钮
        ctk.CTkButton(cfg_card, text="保存 AI 配置", width=140,
                      command=self._save_llm, **primary_button_style()).pack(
            anchor="w", padx=SPACING["xl"], pady=(SPACING["sm"], SPACING["lg"]))

        self._sync_llm_fields()

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
            ("版本", "v3.0"),
            ("技术栈", "Python + CustomTkinter + Ollama/OpenAI兼容"),
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

        # 桌面行为：最小化到托盘
        tray_row = ctk.CTkFrame(data_card, fg_color="transparent")
        tray_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(tray_row, text="关闭窗口时最小化到托盘", font=font_typo("caption"),
                     text_color=colors["text"]).pack(side="left")
        self.tray_var = tk.BooleanVar(value=bool(self.app.config_manager.get("minimize_to_tray", True)))
        ctk.CTkSwitch(tray_row, text="", variable=self.tray_var,
                      command=self._toggle_tray).pack(side="right")

        ctk.CTkButton(data_card, text="重置检测统计", width=120,
                      command=self._reset_stats, **secondary_button_style()).pack(anchor="w", padx=SPACING["xl"], pady=(SPACING["sm"], SPACING["lg"]))

    # ------------------------------------------------ AI 配置

    def _sync_llm_fields(self):
        """按「启用 / 模式」显隐相关字段行。"""
        enabled = bool(self.llm_enable_var.get())
        is_local = self.llm_mode_var.get() == "本地 Ollama"
        # 先全部隐藏
        for row in (self.llm_local_row, self.llm_cloud_row, self.llm_key_row, self.llm_preset_row):
            row.pack_forget()
        if not enabled:
            return
        if is_local:
            self.llm_local_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
        else:
            self.llm_cloud_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
            self.llm_key_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))
            self.llm_preset_row.pack(fill="x", padx=SPACING["xl"], pady=(0, SPACING["xs"]))

    def _apply_cloud_preset(self, name: str):
        """快捷填入常见 OpenAI 兼容端点。"""
        url = _CLOUD_PRESETS.get(name, "")
        if not url:
            return
        self.llm_cloud_entry.delete(0, "end")
        self.llm_cloud_entry.insert(0, url)
        # 顺手给出该端点的常见模型名提示
        preset_models = {
            "DeepSeek": "deepseek-chat",
            "OpenAI": "gpt-4o-mini",
            "通义千问": "qwen-plus",
        }.get(name)
        if preset_models:
            self.llm_model_entry.delete(0, "end")
            self.llm_model_entry.insert(0, preset_models)

    def _save_llm(self):
        """持久化 AI 配置并注入引擎。"""
        enabled = bool(self.llm_enable_var.get())
        is_local = self.llm_mode_var.get() == "本地 Ollama"
        mode = "local" if is_local else "cloud"
        try:
            contract = save_llm_config(
                self.app.config_manager,
                enabled=enabled,
                mode=mode,
                api_key=self.llm_key_entry.get().strip(),
                base_url=self.llm_cloud_entry.get().strip() or None,
                model=self.llm_model_entry.get().strip() or None,
                local_base=self.llm_local_entry.get().strip() or None,
            )
            # 注入运行中的引擎
            ComplianceDetector.get_instance().apply_llm_config(contract)
        except Exception as e:  # pragma: no cover - UI 兜底
            messagebox.showerror("保存失败", f"AI 配置保存出错：{e}")
            return

        if not enabled:
            msg = "已关闭 AI 增强，仅使用本地规则检测。"
        elif mode == "cloud" and not contract:
            msg = "云端模式需填写 API Key 才会生效。当前仅使用本地规则。"
        elif mode == "local":
            msg = "已启用本地 Ollama。请确保服务已启动（ollama serve）。"
        else:
            msg = "已启用云端 API 增强。"
        toast = ToastNotification(self, "AI 配置已保存")
        toast.show(self)
        messagebox.showinfo("AI 配置", msg)

    # ------------------------------------------------ Ollama 探测

    def _check_ollama(self):
        """检查Ollama状态（后台线程）"""
        colors = get_colors()
        self.ollama_status_btn.configure(state="disabled", text="检测中...")
        self.ollama_status_label.configure(text="正在检测Ollama服务...", text_color=colors["text_secondary"])
        self.ollama_models_label.configure(text="")

        base = self.llm_local_entry.get().strip() or None

        def worker():
            available, models = ComplianceDetector.check_ollama_available(base)
            self.after(0, lambda: self._show_ollama_status(available, models))

        threading.Thread(target=worker, daemon=True).start()

    def _show_ollama_status(self, available, models):
        """显示Ollama状态"""
        colors = get_colors()
        self.ollama_status_btn.configure(state="normal", text="检查状态")

        want = (self.llm_model_entry.get().strip() or "qwen2.5:7b")
        if available:
            self.ollama_status_label.configure(text="✅ Ollama 服务运行中", text_color=colors["success"])
            if models:
                model_text = "已安装模型：\n" + "\n".join(f"  • {m}" for m in models)
                # 按配置的模型名（忽略 :tag 大小写）做包含匹配
                base = want.split(":")[0]
                if any(base in m for m in models):
                    model_text += f"\n\n✅ 已找到「{want}」，可使用 AI 深度检测"
                else:
                    model_text += f"\n\n⚠️ 未找到「{want}」，请运行：ollama pull {want}"
                self.ollama_models_label.configure(text=model_text)
        else:
            self.ollama_status_label.configure(text="❌ Ollama 服务未运行", text_color=colors["danger"])
            self.ollama_models_label.configure(
                text=f"请安装并启动 Ollama：\n  1. 下载：https://ollama.com\n  2. 启动：ollama serve\n  3. 拉取模型：ollama pull {want}")

    def _toggle_tray(self):
        """保存「最小化到托盘」开关。"""
        self.app.config_manager.set("minimize_to_tray", bool(self.tray_var.get()))

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
