#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""移民 / 留学行业语料回归测试（正样本 + 负样本）。

为什么单独一个文件
------------------
通用测试只覆盖引擎机制，**无法发现"词库覆盖缺口"**——那是业务知识问题。
本文件用真实业务语料做双向断言：

* 正样本：行业里真正会被封号/限流的写法，必须检出；
* 负样本：正常业务表述与日常用语，**必须不报**（误报治理）。

任何一条负样本变红，都意味着工具开始"狼来了"，用户会关掉它——
对合规工具来说，误报比漏检更致命。

语料来源：2026-09 澳洲移民 / 留学内容投放的真实高频表达 +
《广告法》第九条绝对化用语 + 小红书/抖音社区公约导流条款。
"""

from __future__ import annotations

import pytest

from guardian.engine import DetectionEngine
from guardian.schema import DetectionOptions

#: 本站涉及的全部行业包
INDUSTRIES = ["immigration", "study_abroad"]


@pytest.fixture(scope="module")
def engine() -> DetectionEngine:
    return DetectionEngine()


def detect(engine: DetectionEngine, text: str):
    return engine.detect_text(text, DetectionOptions(industries=INDUSTRIES))


def keywords(result) -> set[str]:
    return {f.matched_text for f in result.findings}


# ================================================================ 正样本

@pytest.mark.parametrize("text,expect", [
    # —— 虚假承诺（签证结果不可承诺）——
    ("保证获批，不通过全额退款", "保证获批"),
    ("百分百下签，零拒签记录", "百分百下签"),
    ("我们保证通过你的签证申请", "保证通过"),
    ("包获批，材料我们全包", "包获批"),
    ("稳获批，多年经验", "稳获批"),
    # —— 关系暗示 ——
    ("我们跟移民局有关系，好办事", "跟移民局有关系"),
    ("内部名额有限，先到先得", "内部名额"),
    ("有内部指标，你懂的", "内部指标"),
    ("这事得走后门才行", "走后门"),
    # —— 伪造材料（刑事风险）——
    ("我们可以帮你做假流水", "假流水"),
    ("假学历也能过职业评估", "假学历"),
    ("可以挂靠公司做雇主担保", "挂靠公司"),
    ("买工作拿PR，明码标价", "买工作"),
    # —— 绝对化价格 / 极限词 ——
    ("全澳最低价，不成功不收费", "全澳最低价"),
    ("我们是澳洲第一的移民机构", "澳洲第一"),
    ("澳洲唯一官方合作渠道", "澳洲唯一"),
    # —— 原有规则仍然有效（防回归）——
    ("澳洲雇主担保移民，保证获批", "保证获批"),
    ("内部渠道，包你下签", "内部渠道"),
    ("零拒签率不是梦", "零拒签"),
])
def test_immigration_violations_detected(engine, text, expect):
    result = detect(engine, text)
    assert result.findings, f"未检出任何违规：{text!r}"
    assert any(expect in f.matched_text or f.matched_text in expect
               for f in result.findings), (
        f"期望命中 {expect!r}，实际命中 {keywords(result)}"
    )


@pytest.mark.parametrize("text,expect", [
    ("名校保录，一步进G5", "名校保录"),
    ("保录取，不成功全额退款", "保录取"),
    ("包offer，让名校找你", "包offer"),
    ("代考包过，安全可靠", "代考"),
    ("假成绩单也能申请", "假成绩单"),
    ("代写论文不会被查", "代写"),
    ("内部招生名额，仅剩两个", "内部招生名额"),
])
def test_study_abroad_violations_detected(engine, text, expect):
    result = detect(engine, text)
    assert result.findings, f"未检出任何违规：{text!r}"
    assert any(expect in f.matched_text or f.matched_text in expect
               for f in result.findings), (
        f"期望命中 {expect!r}，实际命中 {keywords(result)}"
    )


@pytest.mark.parametrize("text,expect", [
    ("加我微信，拉你进群", "加我微信"),
    ("加个微信详聊", "加个微信"),
    ("加卫星，我发你资料", "加卫星"),
    ("卫星号在简介里", "卫星号"),
    ("需要咨询的私聊我", "私聊我"),
    ("站外联系更方便", "站外联系"),
])
def test_diversion_detected(engine, text, expect):
    result = detect(engine, text)
    assert result.findings, f"未检出任何违规：{text!r}"
    assert any(expect in f.matched_text or f.matched_text in expect
               for f in result.findings), (
        f"期望命中 {expect!r}，实际命中 {keywords(result)}"
    )


# ---------------------------------------------------------------- 谐音抗规避链
#
# 这是本工具最容易被高估的能力，必须有端到端语料兜住：
# 只有词库里有 `微信` 这条规则，谐音表里的 `薇/威/溦 → 微` 才有落点。

@pytest.mark.parametrize("text", [
    "加我薇信",
    "加我威信",
    "加我溦信",
    "威信联系我",
])
def test_homophone_diversion_chain_works(engine, text):
    """谐音写法必须被检出——否则"抗规避"只是宣传语。"""
    result = detect(engine, text)
    assert result.findings, f"谐音规避未检出：{text!r}"
    assert any(f.match_type == "variant" for f in result.findings), (
        f"应标记为变体命中，实际：{[(f.matched_text, f.match_type) for f in result.findings]}"
    )


# ================================================================ 负样本

@pytest.mark.parametrize("text", [
    # —— 正常业务表述（这些词是行业常用语，绝不能报）——
    "我们提供澳洲雇主担保移民服务",
    "专注澳洲技术移民与投资移民",
    "帮助学生申请澳洲八大名校",
    "签证材料准备与递交服务",
    "我们协助客户完成职业评估",
    "提供留学规划与文书指导",
    "移民局最新政策解读",
    "澳洲移民配额与职业清单更新",
    # —— 日常表达（曾经的裸关键词误报源）——
    "这个和那个有关系吗",
    "做事情要一步到位",
    "他被保送去了清华",
    "这个方案直签合同",
    "我把文件包送到你家",
    # —— 微信的正常搭配（context_excludes 生效）——
    "微信支付很方便",
    "关注我们的微信公众号",
    "微信读书上有很多好书",
    "微信视频号直播中",
    # —— 关注我：小红书鼓励的正常 CTA ——
    "喜欢的话记得关注我哦",
    "关注我不迷路",
])
def test_normal_text_produces_no_violation(engine, text):
    """正常文案必须零命中——误报会让用户直接卸载工具。"""
    result = detect(engine, text)
    assert not result.findings, (
        f"误报！{text!r} -> {[(f.matched_text, f.severity) for f in result.findings]}"
    )


# ---------------------------------------------------------------- 结构性断言

def test_bare_business_words_not_in_rulebank(engine):
    """裸业务词不得入库（否则整个工具不可用）。"""
    kws = {r.keyword for r in engine.bank.all}
    for word in ("移民", "签证", "PR", "绿卡", "留学", "雇主担保", "工签"):
        assert word not in kws, f"裸业务词 {word!r} 不应作为关键词"


def test_broken_broad_keywords_removed(engine):
    """已确认的高危误报词必须已从词库移除。"""
    kws = {r.keyword for r in engine.bank.all}
    for word in ("有关系", "一步到位", "直签", "保送", "包送", "关注我"):
        assert word not in kws, f"高危误报词 {word!r} 仍在词库"


def test_wechat_rule_has_context_excludes(engine):
    """`微信` 规则必须带豁免搭配，否则日常表述会被误杀。"""
    rules = [r for r in engine.bank.all if r.keyword == "微信"]
    assert rules, "词库缺少 `微信` 规则（谐音链需要它作为落点）"
    assert all(r.context_excludes for r in rules), "`微信` 规则未配置 context_excludes"


def test_study_abroad_pack_loads(engine):
    """留学包应可被行业过滤命中（可插拔生态）。"""
    from guardian.rulebank import RuleBank
    bank = RuleBank()
    assert any(r.industry == "study_abroad" for r in bank.all), "留学行业包未加载"
    assert len([r for r in bank.all if r.industry == "study_abroad"]) >= 30
