#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测引擎（v3 新内核）。

职责
----
把"规则 + 文本 → 检测结果"这条主链路编排清楚，取代 v2.4 里
detector.py 那个 1171 行、检测/LLM/规则CRUD/备份职责混杂的单体类。

主链路（detect_text）
--------------------
1. 按选项过滤规则（平台 / 账号 / 行业 / 最低严重度）
2. 构建关键词索引（精确词 → Aho 自动机；正则词 → 单独 re 通道）
3. 字面命中（raw text）
4. 变体命中（归一化后文本：谐音/跳字/繁简/全角）+ 可选拼音变体
5. 去重（同位置保留最长）
6. 反误杀守卫（context_guard：上下文豁免 + 短词降级）
7. 生成 Finding 列表、合规分 summary、safe_text（只改写 allow_auto_replace 项）
8. 可选 LLM 语义增强（无可用 Provider 时自动跳过，纯规则引擎完整工作）

设计约束
--------
本模块属于内核层，禁止 import tkinter / customtkinter / fastapi。
"""

from __future__ import annotations

import re
import time
from typing import Optional

from guardian import context_guard
from guardian.matcher import create_matcher
from guardian.matcher.base import Hit, KeywordIndex
from guardian.normalize import normalize, romanize, pinyin_index
from guardian.rulebank import RuleBank
from guardian.schema import (
    SEVERITY_LEVELS,
    DetectionOptions,
    DetectionResult,
    Finding,
    Rule,
    severity_weight,
)

_ENGINE_VERSION = "3.0.0-alpha"


def _downgrade(severity: str) -> str:
    """变体命中时把严重度降一级。"""
    order = ["critical", "high", "medium", "low"]
    try:
        i = order.index(severity)
        return order[min(i + 1, len(order) - 1)]
    except ValueError:
        return "low"


def _contains_non_cjk(s: str) -> bool:
    """字符串里是否含非汉字字符（字母/数字/标点）。

    拼音变体通道的准入闸门：只有源文本真的混入了非汉字（用户写了拼音或
    字母），才认定这是"刻意规避"。纯中文文本一律拒绝——否则相邻汉字的
    拼音会跨字拼出别的关键词，产生大面积误报（详见调用处注释）。
    """
    return any(not ("\u4e00" <= ch <= "\u9fff") for ch in s)


def _replacement_for(rule: Rule) -> Optional[str]:
    """计算自动改写时用来替换原文的字符串。

    **只认显式替换词**：``replacements`` 非空 → 用第一个；否则不自动改写。

    历史教训：曾用"建议文本含'删除'就把命中改写为空串"的启发式，结果
    "全网最低价"这类规则会把命中片段整段删掉（"最X"正则命中"最好"→删除，
    句子变成"这是的服务"）。自动改写必须由词库明确给出替换词，
    没有替换词就只高亮、由人工处理（与 P0 保守防线一致）。
    """
    if rule.replacements:
        return rule.replacements[0]
    return None


class DetectionEngine:
    """检测引擎（不可变快照，线程安全单例由 get_engine() 管理）。"""

    def __init__(self, rulebank: Optional[RuleBank] = None,
                 rules_dir: Optional[str] = None):
        self.bank = rulebank or RuleBank(rules_dir)
        self._cache: dict[str, object] = {}

    # ------------------------------------------------ 索引构建

    def _index_key(self, options: DetectionOptions) -> str:
        ind = options.industries or []
        return f"{options.platform}|{options.account_type}|{sorted(ind)}|{options.min_severity}"

    def _get_matcher(self, rules: list[Rule]):
        exact: KeywordIndex = {}
        regex: list[Rule] = []
        for r in rules:
            if r.match_mode == "regex":
                regex.append(r)
            else:
                exact.setdefault(r.keyword, []).append(r)
        matcher = create_matcher(exact)
        return matcher, exact, regex

    # ------------------------------------------------ 入口

    def detect_text(self, text: str, options: Optional[DetectionOptions] = None) \
            -> DetectionResult:
        options = options or DetectionOptions()
        t0 = time.time()

        if not text or not text.strip():
            return DetectionResult(text=text, summary={"counts": {}, "score": 100,
                                "risk_level": "基本合规", "text_length": len(text)},
                                  safe_text=text, meta={"engine_version": _ENGINE_VERSION})

        text = text[: options.max_text_len] if len(text) > options.max_text_len else text

        rules = self.bank.filter(
            platform=options.platform,
            account_type=options.account_type,
            industries=options.industries,
            min_severity=options.min_severity,
        )
        matcher, exact_idx, regex_rules = self._get_matcher(rules)

        # 1) 字面命中
        raw_hits: list[dict] = []
        for start, end, keyword, rule in matcher.iter_hits(text):
            raw_hits.append(self._mk_hit(start, end, keyword, rule, "keyword"))

        # 正则通道
        for rule in regex_rules:
            try:
                pat = re.compile(rule.keyword)
            except re.error:
                continue
            for m in pat.finditer(text):
                raw_hits.append(self._mk_hit(m.start(), m.end(), rule.keyword, rule, "regex"))

        # 2) 变体命中（归一化后）
        variant_hits: list[dict] = []
        if options.use_variants:
            norm = normalize(text)
            for start, end, keyword, rule in matcher.iter_hits(norm.text):
                o_s, o_e = norm.original_span(start, end)
                orig_sub = text[o_s:o_e]
                # 字面也能匹配到的（orig_sub==keyword）属重复，跳过
                if orig_sub == keyword:
                    continue
                h = self._mk_hit(o_s, o_e, keyword, rule, "variant",
                                 variant_of=keyword, conf=0.8)
                variant_hits.append(h)

            # 2b) 拼音变体（可选，依赖 pypinyin；仅全拼 + 字符边界对齐）
            pidx = pinyin_index(rules)
            if pidx:
                from guardian.matcher import create_matcher as _cm
                pmatcher = _cm(pidx)
                rom = romanize(norm.text)
                if rom.text:
                    for s, e, keyword, rule in pmatcher.iter_hits(rom.text):
                        cs = rom.char_span(s, e)
                        if cs is None:
                            continue  # 没对齐到整字边界 → 误报，丢弃
                        n_s, n_e = cs
                        if n_e > len(norm.index_map):
                            continue
                        o_s = norm.index_map[n_s]
                        o_e = norm.index_map[n_e - 1] + 1
                        orig_sub = text[o_s:o_e]
                        # 字面已能命中（orig_sub == 关键词）属重复，跳过
                        if orig_sub == rule.keyword:
                            continue
                        # ⚠️ 拼音通道只接受"用户真的写了拼音"的命中。
                        #
                        # 纯中文文本里，相邻两字的拼音会跨字拼出别的关键词——
                        # 实测事故："澳洲雇主担保签证" 中「担保签证」的拼音
                        # dan-bao-qian-zheng 含子串 baoqianzheng，正好等于
                        # 关键词「包签证」的全拼，于是把一句完全正常的话判成
                        # 虚假承诺。这类跨字碰撞无法靠"边界对齐"消除（每个
                        # 汉字本身就是一个对齐单位），必须要求源文本里真的
                        # 混有非汉字字符（拼音/字母），才认定是刻意规避写法。
                        if not _contains_non_cjk(orig_sub):
                            continue
                        h = self._mk_hit(o_s, o_e, keyword, rule, "variant",
                                         variant_of=rule.keyword, conf=0.7)
                        variant_hits.append(h)

        # 3) 合并 + 去重
        all_hits = raw_hits + variant_hits
        all_hits = self._dedupe(all_hits)

        # 4) 规则级上下文豁免（rule.context_excludes，比全局表更精确）
        all_hits = self._apply_rule_excludes(all_hits, text)

        # 5) 反误杀守卫
        exempt_spans = context_guard.find_exempt_spans(text)
        guarded = context_guard.apply_guard(all_hits, text, exempt_spans)

        # 6) 转 Finding + 生成改写文案
        findings = [self._to_finding(i, h, text) for i, h in enumerate(guarded, 1)]
        safe_text = self._build_safe_text(text, findings, options)

        # 7) summary
        summary = self._build_summary(findings, len(text))

        # 8) 可选 LLM
        llm_analysis = None
        meta = {
            "engine_version": _ENGINE_VERSION,
            "matcher_backend": matcher.backend,
            "rule_count": len(rules),
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        }
        if options.use_llm:
            llm_analysis, provider_name = self._maybe_llm(text, findings)
            meta["llm_provider"] = provider_name
            meta["llm_used"] = llm_analysis is not None

        return DetectionResult(
            text=text, findings=findings, summary=summary,
            safe_text=safe_text, llm_analysis=llm_analysis, meta=meta,
        )

    # ------------------------------------------------ 内部工具

    def _apply_rule_excludes(self, hits: list[dict], text: str) -> list[dict]:
        """规则级上下文豁免：命中落在该规则自己的 ``context_excludes`` 词组内 → 丢弃。

        为什么需要（而不只用全局 EXEMPT_PHRASES）
        ----------------------------------------
        像 ``微信`` 这类词，在广告文案里是导流信号（该报），但在
        "微信支付 / 微信公众号 / 微信视频号" 里是正常表述（不该报）。
        这种"取决于具体搭配"的豁免，由词库维护者在规则上直接声明最自然，
        也比往全局表里塞词更不容易误伤别的规则。
        """
        if not hits:
            return hits
        cache: dict[str, list[tuple[int, int]]] = {}
        kept: list[dict] = []
        for h in hits:
            rule = self.bank.get(h["rule_id"])
            excludes = getattr(rule, "context_excludes", None) if rule else None
            if not excludes:
                kept.append(h)
                continue
            spans = cache.get(rule.id)
            if spans is None:
                spans = []
                for phrase in excludes:
                    if not phrase:
                        continue
                    pos = text.find(phrase)
                    while pos != -1:
                        spans.append((pos, pos + len(phrase)))
                        pos = text.find(phrase, pos + 1)
                cache[rule.id] = spans
            s, e = h["start"], h["end"]
            if any(s >= ps and e <= pe for ps, pe in spans):
                continue
            kept.append(h)
        return kept

    def _mk_hit(self, start, end, keyword, rule, match_type,
                variant_of=None, conf=1.0) -> dict:
        severity = rule.severity_for(self._account())
        allow = rule.allow_auto_replace
        if match_type == "variant":
            severity = _downgrade(severity)
            allow = False  # 变体绝不自动改写，交人工确认
        return {
            "start": start, "end": end, "keyword": keyword,
            "rule_id": rule.id, "category": rule.category,
            "severity": severity, "source": rule.source,
            "industry": rule.industry, "platform": rule.platforms[0]
            if rule.platforms != ["*"] else "*",
            "suggestion": rule.suggestion,
            "replacements": rule.replacements,
            "allow_auto_replace": allow,
            "match_type": match_type, "variant_of": variant_of,
            "confidence": conf,
        }

    def _account(self) -> str:
        # 简化：引擎内部用 non_blue_v 取默认严重度（调用方已通过 filter 控制）
        return "non_blue_v"

    def _dedupe(self, hits: list[dict]) -> list[dict]:
        """合并去重：字面/变体命中优先，正则仅作"兜底网"。

        * 字面（keyword）与变体先按 位置→最长→类型→严重度 贪心选取；
        * 正则命中只在**不与被选命中重叠**时补充进来——即"词库没覆盖到的
          组合"才由正则兜底，避免正则抢掉带 suggestion/replacements 的
          精确规则（否则自动改写会因正则规则无替换词而失效）。
        """
        curated = [h for h in hits if h["match_type"] != "regex"]
        fallback = [h for h in hits if h["match_type"] == "regex"]

        kept = self._greedy_pick(curated)
        for h in sorted(fallback, key=lambda x: (x["start"], -len(x["keyword"]),
                                                 -severity_weight(x["severity"]))):
            if not any(h["start"] < k["end"] and h["end"] > k["start"] for k in kept):
                kept.append(h)
        return sorted(kept, key=lambda h: h["start"])

    @staticmethod
    def _greedy_pick(hits: list[dict]) -> list[dict]:
        """贪心保留不重叠命中：位置 → 最长 → 类型(字面>变体) → 高严重度。"""
        rank = {"keyword": 0, "variant": 1, "regex": 2}
        hits = sorted(hits, key=lambda h: (h["start"], -len(h["keyword"]),
                                           rank.get(h["match_type"], 9),
                                           -severity_weight(h["severity"])))
        kept: list[dict] = []
        for h in hits:
            if any(h["start"] < k["end"] and h["end"] > k["start"] for k in kept):
                continue
            kept.append(h)
        return kept

    def _to_finding(self, fid: int, h: dict, text: str) -> Finding:
        return Finding(
            id=fid, start=h["start"], end=h["end"],
            matched_text=text[h["start"]:h["end"]],
            rule_id=h["rule_id"], keyword=h["keyword"],
            category=h["category"], severity=h["severity"],
            source=h["source"], platform=h["platform"],
            suggestion=h["suggestion"], replacements=list(h["replacements"]),
            allow_auto_replace=h["allow_auto_replace"],
            match_type=h["match_type"], variant_of=h["variant_of"],
            confidence=h["confidence"],
        )

    def _build_safe_text(self, text: str, findings: list[Finding],
                         options: DetectionOptions) -> str:
        """只替换 allow_auto_replace=True 的字面命中（变体一律不自动改写）。

        默认 ``options.auto_replace=False`` → 返回原文（仅高亮，保守不改写）；
        显式开启后才执行自动改写。这样避免默认就露出半成品改写文案
        （例如规则 keyword 比常见短语短一截时会残留尾字）。UI 的"一键改写"
        按钮显式开启该开关并提供预览。
        """
        if not options.auto_replace:
            return text
        edits = [(f.start, f.end, f) for f in findings
                 if f.allow_auto_replace and f.match_type in ("keyword", "regex")]
        if not edits:
            return text
        edits.sort(key=lambda x: x[0], reverse=True)
        out = text
        for s, e, f in edits:
            rule = self.bank.get(f.rule_id)
            if rule is None:
                continue
            repl = _replacement_for(rule)
            if repl is None:
                continue
            out = out[:s] + repl + out[e:]
        return out

    def _build_summary(self, findings: list[Finding], text_len: int) -> dict:
        counts = {k: 0 for k in SEVERITY_LEVELS}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        penalty = sum(severity_weight(f.severity) for f in findings)
        score = max(0, 100 - penalty)
        if counts["critical"] > 0:
            risk = "高风险"
        elif counts["high"] > 0:
            risk = "中风险"
        elif counts["medium"] > 0:
            risk = "低风险"
        else:
            risk = "基本合规"
        return {"score": score, "risk_level": risk, "counts": counts,
                "text_length": text_len}

    def _maybe_llm(self, text: str, findings: list[Finding]):
        from guardian.llm import create_provider
        from guardian.llm.base import LLMRequest

        provider = create_provider(self._llm_config or {})
        if not provider.is_configured():
            return None, provider.name
        req = LLMRequest(text=text, findings=[
            {"keyword": f.keyword, "category": f.category} for f in findings])
        res = provider.analyze(req)
        return (res.analysis if res.ok else None), provider.name

    # LLM 配置（由 set_llm_config 注入，默认空 → NullProvider）
    _llm_config: dict = {}

    def set_llm_config(self, config: dict) -> None:
        self._llm_config = config or {}


# ============================================================ 单例管理

_engine: Optional[DetectionEngine] = None
#: 按 rules_dir 分桶缓存（默认目录用 None 作键）——不同词库目录互不串味，
#: 同一目录内仍复用同一引擎实例（线程安全由 RuleBank 不可变性保证）。
_engines: dict[str, DetectionEngine] = {}


def get_engine(rules_dir: Optional[str] = None) -> DetectionEngine:
    """进程内单例（按 rules_dir 分桶）。

    * 相同 ``rules_dir``（含均为 None）→ 返回同一个引擎实例。
    * 不同 ``rules_dir`` → 各自独立引擎（测试 / 多词库场景隔离）。
    """
    key = str(rules_dir) if rules_dir else ""
    eng = _engines.get(key)
    if eng is None:
        eng = DetectionEngine(rules_dir=rules_dir)
        _engines[key] = eng
    return eng


def reset_engine(rules_dir: Optional[str] = None) -> None:
    """失效缓存引擎。

    * 传 ``rules_dir`` → 只清该词库目录的缓存（精准热更新）。
    * 不传 → 清空全部（测试隔离用）。
    """
    global _engine
    if rules_dir is None:
        _engine = None
        _engines.clear()
    else:
        _engines.pop(str(rules_dir), None)
