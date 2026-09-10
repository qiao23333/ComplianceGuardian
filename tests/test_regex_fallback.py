#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正则兜底规则 与 自动改写安全网 的回归测试。

背景
----
v3 把旧检测器里硬编码的 12 条正则（"最X""极X""第X""国家级"…）迁移成了
``rules/regex_patterns.json``，由引擎作为**兜底网**参与检测。这带来三个
必须锁定的行为：

1. **正则不得抢掉字面规则**：同区间既有精确 keyword 又有正则命中时，
   应保留 keyword（它带 suggestion / replacements），否则自动改写会失效。
2. **无显式替换词绝不改写**：正则规则的 suggestion 常写"删除'最'字…"，
   早期启发式会据此把命中**整段删掉**（"最好"→"" → "这是的服务"），
   必须改为"只高亮、不改写"。
3. **混合关键词不产生拼音伪变体**："100%有效" 这类含数字的关键词若进
   拼音索引，会被拆出 "100" 造成伪命中。
"""

from __future__ import annotations

import pytest

from guardian.engine import DetectionEngine
from guardian.schema import DetectionOptions


@pytest.fixture(scope="module")
def engine():
    return DetectionEngine()


def _detect(engine, text, **kw):
    return engine.detect_text(text, DetectionOptions(**kw))


# ---------------------------------------------------------------- 正则兜底


def test_regex_catches_uncovered_combo(engine):
    """词库未覆盖的组合由正则兜底捕获（"第3名" → "第3"）。"""
    r = _detect(engine, "销量第3名")
    hits = {f.matched_text: f.match_type for f in r.findings}
    assert "第3" in hits, f"正则兜底未生效：{hits}"
    assert hits["第3"] == "regex"


def test_keyword_wins_over_regex_same_region(engine):
    """同区间的精确 keyword 优先于正则（保留 curated 元数据）。"""
    r = _detect(engine, "这是全网最好的移民服务")
    # 应当报 keyword "最好"（带替换词），而不是正则"全网最好"
    best = [f for f in r.findings if f.matched_text == "最好"]
    assert best, f"未命中 keyword '最好'：{[(f.matched_text, f.match_type) for f in r.findings]}"
    assert best[0].match_type == "keyword"


def test_safe_text_uses_curated_replacement(engine):
    """自动改写用 curated 替换词：'全网最好' → '全网良好'（不残留正则空改）。"""
    r = _detect(engine, "这是全网最好的移民服务", auto_replace=True)
    assert r.safe_text == "这是全网良好的移民服务", r.safe_text


# ---------------------------------------------------------------- 改写安全网


def test_no_replacement_means_no_rewrite(engine):
    """正则规则无显式替换词时（suggestion='删除排名类表述'），
    自动改写必须**保持原文**，绝不能因"删除"字样把命中改成空串。"""
    r = _detect(engine, "销量第3名", auto_replace=True)
    # 兜底正则 "第\\d+" 没有 replacements → 不改写
    assert r.safe_text == "销量第3名", r.safe_text


def test_regex_hit_never_deletes_text(engine):
    """回归：'这是最好的服务' 曾被改成 '这是的服务'（删了'最好'）。"""
    r = _detect(engine, "这是最好的服务", auto_replace=True)
    assert r.safe_text == "这是良好的服务", r.safe_text
    assert "这是的服务" not in r.safe_text


def test_auto_replace_off_by_default(engine):
    r = _detect(engine, "这是最好的服务")
    assert r.safe_text == "这是最好的服务"


# ---------------------------------------------------------------- 拼音伪变体


def test_mixed_keyword_no_pinyin_variant(engine):
    """含数字的关键词（"100%有效"）不得被拼音通道拆出伪变体 "100"。"""
    r = _detect(engine, "100%有效")
    kws = {f.matched_text for f in r.findings}
    assert "100" not in kws, f"出现拼音伪变体：{kws}"
    assert "100%有效" in kws, f"字面应命中完整关键词：{kws}"
