#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归一化与变体检测层。

* ``pipeline``：噪声/全角/繁简/谐音归一化 + index_map 回映射
* ``variants``：拼音 / 首字母变体（可选增强，依赖 pypinyin）

引擎层会先用 ``normalize`` 跑一轮（捕获谐音/跳字/繁简/全角变体），
若 pypinyin 可用再用 ``romanize`` + ``pinyin_index`` 跑一轮（捕获拼音变体）。
"""

from guardian.normalize.pipeline import NormalizedText, normalize, normalize_strip_only
from guardian.normalize.variants import RomanizedText, pinyin_index, romanize

__all__ = [
    "NormalizedText",
    "normalize",
    "normalize_strip_only",
    "RomanizedText",
    "pinyin_index",
    "romanize",
]
