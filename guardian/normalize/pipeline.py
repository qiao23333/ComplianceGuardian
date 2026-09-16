#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本归一化管线（变体抗规避检测的核心）。

目标
----
把"加了规避花招"的文本还原成规范形式，让关键词自动机能命中：

    原文本:  "加 薇 信  微 信"
    归一后:  "加微信微信"   （去噪声 + 薇→微）
    命中:    "微信" 两次

关键设计：``index_map``
--------------------------------
归一化会**删字符**（去噪声）或**换字符**（谐音/繁简）。我们用一张映射表
``index_map[j] = 原文字符下标``，把归一化文本里的命中坐标回映射到原文，
这样 UI 高亮和改写都能精准定位到"带花招"的那段。

管线步骤（顺序敏感）
--------------------
1. 去噪声：空格 / 零宽字符 / 中间点 / 下划线等插在字间的干扰符
2. 全角→半角（字母数字）：ＷＥＩＸＩＮ → WEIXIN
3. 繁体→简体（OpenCC，失败则跳过）
4. 谐音/形近字替换（rules/overrides/homophone.json）

步骤 2~4 是**等长 1:1 替换**，不改动 index_map；
步骤 1 会删字符，重建 index_map。

⚠️ 「阿拉伯数字→中文数字」**不在这条管线里**，它是独立通道（``to_cjk_digits``），
原因见该函数上方的说明 —— 放进主链路会反向砸掉全角数字的归一化命中能力。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ============================================================ 噪声字符集

#: 插在字间用于规避的"干扰符"。注意：不放连字符 '-' / 斜杠 '/'，
#: 以免误删正常写法（如日期、网址）。
_NOISE_CHARS = {
    "\u0020",  # 空格
    "\u00a0",  # 不换行空格
    "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005",
    "\u2006", "\u2007", "\u2008", "\u2009", "\u200a",  # 各类窄空格
    "\u200b",  # 零宽空格
    "\u200c",  # 零宽不连字
    "\u200d",  # 零宽连字
    "\ufeff",  # BOM / 零宽无断空格
    "\u3000",  # 全角空格
    "\u30fb",  # 中间点（日文中点，常被用来分隔）
    "\u00b7",  # 间隔号 ·
    "_",       # 下划线（加_微_信）
    "・",      # 居中句号（另一种分隔点）
}


def _is_noise(ch: str) -> bool:
    return ch in _NOISE_CHARS


# ============================================================ 全角→半角

#: 全角 ASCII 可视字符（！～）→ 半角（!~）的偏移
def _fullwidth_to_half(ch: str) -> str:
    code = ord(ch)
    if 0xFF01 <= code <= 0xFF5E:  # ！到～
        return chr(code - 0xFEE0)
    if ch == "\u3000":  # 全角空格
        return " "
    return ch


# ============================================================ 阿拉伯数字 → 中文数字

#: 单字符数字映射：0-9 ↔ 零-九 都是 1 个字符，属**等长**替换，
#: 因此转换后的坐标可直接复用原 index_map（见 ``to_cjk_digits``）。
#:
#: 为什么需要这一层
#: ----------------
#: 中文里数字有阿拉伯与汉字两套写法，**使用边界纯凭手感**：
#: "7天瘦" 与 "七天瘦" 是同一种违规表述，用户写哪个全看习惯。
#: 词库每个关键词只能收一种写法，另一种就成了漏检口子 ——
#: 实测「七天瘦」命中而「7天瘦」漏检，而后者才是营销文案里的主流写法。
#:
#: ⚠️ **刻意不放进 ``normalize()`` 主链路**。曾经试过在管线里直接转换，
#: 结果是反向砸了另一个能力：全角「成功率１００％」原本靠"全角→半角"
#: 归一后命中关键词「100%」，数字一转成"一零零"就再也匹配不上，
#: 对拍门禁当场把这条回归抓了出来（``test_normalized_channel_remaps_to_original_span``）。
#: 归一化的职责是**忠实还原花招**，而数字是"同一表述的两种合法写法"，
#: 性质不同 —— 所以它单独走一条通道，两个方向都保住。
#:
#: ⚠️ 只做**单字符**映射。多位数（"10"→"十"）会改变长度，击穿
#: index_map 与命中坐标的回映射，必须排除。这类"多位数字 + 汉字数字"
#: 混写（如"限三十五岁"）目前仍是已知边界。
#:
#: ⚠️ 反向（汉字→阿拉伯）刻意不做：词库中 33 条含阿拉伯数字的关键词
#: （100% / 0元购 / P2P …）靠**原文通道**命中，本层只服务数字通道，
#: 单向即可，反向会让"一零零%"这类不自然写法进入匹配空间。
_DIGIT_TO_CJK = {
    "0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
    "5": "五", "6": "六", "7": "七", "8": "八", "9": "九",
}


