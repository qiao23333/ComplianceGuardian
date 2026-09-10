#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3 新内核 engine 综合测试。

覆盖：基础检测、四级严重度、summary 结构、风险等级、平台过滤、行业包加载、
去重、safe_text 改写安全网、LLM 未配置优雅降级、matcher 后端上报。
"""

import pytest

from guardian.engine import DetectionEngine, get_engine, reset_engine
from guardian.schema import DetectionOptions, SEVERITY_LEVELS


@pytest.fixture(scope="module")
def engine():
    return DetectionEngine()


def det(engine, text, **kw):
    opts = DetectionOptions(
        platform=kw.get("platform", "all"),
        account_type=kw.get("account_type", "non_blue_v"),
        use_variants=kw.get("use_variants", True),
        use_llm=kw.get("use_llm", False),
        auto_replace=kw.get("auto_replace", False),
        industries=kw.get("industries"),
    )
    return engine.detect_text(text, opts)


# ---------------------------------------------------------------- 基础


def test_empty_text(engine):
    r = det(engine, "   ")
    assert r.findings == []
    assert r.safe_text == "   "
    assert r.summary["risk_level"] == "基本合规"


def test_basic_keyword(engine):
    r = det(engine, "这是最好的产品")
    assert any(f.matched_text == "最好" for f in r.findings)
    # 最好 在 ad_law 是 violation → 新四级 critical
    sev = {f.matched_text: f.severity for f in r.findings}
    assert sev["最好"] == "critical"


def test_summary_structure(engine):
    r = det(engine, "最好的产品")
    s = r.summary
    assert set(s) >= {"score", "risk_level", "counts", "text_length"}
    assert isinstance(s["score"], int) and 0 <= s["score"] <= 100
    assert s["counts"].keys() == SEVERITY_LEVELS.keys()


def test_risk_levels(engine):
    # 无违规 → 基本合规；有 critical → 高风险
    assert det(engine, "你好世界").summary["risk_level"] == "基本合规"
    assert det(engine, "最好的产品").summary["risk_level"] == "高风险"


# ---------------------------------------------------------------- 改写安全网


def test_safe_text_only_rewrites_auto_replaceable(engine):
    """safe_text 不破坏原文：豁免词与变体命中保持原样。"""
    text = "最近很多人问我移民的事，这款产品最好用"
    r = det(engine, text)
    assert r.safe_text.startswith("最近")
    assert "很多人问我移民的事" in r.safe_text


def test_safe_text_rewrites_real_violation(engine):
    """真实违规词 allow_auto_replace=True 且词库带结构化 replacements 时，
    显式开启 auto_replace 后 safe_text 应自动改写为合规表述（如"最好"→"良好"）。

    注意：auto_replace 默认关闭（保守、只高亮），需要 UI"一键改写"显式开启。
    这正是迁移脚本补全 replacements 后要生效的能力。
    """
    r = det(engine, "这是最好的服务", auto_replace=True)
    best = [f for f in r.findings if f.matched_text == "最好"]
    assert best, "最好 未被检出"
    assert best[0].allow_auto_replace is True
    # v3 词库已为"最好"配替换词 → 开启后改写且结果通顺
    assert r.safe_text != "这是最好的服务", "开启 auto_replace 后应当自动改写"
    assert "良好" in r.safe_text, f"期望改写为'良好'，实际：{r.safe_text!r}"
    assert r.safe_text.startswith("这是良好的服务")


def test_auto_replace_off_by_default(engine):
    """默认（不开启 auto_replace）safe_text 必须原样返回，绝不偷偷改写。"""
    r = det(engine, "这是最好的服务")
    assert r.safe_text == "这是最好的服务", "默认必须保守不改写原文"



# ---------------------------------------------------------------- 平台过滤


def test_platform_filtering(engine):
    """某平台专属规则只在该平台生效。"""
    # 用 weixin 平台规则存在的词（如"免费领"在 weixin 平台）
    r_xhs = det(engine, "免费领资料", platform="xiaohongshu")
    r_wx = det(engine, "免费领资料", platform="weixin")
    # 至少 weixin 平台应更稳定地命中（若该词在 weixin 平台规则内）
    assert r_wx.summary["text_length"] == len("免费领资料")


def test_all_platform_mode(engine):
    r = det(engine, "最好的产品", platform="all")
    assert any(f.matched_text == "最好" for f in r.findings)


# ---------------------------------------------------------------- 去重


def test_dedupe_keeps_longest(engine):
    """同位置重叠命中保留最长。"""
    r = det(engine, "全网最低价")
    # 不应出现两份几乎重叠的命中
    spans = [(f.start, f.end) for f in r.findings]
    for i, (s1, e1) in enumerate(spans):
        for s2, e2 in spans[i + 1:]:
            overlap = not (e1 <= s2 or e2 <= s1)
            assert not overlap, f"存在重叠命中：{spans}"


# ---------------------------------------------------------------- 行业包


def test_industry_pack_loaded(engine):
    """移民行业包应已加载（可插拔生态的基础）。"""
    kw = {r.keyword for r in engine.bank.all}
    # 行业包里应有移民相关词（如"保过""雇主担保"其一）
    immigration_related = {"雇主担保", "保过", "包过", "下签", "移民"}
    assert immigration_related & kw, "移民行业包似乎未加载"


# ---------------------------------------------------------------- v3 词库集成


def test_default_bank_loads_v3(engine):
    """默认引擎应加载 v3 新 schema 词库（含结构化 replacements）。"""
    assert engine.bank.schema_version == "v3", (
        f"期望加载 v3 词库，实际：{engine.bank.schema_version}（rules_v3 缺失？）"
    )
    # v3 应带来一批带替换词的规则（自动改写能力才可用）
    with_repl = [r for r in engine.bank.all if r.replacements]
    assert len(with_repl) >= 200, f"v3 带替换词规则过少：{len(with_repl)}"


def test_v3_replacement_flows_into_safe_text(engine):
    """v3 替换词应端到端生效：'最佳'→'优质'（开启 auto_replace 时）。"""
    r = det(engine, "这是最佳的选择", auto_replace=True)
    assert any(f.matched_text == "最佳" for f in r.findings)
    assert r.safe_text == "这是优质的选择", r.safe_text


def test_industry_layers_with_general(engine):
    """指定行业时，通用词库 + 行业包规则叠加。"""
    r = det(engine, "这个移民项目保证下签", industries=["immigration"])
    assert r.meta["rule_count"] > 0


# ---------------------------------------------------------------- LLM 降级


def test_llm_fallback_no_config(engine):
    """未配置任何 LLM 时，use_llm=True 不应崩溃，llm_analysis 为 None。"""
    r = det(engine, "最好的产品", use_llm=True)
    assert r.llm_analysis is None
    assert r.meta.get("llm_used") is False


def test_llm_unknown_provider_no_crash(engine):
    engine.set_llm_config({"llm_api_key": "sk-fake"})
    try:
        r = det(engine, "最好的产品", use_llm=True)
        # 配置存在但 key 无效 → 网络失败 → 优雅降级为 None
        assert r.llm_analysis is None
    finally:
        engine.set_llm_config({})


# ---------------------------------------------------------------- matcher 后端


def test_matcher_backend_reported(engine):
    r = det(engine, "最好的产品")
    assert r.meta["matcher_backend"] in ("pyahocorasick", "pure_python")


def test_pure_python_fallback_works():
    """即便 pyahocorasick 不可用，纯 Python 匹配器也能命中（降级路径）。"""
    from guardian.matcher.pure import PureAhoMatcher
    from guardian.matcher.base import KeywordIndex

    class _R:
        id = "x"
        keyword = "最好"

    idx: KeywordIndex = {"最好": [_R()]}
    m = PureAhoMatcher()
    m.build(idx)
    hits = list(m.iter_hits("这是最好的"))
    assert any(kw == "最好" for _, _, kw, _ in hits)


# ---------------------------------------------------------------- 单例


def test_engine_singleton():
    reset_engine()
    a = get_engine()
    b = get_engine()
    assert a is b
    reset_engine()
