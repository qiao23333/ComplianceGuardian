#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归一化管线测试：index_map 精准回映射是变体抗规避的基石。

核心保证：归一化（去噪声 / 全角→半角 / 繁简 / 谐音）后，任何命中坐标都能
精确还原回**带规避花招**的原文位置，UI 高亮与改写才不会偏一格。
"""

import pytest

from guardian.normalize import normalize, normalize_strip_only
from guardian.normalize.pipeline import NormalizedText

try:
    from opencc import OpenCC
    _HAS_OPENCC = True
except Exception:
    _HAS_OPENCC = False


# ---------------------------------------------------------------- 纯噪声：回映射自洽


@pytest.mark.parametrize("text", [
    "加 微 信 领 取 资 料",       # 微不在谐音表，空格是唯一干扰
    "最 近 很 多 人 问",
    "微　信　　公　众　号",        # 全角空格（无谐音/全角字母）
    "加·微·信·了·解·更·多",
    "零宽\u200b字符\u200b插入",
    "中　间　点　分　隔",
    "微 信 微 信 微 信",
    "跳 字 跳 字 跳 字 测 试",
    "最·后·提·醒·一·次",
])
def test_noise_roundtrip(text):
    """纯噪声（无谐音/繁简）情况下：归一化后逐字符回映射 == 去噪后的原文。"""
    n = normalize(text)
    rebuilt = "".join(text[n.original_span(j, j + 1)[0]:n.original_span(j, j + 1)[1]]
                     for j in range(len(n.text)))
    assert rebuilt == n.text, f"回映射失真：\n原文 {text!r}\n归一 {n.text!r}\n重建 {rebuilt!r}"
    assert " " not in n.text


def test_original_span_maps_to_source_chars():
    """original_span 能把归一化坐标还原成原文片段（含被删的噪声）。"""
    text = "加 微 信"
    n = normalize(text)              # -> "加微信"
    s, e = n.original_span(1, 3)     # 归一化 [1,3) = 微信
    assert text[s:e] == "微 信"      # 还原回带空格的原文


def test_homophone_original_substring():
    """谐音替换后，original_substring 仍指向**原文**（薇信），而非归一化结果。"""
    text = "薇 信"
    n = normalize(text)              # -> "微信"（薇→微）
    assert n.text == "微信"
    assert n.original_substring(0, 2) == "薇 信"


def test_homophone_normalization():
    """谐音/形近字归一：薇→微，使 Aho 能命中"微信"。"""
    n = normalize("薇信")
    assert "微" in n.text, n.text
    assert "薇" not in n.text, n.text


@pytest.mark.skipif(not _HAS_OPENCC, reason="未安装 opencc-python-reimplemented")
def test_traditional_to_simplified():
    """繁体→简体（若装了 OpenCC）。"""
    n = normalize("微信公眾號")
    assert "众" in n.text


def test_fullwidth_to_halfwidth():
    """全角字母数字→半角。"""
    n = normalize("ＷＥＩＸＩＮ")
    assert n.text == "WEIXIN"


def test_strip_only_lightweight():
    """轻量去噪声（不替换、不繁简）仅供 UI 预览。"""
    assert normalize_strip_only("加 薇 信") == "加薇信"
