#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼音 / 首字母变体检测（可选增强）。

原理
----
把文本和关键词都转成拼音串，在拼音空间里做匹配：

    原文本:  "加微信"  → 拼音 "jiaweixin"
    关键词:  "微信"    → 拼音 "weixin"
    命中:    "weixin" 落在 "jiaweixin" 中 → 变体命中

首字母同理："微信" → "wx"。

依赖 pypinyin；若环境未安装，``romanize`` 返回空、``pinyin_index`` 返回空，
引擎层据此跳过这一步（纯规则 + 归一化变体照常工作）。

注意
----
拼音命中的可靠性低于字面/谐音命中，因此引擎会把这类命中标为
``match_type="variant"``、``confidence=0.8``，并默认**不**自动改写，
只提示人工确认。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from guardian.matcher.base import KeywordIndex
from guardian.schema import Rule

_PYPINYIN = None


def _lazy_pinyin():
    """懒加载 pypinyin，返回 lazy_pinyin 函数或 None。"""
    global _PYPINYIN
    if _PYPINYIN is not None:
        return _PYPINYIN
    try:
        from pypinyin import lazy_pinyin as _lp

        _PYPINYIN = _lp
        return _PYPINYIN
    except Exception:  # pragma: no cover
        return None


@dataclass
class RomanizedText:
    """拼音化结果。

    Attributes:
        text: 连续拼音串（如 "jiaweixin"）
        idx:  ``idx[j]`` = 该拼音字母对应的**归一化文本字符下标**
        normalized: 归一化文本（用于二级映射回原文）
    """

    text: str
    idx: list[int] = field(default_factory=list)
    normalized: str = ""

    def mapped_original(self, norm_index_map: list[int], s: int, e: int) -> tuple[int, int]:
        """把拼音坐标 [s,e) 经归一化映射回原文 [orig_s, orig_e)。"""
        if not self.idx:
            return (s, e)
        o_s = norm_index_map[self.idx[s]]
        o_e = norm_index_map[self.idx[min(e, len(self.idx)) - 1]] + 1
        return (o_s, o_e)

    def char_span(self, s: int, e: int):
        """若拼音命中 [s, e) 落在**整字边界**上，返回归一化字符跨度 [n_s, n_e)；否则 None。

        这是拼音变体检测防误报的核心闸门：拼音字母与汉字并非 1:1 对应，
        一个 2 字母拼音片段（如 "zh"）会落进「这」(zhe) 的拼音**内部**，
        直接映射会得到单字级误报。只有命中首尾都对齐到汉字边界，才算有效。
        """
        if not self.idx or s < 0 or e > len(self.idx) or s >= e:
            return None
        # 起点必须是某字的首字母（上一字母属于另一个字）
        if s > 0 and self.idx[s - 1] == self.idx[s]:
            return None
        # 终点必须是某字的末字母（下一字母属于另一个字）
        if e < len(self.idx) and self.idx[e - 1] == self.idx[e]:
            return None
        n_s = self.idx[s]
        n_e = self.idx[e - 1] + 1
        return (n_s, n_e)


def romanize(normalized_text: str) -> RomanizedText:
    """把归一化文本转成连续拼音串，并保留到归一化文本的索引。"""
    lp = _lazy_pinyin()
    if lp is None:
        return RomanizedText(text="", idx=[], normalized=normalized_text)
    parts = lp(normalized_text, strict=False, errors="default")
    out: list[str] = []
    idx: list[int] = []
    for i, p in enumerate(parts):
        for ch in p:  # 每个拼音字母都指回原（归一化）字符 i
            out.append(ch)
            idx.append(i)
    return RomanizedText(text="".join(out), idx=idx, normalized=normalized_text)


def _is_all_cjk(s: str) -> bool:
    """判断字符串是否**全部由汉字组成**（不含数字/字母/标点/空格）。"""
    return bool(s) and all("\u4e00" <= ch <= "\u9fff" for ch in s)


def pinyin_index(rules: list[Rule]) -> KeywordIndex:
    """从规则关键词生成**全拼**索引（变体抗规避的可选增强）。

    设计取舍：
    * **只收纯汉字关键词**：含数字/符号/字母的关键词（如 "100%有效"）跳过。
      原因：``lazy_pinyin`` 会让非汉字原样透传，导致 "100%有效" →
      "100%youxiao"，其中 "100" 段会在拼音空间里被当成命中，回映射后
      产出 "100" 这种伪变体（实测踩过）。
    * 只保留**全拼**（如 "微信" → "weixin"），**丢弃首字母**。
      原因：2 字母首字母（"wx"/"zh"/"sh"）在连写拼音串里碰撞极多——
      例如 "zh" 会落进「这」(zhe) 的拼音内部，造成单字级误报。
      全拼长度 ≥ 4，且配合引擎层的「字符边界对齐」校验后可靠性足够。
    * 单字关键词（len<2）跳过：拼音噪声远大于收益。
    * 多音字由 pypinyin 默认处理，够用；不追求 100% 准确。

    注意：拼音命中天生比字面/谐音命中不可靠，引擎层会把它标为
    ``match_type="variant"``、``confidence=0.7``，且**绝不**自动改写，
    只作为人工确认提示。
    """
    lp = _lazy_pinyin()
    if lp is None:
        return {}
    index: KeywordIndex = {}
    for rule in rules:
        kw = rule.keyword.strip()
        if len(kw) < 2:  # 单字拼音变体噪声太大，跳过
            continue
        if not _is_all_cjk(kw):  # 混合关键词（含数字/符号）交给字面通道
            continue
        parts = lp(kw, strict=False, errors="default")
        if not parts:
            continue
        full = "".join(parts)
        if not full:
            continue
        index.setdefault(full, []).append(rule)
    return index
