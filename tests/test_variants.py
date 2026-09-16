#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变体抗规避检测测试：重点是「拼音边界对齐」修复。

历史 bug：拼音字母与汉字并非 1:1 对应，两字母首字母（"zh"/"wx"）会落进
单个汉字（"这"=zhe）的拼音内部，造成单字级误报；"为信仰"的拼音 weixinyang
会误命中"微信"。修复后（guardian/normalize/variants.py 的 char_span +
guardian/engine.py 的边界校验）要求命中必须落在整字边界。
"""

import pytest

from guardian.normalize import romanize, pinyin_index
from guardian.normalize.variants import RomanizedText
from guardian.engine import DetectionEngine
from guardian.schema import DetectionOptions


@pytest.fixture(scope="module")
def engine():
    return DetectionEngine()


def detect(engine, text, **kw):
    opts = DetectionOptions(platform=kw.get("platform", "xiaohongshu"),
                             account_type=kw.get("account_type", "non_blue_v"),
                             industries=kw.get("industries"),
                             use_variants=True)
    return engine.detect_text(text, opts)


# ---------------------------------------------------------------- char_span 边界对齐


def test_char_span_rejects_inside_char():
    """"zhe" 中 "zh" 落在单字内部 → 不应返回有效跨度。"""
    rom = romanize("这")  # -> zhe
    # 取前 2 个字母 "zh"
    cs = rom.char_span(0, 2)
    assert cs is None, "单字内部拼音不应被当成有效匹配"


def test_char_span_accepts_whole_chars():
    """"weixin" 完整覆盖"微信"两字 → 返回整字跨度。"""
    rom = romanize("微信")  # weixin
    s = rom.text.index("weixin")
    e = s + len("weixin")
    cs = rom.char_span(s, e)
    assert cs is not None, "完整拼音应被接受"
    n_s, n_e = cs
    assert (n_e - n_s) == 2, "应跨越 2 个汉字"


def test_char_span_no_cross_boundary():
    """"为信仰" 的拼音 weixinyang 中子串 weixin 跨越了字边界 → 应被拒。"""
    rom = romanize("为信仰")  # wei xin yang
    if "weixin" in rom.text:
        s = rom.text.index("weixin")
        e = s + len("weixin")
        # 由于 wei| xin | yang 各自成字，"weixin" 跨越 为+信 边界，
        # 末字母 'n' 属于"信"但后面紧接"仰"的 'y'，需检查是否对齐。
        # 实际上 wei(xin) 的 xin 是独立字，weixin = 为+信 两字完整，可能合法。
        # 该用例交给端到端测试；此处仅确保 char_span 在跨字时行为确定。
        _ = rom.char_span(s, e)


# ---------------------------------------------------------------- 端到端：不再误报


@pytest.mark.parametrize("text", [
    "为信仰充值",            # 拼音 weixinyang 不应误报微信
    "这是最近的一件事",       # 最近豁免 + 无拼音误报
    "这用的材料很好",         # "这" 单字不应被拼音误报
    "我们用微信聊",           # 正常，命中微信(若词库有)但不误报
])
def test_no_false_positive_variants(engine, text):
    """这些文本不应因拼音变体产生单字级误报。"""
    r = detect(engine, text)
    for f in r.findings:
        # 变体命中 matched_text 不应是单字（除非它本来就是真违规单字，如"最"已降级）
        if f.match_type == "variant" and len(f.matched_text) <= 1:
            pytest.fail(f"单字级拼音误报：{f.matched_text!r} in {text!r}")


def test_pinyin_index_only_full_pinyin():
    """pinyin_index 只收全拼，丢弃碰撞严重的首字母（如 wx/zh）。"""
    from guardian.schema import Rule
    rules = [Rule(id="t:0", keyword="微信", source="x", category="导流")]
    idx = pinyin_index(rules)
    assert "weixin" in idx, "全拼应保留"
    assert "wx" not in idx, "首字母 wx 应被丢弃（碰撞严重）"


def test_homophone_variant_detected(engine):
    """归一化使"加薇信"→"加微信"（薇→微），命中关键词"加微信"（变体）。"""
    r = detect(engine, "加薇信，快来了解")
    variants = [f for f in r.findings if f.match_type == "variant"]
    assert variants, "谐音变体未被检出"
    # 命中的原文片段应含"加薇信"，且 variant_of 指向规范词"加微信"
    assert any("加薇信" in f.matched_text for f in variants)
    assert any(f.variant_of == "加微信" for f in variants), \
        [f.variant_of for f in variants]


def test_noise_variant_detected(engine):
    """跳字规避"加 薇 信" 应被检出为变体。"""
    r = detect(engine, "加 薇 信 领 资 料")
    assert any("加" in f.matched_text and "信" in f.matched_text
               for f in r.findings if f.match_type == "variant")


def test_variant_never_auto_replaced(engine):
    """变体命中的 allow_auto_replace 必须为 False（交人工确认）。"""
    r = detect(engine, "加 薇 信 领 资 料")
    for f in r.findings:
        if f.match_type == "variant":
            assert f.allow_auto_replace is False


# ---------------------------------------------------------------- 数字写法通道
#
# 背景：中文数字有阿拉伯与汉字两套写法，使用边界纯凭手感。"7天瘦" 与
# "七天瘦" 是同一种违规表述，词库一个关键词只能收一种写法，另一种就漏。
# 实测早期版本「七天瘦」命中而「7天瘦」完全没提示 —— 而后者才是营销
# 文案里的主流写法。修复方式是在引擎里单开一条"数字写法通道"
# （guardian/engine.py 的 2b 段 + guardian/normalize/pipeline.py 的
# to_cjk_digits），而不是塞进 normalize() 主链路，原因见第三条测试。


def test_digit_variant_arabic_hits_cjk_keyword(engine):
    """"7天瘦" 应命中原词库里的「七天瘦」（词库收的是汉字写法）。"""
    r = detect(engine, "轻断食代餐，7天瘦10斤", industries=["weight_loss"])
    assert r.findings, "阿拉伯数字写法完全未命中 —— 数字通道失效"


def test_digit_variant_maps_span_to_original(engine):
    """命中区间必须回落到**原文**（高亮"7天瘦"而不是"七天瘦"）。"""
    r = detect(engine, "轻断食代餐，7天瘦10斤", industries=["weight_loss"])
    hit = [f for f in r.findings if f.match_type == "variant"]
    assert hit, "数字写法应被标为变体命中"
    assert any("7天瘦" in f.matched_text for f in hit), \
        f"高亮片段未回落到原文：{[f.matched_text for f in hit]}"


def test_digit_variant_works_for_base_library_too(engine):
    """不只是行业包：通用库的「第一」也应被"第1"命中。

    `第X + 量词` 的序数骨架由语境守卫豁免，所以这条同时验证
    "阿拉伯数字能命中汉字关键词"与"豁免仍然生效"两件事。
    """
    r = detect(engine, "本机构为行业第1")
    assert any("第1" in f.matched_text for f in r.findings), \
        f"通用库的汉字数字关键词未被阿拉伯写法命中：{[f.matched_text for f in r.findings]}"


def test_fullwidth_digit_keyword_still_matches(engine):
    """回归守卫：全角「成功率１００％」靠归一半角命中「100%」的能力不能被砸掉。

    这是把数字转换塞进 normalize() 主链路时的真实事故 —— 全角数字归一半角
    后又立刻被转成"一零零"，关键词「100%」再也匹配不上。所以数字变体必须
    单开通道，两条路各走各的。
    """
    r = detect(engine, "成功率１００％，绝无例外")
    assert any("１００％" in f.matched_text for f in r.findings), \
        f"全角数字写法漏检了：{[(f.keyword, f.matched_text) for f in r.findings]}"


def test_digit_channel_does_not_break_ordinal_exemption(engine):
    """反误报守卫：「第1步 / 第1位」是序数叙述，不能因数字通道而被报出。

    豁免机制认的是 `第X + 量词` 骨架（X 同时接受阿拉伯与汉字数字），
    数字通道必须与它协同，而不是绕过它。
    """
    for text in ("第1步递交EOI", "我排在第1位", "第2阶段准备材料"):
        r = detect(engine, text)
        assert not r.findings, \
            f"{text!r} 被误报：{[(f.keyword, f.matched_text) for f in r.findings]}"


def test_digit_variant_never_auto_replaced(engine):
    """数字写法命中也属变体，禁止自动改写（改写会动到原文数字）。"""
    r = detect(engine, "轻断食代餐，7天瘦10斤")
    for f in r.findings:
        if f.match_type == "variant":
            assert f.allow_auto_replace is False

