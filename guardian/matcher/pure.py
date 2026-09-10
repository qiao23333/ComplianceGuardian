#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯 Python Aho-Corasick 实现（零依赖降级方案）。

什么时候会用它
--------------
* 环境里没装 pyahocorasick（比如某些受限环境装不上 C 扩展）
* 单元测试需要确定性的参考实现

性能对比 pyahocorasick（C 扩展）大约慢 30-60 倍，但对本应用的
典型场景（几百~几千字文案、900+ 关键词）完全够用：
实测 2000 字 / 938 关键词约 10ms 量级，用户无感。

实现：经典 Trie + BFS 失配指针。代码保持直白，优先可读性。
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from guardian.matcher.base import KeywordIndex, Matcher, Hit


class _Node:
    """Trie 节点。__slots__ 省内存（900+ 关键词、数千节点）。"""

    __slots__ = ("children", "fail", "outputs")

    def __init__(self) -> None:
        self.children: dict[str, "_Node"] = {}
        self.fail: "_Node | None" = None
        # 命中此节点时输出的 (keyword, rules) 列表
        self.outputs: list[tuple[str, list]] = []


class PureAhoMatcher(Matcher):
    """纯 Python Aho-Corasick 多模式匹配器。"""

    backend = "pure-python"

    def __init__(self) -> None:
        self._root = _Node()
        self._keywords = 0

    # ------------------------------------------------ 构建

    def build(self, index: KeywordIndex) -> None:
        self._root = _Node()
        self._keywords = 0

        # 1. 建 Trie
        for keyword, rules in index.items():
            if not keyword:
                continue
            node = self._root
            for ch in keyword:
                node = node.children.setdefault(ch, _Node())
            node.outputs.append((keyword, rules))
            self._keywords += 1

        # 2. BFS 构建失配指针
        queue: deque[_Node] = deque()
        for child in self._root.children.values():
            child.fail = self._root
            queue.append(child)

        while queue:
            node = queue.popleft()
            for ch, child in node.children.items():
                queue.append(child)
                # 沿失配链找到最长的真后缀节点
                fail = node.fail
                while fail is not None and ch not in fail.children:
                    fail = fail.fail
                child.fail = fail.children[ch] if fail and ch in fail.children else self._root
                # 合并失配链上的输出（路径压缩：一次命中即可输出全部后缀匹配）
                child.outputs = child.outputs + child.fail.outputs

    # ------------------------------------------------ 扫描

    def iter_hits(self, text: str) -> Iterable[Hit]:
        node = self._root
        for pos, ch in enumerate(text):
            while node is not self._root and ch not in node.children:
                node = node.fail or self._root
            node = node.children.get(ch, self._root)
            for keyword, rules in node.outputs:
                start = pos - len(keyword) + 1
                for rule in rules:
                    yield (start, pos + 1, keyword, rule)

    def keyword_count(self) -> int:
        return self._keywords
