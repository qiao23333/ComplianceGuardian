#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量文件检测页面 — 选择文件夹/多文件，批量跑检测并汇总导出。

内核在 guardian.batch_detect.BatchRunner（纯 Python、可测试）。
支持 .txt/.md/.csv/.json/.html/.py 等文本，以及 python-docx 可用时的 .docx。
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from apps.desktop.ui.theme import (
    get_colors, font_typo, SPACING, CORNER_RADIUS,
    secondary_button_style, primary_button_style, card_frame_style,
)
from guardian.batch_detect import BatchRunner
from guardian.schema import DetectionOptions


class BatchPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self.targets = []
        self.results = []
        self._running = False
        self._build_ui()

    def _build_ui(self):
        colors = get_colors()
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["xxl"], pady=(SPACING["xl"], 0))
        ctk.CTkLabel(header, text="批量检测", font=font_typo("h1"),
                     text_color=colors["text"]).pack(side="left")
        ctk.CTkLabel(header, text="文件夹 / 多文件 · 汇总风险分布",
                     font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(
            side="left", padx=(SPACING["md"], 0), pady=(8, 0))

        card = ctk.CTkFrame(self, **card_frame_style())
        card.pack(fill="x", padx=SPACING["xxl"], pady=(SPACING["lg"], SPACING["md"]))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=SPACING["lg"], pady=SPACING["md"])

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="选择文件夹", width=110,
                      command=self._pick_dir, **secondary_button_style()).pack(
            side="left", padx=(0, SPACING["xs"]))
        ctk.CTkButton(btn_row, text="选择文件", width=100,
                      command=self._pick_files, **secondary_button_style()).pack(
            side="left", padx=(0, SPACING["xs"]))
        ctk.CTkButton(btn_row, text="开始扫描", width=110,
                      command=self._run, **primary_button_style()).pack(
            side="left", padx=(0, SPACING["sm"]))
        ctk.CTkButton(btn_row, text="导出 CSV", width=100,
                      command=self._export_csv, **secondary_button_style()).pack(
            side="right", padx=(SPACING["xs"], 0))
        ctk.CTkButton(btn_row, text="导出 Excel", width=100,
                      command=self._export_xlsx, **secondary_button_style()).pack(
            side="right")

        self.target_label = ctk.CTkLabel(inner, text="未选择目标",
                                         font=font_typo("micro"),
                                         text_color=colors["text_tertiary"])
        self.target_label.pack(anchor="w", pady=(SPACING["sm"], 0))

        # 汇总
        self.summary_label = ctk.CTkLabel(inner, text="", font=font_typo("caption_bold"),
                                          text_color=colors["text"])
        self.summary_label.pack(anchor="w", pady=(SPACING["xs"], 0))

        # 结果列表
        list_card = ctk.CTkFrame(self, **card_frame_style())
        list_card.pack(fill="both", expand=True,
                       padx=SPACING["xxl"], pady=(0, SPACING["xl"]))
        ctk.CTkLabel(list_card, text="扫描结果", font=font_typo("h3"),
                     text_color=colors["text"]).pack(
            anchor="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["xs"]))
        self.list_frame = ctk.CTkScrollableFrame(list_card, fg_color="transparent",
                                                 corner_radius=0)
        self.list_frame.pack(fill="both", expand=True,
                             padx=SPACING["md"], pady=(0, SPACING["md"]))

    # -------------------------------------------------- 选择目标

    def _pick_dir(self):
        d = tk.filedialog.askdirectory(title="选择要检测的文件夹")
        if d:
            self.targets = [Path(d)]
            self.target_label.configure(text=f"目标目录：{d}")

    def _pick_files(self):
        files = tk.filedialog.askopenfilenames(
            title="选择要检测的文件",
            filetypes=[("文本/文档", "*.txt *.md *.csv *.json *.html *.py *.docx"),
                       ("全部文件", "*.*")])
        if files:
            self.targets = [Path(f) for f in files]
            self.target_label.configure(
                text=f"已选 {len(files)} 个文件")

    # -------------------------------------------------- 扫描

    def _run(self):
        if self._running:
            return
        if not self.targets:
            messagebox.showwarning("未选择", "请先选择文件夹或文件")
            return
        colors = get_colors()
        self._running = True
        self.summary_label.configure(text="扫描中...", text_color=colors["primary"])

        def worker():
            try:
                runner = BatchRunner(options=DetectionOptions(use_variants=True))
                results = runner.scan(self.targets, recursive=True)
                summary = runner.summarize(results)
                self.after(0, lambda: self._on_done(results, summary))
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, results, summary):
        colors = get_colors()
        self._running = False
        self.results = results
        self.summary_label.configure(
            text=(f"共 {summary.total_files} 个文件 ｜ 已扫描 {summary.scanned} ｜ "
                  f"跳过 {summary.skipped} ｜ 有风险 {summary.risky_files} ｜ "
                  f"高危 {summary.severity_dist.get('critical', 0)} "
                  f"中危 {summary.severity_dist.get('high', 0)}"),
            text_color=colors["text"])
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not results:
            ctk.CTkLabel(self.list_frame, text="未发现可检测的文件",
                         font=font_typo("caption"),
                         text_color=colors["text_tertiary"]).pack(pady=SPACING["lg"])
            return
        for r in results:
            self._row(r)

    def _on_error(self, msg):
        self._running = False
        self.summary_label.configure(text="扫描失败", text_color=get_colors()["danger"])
        messagebox.showerror("扫描失败", msg)

    def _row(self, r):
        colors = get_colors()
        rc = _risk_color(r.risk_level)
        row = ctk.CTkFrame(self.list_frame, fg_color=colors["card"],
                           corner_radius=CORNER_RADIUS["sm"])
        row.pack(fill="x", pady=(0, SPACING["xs"]))
        ctk.CTkFrame(row, width=6, height=0, fg_color=rc).pack(side="left", fill="y")
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=SPACING["md"],
                  pady=SPACING["xs"])
        name = Path(r.path).name
        ctk.CTkLabel(info, text=name, font=font_typo("caption_bold"),
                     text_color=colors["text"]).pack(anchor="w")
        if r.skipped:
            sub = f"跳过：{r.error}"
        else:
            c = r.counts or {}
            sub = (f"{r.risk_level} · {r.score}分 · 命中{r.findings_count} "
                   f"(危{c.get('critical',0)}/中{c.get('high',0)}/低{c.get('medium',0)})"
                   + (f" · {' / '.join(r.top_findings)}" if r.top_findings else ""))
        ctk.CTkLabel(info, text=sub, font=font_typo("micro"),
                     text_color=colors["text_secondary"],
                     wraplength=640, justify="left").pack(anchor="w")

    # -------------------------------------------------- 导出

    def _export_csv(self):
        if not self.results:
            messagebox.showwarning("无结果", "请先扫描")
            return
        p = tk.filedialog.asksaveasfilename(
            title="保存 CSV", defaultextension=".csv",
            initialfile="批量检测报告.csv")
        if not p:
            return
        try:
            runner = BatchRunner()
            runner.export_csv(self.results, p)
            messagebox.showinfo("已导出", f"CSV 已保存：\n{p}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _export_xlsx(self):
        if not self.results:
            messagebox.showwarning("无结果", "请先扫描")
            return
        p = tk.filedialog.asksaveasfilename(
            title="保存 Excel", defaultextension=".xlsx",
            initialfile="批量检测报告.xlsx")
        if not p:
            return
        try:
            runner = BatchRunner()
            out = runner.export_xlsx(self.results, p)
            if out is None:
                messagebox.showwarning("缺少依赖",
                                       "未安装 openpyxl，无法生成 Excel。\n"
                                       "可改用「导出 CSV」。")
            else:
                messagebox.showinfo("已导出", f"Excel 已保存：\n{out}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def refresh(self):
        pass


def _risk_color(level):
    return {
        "高风险": "#d92d20", "中风险": "#f79009", "低风险": "#fdb022",
        "基本合规": "#12b76a",
    }.get(level, "#475467")
