#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""匹配器工厂：自动选择最快可用的后端。

优先级：pyahocorasick(C 扩展) > 纯 Python 实现。
返回对象会带上 ``backend`` 属性，便于写进检测结果的 meta 字段做诊断。
"""

from __future__ import annotations

from guardian.matcher.aho import AHO_AVAILABLE, AhoMatcher
from guardian.matcher.base import KeywordIndex, Matcher
from guardian.matcher.pure import PureAhoMatcher


def create_matcher(index: KeywordIndex | None = None) -> Matcher:
    """创建并（可选地）构建匹配器。

    * 优先 pyahocorasick；不可用则降级到纯 Python 实现。
    * 传入 ``index`` 时直接构建好，调用方无需关心后端差异。
    """
    matcher: Matcher
    if AHO_AVAILABLE:
        matcher = AhoMatcher()
    else:
        matcher = PureAhoMatcher()
    if index is not None:
        matcher.build(index)
    return matcher


def backend_name() -> str:
    """当前环境实际能用的后端名（诊断用）。"""
    return "pyahocorasick" if AHO_AVAILABLE else "pure-python"
