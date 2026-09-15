#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规检测工具 v2.2 — 复用 UI 组件库（现代仪表盘风）

新增组件：
- GradientCard: 渐变背景统计卡片
- GlassCard: 磨砂玻璃信息卡片
- ProgressRing: 合规分数圆环（Canvas绘制）
- BarChart: 迷你条形图（词库统计）
- StatusPill: 状态胶囊标签
- ToastNotification: 底部弹出通知
- HoverTooltip: 悬停浮窗

升级组件：
- StatCard: 加入渐变条+精致排版
- ScoreRing: 改为圆环进度指示
"""
import tkinter as tk
import customtkinter as ctk
from apps.desktop.ui.theme import (
    get_colors, font_safe, font_emoji, font_typo, SPACING, CORNER_RADIUS,
    card_frame_style, glass_card_style, elevated_card_style,
    gradient_button_style, status_pill_style,
)


class GradientCard(ctk.CTkFrame):
    """渐变背景统计卡片 — 仪表盘顶部使用

    CustomTkinter 不支持真渐变，用深色顶部条 + 白色/暗色底模拟渐变效果。
    """
    def __init__(self, master, title, value, subtitle="", icon="",
                 gradient_key="gradient_card_blue_top", **kwargs):
        super().__init__(master, **kwargs)
        colors = get_colors()
        self.configure(fg_color=colors["card"],
                       corner_radius=CORNER_RADIUS["xl"],
                       border_color=colors["border_light"],
                       border_width=1)

        # 顶部渐变色条（模拟渐变头部）
        gradient_bar = ctk.CTkFrame(self, height=6, fg_color=colors[gradient_key],
                                    corner_radius=0)
        gradient_bar.pack(fill="x", padx=0, pady=(0, 0))

        # 内容区
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(SPACING["md"], SPACING["lg"]))

        # 图标 + 标题行
        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x", pady=(0, SPACING["xs"]))
        if icon:
            ctk.CTkLabel(header, text=icon, font=font_emoji(20)).pack(side="left", padx=(0, SPACING["sm"]))
        ctk.CTkLabel(header, text=title, font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(side="left")

        # 数值
        self.value_label = ctk.CTkLabel(content, text=value, font=font_safe(36, "bold"),
                                        text_color=colors[gradient_key])
        self.value_label.pack(anchor="w", pady=(SPACING["xs"], 0))

        # 副标题
        self.subtitle_label = ctk.CTkLabel(content, text=subtitle, font=font_typo("micro"),
                                           text_color=colors["text_tertiary"])
        if subtitle:
            self.subtitle_label.pack(anchor="w")

    def update_value(self, value=None, subtitle=None):
        if value is not None:
            self.value_label.configure(text=value)
        if subtitle is not None:
            self.subtitle_label.configure(text=subtitle)


class GlassCard(ctk.CTkFrame):
    """磨砂玻璃卡片 — LLM分析区、特殊信息区"""
    def __init__(self, master, **kwargs):
        style = glass_card_style()
        for k, v in kwargs.items():
            style[k] = v
        super().__init__(master, **style)
        colors = get_colors()
        self.colors = colors


class ProgressRing(ctk.CTkFrame):
    """合规分数圆环 — 用 Canvas 绘制弧形进度"""
    def __init__(self, master, score, size=120, **kwargs):
        super().__init__(master, **kwargs)
        colors = get_colors()
        self.configure(fg_color=colors["card"],
                       corner_radius=CORNER_RADIUS["xl"],
                       border_color=colors["border_light"],
                       border_width=1,
                       width=size + 40, height=size + 70)

        # Canvas 绘制圆环
        ring_size = size
        canvas = tk.Canvas(self, width=ring_size, height=ring_size,
                           bg=colors["card"], highlightthickness=0)
        canvas.pack(pady=(SPACING["lg"], SPACING["sm"]))

        # 确定颜色
        if score >= 80:
            ring_color = colors["ring_success"]
        elif score >= 60:
            ring_color = colors["ring_warning"]
        else:
            ring_color = colors["ring_danger"]

        track_color = colors["ring_track"]
        center = ring_size // 2
        radius = ring_size // 2 - 10

        # 背景轨道
        canvas.create_arc(center - radius, center - radius,
                          center + radius, center + radius,
                          start=90, extent=-360,
                          style="arc", width=8, outline=track_color)

        # 进度弧
        extent = -(score / 100) * 360
        canvas.create_arc(center - radius, center - radius,
                          center + radius, center + radius,
                          start=90, extent=extent,
                          style="arc", width=8, outline=ring_color)

        # 中心数字
        canvas.create_text(center, center, text=str(score),
                           font=font_safe(28, "bold"), fill=ring_color)

        # 底部标签
        ctk.CTkLabel(self, text="合规分数", font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack()
        ctk.CTkLabel(self, text="/ 100", font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack()

    def update_score(self, score):
        """重新绘制圆环（销毁重建）"""
        colors = get_colors()
        for widget in self.winfo_children():
            widget.destroy()

        ring_size = 120
        canvas = tk.Canvas(self, width=ring_size, height=ring_size,
                           bg=colors["card"], highlightthickness=0)
        canvas.pack(pady=(SPACING["lg"], SPACING["sm"]))

        if score >= 80:
            ring_color = colors["ring_success"]
        elif score >= 60:
            ring_color = colors["ring_warning"]
        else:
            ring_color = colors["ring_danger"]

        track_color = colors["ring_track"]
        center = ring_size // 2
        radius = ring_size // 2 - 10

        canvas.create_arc(center - radius, center - radius,
                          center + radius, center + radius,
                          start=90, extent=-360,
                          style="arc", width=8, outline=track_color)

        extent = -(score / 100) * 360
        canvas.create_arc(center - radius, center - radius,
                          center + radius, center + radius,
                          start=90, extent=extent,
                          style="arc", width=8, outline=ring_color)

        canvas.create_text(center, center, text=str(score),
                           font=font_safe(28, "bold"), fill=ring_color)

        ctk.CTkLabel(self, text="合规分数", font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack()
        ctk.CTkLabel(self, text="/ 100", font=font_typo("micro"),
                     text_color=colors["text_tertiary"]).pack()


class BarChart(ctk.CTkFrame):
    """迷你条形图 — 词库概览统计

    data 每项为 ``(label, value, color_key[, detail])``。

    ``detail`` 用于承载"细分说明"（例如"小红书 123 · 抖音 63 · 视频号 60"）。
    加这个参数是为了消灭仪表盘上的**信息重复**：原先同一份词库数据被画了
    两遍 —— 上面一组彩色进度条，下面又一份带细分的列表。用户看到十行内容
    其实只有五个含义，还白白多出 40 多个控件（每个 CTkFrame 都是
    canvas + 子控件，重建一次就是几十毫秒）。现在明细并入条形图本身。
    """
    def __init__(self, master, data, max_value=None, **kwargs):
        """
        data: list of (label, value, color_key) 或 (label, value, color_key, detail)
        color_key: 使用 COLORS 中的键名，如 "primary", "success", "warning", "danger"
        """
        super().__init__(master, **kwargs)
        colors = get_colors()
        self.configure(fg_color=colors["card"], corner_radius=CORNER_RADIUS["lg"])

        if max_value is None:
            max_value = max((item[1] for item in data), default=1)

        for item in data:
            label, value, color_key = item[0], item[1], item[2]
            detail = item[3] if len(item) > 3 else ""

            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=SPACING["lg"], pady=SPACING["xs"])

            # 左侧文字列：名称 + 可选明细
            #
            # ⚠️ 必须显式写 ``height=1``：CTkFrame 的 height 默认值是 200，
            # 只给 width 不给 height 时，内部 canvas 会请求 200px 高度，
            # 于是每一行都被撑到 200px（一屏只能放下两条）。
            # 传 height=1 后，实际高度取"canvas 请求 1px"与"子控件请求"
            # 的较大值，即自然贴合内容。
            #
            # 也刻意**不用** pack_propagate(False)：那会把高度锁死在 1px
            # 从而裁掉文字。宽度靠 label 的 wraplength 控制，超长明细自动换行。
            text_col = ctk.CTkFrame(row, fg_color="transparent", width=170, height=1)
            text_col.pack(side="left")

            ctk.CTkLabel(text_col, text=label, font=font_typo("caption"),
                         text_color=colors["text_secondary"], anchor="w",
                         wraplength=165, justify="left").pack(fill="x")
            if detail:
                ctk.CTkLabel(text_col, text=detail, font=font_typo("micro"),
                             text_color=colors["text_tertiary"], anchor="w",
                             wraplength=165, justify="left").pack(fill="x")

            # 进度条背景
            bar_bg = ctk.CTkFrame(row, fg_color=colors["ring_track"],
                                  corner_radius=CORNER_RADIUS["sm"], height=14)
            bar_bg.pack(side="left", fill="x", expand=True, padx=SPACING["sm"])

            # 进度条填充
            ratio = value / max_value if max_value > 0 else 0
            bar_fill = ctk.CTkFrame(bar_bg, fg_color=colors.get(color_key, colors["primary"]),
                                     corner_radius=CORNER_RADIUS["sm"], height=14)
            bar_fill.place(relx=0, rely=0, relwidth=max(ratio, 0.02), relheight=1)

            ctk.CTkLabel(row, text=str(value), font=font_typo("caption_bold"),
                         text_color=colors.get(color_key, colors["primary"]), width=40).pack(side="right")


class StatCard(ctk.CTkFrame):
    """统计卡片 — 升级版，带渐变条"""
    def __init__(self, master, title, value, subtitle="", icon="",
                 gradient_key="gradient_card_blue_top", **kwargs):
        super().__init__(master, **kwargs)
        colors = get_colors()
        self.configure(fg_color=colors["card"], corner_radius=CORNER_RADIUS["lg"],
                       border_color=colors["border_light"], border_width=1)

        # 顶部渐变色条
        gradient_bar = ctk.CTkFrame(self, height=4, fg_color=colors[gradient_key],
                                    corner_radius=0)
        gradient_bar.pack(fill="x")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(SPACING["md"], SPACING["lg"]))

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x", pady=(0, SPACING["xs"]))
        if icon:
            ctk.CTkLabel(header, text=icon, font=font_emoji(18)).pack(side="left", padx=(0, SPACING["sm"]))
        ctk.CTkLabel(header, text=title, font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(side="left")

        self.value_label = ctk.CTkLabel(content, text=value, font=font_safe(32, "bold"),
                                        text_color=colors[gradient_key])
        self.value_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(content, text=subtitle, font=font_typo("micro"),
                                           text_color=colors["text_tertiary"])
        if subtitle:
            self.subtitle_label.pack(anchor="w")

    def update_value(self, value=None, subtitle=None):
        if value is not None:
            self.value_label.configure(text=value)
        if subtitle is not None:
            self.subtitle_label.configure(text=subtitle)
            self.subtitle_label.pack(anchor="w")


class RiskBadge(ctk.CTkFrame):
    """风险等级徽章 — 保留兼容"""
    RISK_STYLES = {
        "安全": "safe",
        "低风险": "low",
        "中风险": "medium",
        "高风险": "high",
        "极高风险": "extreme",
    }

    def __init__(self, master, risk_level, **kwargs):
        super().__init__(master, **kwargs)
        colors = get_colors()
        level_key = self.RISK_STYLES.get(risk_level, "medium")
        style = status_pill_style(level_key)
        self.configure(fg_color=style["bg"], corner_radius=CORNER_RADIUS["md"], height=32)
        ctk.CTkLabel(self, text=f"{style['icon']}  {risk_level}",
                     font=font_safe(13, "bold"), text_color=style["fg"]).pack(padx=SPACING["md"], pady=SPACING["xs"])


class StatusPill(ctk.CTkFrame):
    """状态胶囊标签 — 替代 RiskBadge，更现代"""
    def __init__(self, master, level="safe", text="", **kwargs):
        """
        level: safe / low / medium / high / extreme
        """
        super().__init__(master, **kwargs)
        colors = get_colors()
        style = status_pill_style(level)
        self.configure(fg_color=style["bg"], corner_radius=CORNER_RADIUS["md"], height=28)
        display_text = f"{style['icon']}  {text}" if text else f"{style['icon']}"
        ctk.CTkLabel(self, text=display_text,
                     font=font_typo("caption_bold"), text_color=style["fg"]).pack(padx=SPACING["md"], pady=2)


class ScoreRing(ctk.CTkFrame):
    """合规分数圆环 — 简化版（兼容旧代码）"""
    def __init__(self, master, score, **kwargs):
        colors = get_colors()
        super().__init__(master, fg_color=colors["card"], corner_radius=CORNER_RADIUS["xl"],
                         border_color=colors["border_light"], border_width=1, **kwargs)

        if score >= 80:
            color = colors["ring_success"]
        elif score >= 60:
            color = colors["ring_warning"]
        else:
            color = colors["ring_danger"]

        ctk.CTkLabel(self, text="合规分数", font=font_typo("caption"),
                     text_color=colors["text_secondary"]).pack(anchor="w", padx=SPACING["lg"], pady=(SPACING["md"], 0))
        ctk.CTkLabel(self, text=str(score), font=font_safe(48, "bold"),
                     text_color=color).pack(anchor="w", padx=SPACING["lg"])
        ctk.CTkLabel(self, text="/ 100", font=font_typo("caption"),
                     text_color=colors["text_tertiary"]).pack(anchor="w", padx=SPACING["lg"], pady=(0, SPACING["lg"]))


class ToastNotification(ctk.CTkLabel):
    """底部弹出精致通知"""
    def __init__(self, master, message, icon="✅", duration=2500, **kwargs):
        colors = get_colors()
        super().__init__(master, text=f"{icon}  {message}",
                         font=font_safe(14, "bold"),
                         text_color=colors["text_on_primary"],
                         fg_color=colors["success"],
                         corner_radius=CORNER_RADIUS["md"],
                         height=40, **kwargs)

    def show(self, parent, duration=2500):
        """在父组件上显示，指定时间后消失"""
        self.place(relx=0.5, rely=0.92, anchor="center")
        parent.after(duration, self.destroy)


class HoverTooltip:
    """悬停浮窗管理器 — 高亮词详情弹出

    用法：
        tooltip = HoverTooltip(text_widget)
        tooltip.bind_tag("violation", violation_data_dict)
    """
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self._tooltip_window = None
        self._tag_data = {}  # tag_name -> list of (start_index, end_index, data_dict)

    def bind_tag(self, tag_name, violations_list):
        """为指定标签绑定违规数据"""
        self._tag_data[tag_name] = []
        for v in violations_list:
            start_idx = v.get("_display_start", "1.0")
            end_idx = v.get("_display_end", "1.0")
            self._tag_data[tag_name].append((start_idx, end_idx, v))

        self.text_widget.tag_bind(tag_name, "<Motion>", self._on_motion)
        self.text_widget.tag_bind(tag_name, "<Leave>", self._on_leave)

    def _on_motion(self, event):
        """鼠标移入高亮词时弹出浮窗"""
        # 获取鼠标位置对应的文本索引
        index = self.text_widget.index(f"@{event.x},{event.y}")

        # 查找匹配的违规数据
        for tag_name, entries in self._tag_data.items():
            for start_idx, end_idx, data in entries:
                # 比较索引范围
                if self._index_in_range(index, start_idx, end_idx):
                    self._show_tooltip(event, data)
                    return

    def _on_leave(self, event):
        """鼠标离开时销毁浮窗"""
        self._hide_tooltip()

    def _index_in_range(self, index, start, end):
        """检查索引是否在指定范围内"""
        try:
            idx_line, idx_col = map(int, index.split("."))
            s_line, s_col = map(int, start.split("."))
            e_line, e_col = map(int, end.split("."))
            if idx_line < s_line or (idx_line == s_line and idx_col < s_col):
                return False
            if idx_line > e_line or (idx_line == e_line and idx_col > e_col):
                return False
            return True
        except (ValueError, AttributeError):
            return False

    def _show_tooltip(self, event, data):
        """显示浮窗"""
        self._hide_tooltip()

        colors = get_colors()

        # 创建浮窗 Toplevel
        tw = tk.Toplevel(self.text_widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=colors["card"])

        # 计算浮窗位置
        x = event.x_root + 15
        y = event.y_root + 10
        tw.wm_geometry(f"+{x}+{y}")

        self._tooltip_window = tw

        # 浮窗内容
        frame = ctk.CTkFrame(tw, fg_color=colors["card"],
                              corner_radius=CORNER_RADIUS["md"],
                              border_color=colors["border"],
                              border_width=1)
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        # 关键词
        keyword = data.get("keyword", "")
        category = data.get("category", "")
        severity = data.get("severity", "warning")
        suggestion = data.get("suggestion", "")
        source = data.get("source", "")
        law_ref = data.get("law_ref", "")
        note = data.get("note", "")
        blue_v_label = data.get("blue_v_label", "")

        # 严重程度颜色
        sev_color = colors["danger"] if severity == "violation" else colors["warning"]
        sev_text = "🔴 违规" if severity == "violation" else "🟡 警告"

        # 标题行
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))

        ctk.CTkLabel(header, text=f"「{keyword}」", font=font_safe(14, "bold"),
                     text_color=sev_color).pack(side="left")
        ctk.CTkLabel(header, text=sev_text, font=font_typo("micro_bold"),
                     text_color=sev_color).pack(side="right")

        # 分类 + 来源
        detail_line = ctk.CTkFrame(frame, fg_color="transparent")
        detail_line.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["xs"]))
        ctk.CTkLabel(detail_line, text=f"分类：{category}", font=font_typo("micro"),
                     text_color=colors["text_secondary"]).pack(side="left")
        if source:
            ctk.CTkLabel(detail_line, text=f"来源：{source}", font=font_typo("micro"),
                         text_color=colors["text_tertiary"]).pack(side="right")

        # 法条引用
        if law_ref:
            ctk.CTkLabel(frame, text=f"📜 {law_ref}", font=font_typo("micro"),
                         text_color=colors["text_secondary"]).pack(anchor="w", padx=SPACING["md"])
        if note:
            ctk.CTkLabel(frame, text=note, font=font_typo("micro"),
                         text_color=colors["text_tertiary"], wraplength=300,
                         justify="left", anchor="w").pack(fill="x", padx=SPACING["md"])

        # 蓝V标签
        if blue_v_label:
            ctk.CTkLabel(frame, text=f"[{blue_v_label}]", font=font_typo("caption_bold"),
                         text_color=colors["primary"]).pack(anchor="w", padx=SPACING["md"])

        # 建议
        if suggestion:
            ctk.CTkLabel(frame, text=f"💡 {suggestion}", font=font_typo("caption"),
                         text_color=colors["text"], wraplength=300, justify="left",
                         anchor="w").pack(fill="x", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]))

    def _hide_tooltip(self):
        """销毁浮窗"""
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None


class SegmentedControl(ctk.CTkFrame):
    """分段选择器 — 平台选择、标签页切换"""

    def __init__(self, master, segments, on_select, initial=0, **kwargs):
        """
        segments: list of (label, value)
        on_select: callback(value) when segment selected
        """
        colors = get_colors()
        super().__init__(master, fg_color=colors["bg"],
                         corner_radius=CORNER_RADIUS["lg"], **kwargs)
        self._segments = segments
        self._on_select = on_select
        self._selected_idx = initial
        self._buttons = []
        self._build_buttons()

    def _build_buttons(self):
        colors = get_colors()
        for widget in self.winfo_children():
            widget.destroy()
        self._buttons = []

        for i, (label, value) in enumerate(self._segments):
            is_active = i == self._selected_idx
            btn = ctk.CTkButton(
                self, text=label,
                width=90, height=32,
                corner_radius=CORNER_RADIUS["md"],
                fg_color=colors["primary"] if is_active else colors["card"],
                hover_color=colors["primary_hover"] if is_active else colors["hover"],
                text_color=colors["text_on_primary"] if is_active else colors["text"],
                border_width=0 if is_active else 1,
                border_color=colors["border_light"],
                font=font_safe(13, "bold" if is_active else "normal"),
                command=lambda v=value, idx=i: self._select(idx, v),
            )
            btn.pack(side="left", padx=(0, SPACING["xs"]))
            self._buttons.append(btn)

    def _select(self, idx, value):
        self._selected_idx = idx
        self._build_buttons()
        self._on_select(value)

    def set_selected(self, idx):
        self._selected_idx = idx
        self._build_buttons()
