#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v3 阶段暴露出的两个真 bug 的回归测试（批判性自检中发现）。

Bug 1 — 拼音通道在纯拉丁文本上退化成单字母命中
    根因：``pypinyin.lazy_pinyin("jiaweixin")`` 把整段拉丁文当作**一个** part
    返回（``['jiaweixin']``），``romanize`` 按 part 下标填 ``idx``，于是
    ``idx`` 全部等于 0；``char_span`` 的整字边界校验因此失效，命中被裁成
    ``[0:1]`` → 单字母 "j"。
    修复：``romanize`` 传 ``errors=_per_char``，非汉字片段按字符拆分，
    保证 ``len(parts) == len(text)``，映射恢复逐字对齐。

Bug 2 — 桌面端从不启用行业包
    ``ComplianceDetector.detect`` 构造 ``DetectionOptions`` 时没有传
    ``industries``，而默认值是 ``None``（仅通用词库）。结果
    ``rules/industry_packs/immigration`` 的 140 条行业红线在 App 内**全部失效**
    （保证下签 / 零拒签 / 移民局认证…），而行业词库正是本工具的核心差异点。
    修复：默认读取用户配置 ``enabled_industry_packs``（缺省启用移民包）。
"""

from __future__ import annotations

import pytest

from guardian.detector import ComplianceDetector, _configured_industry_packs
from guardian.engine import DetectionEngine
from guardian.normalize.variants import romanize
from guardian.schema import DetectionOptions


# ------------------------------------------------- Bug 1: 拼音映射对齐


def test_romanize_keeps_per_char_alignment_for_latin():
    """纯拉丁文本的 idx 必须逐字符递增，不能全指向 0。"""
    rom = romanize("jiaweixin")
    assert rom.idx == list(range(len("jiaweixin"))), (
        f"拉丁文本索引未逐字对齐：{rom.idx}"
    )


def test_romanize_mixed_text_alignment():
    """中英混排时 part 数必须等于源字符数（否则映射整体错位）。"""
    text = "加我微信abc"
    rom = romanize(text)
    assert max(rom.idx) < len(text)
    # 每个源字符至少被一个字母指回
    assert set(rom.idx) == set(range(len(text)))


@pytest.fixture(scope="module")
def engine() -> DetectionEngine:
    return DetectionEngine()


def test_pinyin_input_hits_whole_string_not_single_letter(engine):
    """直接输入拼音串应整串命中（变体），而不是退化成单字母伪命中。"""
    r = engine.detect_text("jiaweixin", DetectionOptions())
    assert r.findings, "拼音串 jiaweixin 未命中"
    for f in r.findings:
        assert len(f.matched_text) > 1, (
            f"出现单字符伪命中：{f.matched_text!r} span=[{f.start}:{f.end}]"
        )
        assert f.matched_text == "jiaweixin", f"命中片段异常：{f.matched_text!r}"


# ------------------------------------------------- Bug 2: 行业包默认启用


def test_configured_industry_packs_defaults_to_immigration():
    """读不到配置时回退默认，且默认包含移民包。"""
    assert "immigration" in _configured_industry_packs()


@pytest.mark.parametrize("text", [
    "保证下签",
    "零拒签",
    "移民局认证机构",
])
def test_shim_detect_enables_industry_pack_by_default(text):
    """桌面端 shim 默认应启用行业包，行业红线必须能检出。"""
    d = ComplianceDetector()
    res = d.detect(text)
    assert res["summary"]["violations"] >= 1, (
        f"{text!r} 未被检出——行业包似乎未启用"
    )


def test_shim_detect_can_disable_industry_packs():
    """显式传空列表可只跑通用词库（行业红线不再命中）。"""
    d = ComplianceDetector()
    res = d.detect("保证下签", industries=[])
    assert res["summary"]["violations"] == 0, (
        "industries=[] 时不应命中行业规则"
    )
