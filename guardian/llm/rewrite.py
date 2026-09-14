#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改写能力的请求 / 返回契约与解析器。

与 ``base.py`` 里的 ``analyze``（旧的"语义增强"）的区别：

===========  ==========================  ==========================
             analyze（旧，保留兼容）      rewrite（本模块）
===========  ==========================  ==========================
产出         风险总结 / 建议 / 额外发现   改写后的完整文案 + 逐处对照
语义         让模型做判定                 让模型做改写
稳定性       模型自由发挥，结论不可复现    输入输出都有原文锚定
用途         参考                         直接可用
===========  ==========================  ==========================

``rewrite`` 是现在的主路径：判定由规则引擎负责，模型只负责把话说圆。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass
class RewriteRequest:
    """一次改写请求。

    ``findings`` 是规则引擎给出的命中清单，必须带 ``matchedText`` /
    ``keyword`` / ``suggestion`` / ``replacements`` 等字段——清单越具体，
    模型改得越贴规则。
    """
    text: str
    findings: Sequence[dict] = field(default_factory=list)
    platform: Optional[str] = None
    account_type: Optional[str] = None
    industry_label: Optional[str] = None
    must_keep: Sequence[str] = field(default_factory=list)
    tone: Optional[str] = None
    prompt_override: Optional[str] = None


@dataclass
class RewriteResult:
    """一次改写的返回。

    ``ok=False`` 时 ``error`` 有值，``rewritten`` 为 None——调用方应直接
    展示错误并保留原始自动改写结果，绝不能因为 AI 挂了就让整个检测失败。
    """
    ok: bool
    rewritten: Optional[str] = None
    changes: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    error: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: float = 0.0

    @property
    def changed_count(self) -> int:
        return len(self.changes)

    def summary_line(self) -> str:
        """一行人类可读的结果说明，给 UI 直接显示。"""
        if not self.ok:
            return "AI 改写未完成：%s" % (self.error or "未知错误")
        bits = ["改了 %d 处" % self.changed_count]
        if self.kept:
            bits.append("保住 %d 个卖点" % len(self.kept))
        if self.unresolved:
            bits.append("%d 处需人工确认" % len(self.unresolved))
        return " · ".join(bits)


def parse_rewrite(raw: str, *, provider: Optional[str] = None,
                  model: Optional[str] = None,
                  latency_ms: float = 0.0) -> RewriteResult:
    """把模型返回的原始文本解析成 RewriteResult（尽力而为，不抛异常）。

    模型经常不听话——套 markdown 代码块、在 JSON 前后加解释、把 changes
    写成字符串数组。这里做容错归一，实在解析不出来就返回一个 ok=False
    且 is_raw 的结果，让上层把原文亮给用户看，而不是显示"解析失败"了事。
    """
    from guardian.llm.base import extract_json

    data = extract_json(raw)
    if not isinstance(data, dict):
        # 解析不出 JSON：至少把原文留着，用户还能自己看
        return RewriteResult(
            ok=False,
            error="模型返回的不是可解析的 JSON",
            rewritten=raw.strip() or None,
            provider=provider, model=model, latency_ms=latency_ms,
        )

    rewritten = data.get("rewritten") or data.get("rewrite") or data.get("text")
    if isinstance(rewritten, str):
        rewritten = rewritten.strip()

    return RewriteResult(
        ok=bool(rewritten),
        rewritten=rewritten,
        changes=_norm_changes(data.get("changes")),
        kept=_norm_str_list(data.get("kept") or data.get("kept_points")),
        unresolved=_norm_unresolved(data.get("unresolved")),
        error=None if rewritten else "模型没有返回改写后的文案",
        provider=provider, model=model, latency_ms=latency_ms,
    )


def _norm_changes(raw) -> list:
    """归一 changes：只保留有 before/after 的项，容忍字符串写法。"""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            out.append({"before": item, "after": "", "reason": "", "rule": ""})
        elif isinstance(item, dict):
            out.append({
                "before": str(item.get("before") or item.get("from") or ""),
                "after": str(item.get("after") or item.get("to") or ""),
                "reason": str(item.get("reason") or ""),
                "rule": str(item.get("rule") or ""),
            })
    return out


def _norm_str_list(raw) -> list:
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x).strip()]


def _norm_unresolved(raw) -> list:
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            out.append({"text": item, "why": "", "need": ""})
        elif isinstance(item, dict):
            out.append({
                "text": str(item.get("text") or item.get("before") or ""),
                "why": str(item.get("why") or item.get("reason") or ""),
                "need": str(item.get("need") or ""),
            })
    return out


class _Timer:
    """小工具：给 provider 包一层耗时统计。"""

    def __init__(self) -> None:
        self.t0 = time.time()

    @property
    def ms(self) -> float:
        return (time.time() - self.t0) * 1000
