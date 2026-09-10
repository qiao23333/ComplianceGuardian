#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多模式串匹配器层。

此层只负责"找命中区间"，不关心规则语义、不做过滤、不改写。
* ``base``：抽象接口 + 类型
* ``aho``：pyahocorasick 后端（快）
* ``pure``：纯 Python 降级（零依赖，测试确定性参考实现）
* ``factory``：自动选后端
"""

from guardian.matcher.aho import AHO_AVAILABLE, AhoMatcher
from guardian.matcher.base import Hit, KeywordIndex, Matcher
from guardian.matcher.factory import backend_name, create_matcher
from guardian.matcher.pure import PureAhoMatcher

__all__ = [
    "AHO_AVAILABLE",
    "AhoMatcher",
    "Hit",
    "KeywordIndex",
    "Matcher",
    "PureAhoMatcher",
    "backend_name",
    "create_matcher",
]
