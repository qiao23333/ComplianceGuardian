#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 回归测试：单字 / 极短关键词误杀防护。

背景（v2.4 及以前的事故）
------------------------
`rules/ad_law.json` 第一条是 `{"keyword": "最"}`，导致正常词组被误判：

    输入：最近很多人问我移民的事，这款产品最好用
    输出：命中 ["最", "最好"]，且修改后文案变成
          "近很多人问我移民的事，这款产品良好用"   ← 原文被改坏

在商品化场景下这是**事故级** bug：用户信任工具给出的"修改后文案"，
直接复制发布，结果发出去的是被改坏的句子。

本测试锁住三道防线：
1. 上下文排除 —— "最近/最后/最终"等正常词组内的命中被豁免
2. 短词降级 —— ≤2 字的极限词降级为 `low`（仅提示，不计分）
3. 改写安全网 —— 短词一律禁止自动改写原文
"""

import pytest

from guardian.detector import ComplianceDetector


@pytest.fixture(scope="module")
def detector():
    """全局共享一个 detector 实例（词库加载较慢）。"""
    return ComplianceDetector.get_instance("rules")


def hit_keywords(result):
    return [v["keyword"] for v in result["violations"]]


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
def test_normal_phrases_not_flagged(detector, text, exempt_word):
    """正常时间/顺序词组里的"最"不应产生违规项。"""
    result = detector.detect(text, "all", "non_blue_v")
    keywords = hit_keywords(result)
    assert "最" not in keywords, f"'{exempt_word}' 里的'最'被误判为违规：{keywords}"


def test_original_text_not_destroyed(detector):
    """核心回归：修改后文案绝不能把'最近'改成'近'。"""
    text = "最近很多人问我移民的事，这款产品最好用"
    result = detector.detect(text, "all", "non_blue_v")

    modified = result["modified_text"]
    # "最近"必须完整保留在句首（这是本 P0 的核心断言）
    # 事故版本会以"近很多人…"开头 —— "最"字被删掉了
    assert modified.startswith("最近"), f"'最近'被改坏了，修改后文案为：{modified!r}"
    assert not modified.startswith("近很"), f"原文被改坏：{modified!r}"
    # 只允许改动"最好"这一处，其余部分必须与原文一致
    assert "很多人问我移民的事" in modified, f"原文被改坏：{modified!r}"


def test_exempt_word_survives_in_modified_text(detector):
    """豁免词组在修改后文案中必须原样保留。"""
    text = "最后提醒一次，我们的服务是最好的"
    result = detector.detect(text, "all", "non_blue_v")
    assert "最后" in result["modified_text"], result["modified_text"]


# ---------------------------------------------------------------- 防线 2 & 3
# 短词降级 + 禁止自动改写


def test_short_keyword_downgraded_to_low(detector):
    """单字极限词若真命中，严重度应降级为 low（仅提示）。"""
    # 构造一个"最"字确实独立出现、且不在豁免词组内的场景
    text = "这个价格之最"
    result = detector.detect(text, "all", "non_blue_v")
    for v in result["violations"]:
        if v["keyword"] == "最":
            assert v["severity"] == "low", f"单字'最'未降级：{v['severity']}"
            assert v.get("allow_auto_replace") is False, "单字'最'不应允许自动改写"


def test_short_keyword_never_auto_replaced(detector):
    """短词绝不能被自动改写（防止原文被改坏）。"""
    from guardian.context_guard import should_auto_replace, is_short_keyword

    short = {"keyword": "最", "category": "极限词", "severity": "violation"}
    assert is_short_keyword(short) is True
    assert should_auto_replace(short) is False, "短词必须禁止自动改写"

    # 正常长度的极限词不受影响
    normal = {"keyword": "最好", "category": "极限词", "severity": "violation"}
    assert is_short_keyword(normal) is False
    assert should_auto_replace(normal) is True


def test_industry_short_words_not_downgraded(detector):
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
        ("我们的成功率百分之百，保证获批", "保证获批"),
    ],
)
def test_real_violations_still_detected(detector, text, expected):
    """真·极限词与行业红线必须仍然被检出（防止过度豁免导致漏检）。"""
    result = detector.detect(text, "all", "non_blue_v")
    keywords = hit_keywords(result)
    assert expected in keywords, f"真违规词'{expected}'被漏检，实际命中：{keywords}"


def test_two_char_limit_words_keep_violation_severity(detector):
    """2 字真极限词（最好/唯一/顶级）不能降级 —— 只有单字才降级。"""
    result = detector.detect("这是独家首创的唯一选择", "all", "non_blue_v")
    severities = {v["keyword"]: v["severity"] for v in result["violations"]}
    assert severities.get("独家") != "low", f"'独家'被错误降级：{severities}"


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
