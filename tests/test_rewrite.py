#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 改写路径的测试。

这里测的不是"模型答得好不好"（那要联网、要花钱、还不稳定），而是
**契约是否守得住**：

1. 提示词必须把边界说死——判定归规则引擎，模型只改写。少写一句，
   模型就会开始"帮我多找几个违规词"，那是本项目最不想要的行为。
2. 模型输出千奇百怪（套代码块、changes 写成字符串数组、干脆不返回 JSON），
   解析层必须扛住，且**永远不能抛异常把检测流程带崩**。
3. AI 不可用 / 调用失败时，规则引擎的结果必须完好无损。
   本项目的底线是"没有 AI 也是完整产品"，这条得用测试钉住。
"""

from __future__ import annotations

import pytest

from guardian.llm.base import LLMProvider, extract_json
from guardian.llm.null import NullProvider
from guardian.llm.prompts import build_rewrite_prompt, format_findings
from guardian.llm.rewrite import RewriteRequest, parse_rewrite


# ============================================================ 测试替身

class FakeProvider(LLMProvider):
    """可编程的假 Provider：返回预设文本，不联网。"""

    name = "fake"

    def __init__(self, response: str = "", ok: bool = True, error: str = None):
        self._response = response
        self._ok = ok
        self._error = error
        self.last_prompt = ""
        self.last_system = None

    def is_configured(self) -> bool:
        return True

    def complete(self, prompt: str, *, system=None):
        self.last_prompt = prompt
        self.last_system = system
        return self._ok, self._response, self._error


# ============================================================ 提示词边界

class TestPromptBoundary:
    """提示词必须明确"不要判定"——这是 AI 用法的核心约束。"""

    def test_prompt_forbids_judging(self):
        p = build_rewrite_prompt("全网最低价", [{"matchedText": "全网最低"}])
        assert "不要做合规判定" in p
        # 必须解释原因，否则模型不懂为什么不让它判
        assert "规则引擎" in p
        assert "不要" in p and "新增" in p

    def test_prompt_carries_rewrite_rules(self):
        p = build_rewrite_prompt("保签包过", [])
        for must in ["最小改动", "保住卖点", "不编事实", "不弱化到废话"]:
            assert must in p, "缺少改写铁律：%s" % must

    def test_prompt_demands_json_contract(self):
        p = build_rewrite_prompt("x", [])
        for key in ["rewritten", "changes", "kept", "unresolved"]:
            assert key in p

    def test_prompt_allows_honest_unresolved(self):
        """必须明确允许"改不了就说改不了"，否则模型会硬凑假方案。"""
        p = build_rewrite_prompt("x", [])
        assert "不要硬凑" in p

    def test_prompt_includes_findings_detail(self):
        p = build_rewrite_prompt("全网最低价", [{
            "matchedText": "全网最低",
            "keyword": "全网最低",
            "category": "极限词",
            "severity": "high",
            "suggestion": "删除比价表述",
            "replacements": ["较优", "实惠"],
        }])
        assert "全网最低" in p
        assert "极限词" in p
        assert "较优" in p

    def test_prompt_includes_platform_context(self):
        p = build_rewrite_prompt("加微信", [], platform="xiaohongshu",
                                 account_type="blue_v", industry_label="移民行业")
        assert "小红书" in p
        assert "蓝V" in p
        assert "移民行业" in p

    def test_must_keep_rendered(self):
        p = build_rewrite_prompt("x", [], must_keep=["雇主担保", "482 签证"])
        assert "必须保留" in p
        assert "雇主担保" in p


# ============================================================ 命中清单渲染

class TestFormatFindings:
    def test_empty(self):
        assert "未命中" in format_findings([])

    def test_kernel_snake_case(self):
        """内核 Finding 的字段名（蛇形）也要能渲染。"""
        out = format_findings([{
            "matched_text": "保签", "keyword": "保签",
            "category": "承诺", "severity": "critical",
            "source": "移民红线", "match_type": "variant",
        }])
        assert "保签" in out
        assert "规避写法" in out
        assert "移民红线" in out

    def test_ui_camel_case(self):
        out = format_findings([{
            "matchedText": "包过", "keyword": "包过", "matchType": "variant",
        }])
        assert "包过" in out
        assert "规避写法" in out

    def test_replacement_list_rendered(self):
        out = format_findings([{"matchedText": "最好", "replacements": ["较好", "不错"]}])
        assert "较好" in out and "不错" in out


# ============================================================ JSON 容错

class TestExtractJson:
    def test_plain(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_chatty_prefix(self):
        assert extract_json('好的，以下是结果：\n{"a": 1}\n希望有帮助') == {"a": 1}

    def test_garbage(self):
        assert extract_json("模型今天不想输出 JSON") is None

    def test_empty(self):
        assert extract_json("") is None


class TestParseRewrite:
    def test_normal(self):
        r = parse_rewrite(
            '{"rewritten": "合规版本", "changes": [{"before": "a", "after": "b", '
            '"reason": "r", "rule": "1"}], "kept": ["卖点"], "unresolved": []}',
            provider="fake")
        assert r.ok
        assert r.rewritten == "合规版本"
        assert r.changed_count == 1
        assert r.kept == ["卖点"]
        assert r.summary_line().startswith("改了 1 处")

    def test_changes_as_string_list(self):
        """模型把 changes 写成字符串数组是常见跑偏，必须归一而不是崩。"""
        r = parse_rewrite('{"rewritten": "x", "changes": ["删掉最字"]}')
        assert r.ok
        assert r.changes[0]["before"] == "删掉最字"

    def test_kept_as_scalar(self):
        """kept 写成字符串而不是数组 → 归一成空列表，不崩。"""
        r = parse_rewrite('{"rewritten": "x", "kept": "卖点"}')
        assert r.ok
        assert r.kept == []

    def test_unresolved_normalized(self):
        r = parse_rewrite('{"rewritten": "x", "unresolved": [{"text": "t", '
                          '"why": "w", "need": "n"}]}')
        assert r.unresolved[0]["why"] == "w"
        assert "需人工确认" in r.summary_line()

    def test_no_json_keeps_raw(self):
        """完全不是 JSON：别把用户的东西丢了，原样留着让 UI 能显示。"""
        r = parse_rewrite("这是一段普通文字")
        assert not r.ok
        assert r.rewritten == "这是一段普通文字"
        assert "JSON" in r.error

    def test_json_without_rewritten(self):
        r = parse_rewrite('{"changes": []}')
        assert not r.ok
        assert r.error

    def test_missing_changes(self):
        r = parse_rewrite('{"rewritten": "x"}')
        assert r.ok and r.changes == []


# ============================================================ Provider 契约

class TestProviderRewrite:
    def test_rewrite_uses_system_prompt(self):
        p = FakeProvider('{"rewritten": "合规版"}')
        res = p.rewrite(RewriteRequest(text="保过", findings=[]))
        assert res.ok
        assert res.rewritten == "合规版"
        assert p.last_system and "改写" in p.last_system

    def test_rewrite_failure_is_not_exception(self):
        p = FakeProvider(ok=False, error="网络断了")
        res = p.rewrite(RewriteRequest(text="保过", findings=[]))
        assert not res.ok
        assert res.error == "网络断了"
        assert res.rewritten is None

    def test_null_provider_never_raises(self):
        res = NullProvider().rewrite(RewriteRequest(text="保过", findings=[]))
        assert not res.ok
        assert "未配置" in res.error

    def test_prompt_override_respected(self):
        p = FakeProvider('{"rewritten": "x"}')
        p.rewrite(RewriteRequest(text="保过", findings=[], prompt_override="只用这句话"))
        assert p.last_prompt == "只用这句话"

    def test_default_prompt_contains_text(self):
        p = FakeProvider('{"rewritten": "x"}')
        p.rewrite(RewriteRequest(text="这段是原文", findings=[]))
        assert "这段是原文" in p.last_prompt


# ============================================================ 与引擎的集成

class TestEngineRewrite:
    """引擎层的两条路径：调用模型、以及只拼提示词（零配置 BYO-AI）。"""

    def test_build_prompt_without_provider(self):
        """没有任何 AI 配置时，也必须能拿到提示词——这是零配置路径。"""
        from guardian.engine import get_engine

        eng = get_engine()
        prompt = eng.build_rewrite_prompt(
            "保签包过", [{"matchedText": "保签", "keyword": "保签", "category": "承诺"}],
            platform="xiaohongshu")
        assert "保签包过" in prompt
        assert "小红书" in prompt
        assert "不要做合规判定" in prompt

    def test_rewrite_without_provider_returns_error(self):
        from guardian.engine import get_engine

        eng = get_engine()
        res = eng.rewrite("保签包过", [])
        assert not res.ok
        assert res.error
        # 错误信息要给出路，不能只说"失败"
        assert "规则检测结果不受影响" in res.error


# ============================================================ 底线：AI 不影响判定

class TestAiDoesNotAffectJudgement:
    def test_detection_unaffected_by_ai_failure(self):
        """AI 挂掉后，规则检测的分数与命中必须一模一样。

        这是"没有 AI 也是完整产品"的可执行证明。
        """
        from guardian.engine import get_engine

        eng = get_engine()
        text = "澳洲雇主担保移民，保签包过，全网最低价，成功率 100%。"

        result = eng.detect_text(text)
        baseline = (result.summary["score"], len(result.findings))

        eng.set_llm_config({"llm_local_enabled": True,
                            "llm_local_base": "http://127.0.0.1:1",  # 必然连不上
                            "llm_model": "nonexistent"})
        after = eng.detect_text(text)
        eng.set_llm_config({})

        assert (after.summary["score"], len(after.findings)) == baseline
        assert baseline[1] > 0, "样例文案应至少命中一处，否则这个测试没意义"
