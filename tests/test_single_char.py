#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 回归测试：单字 / 极短关键词误杀防护（针对 v3 新内核）。

背景（v2.4 及以前的事故）
------------------------
`rules/ad_law.json` 第一条是 `{"keyword": "最"}`，导致正常词组被误判：

    输入：最近很多人问我移民的事，这款产品最好用
    输出：命中 ["最", "最好"]，且修改后文案变成
          "近很多人问我移民的事，这款产品良好用"   ← 原文被改坏

在商品化场景下这是**事故级** bug：用户信任工具给出的"修改后文案"，
直接复制发布，结果发出去的是被改坏的句子。

三道防线（均在 guardian/context_guard.py + guardian/engine.py）：
1. 上下文排除 —— "最近/最后/最终"等正常词组内的命中被豁免
2. 短词降级 —— 单字极限词降级为 `low`（仅提示，不计分、禁止改写）
3. 改写安全网 —— 短词一律禁止自动改写原文

本文件直接测试新内核（engine / context_guard），并保留一条经 shim 的
"修改后文案不破坏原文"用户级回归。
"""

import pytest

from guardian.engine import DetectionEngine
from guardian.schema import DetectionOptions
from guardian.detector import ComplianceDetector  # 兼容 shim（用户级回归用）


@pytest.fixture(scope="module")
def engine():
    return DetectionEngine()


def detect(engine, text, platform="all", account="non_blue_v", variants=True):
    opts = DetectionOptions(platform=platform, account_type=account,
                            use_variants=variants)
    return engine.detect_text(text, opts)


# ---------------------------------------------------------------- 防线 1
# 上下文排除：正常词组不该被报


@pytest.mark.parametrize(
    "text,exempt_word",
    [
        ("最近很多人问我移民的事", "最近"),
        ("最后提醒一次，名额有限", "最后"),
        ("最终结果以官方通知为准", "最终"),
        ("最初的方案已经调整", "最初"),
        ("最迟下周三给你答复", "最迟"),
        ("最早也要三个月", "最早"),
    ],
)
def test_normal_phrases_not_flagged(engine, text, exempt_word):
    """正常时间/顺序词组里的"最"不应产生违规项。"""
    r = detect(engine, text)
    matched = [f.matched_text for f in r.findings]
    assert "最" not in matched, f"'{exempt_word}' 里的'最'被误判为违规：{matched}"


def test_original_text_not_destroyed(engine):
    """核心回归：safe_text 绝不能把'最近'改成'近'。"""
    text = "最近很多人问我移民的事，这款产品最好用"
    r = detect(engine, text)
    safe = r.safe_text
    assert safe.startswith("最近"), f"'最近'被改坏了，safe_text 为：{safe!r}"
    assert "很多人问我移民的事" in safe, f"原文被改坏：{safe!r}"


def test_exempt_word_survives_in_safe_text(engine):
    """豁免词组在 safe_text 中必须原样保留。"""
    text = "最后提醒一次，我们的服务是最好的"
    r = detect(engine, text)
    assert "最后" in r.safe_text, r.safe_text


# ---------------------------------------------------------------- 防线 2 & 3
# 短词降级 + 禁止自动改写


def test_short_keyword_downgraded_to_low(engine):
    """单字极限词若真命中，严重度应降级为 low（仅提示）。"""
    text = "这个价格之最"
    r = detect(engine, text)
    hits = [f for f in r.findings if f.matched_text == "最"]
    assert hits, "单字'最'未被检出"
    for h in hits:
        assert h.severity == "low", f"单字'最'未降级：{h.severity}"
        assert h.allow_auto_replace is False, "单字'最'不应允许自动改写"


def test_short_keyword_never_auto_replaced():
    """短词绝不能被自动改写（防止原文被改坏）。"""
    from guardian.context_guard import should_auto_replace, is_short_keyword

    short = {"keyword": "最", "category": "极限词", "severity": "violation"}
    assert is_short_keyword(short) is True
    assert should_auto_replace(short) is False, "短词必须禁止自动改写"

    # 正常长度的极限词不受影响
    normal = {"keyword": "最好", "category": "极限词", "severity": "violation"}
    assert is_short_keyword(normal) is False
    assert should_auto_replace(normal) is True


def test_industry_short_words_not_downgraded():
    """行业红线里的短词（如'包过'）不能被降级 —— 只降级极限词类目。"""
    from guardian.context_guard import is_short_keyword

    industry = {"keyword": "包过", "category": "虚假承诺", "severity": "violation"}
    assert is_short_keyword(industry) is False, "行业红线短词不应被降级"


# ---------------------------------------------------------------- 反向验证
# 确保修复没有造成"漏检"（矫枉过正）


@pytest.mark.parametrize(
    "text,expected",
    [
        ("这是全网最好的移民服务", "最好"),
        ("独家首创的唯一选择", "独家"),
        ("全网最低价，最快三天获批", "最快"),
        ("我们的成功率百分之百，保证获批", "百分之百"),
    ],
)
def test_real_violations_still_detected(engine, text, expected):
    """真·极限词必须仍然被检出（防止过度豁免导致漏检）。"""
    r = detect(engine, text)
    matched = [f.matched_text for f in r.findings]
    assert expected in matched, f"真违规词'{expected}'被漏检，实际命中：{matched}"


def test_two_char_limit_words_keep_violation_severity(engine):
    """2 字真极限词（独家/唯一）不能降级 —— 只有单字才降级。"""
    r = detect(engine, "这是独家首创的唯一选择")
    sev = {f.matched_text: f.severity for f in r.findings}
    assert sev.get("独家") != "low", f"'独家'被错误降级：{sev}"
    assert sev.get("唯一") != "low", f"'唯一'被错误降级：{sev}"


# ---------------------------------------------------------------- 守卫单元测试


def test_context_guard_exempt_detection():
    """直接验证上下文排除逻辑。"""
    from guardian.context_guard import (
        find_exempt_spans,
        is_context_exempt,
        EXEMPT_PHRASES,
    )

    text = "最近很多人问我"
    spans = find_exempt_spans(text)
    assert spans, "未扫描到豁免词组"
    # "最" 命中 (0,1)，应被 "最近" (0,2) 覆盖
    assert is_context_exempt(text, 0, 1, spans) == "最近"


def test_context_guard_no_false_exempt():
    """不在豁免词组内的命中不应被豁免（防止漏检）。"""
    from guardian.context_guard import is_context_exempt

    text = "这是最好的产品"
    # "最" 在 (2,3)，"最好" 是词组但不在豁免表内
    assert is_context_exempt(text, 2, 3) is None


def test_exempt_table_conservative():
    """豁免表必须保守：不得包含明确的极限词。"""
    from guardian.context_guard import EXEMPT_PHRASES

    forbidden = ["最新", "最好", "最佳", "最优", "最强", "最大", "最高", "最低", "最快"]
    all_phrases = [p for phrases in EXEMPT_PHRASES.values() for p in phrases]
    for bad in forbidden:
        assert bad not in all_phrases, f"豁免表错误地包含了真极限词：{bad}"


# ---------------------------------------------------------------- 用户级（经 shim）


def test_shim_modified_text_preserves_original():
    """经兼容 shim 调用，修改后文案不能破坏原文（用户直接可见的回归）。"""
    det = ComplianceDetector.get_instance()
    text = "最近很多人问我移民的事，这款产品最好用"
    r = det.detect(text, "all", "non_blue_v")
    assert r["modified_text"].startswith("最近"), r["modified_text"]
