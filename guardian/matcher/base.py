#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""匹配器抽象接口。

匹配器只做一件事：给定文本和关键词→规则映射，找出所有命中区间。
不知道规则含义、不做过滤、不改写——那些是 engine 和 context_guard 的事。

约定
----
* 同一个关键词可能对应**多条规则**（如"加微信"同时存在于三个平台词库），
  因此索引值是 ``list[Rule]``。这是 v2.4 修过的 AC 覆盖 bug 的教训。
* 返回的 hit 坐标是 ``[start, end)`` 左闭右开，指向传入的 text。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from guardian.schema import Rule

#: 关键词 → 该关键词的全部规则
KeywordIndex = dict[str, list[Rule]]

#: 一次命中：(start, end, keyword, rule)
Hit = tuple[int, int, str, Rule]


class Matcher(ABC):
    """多模式串匹配器接口。"""

    #: 后端标识（"pyahocorasick" / "pure-python"），写进结果 meta 便于诊断
    backend: str = "abstract"

    @abstractmethod
    def build(self, index: KeywordIndex) -> None:
        """用关键词索引构建自动机。可重复调用（覆盖上一次）。"""

    @abstractmethod
    def iter_hits(self, text: str) -> Iterable[Hit]:
        """扫描文本，产出所有命中（可能重复/重叠，交给 engine 去重）。"""

    @abstractmethod
    def keyword_count(self) -> int:
        """已构建的关键词数量（诊断用）。"""
