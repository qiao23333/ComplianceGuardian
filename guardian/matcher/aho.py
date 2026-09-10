#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pyahocorasick 后端封装。

C 扩展，速度比纯 Python 实现快 30-60 倍。本机实测在 Python 3.11.4 +
Windows 上 `pip install pyahocorasick` 可直接拿到预编译 wheel，无需编译。

若导入失败，调用方应通过 ``matcher.factory`` 回退到 ``PureAhoMatcher``。
"""

from __future__ import annotations

from typing import Iterable

try:
    import ahocorasick

    AHO_AVAILABLE = True
except ImportError:  # pragma: no cover - 取决于运行环境
    ahocorasick = None
    AHO_AVAILABLE = False

from guardian.matcher.base import KeywordIndex, Matcher, Hit
from guardian.schema import Rule


class AhoMatcher(Matcher):
    """pyahocorasick 多模式匹配器封装。"""

    backend = "pyahocorasick"

    def __init__(self) -> None:
        self._automaton = ahocorasick.Automaton() if AHO_AVAILABLE else None
        self._keywords = 0

    def build(self, index: KeywordIndex) -> None:
        if not AHO_AVAILABLE:
            raise RuntimeError("pyahocorasick 未安装，请使用 PureAhoMatcher")
        # 先用普通 dict 聚合（同一关键词可能来自多个词库 → 多条规则）
        agg: dict[str, list] = {}
        for keyword, rules in index.items():
            if not keyword:
                continue
            agg.setdefault(keyword, []).extend(rules)
            self._keywords += 1
        auto = ahocorasick.Automaton()
        for keyword, rules in agg.items():
            auto.add_word(keyword, (keyword, list(rules)))
        auto.make_automaton()
        self._automaton = auto

    def iter_hits(self, text: str) -> Iterable[Hit]:
        if self._automaton is None:
            return
        # ahocorasick 的 end 是 "最后一个字符的下标"（闭区间），
        # 转成左闭右开 [start, end)
        for end_idx, (keyword, rules) in self._automaton.iter(text):
            start = end_idx - len(keyword) + 1
            end = end_idx + 1
            for rule in rules:
                yield (start, end, keyword, rule)

    def keyword_count(self) -> int:
        return self._keywords
