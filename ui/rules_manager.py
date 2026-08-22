#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库管理页面 — v2.2 现代仪表盘风

升级内容：
1. SegmentedControl 标签页样式
2. Treeview 自定义样式
3. 精致添加/编辑对话框
4. 词库版本管理（备份+恢复）
5. 暗色模式支持
"""
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ui.theme import (
    get_colors, font_safe, font_typo, SPACING, CORNER_RADIUS,
    primary_button_style, secondary_button_style, card_frame_style,
    danger_button_style, gradient_button_style,
)
from ui.widgets import SegmentedControl, ToastNotification
from core.detector import ComplianceDetector


class RulesManagerPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)  # app.py 也传了 fg_color，避免重复
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self.detector = ComplianceDetector.get_instance()
        self.current_tab = "广告法"
        self._rules_loaded = False
        self._build_ui()

    def _build_ui(self):
        colors = get_colors()

        # 标题区
        ctk.CTkLabel(self, text="词库管理", font=font_typo("h1"),
                     text_color=colors["text"]).pack(anchor="w", padx=SPACING["xxl"], pady=(SPACING["xl"], SPACING["xs"]))
        ctk.CTkLabel(self, text="查看、编辑、导入合规检测规则词库",
                     font=font_typo("body"),
                     text_color=colors["text_secondary"]).pack(anchor="w", padx=SPACING["xxl"], pady=(0, SPACING["lg"]))

        # 顶部操作栏
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=SPACING["xxl"], pady=(0, SPACING["md"]))

        # 标签页 — SegmentedControl
        tabs = [("广告法", "广告法"), ("平台规则", "平台规则"), ("蓝V限制", "蓝V限制"), ("行业红线", "行业红线")]
        self.tab_control = SegmentedControl(
            top_bar, segments=tabs,
            on_select=self._switch_tab,
            initial=0,
        )
        self.tab_control.pack(side="left")

        # 操作按钮
        ctk.CTkButton(top_bar, text="➕ 添加规则", command=self._show_add_dialog,
                      **gradient_button_style()).pack(side="right", padx=(SPACING["sm"], 0))
        ctk.CTkButton(top_bar, text="📥 导入文件", command=self._import_file,
                      **secondary_button_style()).pack(side="right", padx=(SPACING["xs"], 0))
        ctk.CTkButton(top_bar, text="🔄 重新加载", command=self._reload,
                      **secondary_button_style()).pack(side="right", padx=(SPACING["xs"], 0))

        # 版本管理按钮
        ctk.CTkButton(top_bar, text="💾 备份", width=70, height=36,
                      command=self._backup_rules,
                      fg_color=colors["success_light"], hover_color=colors["hover"],
                      text_color=colors["success"],
                      border_width=1, border_color=colors["success"],
                      font=font_typo("caption_bold"),
                      corner_radius=CORNER_RADIUS["md"]).pack(side="right", padx=(SPACING["xs"], 0))
        ctk.CTkButton(top_bar, text="📂 恢复", width=70, height=36,
                      command=self._restore_rules,
                      fg_color=colors["info_light"], hover_color=colors["hover"],
                      text_color=colors["info"],
                      border_width=1, border_color=colors["info"],
                      font=font_typo("caption_bold"),
                      corner_radius=CORNER_RADIUS["md"]).pack(side="right", padx=(SPACING["xs"], 0))

        # 规则列表 — Treeview（自定义样式）
        list_card = ctk.CTkFrame(self, **card_frame_style())
        list_card.pack(fill="both", expand=True, padx=SPACING["xxl"], pady=(0, SPACING["xxl"]))

        # 设置 ttk 样式
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=colors["card"],
                        foreground=colors["text"],
                        fieldbackground=colors["card"],
                        font=font_safe(12, "normal"),
                        rowheight=32,
                        borderwidth=0,
                        )
        style.configure("Treeview.Heading",
                        background=colors["hover"],
                        foreground=colors["text_secondary"],
                        font=font_typo("caption_bold"),
                        borderwidth=0,
                        )
        style.map("Treeview",
                  background=[("selected", colors["selected"])],
                  foreground=[("selected", colors["primary"])],
                  )
        style.map("Treeview.Heading",
                  background=[("active", colors["pressed"])],
                  )

        # 创建 Treeview
        columns = ("keyword", "severity", "category", "source")
        self.tree = ttk.Treeview(list_card, columns=columns, show="headings", height=20,
                                 style="Treeview")

        self.tree.heading("keyword", text="关键词")
        self.tree.heading("severity", text="严重程度")
        self.tree.heading("category", text="分类")
        self.tree.heading("source", text="来源")

        self.tree.column("keyword", width=200, anchor="w")
        self.tree.column("severity", width=100, anchor="center")
        self.tree.column("category", width=150, anchor="w")
        self.tree.column("source", width=120, anchor="w")

        # 滚动条
        vsb = ttk.Scrollbar(list_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(SPACING["lg"], 0), pady=SPACING["lg"])
        vsb.pack(side="right", fill="y", pady=SPACING["lg"], padx=(0, SPACING["lg"]))

        # 底部操作按钮
        self.action_frame = ctk.CTkFrame(list_card, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        ctk.CTkButton(self.action_frame, text="删除选中", width=100,
                      **danger_button_style(),
                      command=self._delete_selected).pack(side="left", padx=(0, SPACING["xs"]))
        ctk.CTkButton(self.action_frame, text="编辑选中", width=100,
                      **secondary_button_style(),
                      command=self._edit_selected).pack(side="left")

    # ============================================================
    # 标签页切换
    # ============================================================

    def _switch_tab(self, tab):
        self.current_tab = tab
        self._rules_loaded = False
        self._load_rules_list()

    def _get_current_rules(self):
        if self.current_tab == "广告法":
            return self.detector.ad_law
        elif self.current_tab == "平台规则":
            rules = []
            for plat, rlist in self.detector.platform_rules.items():
                for r in rlist:
                    r_copy = r.copy()
                    r_copy["_platform"] = self.detector.PLATFORM_NAMES.get(plat, plat)
                    rules.append(r_copy)
            return rules
        elif self.current_tab == "蓝V限制":
            return self.detector.blue_v_only
        elif self.current_tab == "行业红线":
            return self.detector.user_custom
        return []

    def _load_rules_list(self):
        """加载规则列表到 Treeview"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        rules = self._get_current_rules()
        if not rules:
            self.tree.insert("", "end", values=("暂无规则，点击「添加规则」或「导入文件」开始", "", "", ""))
            self._rules_loaded = True
            return

        for i, rule in enumerate(rules):
            keyword = rule.get("keyword", "")
            severity = rule.get("severity", "")
            category = rule.get("category", "")
            source = rule.get("source", self.current_tab)
            if self.current_tab == "平台规则" and "_platform" in rule:
                source = rule["_platform"]

            # 严重程度显示
            sev_display = {
                "violation": "🔴 违规",
                "warning": "🟡 警告",
                "blue_v_required": "🔵 蓝V专属",
            }.get(severity, severity)

            self.tree.insert("", "end", iid=str(i), values=(keyword, sev_display, category, source))

        self._rules_loaded = True

    # ============================================================
    # 规则操作
    # ============================================================

    def _delete_selected(self):
        """删除选中的规则"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的规则")
            return

        # 修改前自动备份
        try:
            self.detector.backup_rules()
        except Exception:
            pass

        for item_id in selection:
            idx = int(item_id)
            rules = self._get_current_rules()
            if 0 <= idx < len(rules):
                rule = rules[idx]
                keyword = rule.get("keyword", "")
                if messagebox.askyesno("确认删除", f"确定要删除「{keyword}」吗？"):
                    self._remove_rule(idx)

        self._load_rules_list()

    def _edit_selected(self):
        """编辑选中的规则"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要编辑的规则")
            return
        item_id = selection[0]
        idx = int(item_id)
        rules = self._get_current_rules()
        if 0 <= idx < len(rules):
            self._show_add_dialog(edit_idx=idx)

    def _show_add_dialog(self, edit_idx=None):
        """显示添加/编辑规则对话框"""
        colors = get_colors()
        dialog = ctk.CTkToplevel(self)
        dialog.title("编辑规则" if edit_idx is not None else "添加规则")
        dialog.geometry("460x480")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 230
        y = (dialog.winfo_screenheight() // 2) - 240
        dialog.geometry(f"+{x}+{y}")

        # 渐变标题栏
        title_bar = ctk.CTkFrame(dialog, fg_color=colors["primary"], height=50, corner_radius=0)
        title_bar.pack(fill="x")
        ctk.CTkLabel(title_bar, text="编辑规则" if edit_idx is not None else "添加规则",
                     font=font_typo("h2"), text_color=colors["text_on_primary"]).pack(anchor="w", padx=SPACING["lg"], pady=SPACING["md"])

        container = ctk.CTkFrame(dialog, fg_color=colors["bg"])
        container.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])

        # 加载现有数据
        existing_rule = None
        if edit_idx is not None:
            rules = self._get_current_rules()
            if 0 <= edit_idx < len(rules):
                existing_rule = rules[edit_idx]

        # 关键词
        ctk.CTkLabel(container, text="关键词", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        kw_entry = ctk.CTkEntry(container, width=400, height=36, corner_radius=CORNER_RADIUS["md"],
                                border_color=colors["border"],
                                fg_color=colors["card"])
        kw_entry.pack(fill="x", pady=(0, SPACING["md"]))
        if existing_rule:
            kw_entry.insert(0, existing_rule.get("keyword", ""))

        # 类别
        ctk.CTkLabel(container, text="类别", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        cat_entry = ctk.CTkEntry(container, width=400, height=36, corner_radius=CORNER_RADIUS["md"],
                                 border_color=colors["border"],
                                 fg_color=colors["card"],
                                 placeholder_text="如：极限词、导流违规、行业红线")
        cat_entry.pack(fill="x", pady=(0, SPACING["md"]))
        if existing_rule:
            cat_entry.insert(0, existing_rule.get("category", ""))

        # 严重程度
        ctk.CTkLabel(container, text="严重程度", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        sev_var = ctk.StringVar(value=existing_rule.get("severity", "violation") if existing_rule else "violation")
        sev_frame = ctk.CTkFrame(container, fg_color="transparent")
        sev_frame.pack(fill="x", pady=(0, SPACING["md"]))
        ctk.CTkRadioButton(sev_frame, text="🔴 违规", variable=sev_var, value="violation",
                           font=font_typo("caption")).pack(side="left", padx=(0, SPACING["md"]))
        ctk.CTkRadioButton(sev_frame, text="🟡 警告", variable=sev_var, value="warning",
                           font=font_typo("caption")).pack(side="left")

        # 建议
        ctk.CTkLabel(container, text="修改建议", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        sug_entry = ctk.CTkEntry(container, width=400, height=36, corner_radius=CORNER_RADIUS["md"],
                                 border_color=colors["border"],
                                 fg_color=colors["card"],
                                 placeholder_text="如：改为'优惠'或删除")
        sug_entry.pack(fill="x", pady=(0, SPACING["md"]))
        if existing_rule:
            sug_entry.insert(0, existing_rule.get("suggestion", ""))

        # 备注
        ctk.CTkLabel(container, text="备注说明", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        note_entry = ctk.CTkTextbox(container, width=400, height=60, corner_radius=CORNER_RADIUS["md"],
                                    border_color=colors["border"], border_width=1,
                                    fg_color=colors["card"])
        note_entry.pack(fill="x", pady=(0, SPACING["lg"]))
        if existing_rule and existing_rule.get("note"):
            note_entry.insert("1.0", existing_rule.get("note", ""))

        def save_rule():
            kw = kw_entry.get().strip()
            if not kw:
                messagebox.showwarning("提示", "请输入关键词", parent=dialog)
                return

            # 修改前自动备份
            try:
                self.detector.backup_rules()
            except Exception:
                pass

            if edit_idx is not None:
                self._remove_rule(edit_idx)

            # 根据 current_tab 分流保存到对应词库
            self.detector.add_rule_to_category(
                tab_name=self.current_tab,
                keyword=kw,
                category=cat_entry.get().strip(),
                severity=sev_var.get(),
                suggestion=sug_entry.get().strip(),
                note=note_entry.get("1.0", "end-1c").strip()
            )
            self.detector.reload_rules()
            dialog.destroy()
            self._load_rules_list()
            # 保存成功反馈
            toast = ToastNotification(self, f"已添加「{kw}」到{self.current_tab}")
            toast.show(self)

        # 按钮区：保存 + 取消
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="保存规则", command=save_rule,
                      **gradient_button_style()).pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))
        ctk.CTkButton(btn_frame, text="取消", width=80,
                      command=dialog.destroy,
                      **secondary_button_style()).pack(side="right")

    def _show_add_dialog_with_keyword(self, keyword):
        """右键菜单触发：打开添加对话框，预填关键词"""
        colors = get_colors()
        dialog = ctk.CTkToplevel(self)
        dialog.title("添加到词库")
        dialog.geometry("460x480")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 230
        y = (dialog.winfo_screenheight() // 2) - 240
        dialog.geometry(f"+{x}+{y}")

        # 渐变标题栏
        title_bar = ctk.CTkFrame(dialog, fg_color=colors["primary"], height=50, corner_radius=0)
        title_bar.pack(fill="x")
        ctk.CTkLabel(title_bar, text=f"添加「{keyword[:15]}」到词库",
                     font=font_typo("h2"), text_color=colors["text_on_primary"]).pack(anchor="w", padx=SPACING["lg"], pady=SPACING["md"])

        container = ctk.CTkFrame(dialog, fg_color=colors["bg"])
        container.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])

        # 关键词（已预填）
        ctk.CTkLabel(container, text="关键词", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        kw_entry = ctk.CTkEntry(container, width=400, height=36, corner_radius=CORNER_RADIUS["md"],
                                border_color=colors["border"], fg_color=colors["card"])
        kw_entry.pack(fill="x", pady=(0, SPACING["md"]))
        kw_entry.insert(0, keyword)

        # 保存到哪个词库
        ctk.CTkLabel(container, text="保存到", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        tab_var = ctk.StringVar(value="行业红线")
        tab_frame = ctk.CTkFrame(container, fg_color="transparent")
        tab_frame.pack(fill="x", pady=(0, SPACING["md"]))
        for tab in ["行业红线", "广告法", "蓝V限制"]:
            ctk.CTkRadioButton(tab_frame, text=tab, variable=tab_var, value=tab,
                               font=font_typo("caption")).pack(side="left", padx=(0, SPACING["md"]))

        # 类别
        ctk.CTkLabel(container, text="类别", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(anchor="w", pady=(0, SPACING["xs"]))
        cat_entry = ctk.CTkEntry(container, width=400, height=36, corner_radius=CORNER_RADIUS["md"],
                                 border_color=colors["border"], fg_color=colors["card"],
                                 placeholder_text="如：极限词、导流违规")
        cat_entry.pack(fill="x", pady=(0, SPACING["md"]))

        # 严重程度
        sev_var = ctk.StringVar(value="violation")
        sev_frame = ctk.CTkFrame(container, fg_color="transparent")
        sev_frame.pack(fill="x", pady=(0, SPACING["md"]))
        ctk.CTkRadioButton(sev_frame, text="🔴 违规", variable=sev_var, value="violation",
                           font=font_typo("caption")).pack(side="left", padx=(0, SPACING["md"]))
        ctk.CTkRadioButton(sev_frame, text="🟡 警告", variable=sev_var, value="warning",
                           font=font_typo("caption")).pack(side="left")

        def save():
            kw = kw_entry.get().strip()
            if not kw:
                messagebox.showwarning("提示", "请输入关键词", parent=dialog)
                return
            self.detector.add_rule_to_category(
                tab_name=tab_var.get(),
                keyword=kw,
                category=cat_entry.get().strip(),
                severity=sev_var.get(),
                suggestion="",
                note="",
            )
            self.detector.reload_rules()
            dialog.destroy()
            self._load_rules_list()
            toast = ToastNotification(self, f"已添加「{kw}」到{tab_var.get()}")
            toast.show(self)

        btn_frame2 = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame2.pack(fill="x")
        ctk.CTkButton(btn_frame2, text="保存规则", command=save,
                      **gradient_button_style()).pack(side="left", fill="x", expand=True, padx=(0, SPACING["xs"]))
        ctk.CTkButton(btn_frame2, text="取消", width=80,
                      command=dialog.destroy,
                      **secondary_button_style()).pack(side="right")

    def _remove_rule(self, index):
        """删除规则（根据当前标签页调用对应的删除方法）"""
        if self.current_tab == "行业红线":
            self.detector.remove_custom_rule(index)
        elif self.current_tab == "平台规则":
            messagebox.showwarning("提示", "平台规则暂不支持删除，请在词库文件中手动删除")
            return
        else:
            if self.current_tab == "广告法":
                rules = self.detector.ad_law
            elif self.current_tab == "蓝V限制":
                rules = self.detector.blue_v_only
            else:
                return
            if 0 <= index < len(rules):
                rules.pop(index)
                self.detector._save_rules(self.current_tab)

    def _import_file(self):
        filepath = filedialog.askopenfilename(
            title="选择词库文件",
            filetypes=[("文本文件", "*.txt"), ("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not filepath:
            return

        # 导入前自动备份
        try:
            self.detector.backup_rules()
        except Exception:
            pass

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            count = 0
            if filepath.endswith(".json"):
                rules = json.loads(content)
                for r in rules:
                    self.detector.add_rule_to_category(
                        tab_name=self.current_tab,
                        keyword=r.get("keyword", ""),
                        category=r.get("category", ""),
                        severity=r.get("severity", "violation"),
                        suggestion=r.get("suggestion", ""),
                        note=r.get("note", "")
                    )
                    count += 1
            else:
                for line in content.strip().split("\n"):
                    kw = line.strip()
                    if kw:
                        self.detector.add_rule_to_category(
                            tab_name=self.current_tab,
                            keyword=kw,
                            category="行业红线",
                            severity="violation",
                            suggestion="根据公司规定修改"
                        )
                        count += 1

            self.detector.reload_rules()
            messagebox.showinfo("成功", f"已导入 {count} 条规则到「{self.current_tab}」")
            self._load_rules_list()
        except Exception as e:
            messagebox.showerror("错误", f"导入失败：{e}")

    def _reload(self):
        self.detector.reload_rules()
        self._load_rules_list()
        messagebox.showinfo("成功", "词库已重新加载")

    # ============================================================
    # 版本管理
    # ============================================================

    def _backup_rules(self):
        """手动备份词库"""
        try:
            backup_path = self.detector.backup_rules()
            toast = ToastNotification(self, f"已备份到 {backup_path}")
            toast.show(self)
        except Exception as e:
            messagebox.showerror("备份失败", f"备份出错：{e}")

    def _restore_rules(self):
        """恢复历史版本"""
        backups = self.detector.list_backups()
        if not backups:
            messagebox.showinfo("提示", "暂无备份记录")
            return

        colors = get_colors()
        dialog = ctk.CTkToplevel(self)
        dialog.title("恢复历史版本")
        dialog.geometry("420x350")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 210
        y = (dialog.winfo_screenheight() // 2) - 175
        dialog.geometry(f"+{x}+{y}")

        # 渐变标题栏
        title_bar = ctk.CTkFrame(dialog, fg_color=colors["info"], height=50, corner_radius=0)
        title_bar.pack(fill="x")
        ctk.CTkLabel(title_bar, text="📂 恢复历史版本",
                     font=font_typo("h2"), text_color=colors["text_on_primary"]).pack(anchor="w", padx=SPACING["lg"], pady=SPACING["md"])

        container = ctk.CTkFrame(dialog, fg_color=colors["bg"])
        container.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])

        ctk.CTkLabel(container, text="选择要恢复的备份：", font=font_typo("caption_bold"),
                     text_color=colors["text"]).pack(anchor="w", pady=(0, SPACING["md"]))

        # 备份列表
        backup_var = ctk.StringVar()
        for b in backups:
            label = f"{b['timestamp']}  ({b['file_count']} 个文件)"
            ctk.CTkRadioButton(container, text=label, variable=backup_var, value=b["name"],
                               font=font_typo("caption")).pack(anchor="w", pady=(0, SPACING["xs"]))

        def restore():
            if not backup_var.get():
                messagebox.showwarning("提示", "请选择一个备份", parent=dialog)
                return
            try:
                self.detector.restore_backup(backup_var.get())
                dialog.destroy()
                self._load_rules_list()
                toast = ToastNotification(self, "已恢复历史版本")
                toast.show(self)
            except Exception as e:
                messagebox.showerror("恢复失败", f"恢复出错：{e}", parent=dialog)

        ctk.CTkButton(container, text="恢复选中版本", command=restore,
                      **gradient_button_style()).pack(fill="x", pady=(SPACING["md"], 0))

    def refresh(self):
        """刷新页面（只在首次显示时加载规则）"""
        if not self._rules_loaded:
            self._load_rules_list()

    def apply_theme(self):
        """暗色模式切换时重建UI"""
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
        self._rules_loaded = False
        self._load_rules_list()