def to_cjk_digits(text: str) -> str:
    """把阿拉伯数字**逐字符**换成中文数字，长度不变。

    长度不变是关键：调用方可以拿转换后的字符串直接复用原文本的坐标映射
    （``NormalizedText.original_span``），命中位置能精准回落到原文，
    不会出现"高亮错位"。转换内容相同则返回原串（调用方据此跳过整条通道）。
    """
    return "".join(_DIGIT_TO_CJK.get(ch, ch) for ch in text)


# ============================================================ 繁体→简体

@lru_cache(maxsize=1)
def _get_opencc():
    """懒加载 OpenCC（装不上就返回 None，管线降级跳过繁简转换）。"""
    try:
        from opencc import OpenCC

        return OpenCC("t2s")  # 繁体 → 简体
    except Exception:  # pragma: no cover - 取决于是否装 opencc
        return None


# ============================================================ 谐音表

@lru_cache(maxsize=1)
def _load_homophone_map() -> dict[str, str]:
    """加载 rules/overrides/homophone.json 的形近/音近字映射。"""
    path = Path(__file__).resolve().parents[2] / "rules" / "overrides" / "homophone.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data.get("map", {}))
    except Exception:  # pragma: no cover
        return {}


# ============================================================ 归一化结果


@dataclass
class NormalizedText:
    """归一化结果。

    Attributes:
        text: 归一化后的字符串（用于跑匹配器）
        index_map: ``index_map[j]`` = 该归一化字符对应的**原文字符下标**
        original: 原始文本（用于回映射时取片段）
    """

    text: str
    index_map: list[int] = field(default_factory=list)
    original: str = ""

    def original_span(self, norm_s: int, norm_e: int) -> tuple[int, int]:
        """把归一化坐标 [norm_s, norm_e) 回映射到原文 [orig_s, orig_e)。"""
        if not self.index_map:
            return (norm_s, norm_e)
        orig_s = self.index_map[norm_s]
        # 末字符的下标 +1 构成右开区间
        orig_e = self.index_map[min(norm_e, len(self.index_map)) - 1] + 1
        return (orig_s, orig_e)

    def original_substring(self, norm_s: int, norm_e: int) -> str:
        o_s, o_e = self.original_span(norm_s, norm_e)
        return self.original[o_s:o_e]


# ============================================================ 主函数


def normalize(text: str) -> NormalizedText:
    """对文本做完整归一化，返回带 index_map 的结果。

    设计：步骤 1（去噪声）改变长度并重建 index_map；
    步骤 2~4 是等长 1:1 替换，index_map 长度不变、含义不变，可直接复用。
    """
    original = text
    homophone = _load_homophone_map()

    # ---- 步骤 1：去噪声（逐字符保留/丢弃，重建 index_map）----
    buf: list[str] = []
    idx_map: list[int] = []
    for i, ch in enumerate(text):
        if _is_noise(ch):
            continue
        buf.append(ch)
        idx_map.append(i)
    norm = "".join(buf)

    # ---- 步骤 2~4：等长替换（index_map 不变）----
    out_chars = []
    opencc = _get_opencc()
    for ch in norm:
        c = _fullwidth_to_half(ch)          # 全角→半角
        if opencc is not None:
            c = opencc.convert(c)           # 繁→简
        c = homophone.get(c, c)             # 谐音/形近
        out_chars.append(c)
    norm = "".join(out_chars)

    return NormalizedText(text=norm, index_map=idx_map, original=original)


def normalize_strip_only(text: str) -> str:
    """仅去噪声（轻量，供 UI 预览"去掉规避空格后"的效果）。"""
    return "".join(ch for ch in text if not _is_noise(ch))
