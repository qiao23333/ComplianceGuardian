#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规检测工具 v2.2 — 完整设计系统（现代仪表盘风 + 暗色模式）

设计语言：高端 SaaS 控制台风格
- Light: 白卡片+灰底+深蓝渐变强调色+微渐变背景
- Dark: 暗卡片+深底+亮蓝霓虹强调色+半透明叠层
"""

import customtkinter as ctk

# ============================================================
# Light 主题色值
# ============================================================
COLORS_LIGHT = {
    # 基础色
    "bg": "#F2F2F7",
    "bg_gradient_top": "#E8ECF4",
    "bg_gradient_bottom": "#F2F2F7",
    "sidebar": "#FFFFFF",
    "sidebar_gradient_top": "#EEF2FF",
    "sidebar_gradient_bottom": "#FFFFFF",
    "card": "#FFFFFF",
    "card_elevated": "#FFFFFF",

    # 主色（渐变）
    "primary": "#0071E3",
    "primary_gradient_start": "#0071E3",
    "primary_gradient_end": "#0040B5",
    "primary_hover": "#0077ED",
    "primary_active": "#0068D1",
    "primary_light": "#E8F4FD",

    # 文字色
    "text": "#1D1D1F",
    "text_secondary": "#6E6E73",
    "text_tertiary": "#AEAEB2",
    "text_on_primary": "#FFFFFF",
    "text_on_gradient": "#FFFFFF",

    # 边框色
    "border": "#D2D2D7",
    "border_light": "#E5E5EA",
    "border_focus": "#0071E3",

    # 状态色
    "success": "#34C759",
    "success_light": "#E8F8EE",
    "warning": "#FF9500",
    "warning_light": "#FFF8E1",
    "danger": "#FF3B30",
    "danger_light": "#FFE5E5",
    "info": "#5AC8FA",
    "info_light": "#E5F5FF",

    # 交互色
    "hover": "#F2F2F7",
    "selected": "#E8F4FD",
    "pressed": "#DCDCDE",
    "disabled": "#E5E5EA",
    "disabled_text": "#AEAEB2",

    # 高亮色（检测结果）
    "highlight_violation_bg": "#FFD6D6",
    "highlight_violation_fg": "#C0392B",
    "highlight_warning_bg": "#FFF3CD",
    "highlight_warning_fg": "#856404",
    "highlight_bluev_bg": "#D6E4FF",
    "highlight_bluev_fg": "#004085",
    "highlight_safe_bg": "#FFFFFF",
    "highlight_safe_fg": "#1D1D1F",

    # 渐变卡片色
    "gradient_card_blue_top": "#0071E3",
    "gradient_card_blue_bottom": "#0040B5",
    "gradient_card_green_top": "#34C759",
    "gradient_card_green_bottom": "#248A3D",
    "gradient_card_orange_top": "#FF9500",
    "gradient_card_orange_bottom": "#CC7700",
    "gradient_card_red_top": "#FF3B30",
    "gradient_card_red_bottom": "#D70015",
    "gradient_card_purple_top": "#AF52DE",
    "gradient_card_purple_bottom": "#8944AB",

    # 磨砂/玻璃色
    "glass_bg": "#F0F4FF",
    "glass_border": "#B8CCFF",
    "glass_text": "#004085",

    # 投影色（伪投影用背景色偏移）
    "shadow_light": "#E5E5EA",
    "shadow_medium": "#D1D1D6",

    # 圆环进度色
    "ring_track": "#E5E5EA",
    "ring_success": "#34C759",
    "ring_warning": "#FF9500",
    "ring_danger": "#FF3B30",
    "ring_primary": "#0071E3",
}

# ============================================================
# Dark 主题色值
# ============================================================
COLORS_DARK = {
    # 基础色
    "bg": "#0A0A0B",
    "bg_gradient_top": "#1C1C2E",
    "bg_gradient_bottom": "#0A0A0B",
    "sidebar": "#1C1C1E",
    "sidebar_gradient_top": "#2C2C3E",
    "sidebar_gradient_bottom": "#1C1C1E",
    "card": "#1C1C1E",
    "card_elevated": "#2C2C2E",

    # 主色（霓虹渐变）
    "primary": "#0A84FF",
    "primary_gradient_start": "#0A84FF",
    "primary_gradient_end": "#5AC8FA",
    "primary_hover": "#409CFF",
    "primary_active": "#007AFF",
    "primary_light": "#1C3A5C",

    # 文字色
    "text": "#F5F5F7",
    "text_secondary": "#98989D",
    "text_tertiary": "#636366",
    "text_on_primary": "#FFFFFF",
    "text_on_gradient": "#FFFFFF",

    # 边框色
    "border": "#38383A",
    "border_light": "#2C2C2E",
    "border_focus": "#0A84FF",

    # 状态色
    "success": "#30D158",
    "success_light": "#1C3A2A",
    "warning": "#FFD60A",
    "warning_light": "#3A3A1C",
    "danger": "#FF453A",
    "danger_light": "#3A1C1C",
    "info": "#64D2FF",
    "info_light": "#1C3A5C",

    # 交互色
    "hover": "#2C2C2E",
    "selected": "#1C3A5C",
    "pressed": "#38383A",
    "disabled": "#2C2C2E",
    "disabled_text": "#636366",

    # 高亮色（检测结果 — 霓虹感）
    "highlight_violation_bg": "#3A1C1C",
    "highlight_violation_fg": "#FF453A",
    "highlight_warning_bg": "#3A3A1C",
    "highlight_warning_fg": "#FFD60A",
    "highlight_bluev_bg": "#1C3A5C",
    "highlight_bluev_fg": "#64D2FF",
    "highlight_safe_bg": "#1C1C1E",
    "highlight_safe_fg": "#F5F5F7",

    # 渐变卡片色
    "gradient_card_blue_top": "#0A84FF",
    "gradient_card_blue_bottom": "#5AC8FA",
    "gradient_card_green_top": "#30D158",
    "gradient_card_green_bottom": "#34C759",
    "gradient_card_orange_top": "#FFD60A",
    "gradient_card_orange_bottom": "#FF9500",
    "gradient_card_red_top": "#FF453A",
    "gradient_card_red_bottom": "#FF3B30",
    "gradient_card_purple_top": "#BF5AF2",
    "gradient_card_purple_bottom": "#AF52DE",

    # 磨砂/玻璃色
    "glass_bg": "#1C2C4E",
    "glass_border": "#3A5C8A",
    "glass_text": "#64D2FF",

    # 投影色
    "shadow_light": "#2C2C2E",
    "shadow_medium": "#38383A",

    # 圆环进度色
    "ring_track": "#2C2C2E",
    "ring_success": "#30D158",
    "ring_warning": "#FFD60A",
    "ring_danger": "#FF453A",
    "ring_primary": "#0A84FF",
}

# ============================================================
# 间距规范
# ============================================================
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

# ============================================================
# 字体规范（层级化）
# ============================================================
TYPOGRAPHY = {
    "display": (48, "bold"),
    "h1": (28, "bold"),
    "h2": (20, "bold"),
    "h3": (16, "bold"),
    "body": (14, "normal"),
    "body_bold": (14, "bold"),
    "caption": (12, "normal"),
    "caption_bold": (12, "bold"),
    "micro": (10, "normal"),
    "micro_bold": (10, "bold"),
}

# ============================================================
# 圆角规范
# ============================================================
CORNER_RADIUS = {
    "sm": 6,
    "md": 10,
    "lg": 14,
    "xl": 20,
}

# ============================================================
# 动态取色函数
# ============================================================
# 兼容旧代码：COLORS 作为默认 Light 引用
COLORS = COLORS_LIGHT


def get_colors():
    """根据当前 appearance mode 返回对应主题色值"""
    mode = ctk.get_appearance_mode()
    if mode == "Dark":
        return COLORS_DARK
    return COLORS_LIGHT


def font_safe(size=14, weight="normal"):
    """统一字体规范（SF Pro Display）"""
    return ("SF Pro Display", size, weight)


def font_typo(key="body"):
    """按 TYPOGRAPHY 规范取字体"""
    size, weight = TYPOGRAPHY.get(key, (14, "normal"))
    return font_safe(size, weight)


# ============================================================
# 样式函数（全部动态取色）
# ============================================================

def apply_root_theme(root):
    colors = get_colors()
    root.configure(fg_color=colors["bg"])


def sidebar_button_style():
    colors = get_colors()
    return {
        "width": 200,
        "height": 42,
        "corner_radius": CORNER_RADIUS["md"],
        "fg_color": "transparent",
        "hover_color": colors["hover"],
        "text_color": colors["text"],
        "font": font_safe(14, "normal"),
        "anchor": "w",
        "compound": "left",
    }


def sidebar_button_active_style():
    colors = get_colors()
    style = sidebar_button_style()
    style["fg_color"] = colors["selected"]
    style["text_color"] = colors["primary"]
    style["hover_color"] = colors["selected"]
    style["font"] = font_safe(14, "bold")
    return style


def primary_button_style():
    colors = get_colors()
    return {
        "corner_radius": CORNER_RADIUS["md"],
        "fg_color": colors["primary"],
        "hover_color": colors["primary_hover"],
        "text_color": colors["text_on_primary"],
        "font": font_safe(13, "bold"),
        "height": 36,
    }


def secondary_button_style():
    colors = get_colors()
    return {
        "corner_radius": CORNER_RADIUS["md"],
        "fg_color": colors["card"],
        "hover_color": colors["hover"],
        "text_color": colors["text"],
        "border_color": colors["border_light"],
        "border_width": 1,
        "font": font_safe(13, "normal"),
        "height": 36,
    }


def danger_button_style():
    colors = get_colors()
    return {
        "corner_radius": CORNER_RADIUS["md"],
        "fg_color": colors["danger"],
        "hover_color": colors["danger_light"],
        "text_color": colors["text_on_primary"],
        "font": font_safe(13, "bold"),
        "height": 36,
    }


def card_frame_style():
    colors = get_colors()
    return {
        "fg_color": colors["card"],
        "corner_radius": CORNER_RADIUS["xl"],
        "border_color": colors["border_light"],
        "border_width": 1,
    }


def elevated_card_style():
    """带投影的高亮卡片样式"""
    colors = get_colors()
    return {
        "fg_color": colors["card_elevated"],
        "corner_radius": CORNER_RADIUS["xl"],
        "border_color": colors["shadow_light"],
        "border_width": 1,
    }


def glass_card_style():
    """半透明磨砂卡片（LLM分析区、特殊信息区）"""
    colors = get_colors()
    return {
        "fg_color": colors["glass_bg"],
        "corner_radius": CORNER_RADIUS["lg"],
        "border_color": colors["glass_border"],
        "border_width": 1,
    }


def gradient_button_style():
    """渐变主按钮样式（视觉上渐变，CustomTkinter不支持真渐变，
    用 primary_gradient_start 作为 fg_color）"""
    colors = get_colors()
    return {
        "corner_radius": CORNER_RADIUS["md"],
        "fg_color": colors["primary_gradient_start"],
        "hover_color": colors["primary_hover"],
        "text_color": colors["text_on_gradient"],
        "font": font_safe(14, "bold"),
        "height": 38,
    }


def status_pill_style(level="safe"):
    """状态胶囊标签样式"""
    colors = get_colors()
    pill_map = {
        "safe": {"bg": colors["success_light"], "fg": colors["success"], "icon": "✅"},
        "low": {"bg": colors["warning_light"], "fg": colors["warning"], "icon": "🟡"},
        "medium": {"bg": colors["warning_light"], "fg": colors["warning"], "icon": "⚠️"},
        "high": {"bg": colors["danger_light"], "fg": colors["danger"], "icon": "🔴"},
        "extreme": {"bg": colors["danger_light"], "fg": colors["danger"], "icon": "🚨"},
    }
    return pill_map.get(level, pill_map["medium"])


def segmented_control_style():
    """分段选择器基础样式"""
    colors = get_colors()
    return {
        "active_fg": colors["primary"],
        "active_hover": colors["primary_hover"],
        "active_text": colors["text_on_primary"],
        "inactive_fg": colors["card"],
        "inactive_hover": colors["hover"],
        "inactive_text": colors["text"],
        "inactive_border": colors["border_light"],
        "corner_radius": CORNER_RADIUS["md"],
        "height": 32,
        "font_active": font_safe(13, "bold"),
        "font_inactive": font_safe(13, "normal"),
    }
