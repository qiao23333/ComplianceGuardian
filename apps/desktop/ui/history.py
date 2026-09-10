#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录页面 — 查看 / 回看 / 导出 / 清空本地检测历史。

数据来自 guardian.storage.HistoryStore（SQLite，落 GUARDIAN_DATA_DIR 或
系统应用数据目录，不写 C 盘项目目录）。本页只读 + 操作，不改动内核。
"""

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from apps.desktop.ui.theme import (
    get_colors, font_typo, SPACING, CORNER_RADIUS,
    secondary_button_style, card_frame_style,
)
from guardian.storage import HistoryStore
from guardian.export_report import export_all


class HistoryPage(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        colors = get_colors()
        kwargs.pop("fg_color", None)
        super().__init__(master, fg_color=colors["bg"], **kwargs)
        self.app = app
        self._build_ui()
        self.current_record = None

    def _build_ui(self):
        colors = get_colors()
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["xxl"], pady=(SPACING["xl"], 0))
        ctk.CTkLabel(header, text="检测历史", font=font_typo("h1"),
                     text_color=colors["text"]).pack(side="left")
        ctk.CTkLabel(header, text="本地存储 · 数据不出本机",
                     font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(
            side="left", padx=(SPACING["md"], 0), pady=(8, 0))

        tools = ctk.CTkFrame(header, fg_color="transparent")
        tools.pack(side="right")
        ctk.CTkButton(tools, text="刷新", width=80,
                      command=self.refresh, **secondary_button_style()).pack(
            side="left", padx=(0, SPACING["xs"]))
        ctk.CTkButton(tools, text="清空历史", width=90,
                      command=self._clear_all, **secondary_button_style()).pack(
            side="left")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True,
                  padx=SPACING["xxl"], pady=(SPACING["lg"], SPACING["xl"]))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        # 左：列表
        left = ctk.CTkFrame(body, **card_frame_style())
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["md"]))
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="记录", font=font_typo("h3"),
                     text_color=colors["text"]).pack(
            anchor="w", padx=SPACING["lg"], pady=SPACING["md"])
        self.list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent",
                                                 corner_radius=0)
        self.list_frame.pack(fill="both", expand=True,
                             padx=SPACING["md"], pady=(0, SPACING["md"]))

        # 右：详情
        right = ctk.CTkFrame(body, **card_frame_style())
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)
        ctk.CTkLabel(right, text="详情", font=font_typo("h3"),
                     text_color=colors["text"]).pack(
            anchor="w", padx=SPACING["lg"], pady=SPACING["md"])
        self.detail_frame = ctk.CTkScrollableFrame(right, fg_color="transparent",
                                                   corner_radius=0)
        self.detail_frame.pack(fill="both", expand=True,
                               padx=SPACING["md"], pady=(0, SPACING["md"]))

        self._empty_detail()

    def _empty_detail(self):
        colors = get_colors()
        for w in self.detail_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.detail_frame, text="选择左侧记录查看详情",
                     font=font_typo("caption"),
                     text_color=colors["text_tertiary"]).pack(pady=SPACING["lg"])

    def refresh(self):
        colors = get_colors()
        for w in self.list_frame.winfo_children():
            w.destroy()
        try:
            store = HistoryStore()
            rows = store.list(limit=100)
            store.close()
        except Exception as e:
            messagebox.showerror("历史读取失败", str(e))
            return
        if not rows:
            ctk.CTkLabel(self.list_frame, text="暂无检测历史",
                         font=font_typo("caption"),
                         text_color=colors["text_tertiary"]).pack(pady=SPACING["lg"])
            return
        for r in rows:
            self._row(r)

    def _row(self, rec):
        colors = get_colors()
        rc = _risk_color(rec.get("risk_level", "基本合规"))
        row = ctk.CTkFrame(self.list_frame, fg_color=colors["card"],
                           corner_radius=CORNER_RADIUS["md"])
        row.pack(fill="x", pady=(0, SPACING["xs"]))
        row.bind("<Button-1>", lambda e, r=rec: self._show_detail(r))
        dot = ctk.CTkFrame(row, width=8, height=8, fg_color=rc,
                          corner_radius=4)
        dot.pack(side="left", padx=SPACING["md"])
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(0, SPACING["md"]),
                  pady=SPACING["xs"])
        ctk.CTkLabel(info, text=f"{rec.get('risk_level')} · {rec.get('score')}分",
                     font=font_typo("caption_bold"),
                     text_color=colors["text"]).pack(anchor="w")
        snippet = (rec.get("text") or "")[:40].replace("\n", " ")
        ctk.CTkLabel(info, text=snippet, font=font_typo("micro"),
                     text_color=colors["text_secondary"]).pack(anchor="w")
        ctk.CTkLabel(info, text=rec.get("created_at", "")[:19].replace("T", " "),
                     font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack(anchor="w")

    def _show_detail(self, rec):
        colors = get_colors()
        self.current_record = rec
        for w in self.detail_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.detail_frame,
                     text=f"风险：{rec.get('risk_level')}  合规分：{rec.get('score')}",
                     font=font_typo("caption_bold"),
                     text_color=colors["text"]).pack(anchor="w",
                                                      padx=SPACING["md"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(self.detail_frame, text="原文", font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(
            anchor="w", padx=SPACING["md"], pady=(SPACING["sm"], 0))
        ctk.CTkLabel(self.detail_frame, text=rec.get("text", ""),
                     font=font_typo("micro"), text_color=colors["text"],
                     wraplength=420, justify="left").pack(
            anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(self.detail_frame, text="改写建议",
                     font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(
            anchor="w", padx=SPACING["md"], pady=(SPACING["sm"], 0))
        ctk.CTkLabel(self.detail_frame,
                     text=rec.get("safe_text") or "（未开启自动改写）",
                     font=font_typo("micro"), text_color=colors["text"],
                     wraplength=420, justify="left").pack(
            anchor="w", padx=SPACING["md"], pady=(0, SPACING["xs"]))

        findings = rec.get("findings") or []
        ctk.CTkLabel(self.detail_frame, text=f"命中（{len(findings)}）",
                     font=font_typo("caption_bold"),
                     text_color=colors["text_secondary"]).pack(
            anchor="w", padx=SPACING["md"], pady=(SPACING["sm"], 0))
        for f in findings[:30]:
            sev = f.get("severity", "low")
            ctk.CTkLabel(self.detail_frame,
                         text=f"• {f.get('matched_text') or f.get('keyword')} "
                              f"[{_sev_label(sev)}] {f.get('category', '')}",
                         font=font_typo("micro"), text_color=_sev_color(sev),
                         wraplength=420, justify="left").pack(
                anchor="w", padx=SPACING["md"], pady=1)

        # 操作按钮
        btns = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        btns.pack(anchor="w", padx=SPACING["md"], pady=SPACING["md"])
        ctk.CTkButton(btns, text="导出此记录", width=110,
                      command=self._export_current,
                      **secondary_button_style()).pack(side="left",
                                                        padx=(0, SPACING["xs"]))
        ctk.CTkButton(btns, text="删除", width=80,
                      command=lambda: self._delete(rec.get("id")),
                      **secondary_button_style()).pack(side="left")

    def _export_current(self):
        if not self.current_record:
            return
        out_dir = tk.filedialog.askdirectory(title="选择报告保存目录")
        if not out_dir:
            return
        try:
            # 历史记录 dict 字段与导出 payload 完全一致，可直接复用
            paths = export_all(self.current_record,
                               Path(out_dir) / "合规检测报告")
            messagebox.showinfo("已导出",
                                f"HTML / PNG / PDF 已保存到：\n{paths['html']}")
            try:
                os.startfile(out_dir)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _delete(self, rid):
        if rid is None:
            return
        try:
            store = HistoryStore()
            store.delete(rid)
            store.close()
            self.refresh()
            self._empty_detail()
        except Exception as e:
            messagebox.showerror("删除失败", str(e))

    def _clear_all(self):
        if not messagebox.askyesno("确认清空", "将删除全部检测历史，不可恢复。"):
            return
        try:
            store = HistoryStore()
            n = store.clear()
            store.close()
            self.refresh()
            self._empty_detail()
            messagebox.showinfo("已清空", f"已删除 {n} 条历史记录")
        except Exception as e:
            messagebox.showerror("清空失败", str(e))


def _risk_color(level):
    return {
        "高风险": "#d92d20", "中风险": "#f79009", "低风险": "#fdb022",
        "基本合规": "#12b76a", "安全": "#12b76a",
    }.get(level, "#475467")


def _sev_color(sev):
    return {
        "critical": "#d92d20", "high": "#f79009",
        "medium": "#fdb022", "low": "#475467",
    }.get(sev, "#475467")


def _sev_label(sev):
    return {"critical": "高危", "high": "中危",
            "medium": "低危", "low": "提示"}.get(sev, sev)

