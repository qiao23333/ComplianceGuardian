#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反误报 / 反漏检回归门禁。

为什么单独建一个文件
--------------------
合规工具的成败不看"规则条数"，只看两个数字：误报率与漏检率。
而这两个数字极容易被后续改动悄悄弄坏 —— 加一条词可能救回一个漏检，
同时引入三个误报；改一条语境规则可能压掉误报，同时放走红线。

所以这里用**语料级断言**把两条底线钉死：

1. 误报率 ≤ 5%（合规文案被误判 → 运营直接弃用工具）；
2. 漏检率为 0%（违规文案连提示都没有 → 工具没有价值）。

同时补充两组"结构性"用例，锁住容易退化的两类具体行为：

* 序数表达必须豁免（``第一步 / 第二阶段 / 第3步 / 首个工作日``）；
* 真极限词必须报出（``销量第一 / 行业第一 / 首家 / 首创 / 国家级``）。

这两组互为对照：只有"该豁免的豁免、该报的报"同时成立，
才说明语境守卫是在做判断，而不是在无脑放宽或收紧。
"""

from __future__ import annotations

import pytest

from guardian.detector import ComplianceDetector
from tests.corpus import CLEAN, RISKY, false_negative_rate, false_positive_rate


@pytest.fixture(scope="module")
def detector():
    return ComplianceDetector.get_instance()


# ============================================================ 语料级底线


def test_false_positive_rate_under_5_percent():
    """合规语料误报率必须 ≤ 5%。

    历史对照：语境守卫只覆盖固定短语时，这个数字是 35.5%
    （31 条里 11 条被误报，全部是"第一步 / 第二阶段 / 第2次"这类序数表达）。
    """
    rate, bad = false_positive_rate()
    assert rate <= 0.05, "误报率超标：\n" + "\n".join(bad)


def test_false_negative_rate_is_zero():
    """违规语料必须全部被提示到（不允许连提示都没有）。"""
    rate, missed = false_negative_rate()
    assert rate == 0.0, "存在漏检：\n" + "\n".join(missed)


def test_corpus_sizes_are_meaningful():
    """语料规模守卫：防止有人为了"让测试过"而删语料。"""
    assert len(CLEAN) >= 25
    assert len(RISKY) >= 25


# ============================================================ 结构性用例

#: 必须被判为**合规**的序数表达 —— 中文里最普通的流程/结构描述
ORDINAL_SAFE = [
    "第一步先准备护照，第二步递交EOI",
    "第一阶段评估资质，第二阶段准备材料",
    "第1步、第2步、第3步我都列好了",
    "第3点是语言成绩有效期",
    "第一篇讲签证类型，第二篇讲材料",
    "我排在第1位等待补料通知",
    "首个工作日收到的回复会统一处理",
    "这是我第一次办签证",
    "最近很多人问我482签证",
    "最后提醒一次：材料要真实",
]

#: 必须被判为**违规**的绝对化/排名宣称 —— 与上面的语料只差一个词
EXTREME_RISKY = [
    "行业第一的移民机构",
    "销量第一的咨询服务",
    "全网销量第一的品牌",
    "我们是首家获批的机构",
    "本公司首创全流程托管",
    "全网最低价的移民服务",
    "国家级资质认证",
    "唯一官方授权渠道",
    "史上最快的审批通道",
    "这款产品效果最好",
]


@pytest.mark.parametrize("text", ORDINAL_SAFE)
def test_ordinal_expressions_are_exempt(detector, text):
    """序数/结构表达不得被判违规（误报会直接毁掉工具可用性）。"""
    result = detector.detect(text, "xiaohongshu", "blue_v")
    hits = [v["keyword"] for v in result["violations"]]
    assert not hits, f"序数表达被误报：{text} → {hits}"


@pytest.mark.parametrize("text", EXTREME_RISKY)
def test_real_extremes_still_reported(detector, text):
    """真·绝对化用语必须继续报出（豁免不能过度，否则变漏检）。"""
    result = detector.detect(text, "xiaohongshu", "blue_v")
    hits = [v["keyword"] for v in result["violations"]]
    assert hits, f"极限词漏检：{text}"


# ============================================================ 死规则复活


def test_placeholder_rules_are_gone():
    """词库里不得再有含 X 占位符的死规则（永不命中的"注水"规则）。"""
    from scripts.harden_rulebank import find_dead_rules

    dead = find_dead_rules()
    assert not dead, "存在死规则：" + str(dead)


@pytest.mark.parametrize(
    "text,expect",
    [
        ("保证3个月出签，否则赔偿", "保证3个月出签"),
        ("保证30天内获批", "保证30天内获批"),
        ("保证两周拿到PR", "保证两周拿到"),
        ("现成雇主资源随便挑", "现成雇主"),
        ("最后一波名额，错过再等一年", "最后一波"),
    ],
)
def test_previously_missed_expressions_now_detected(detector, text, expect):
    """原先因"死规则 / 词库缺失"而漏掉的行业高频违规表达，现已能命中。"""
    result = detector.detect(text, "xiaohongshu", "blue_v")
    hits = [v["keyword"] for v in result["violations"] + result.get("warnings_list", [])]
    s = result["summary"]
    assert s["violations"] + s["warnings"] > 0, f"仍未命中：{text}"
    assert any(expect in h for h in hits) or s["violations"] > 0, f"命中但非预期：{text} → {hits}"


# ============================================================ 挂靠类：宽严成对


#: (文案, 说明) —— 广告语态，必须命中
GUAKAO_RISKY = [
    ("无需英语无需工作经验，挂靠办理，快速拿PR", "挂靠 + 结果动词（不接'雇主'）"),
    ("支持挂靠服务，随时递交申请", "挂靠 + 服务"),
    ("现成雇主资源，挂靠即可递交，内部名额有限", "挂靠 + 即可 + 递交"),
    ("我司可挂靠公司，随时安排", "已有字面规则仍要生效"),
]

#: (文案, 说明) —— 警示 / 无关语境，必须不命中
GUAKAO_CLEAN = [
    ("警惕挂靠骗局，签证申请必须基于真实雇佣关系", "风险提示"),
    ("挂靠担保资格是违法的，我们会明确拒绝这类要求", "合规声明"),
    ("社保挂靠政策解读，本文讲的是养老金计算", "无关语境"),
]


@pytest.mark.parametrize("text,reason", GUAKAO_RISKY)
def test_guakao_advertising_forms_are_caught(detector, text, reason):
    """广告语态的'挂靠'必须被抓到。

    历史缺口：词库里只有 ``挂靠雇主 / 挂靠公司`` 两个字面词组，而字面匹配
    要求"雇主/公司"紧跟在"挂靠"后面 —— 写成"挂靠即可递交""挂靠办理"
    就整条绕过去了，这恰恰是最常见的广告写法。
    """
    result = detector.detect(text, "xiaohongshu", "non_blue_v")
    assert result["summary"]["violations"] > 0, f"漏检（{reason}）：{text}"


@pytest.mark.parametrize("text,reason", GUAKAO_CLEAN)
def test_guakao_warning_context_is_not_flagged(detector, text, reason):
    """警示语境的'挂靠'不能被判违规。

    这是补规则时的**收紧项**：如果偷懒直接收「挂靠」二字，下面这些
    "挂靠是违法的、请警惕"的内容会被误报 —— 而写这类内容的人恰恰是
    最守规矩的那批运营。宽一条必须同时收紧一条，否则就是把误报
    从漏检手里换回来。
    """
    result = detector.detect(text, "xiaohongshu", "non_blue_v")
    hits = [v["matched_text"] for v in result["violations"]]
    assert result["summary"]["violations"] == 0, f"误报（{reason}）：{text} → {hits}"
