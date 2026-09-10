#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规检测页面 — v2.2 现代仪表盘风

升级内容：
1. UI 全面重绘（GlassCard 控制栏、SegmentedControl 平台选择、ProgressRing 分数展示）
2. 悬停浮窗（高亮词详情弹出）
3. 右键菜单（添加到词库、复制文本）
4. 消除所有硬编码颜色，统一用 get_colors()
5. 暗色模式完整支持
"""
import bisect
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from apps.desktop.ui.theme import (
    get_colors, font_safe, font_emoji, font_typo, SPACING, CORNER_RADIUS,
    primary_button_style, secondary_button_style, card_frame_style,
    glass_card_style, elevated_card_style, gradient_button_style,
    status_pill_style,
)
from apps.desktop.ui.widgets import (
    ProgressRing, ScoreRing, GlassCard, StatusPill,
    HoverTooltip, SegmentedControl, ToastNotification,
)
from guardian.detector import ComplianceDetector


class CheckerPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)  # app.py 也传了 fg_color，避免重复
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self.detector = ComplianceDetector.get_instance()
        self.current_result = None
        self.preview_mode = False
        self._detecting = False
        self._llm_running = False
        self._char_timer = None
        self._line_starts = None
        self._tooltip_manager = None
        self._build_ui()
        self._init_text_tags()

    def _build_ui(self):
        colors = get_colors()

        # 标题区
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["xxl"], pady=(SPACING["xl"], 0))

        ctk.CTkLabel(header, text="合规检测", font=font_typo("h1"),
                     text_color=colors["text"]).pack(side="left")
        ctk.CTkLabel(header, text="AI增强 · 正则模式 · 多平台", font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(side="left", padx=(SPACING["md"], 0), pady=(8, 0))

        # 控制栏 — GlassCard 样式
        control_card = ctk.CTkFrame(self, **glass_card_style())
        control_card.pack(fill="x", padx=SPACING["xxl"], pady=(SPACING["lg"], SPACING["md"]))

        control_inner = ctk.CTkFrame(control_card, fg_color="transparent")
        control_inner.pack(fill="x", padx=SPACING["lg"], pady=SPACING["md"])

        # 平台选择 — SegmentedControl 样式
        ctk.CTkLabel(control_inner, text="发布平台", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))

        self.platform_var = ctk.StringVar(value=self.app.config_manager.get("last_platform", "小红书"))

        segments = [("小红书", "小红书"), ("抖音", "抖音"), ("视频号", "微信视频号"), ("通用", "all"), ("对比", "cross_platform")]
        initial_idx = 0
        for i, (_, v) in enumerate(segments):
            if v == self.platform_var.get():
                initial_idx = i
                break

        self.platform_control = SegmentedControl(
            control_inner, segments=segments,
            on_select=self._on_platform_select,
            initial=initial_idx,
        )
        self.platform_control.pack(fill="x", pady=(0, SPACING["md"]))

        # 账号类型
        acct_frame = ctk.CTkFrame(control_inner, fg_color="transparent")
        acct_frame.pack(fill="x")

        ctk.CTkLabel(acct_frame, text="账号类型", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(side="left", padx=(0, SPACING["md"]))

        self.account_var = ctk.StringVar(value=self.app.config_manager.get("last_account_type", "blue_v"))

        self.bluev_btn = ctk.CTkButton(acct_frame, text="蓝V认证", width=90, height=28,
                                       corner_radius=CORNER_RADIUS["sm"],
                                       fg_color=colors["primary"], hover_color=colors["primary_hover"],
                                       text_color=colors["text_on_primary"],
                                       font=font_typo("caption_bold"),
                                       command=lambda: self._select_account("blue_v"))
        self.bluev_btn.pack(side="left", padx=(0, SPACING["xs"]))

        self.nonbluev_btn = ctk.CTkButton(acct_frame, text="非蓝V", width=80, height=28,
                                          corner_radius=CORNER_RADIUS["sm"],
                                          fg_color=colors["card"], hover_color=colors["hover"],
                                          text_color=colors["text"],
                                          border_width=1, border_color=colors["border_light"],
                                          font=font_typo("caption"),
                                          command=lambda: self._select_account("non_blue_v"))
        self.nonbluev_btn.pack(side="left")

        # 检测按钮组
        btn_group = ctk.CTkFrame(control_inner, fg_color="transparent")
        btn_group.pack(side="right")

        self.detect_btn = ctk.CTkButton(btn_group, text="开始检测", width=120,
                                        command=self._run_detection,
                                        **gradient_button_style())
        self.detect_btn.pack(side="left", padx=(0, SPACING["sm"]))

        self.llm_btn = ctk.CTkButton(btn_group, text="AI深度检测", width=120,
                                     command=self._run_llm_detection,
                                     fg_color=colors["card"], hover_color=colors["hover"],
                                     text_color=colors["primary"],
                                     border_width=1, border_color=colors["primary"],
                                     font=font_typo("caption_bold"))
        self.llm_btn.pack(side="left")

        # 主体区域
        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.pack(fill="both", expand=True, padx=SPACING["xxl"], pady=(0, SPACING["xl"]))

        body_frame.grid_columnconfigure(0, weight=3)
        body_frame.grid_columnconfigure(1, weight=2)
        body_frame.grid_rowconfigure(0, weight=1)

        # 左侧：文案输入/高亮预览 — elevated card
        left_card = ctk.CTkFrame(body_frame, **elevated_card_style())
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]))
        left_card.grid_propagate(False)

        left_header = ctk.CTkFrame(left_card, fg_color="transparent")
        left_header.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["xs"]))

        self.mode_label = ctk.CTkLabel(left_header, text="文案输入", font=font_typo("h3"),
                                       text_color=colors["text"])
        self.mode_label.pack(side="left")

        # 快捷操作按钮组
        quick_btns = ctk.CTkFrame(left_header, fg_color="transparent")
        quick_btns.pack(side="right")

        self.paste_btn = ctk.CTkButton(quick_btns, text="📋 粘贴", width=70,
                                        corner_radius=CORNER_RADIUS["sm"],
                                        fg_color=colors["hover"],
                                        hover_color=colors["pressed"],
                                        text_color=colors["text"],
                                        font=font_typo("caption"),
                                        command=self._paste_text)
        self.paste_btn.pack(side="left", padx=(0, SPACING["xs"]))

        self.copy_input_btn = ctk.CTkButton(quick_btns, text="📑 复制", width=70,
                                             corner_radius=CORNER_RADIUS["sm"],
                                             fg_color=colors["hover"],
                                             hover_color=colors["pressed"],
                                             text_color=colors["text"],
                                             font=font_typo("caption"),
                                             command=self._copy_all)
        self.copy_input_btn.pack(side="left", padx=(0, SPACING["xs"]))

        self.clear_btn = ctk.CTkButton(quick_btns, text="🗑 清空", width=70,
                                       corner_radius=CORNER_RADIUS["sm"],
                                       fg_color=colors["hover"],
                                       hover_color=colors["pressed"],
                                       text_color=colors["text"],
                                       font=font_typo("caption"),
                                       command=self._clear_input)
        self.clear_btn.pack(side="left")

        self.toggle_btn = ctk.CTkButton(left_header, text="高亮预览", width=90,
                                        corner_radius=CORNER_RADIUS["sm"],
                                        fg_color="transparent",
                                        hover_color=colors["hover"],
                                        text_color=colors["primary"],
                                        font=font_typo("caption"),
                                        command=self._toggle_mode, state="disabled")

        self.textbox = ctk.CTkTextbox(left_card, font=font_safe(15, "normal"),
                                      fg_color=colors["card"], border_width=0,
                                      corner_radius=CORNER_RADIUS["md"], wrap="word")
        self.textbox.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["xs"]))
        self.textbox.insert("1.0", "")
        self.textbox.bind("<KeyRelease>", self._on_keyrelease)
        # 右键菜单
        self.textbox.bind("<Button-3>", self._on_right_click)

        # 底部状态栏
        footer_frame = ctk.CTkFrame(left_card, fg_color="transparent")
        footer_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))

        self.char_label = ctk.CTkLabel(footer_frame, text="0 字", font=font_typo("micro"),
                                       text_color=colors["text_tertiary"])
        self.char_label.pack(side="left")

        self.toggle_btn.pack(side="right")  # 高亮预览按钮放底部

        self.status_label = ctk.CTkLabel(footer_frame, text="", font=font_typo("micro"),
                                         text_color=colors["text_tertiary"])
        self.status_label.pack(side="right", padx=(SPACING["md"], 0))

        # 右侧：检测结果
        right_card = ctk.CTkFrame(body_frame, **card_frame_style())
        right_card.grid(row=0, column=1, sticky="nsew")
        right_card.grid_propagate(False)

        right_header = ctk.CTkFrame(right_card, fg_color="transparent")
        right_header.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["xs"]))
        ctk.CTkLabel(right_header, text="检测结果", font=font_typo("h3"),
                     text_color=colors["text"]).pack(side="left")
        self.result_status = ctk.CTkLabel(right_header, text="", font=font_typo("micro"),
                                          text_color=colors["text_tertiary"])
        self.result_status.pack(side="right")

        # 空状态
        self.empty_frame = ctk.CTkFrame(right_card, fg_color="transparent")
        self.empty_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        ctk.CTkLabel(self.empty_frame, text="📋", font=font_emoji(40)).pack(pady=(30, SPACING["xs"]))
        ctk.CTkLabel(self.empty_frame, text="等待检测", font=font_typo("h2"),
                     text_color=colors["text_secondary"]).pack(pady=(0, SPACING["xs"]))
        ctk.CTkLabel(self.empty_frame, text="粘贴文案后点击「开始检测」\n或「AI深度检测」获取语义分析",
                     font=font_typo("caption"),
                     text_color=colors["text_tertiary"]).pack(pady=(0, 30))

        # 结果区域
        self.result_frame = ctk.CTkFrame(right_card, fg_color="transparent")

    # ============================================================
    # 交互逻辑
    # ============================================================

    def _init_text_tags(self):
        """初始化文本框高亮标签样式"""
        colors = get_colors()
        self.textbox.tag_config("violation",
                                background=colors["highlight_violation_bg"],
                                foreground=colors["highlight_violation_fg"])
        self.textbox.tag_config("warning",
                                background=colors["highlight_warning_bg"],
                                foreground=colors["highlight_warning_fg"])
        self.textbox.tag_config("blue_v_violation",
                                background=colors["highlight_bluev_bg"],
                                foreground=colors["highlight_bluev_fg"],
                                underline=True)
        self.textbox.tag_config("blue_v_warning",
                                background=colors["highlight_bluev_bg"],
                                foreground=colors["highlight_bluev_fg"])

    def _on_platform_select(self, value):
        """平台选择回调"""
        self.platform_var.set(value)
        # 保存偏好
        self.app.config_manager.set("last_platform", value)

    def _select_account(self, value):
        """账号类型切换"""
        colors = get_colors()
        self.account_var.set(value)
        self.app.config_manager.set("last_account_type", value)
        if value == "blue_v":
            self.bluev_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"],
                                     text_color=colors["text_on_primary"],
                                     font=font_typo("caption_bold"))
            self.nonbluev_btn.configure(fg_color=colors["card"], hover_color=colors["hover"],
                                        text_color=colors["text"], border_width=1,
                                        border_color=colors["border_light"],
                                        font=font_typo("caption"))
        else:
            self.bluev_btn.configure(fg_color=colors["card"], hover_color=colors["hover"],
                                     text_color=colors["text"], border_width=1,
                                     border_color=colors["border_light"],
                                     font=font_typo("caption"))
            self.nonbluev_btn.configure(fg_color=colors["primary"], hover_color=colors["primary_hover"],
                                        text_color=colors["text_on_primary"],
                                        font=font_typo("caption_bold"))

    def _on_keyrelease(self, event=None):
        """按键释放 — debounce字数统计"""
        if self._char_timer:
            self.after_cancel(self._char_timer)
        self._char_timer = self.after(300, self._update_char_count)

    def _update_char_count(self):
        colors = get_colors()
        text = self.textbox.get("1.0", "end-1c")
        self.char_label.configure(text=f"{len(text)} 字")
        self._char_timer = None

    def _on_right_click(self, event):
        """右键菜单 — 添加到词库、复制文本"""
        # 获取选中的文字
        try:
            selected = self.textbox.get("sel.first", "sel.last")
        except tk.TclError:
            selected = ""

        # 获取鼠标位置的单词
        index = self.textbox.index(f"@{event.x},{event.y}")
        word = self.textbox.get(index + " wordstart", index + " wordend").strip()

        menu = tk.Menu(self, tearoff=0)
        colors = get_colors()

        if selected:
            menu.add_command(label=f"复制选中文本", command=lambda: self._copy_selection(selected))
            menu.add_command(label=f"添加「{selected[:10]}」到词库",
                             command=lambda: self._add_to_rules(selected))
        elif word:
            menu.add_command(label=f"添加「{word[:10]}」到词库",
                             command=lambda: self._add_to_rules(word))
        else:
            menu.add_command(label="复制全部文案", command=self._copy_all)

        menu.add_separator()
        menu.add_command(label="清空输入", command=self._clear_input)

        menu.tk_popup(event.x_root, event.y_root)

    def _copy_selection(self, text):
        """复制选中文字"""
        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(text)
        toast = ToastNotification(self, "已复制到剪贴板")
        toast.show(self)

    def _copy_all(self):
        """复制全部文案"""
        text = self.textbox.get("1.0", "end-1c")
        root = self.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(text)
        toast = ToastNotification(self, "已复制全部文案")
        toast.show(self)

    def _add_to_rules(self, keyword):
        """右键添加到词库 — 打开词库管理页面的添加对话框"""
        # 切换到词库管理页面并触发添加
        self.app.show_page("rules")
        rules_page = self.app.pages.get("rules")
        if rules_page:
            rules_page._show_add_dialog_with_keyword(keyword)

    def _clear_input(self):
        """清空输入"""
        self.textbox.delete("1.0", "end")
        self.current_result = None
        self.preview_mode = False

    def _paste_text(self):
        """从剪贴板粘贴文案到输入框"""
        root = self.winfo_toplevel()
        try:
            clipboard_text = root.clipboard_get()
            if clipboard_text:
                self.textbox.delete("1.0", "end")
                self.textbox.insert("1.0", clipboard_text)
                self._update_char_count()
                toast = ToastNotification(self, "已粘贴文案")
                toast.show(self)
            else:
                toast = ToastNotification(self, "剪贴板为空", icon="⚠️")
                toast.show(self)
        except Exception:
            toast = ToastNotification(self, "无法读取剪贴板", icon="❌")
            toast.show(self)

    # ============================================================
    # 检测逻辑
    # ============================================================

    def _run_detection(self):
        """执行检测 — 后台线程化"""
        if self._detecting:
            return

        text = self.textbox.get("1.0", "end-1c")
        if not text.strip():
            return

        platform = self.platform_var.get()
        account_type = self.account_var.get()

        # 保存用户偏好到配置
        self.app.config_manager.set("last_platform", platform)
        self.app.config_manager.set("last_account_type", account_type)

        # 跨平台对比检测
        if platform == "cross_platform":
            self._run_cross_platform_detection(text, account_type)
            return

        plat_map = {"小红书": "xiaohongshu", "抖音": "douyin", "微信视频号": "weixin", "all": "all"}
        plat_key = plat_map.get(platform, "xiaohongshu")

        colors = get_colors()
        self._detecting = True
        self.detect_btn.configure(state="disabled", text="检测中...")
        self.llm_btn.configure(state="disabled")
        self.status_label.configure(text="正在检测...", text_color=colors["primary"])
        self.result_status.configure(text="检测中")

        def worker():
            try:
                result = self.detector.detect(text, plat_key, account_type)
                self.after(0, lambda: self._on_detection_done(result))
            except Exception as e:
                self.after(0, lambda: self._on_detection_error(str(e)))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _run_cross_platform_detection(self, text, account_type):
        """跨平台对比检测"""
        colors = get_colors()
        self._detecting = True
        self.detect_btn.configure(state="disabled", text="对比中...")
        self.llm_btn.configure(state="disabled")
        self.status_label.configure(text="跨平台对比检测中...", text_color=colors["primary"])

        def worker():
            try:
                results = self.detector.detect_all_platforms(text, account_type)
                self.after(0, lambda: self._on_cross_platform_done(results))
            except Exception as e:
                self.after(0, lambda: self._on_detection_error(str(e)))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _on_detection_done(self, result):
        """检测完成回调"""
        colors = get_colors()
        self._detecting = False
        self.detect_btn.configure(state="normal", text="开始检测")
        self.llm_btn.configure(state="normal")
        self.status_label.configure(text="")
        self.result_status.configure(text="")

        self.current_result = result
        self._display_result(result)

        # 更新统计
        self.app.config_manager.set("total_checks", self.app.config_manager.get("total_checks", 0) + 1)
        self.app.config_manager.set("total_violations",
                                    self.app.config_manager.get("total_violations", 0) + result["summary"]["violations"])
        self.toggle_btn.configure(state="normal")

    def _on_cross_platform_done(self, results):
        """跨平台对比检测完成"""
        colors = get_colors()
        self._detecting = False
        self.detect_btn.configure(state="normal", text="开始检测")
        self.llm_btn.configure(state="normal")
        self.status_label.configure(text="对比检测完成", text_color=colors["success"])
        self.after(3000, lambda: self.status_label.configure(text=""))

        self.current_result = None  # 跨平台模式不设单一结果
        self._display_cross_platform_result(results)

        self.app.config_manager.set("total_checks", self.app.config_manager.get("total_checks", 0) + 1)
        self.toggle_btn.configure(state="disabled")  # 跨平台不支持高亮预览

    def _on_detection_error(self, error_msg):
        """检测出错回调"""
        colors = get_colors()
        self._detecting = False
        self.detect_btn.configure(state="normal", text="开始检测")
        self.llm_btn.configure(state="normal")
        self.status_label.configure(text="检测失败", text_color=colors["danger"])
        messagebox.showerror("检测错误", f"检测过程中出错：\n{error_msg}")

    def _run_llm_detection(self):
        """AI深度检测"""
        if self._llm_running or self._detecting:
            return

        text = self.textbox.get("1.0", "end-1c")
        if not text.strip():
            return

        available, models = ComplianceDetector.check_ollama_available()
        if not available:
            messagebox.showwarning("Ollama未运行", "请先启动Ollama服务\n\n终端运行：ollama serve\n或检查Ollama是否已安装")
            return

        if "qwen2.5:7b" not in " ".join(models):
            messagebox.showwarning("模型未找到", f"未找到qwen2.5:7b模型\n\n已安装模型：{', '.join(models)}\n\n请先拉取：ollama pull qwen2.5:7b")
            return

        # 先执行关键词检测
        self._run_detection()

        colors = get_colors()
        self._llm_running = True
        self.llm_btn.configure(state="disabled", text="AI分析中...")
        self.status_label.configure(text="AI深度分析中（约10-30秒）...", text_color=colors["primary"])

        platform = self.platform_var.get()
        account_type = self.account_var.get()
        plat_map = {"小红书": "xiaohongshu", "抖音": "douyin", "微信视频号": "weixin", "all": "all"}
        plat_key = plat_map.get(platform, "xiaohongshu")

        def llm_worker():
            try:
                llm_result = self.detector._llm_analyze(text, plat_key, account_type, self.current_result or {"violations": []})
                self.after(0, lambda: self._on_llm_done(llm_result))
            except Exception as e:
                self.after(0, lambda: self._on_llm_error(str(e)))

        self.after(1500, lambda: threading.Thread(target=llm_worker, daemon=True).start())

    def _on_llm_done(self, llm_result):
        """LLM分析完成回调"""
        colors = get_colors()
        self._llm_running = False
        self.llm_btn.configure(state="normal", text="AI深度检测")
        self.status_label.configure(text="AI分析完成", text_color=colors["success"])
        self.after(3000, lambda: self.status_label.configure(text=""))

        self._display_llm_result(llm_result)

    def _on_llm_error(self, error_msg):
        """LLM分析出错"""
        colors = get_colors()
        self._llm_running = False
        self.llm_btn.configure(state="normal", text="AI深度检测")
        self.status_label.configure(text="AI分析失败", text_color=colors["danger"])
        messagebox.showwarning("AI分析失败", f"Ollama LLM分析出错：\n{error_msg}\n\n请确保Ollama服务正在运行")

    # ============================================================
    # 结果展示
    # ============================================================

    def _display_result(self, result):
        """显示关键词检测结果"""
        colors = get_colors()
        self.empty_frame.pack_forget()
        for widget in self.result_frame.winfo_children():
            widget.destroy()
        self.result_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["md"]))

        summary = result["summary"]

        # 顶部：分数圆环 + 风险胶囊
        top_row = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, SPACING["md"]))

        # 合规分数圆环
        ring = ProgressRing(top_row, summary["score"], size=120)
        ring.pack(side="left", padx=(0, SPACING["md"]))

        # 风险信息区
        info_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info_frame, text="风险等级", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(SPACING["md"], SPACING["xs"]))

        # 风险等级映射
        risk_map = {
            "安全": "safe", "低风险": "low", "中风险": "medium",
            "高风险": "high", "极高风险": "extreme",
        }
        level_key = risk_map.get(summary["risk_level"], "medium")
        StatusPill(info_frame, level=level_key, text=summary["risk_level"]).pack(anchor="w", pady=(0, SPACING["md"]))

        count_text = f"违规 {summary['violations']}  ·  警告 {summary['warnings']}  ·  {summary['text_length']} 字"
        ctk.CTkLabel(info_frame, text=count_text, font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(anchor="w")

        # 违规详情
        if result["violations"]:
            list_header = ctk.CTkFrame(self.result_frame, fg_color="transparent")
            list_header.pack(fill="x", pady=(SPACING["md"], SPACING["xs"]))
            ctk.CTkLabel(list_header, text=f"违规详情 ({len(result['violations'])})",
                         font=font_typo("caption_bold"), text_color=colors["text"]).pack(side="left")

            scroll = ctk.CTkScrollableFrame(self.result_frame, fg_color="transparent",
                                            corner_radius=0, height=180)
            scroll.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))

            for v in result["violations"]:
                self._create_violation_row(scroll, v)

            # 操作按钮
            btn_frame = ctk.CTkFrame(self.result_frame, fg_color="transparent")
            btn_frame.pack(fill="x", pady=(SPACING["xs"], 0))
            ctk.CTkButton(btn_frame, text="复制修改后文案", width=140,
                          command=self._copy_modified, **secondary_button_style()).pack(side="left", padx=(0, SPACING["sm"]))
            ctk.CTkButton(btn_frame, text="重新检测", width=90,
                          command=self._run_detection, **secondary_button_style()).pack(side="left")
        else:
            ctk.CTkLabel(self.result_frame, text="✅ 未发现合规风险", font=font_typo("body_bold"),
                         text_color=colors["success"]).pack(pady=SPACING["lg"])

        # LLM结果区域（如果有）
        if result.get("llm_analysis"):
            self._display_llm_result(result["llm_analysis"])

    def _display_cross_platform_result(self, results):
        """显示跨平台对比结果"""
        colors = get_colors()
        self.empty_frame.pack_forget()
        for widget in self.result_frame.winfo_children():
            widget.destroy()
        self.result_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["md"]))

        # 标题
        ctk.CTkLabel(self.result_frame, text="跨平台对比检测", font=font_typo("h2"),
                     text_color=colors["text"]).pack(anchor="w", pady=(0, SPACING["md"]))

        # 三个平台分数圆环并排（带平台名称）
        ring_row = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        ring_row.pack(fill="x", pady=(0, SPACING["md"]))
        ring_row.grid_columnconfigure((0, 1, 2), weight=1)

        plat_labels = {"xiaohongshu": "小红书", "douyin": "抖音", "weixin": "视频号"}
        for col, plat_key in enumerate(["xiaohongshu", "douyin", "weixin"]):
            result = results.get(plat_key, {})
            score = result.get("summary", {}).get("score", 100)
            plat_label = plat_labels.get(plat_key, plat_key)

            ring_container = ctk.CTkFrame(ring_row, fg_color="transparent")
            ring_container.grid(row=0, column=col, padx=SPACING["xs"])

            ring = ProgressRing(ring_container, score, size=80)
            ring.pack(pady=(0, SPACING["xs"]))

            # 平台名称 + 违规数
            v_count = result.get("summary", {}).get("violations", 0)
            w_count = result.get("summary", {}).get("warnings", 0)
            ctk.CTkLabel(ring_container, text=plat_label, font=font_typo("caption_bold"),
                         text_color=colors["text"]).pack()
            ctk.CTkLabel(ring_container, text=f"违规{v_count} · 警告{w_count}",
                         font=font_typo("micro"), text_color=colors["text_tertiary"]).pack()

        # 差异分析
        diff_frame = ctk.CTkFrame(self.result_frame, **card_frame_style())
        diff_frame.pack(fill="both", expand=True, pady=(0, SPACING["sm"]))

        ctk.CTkLabel(diff_frame, text="平台差异分析", font=font_typo("caption_bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["xs"]))

        # 找出只在某平台违规的关键词
        for plat_key in ["xiaohongshu", "douyin", "weixin"]:
            result = results.get(plat_key, {})
            plat_label = plat_labels.get(plat_key, plat_key)
            violations = result.get("violations", [])

            # 只在此平台违规的关键词
            other_plats = [k for k in ["xiaohongshu", "douyin", "weixin"] if k != plat_key]
            plat_only = []
            for v in violations:
                keyword = v.get("keyword", "")
                found_in_other = False
                for op in other_plats:
                    for ov in results.get(op, {}).get("violations", []):
                        if ov.get("keyword", "") == keyword:
                            found_in_other = True
                            break
                if not found_in_other and keyword:
                    plat_only.append(keyword)

            if plat_only:
                row = ctk.CTkFrame(diff_frame, fg_color=colors["bg"], corner_radius=CORNER_RADIUS["md"])
                row.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["xs"]))
                ctk.CTkLabel(row, text=f"⚠️ {plat_label}独有违规：{', '.join(plat_only[:5])}",
                             font=font_typo("caption"), text_color=colors["danger"],
                             wraplength=350, justify="left").pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

        # 智能建议
        worst_plat = min(results.keys(), key=lambda k: results[k].get("summary", {}).get("score", 100))
        worst_score = results[worst_plat].get("summary", {}).get("score", 100)
        worst_label = plat_labels.get(worst_plat, worst_plat)

        if worst_score < 80:
            suggestion_text = f"此文案在{worst_label}合规分数最低（{worst_score}分），建议针对性修改后再发布。"
            ctk.CTkLabel(diff_frame, text=f"💡 {suggestion_text}",
                         font=font_typo("caption"), text_color=colors["text_secondary"],
                         wraplength=380, justify="left").pack(fill="x", padx=SPACING["lg"], pady=(SPACING["xs"], SPACING["lg"]))

    def _display_llm_result(self, llm_result):
        """显示LLM分析结果 — GlassCard 样式"""
        colors = get_colors()
        if not llm_result or llm_result.get("status") == "error":
            return

        # 确保结果区域存在
        try:
            self.result_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["md"]))
        except Exception:
            pass

        llm_section = GlassCard(self.result_frame)
        llm_section.pack(fill="x", pady=(SPACING["md"], 0))

        # 标题行
        header = ctk.CTkFrame(llm_section, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        ctk.CTkLabel(header, text="🤖 AI语义分析", font=font_typo("caption_bold"),
                     text_color=colors["glass_text"]).pack(side="left")
        model_name = llm_result.get("model", "qwen2.5:7b")
        ctk.CTkLabel(header, text=model_name, font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(side="right")

        # 整体评估
        assessment = llm_result.get("overall_assessment") or llm_result.get("assessment", "")
        if assessment:
            ctk.CTkLabel(llm_section, text=f"📋 {assessment}", font=font_typo("caption"),
                         text_color=colors["text"], wraplength=380, justify="left",
                         anchor="w").pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        # AI合规分数
        ai_score = llm_result.get("compliance_score") or llm_result.get("score")
        if ai_score is not None:
            ctk.CTkLabel(llm_section, text=f"AI评分：{ai_score}/100",
                         font=font_typo("caption_bold"), text_color=colors["glass_text"]).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        # 风险列表
        risks = llm_result.get("risks", [])
        if risks:
            for risk in risks:
                r_severity = risk.get("severity", "warning")
                bg = colors["danger_light"] if r_severity == "violation" else colors["warning_light"]
                fg = colors["danger"] if r_severity == "violation" else colors["warning"]
                icon = "🔴" if r_severity == "violation" else "🟡"

                risk_card = ctk.CTkFrame(llm_section, fg_color=bg, corner_radius=CORNER_RADIUS["sm"])
                risk_card.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["xs"]))

                inner = ctk.CTkFrame(risk_card, fg_color="transparent")
                inner.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

                r_type = risk.get("type", "")
                r_desc = risk.get("description", "")
                r_sugg = risk.get("suggestion", "")

                ctk.CTkLabel(inner, text=f"{icon} {r_type}", font=font_typo("caption_bold"),
                             text_color=fg).pack(anchor="w")
                ctk.CTkLabel(inner, text=r_desc, font=font_typo("micro"),
                             text_color=colors["text"], wraplength=350, justify="left",
                             anchor="w").pack(fill="x", pady=(2, 0))
                ctk.CTkLabel(inner, text=f"💡 {r_sugg}", font=font_typo("micro"),
                             text_color=colors["text_secondary"], wraplength=350, justify="left",
                             anchor="w").pack(fill="x", pady=(1, 0))
        else:
            ctk.CTkLabel(llm_section, text="✅ AI未发现额外风险", font=font_typo("caption"),
                         text_color=colors["success"]).pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["md"]))

        # 底部间距
        ctk.CTkLabel(llm_section, text="", height=4).pack()

    def _create_violation_row(self, parent, v):
        """创建违规详情行 — 左侧色条 + hover"""
        colors = get_colors()
        severity = v["severity"]
        if severity == "violation":
            bg = colors["danger_light"]
            fg = colors["danger"]
            bar_color = colors["danger"]
            icon = "🔴"
        else:
            bg = colors["warning_light"]
            fg = colors["warning"]
            bar_color = colors["warning"]
            icon = "🟡"

        # 外框（带左侧色条）
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=CORNER_RADIUS["sm"])
        row.pack(fill="x", pady=(0, SPACING["xs"]))

        # 左侧色条（2px宽）
        color_bar = ctk.CTkFrame(row, fg_color=bar_color, width=3, corner_radius=0)
        color_bar.pack(side="left", fill="y", padx=0, pady=0)

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=SPACING["md"], pady=SPACING["xs"])

        # 第一行
        top_line = ctk.CTkFrame(inner, fg_color="transparent")
        top_line.pack(fill="x")

        match_tag = " [正则]" if v.get("match_type") == "regex" else ""
        ctk.CTkLabel(top_line, text=f"#{v['id']}", font=font_typo("micro_bold"),
                     text_color=fg, width=24).pack(side="left")
        ctk.CTkLabel(top_line, text=f'「{v["keyword"]}」', font=font_typo("caption_bold"),
                     text_color=fg).pack(side="left", padx=(0, SPACING["sm"]))
        ctk.CTkLabel(top_line, text=f"{icon} {v['category']}{match_tag}", font=font_typo("micro"),
                     text_color=colors["text_secondary"]).pack(side="left", padx=(0, SPACING["sm"]))
        ctk.CTkLabel(top_line, text=v["source"], font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(side="left")

        if v.get("blue_v_label"):
            label_color = colors["primary"] if "蓝V" in v["blue_v_label"] else colors["text_secondary"]
            ctk.CTkLabel(top_line, text=f"[{v['blue_v_label']}]", font=font_typo("micro_bold"),
                         text_color=label_color).pack(side="right")

        # 建议
        ctk.CTkLabel(inner, text=f"💡 {v['suggestion']}", font=font_typo("micro"),
                     text_color=colors["text"], wraplength=340, justify="left",
                     anchor="w").pack(fill="x", pady=(2, 0))

    # ============================================================
    # 高亮预览 + 悬停浮窗
    # ============================================================

    def _toggle_mode(self):
        """切换编辑/高亮预览模式"""
        colors = get_colors()
        if not self.current_result:
            return

        if not self.preview_mode:
            text = self.textbox.get("1.0", "end-1c")
            self._line_starts = self._precompute_line_starts(text)
            self._apply_highlights(text)
            self.textbox.configure(state="disabled")
            self.mode_label.configure(text="高亮预览")
            self.toggle_btn.configure(text="编辑模式")
            self.preview_mode = True

            # 激活悬停浮窗
            self._setup_tooltip()
        else:
            self.textbox.configure(state="normal")
            for tag in ["violation", "warning", "blue_v_violation", "blue_v_warning"]:
                self.textbox.tag_remove(tag, "1.0", "end")
            self.mode_label.configure(text="文案输入")
            self.toggle_btn.configure(text="高亮预览")
            self.preview_mode = False
            self._tooltip_manager = None

    def _setup_tooltip(self):
        """设置悬停浮窗"""
        self._tooltip_manager = HoverTooltip(self.textbox)

        # 为每种高亮标签绑定违规数据
        for tag_name in ["violation", "warning", "blue_v_violation", "blue_v_warning"]:
            matching_violations = []
            for v in self.current_result["violations"]:
                v_tag = self._severity_to_tag(v)
                if v_tag == tag_name:
                    start_idx = self._offset_to_index_fast(v["start"])
                    end_idx = self._offset_to_index_fast(v["end"])
                    v_copy = v.copy()
                    v_copy["_display_start"] = start_idx
                    v_copy["_display_end"] = end_idx
                    matching_violations.append(v_copy)
            if matching_violations:
                self._tooltip_manager.bind_tag(tag_name, matching_violations)

    def _severity_to_tag(self, v):
        """将违规数据映射到标签名"""
        if v.get("blue_v_label"):
            return "blue_v_violation" if v["severity"] == "violation" else "blue_v_warning"
        return v["severity"]

    def _apply_highlights(self, text):
        """在文本上应用高亮标签"""
        for v in self.current_result["violations"]:
            start_idx = self._offset_to_index_fast(v["start"])
            end_idx = self._offset_to_index_fast(v["end"])
            tag = self._severity_to_tag(v)
            self.textbox.tag_add(tag, start_idx, end_idx)

    @staticmethod
    def _precompute_line_starts(text):
        starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    def _offset_to_index_fast(self, offset):
        if not self._line_starts:
            return f"1.{offset}"
        line_idx = bisect.bisect_right(self._line_starts, offset) - 1
        line = line_idx + 1
        col = offset - self._line_starts[line_idx]
        return f"{line}.{col}"

    # ============================================================
    # 工具方法
    # ============================================================

    def _copy_modified(self):
        """复制修改后文案"""
        if self.current_result and self.current_result["modified_text"]:
            root = self.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(self.current_result["modified_text"])
            toast = ToastNotification(self, "已复制修改后文案")
            toast.show(self)

    def refresh(self):
        """刷新页面"""
        self.detector.reload_rules()

    def apply_theme(self):
        """暗色模式切换时刷新"""
        colors = get_colors()
        self.configure(fg_color=colors["bg"])
        self._init_text_tags()
