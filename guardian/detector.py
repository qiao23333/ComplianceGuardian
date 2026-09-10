#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向后兼容门面：把新内核 ``guardian.engine`` 适配成旧 UI 需要的返回结构。

v3 重构后，真正的检测逻辑都在 ``guardian/engine.py``。本文件是一个**薄 shim**：
保留 ``ComplianceDetector`` 这个旧类名与旧方法签名，让桌面 UI（``apps/desktop/ui/*``）
无需改写即可直接享受新内核的能力——变体抗规避检测、LLM Provider 抽象、匹配器降级等。

字段映射（新 → 旧 UI 契约）
---------------------------
* 严重度：``critical/high`` → ``"violation"``；``medium/low`` → ``"warning"``
* 风险等级：``基本合规`` → ``"安全"``；``低风险/中风险/高风险`` 同名；
  ``critical`` 命中 ≥1 → ``"极高风险"``
* 其余字段（id/keyword/category/source/suggestion/start/end/match_type 等）原样透传。

本 shim 会随阶段 3（桌面 UI 重写）被彻底移除，届时 UI 直接调用新引擎 API。
"""

from __future__ import annotations

import threading
from typing import Optional

from guardian.engine import DetectionEngine, get_engine, reset_engine
from guardian.schema import DetectionOptions

# 旧 UI 使用的平台键
_PLATFORMS = ["xiaohongshu", "douyin", "weixin"]

# 新严重度 → 旧显示严重度
_DISPLAY_SEV = {
    "critical": "violation",
    "high": "violation",
    "medium": "warning",
    "low": "warning",
}

# 新风险等级 → 旧 risk_level
_RISK_MAP = {
    "基本合规": "安全",
    "低风险": "低风险",
    "中风险": "中风险",
    "高风险": "高风险",
}


class ComplianceDetector:
    """兼容旧 UI 的检测器门面（内部委托 DetectionEngine 单例）。"""

    _instance: Optional["ComplianceDetector"] = None
    _lock = threading.Lock()

    def __init__(self, rules_dir: Optional[str] = None):
        self._engine = get_engine(rules_dir)
        self.rules_dir = rules_dir

    # ------------------------------------------------ 单例

    @classmethod
    def get_instance(cls, rules_dir: Optional[str] = None) -> "ComplianceDetector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ComplianceDetector(rules_dir)
            return cls._instance

    # ------------------------------------------------ 核心检测

    def detect(self, text: str, platform: str = "all",
               account_type: str = "non_blue_v") -> dict:
        options = DetectionOptions(
            platform=platform,
            account_type=account_type,
            use_variants=True,    # 变体抗规避：默认开启（已修误报）
            use_llm=False,        # 语义增强走独立 _llm_analyze
        )
        return self._convert(self._engine.detect_text(text, options), text)

    def detect_all_platforms(self, text: str,
                             account_type: str = "non_blue_v") -> dict:
        out = {}
        for plat in _PLATFORMS:
            out[plat] = self.detect(text, plat, account_type)
        return out

    def reload_rules(self) -> None:
        """重建内核（词库热更新）。"""
        reset_engine()
        self._engine = get_engine(self.rules_dir)

    # ------------------------------------------------ LLM 语义增强

    def _llm_analyze(self, text: str, platform: str = "all",
                     account_type: str = "non_blue_v",
                     violations: Optional[list] = None) -> Optional[dict]:
        options = DetectionOptions(
            platform=platform,
            account_type=account_type,
            use_variants=True,
            use_llm=True,
        )
        result = self._engine.detect_text(text, options)
        return self._convert_llm(result.llm_analysis, result.meta.get("llm_provider"))

    @classmethod
    def check_ollama_available(cls) -> tuple[bool, list]:
        """探测本地 Ollama 是否可用，返回 (available, 模型名列表)。"""
        from guardian.llm.ollama import OllamaProvider

        prov = OllamaProvider()
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                f"{prov.base_url}/api/tags",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", [])]
            return (bool(models), models)
        except Exception:
            return (False, [])

    # ============================================================ 转换

    @staticmethod
    def _convert(result, text: str) -> dict:
        findings = result.findings
        violations = []
        crit = 0
        for i, f in enumerate(findings, 1):
            disp_sev = _DISPLAY_SEV.get(f.severity, "warning")
            if f.severity == "critical":
                crit += 1
            v = {
                "id": i,
                "start": f.start,
                "end": f.end,
                # 展示用关键词：一律用原文匹配片段，变体命中时也看得懂
                # （如用户写"加 薇 信"，显示"加 薇 信"而非拼音串 jiaweixin）
                "keyword": f.matched_text or f.keyword,
                "original": text[f.start:f.end],
                "category": f.category,
                "severity": disp_sev,
                "source": f.source or "规则引擎",
                "platform": f.platform,
                "blue_v_label": "",
                "suggestion": f.suggestion or "",
                "law_ref": "",
                "note": "",
                "match_type": f.match_type,
                "variant_of": f.variant_of,
                "confidence": f.confidence,
            }
            violations.append(v)

        n_violation = sum(1 for v in violations if v["severity"] == "violation")
        n_warning = sum(1 for v in violations if v["severity"] == "warning")

        if n_violation == 0 and n_warning == 0:
            risk_level = "安全"
        elif crit > 0:
            risk_level = "极高风险"
        else:
            risk_level = _RISK_MAP.get(result.summary.get("risk_level", ""), "中风险")

        summary = {
            "violations": n_violation,
            "warnings": n_warning,
            "text_length": len(text),
            "risk_level": risk_level,
            "score": result.summary.get("score", 100),
        }
        return {
            "violations": violations,
            "summary": summary,
            "modified_text": result.safe_text,
            "llm_analysis": None,
        }

    @staticmethod
    def _convert_llm(analysis: Optional[dict], provider: Optional[str]) -> Optional[dict]:
        if not analysis:
            return {"status": "error", "model": provider or "unknown"}
        risks = []
        for ef in analysis.get("extra_findings", []) or []:
            if isinstance(ef, str):
                risks.append({"type": "疑似风险", "severity": "warning",
                              "description": ef, "suggestion": ""})
            elif isinstance(ef, dict):
                risks.append({
                    "type": ef.get("type", "疑似风险"),
                    "severity": ef.get("severity", "warning"),
                    "description": ef.get("description", ""),
                    "suggestion": ef.get("suggestion", ""),
                })
        return {
            "model": provider or "llm",
            "assessment": analysis.get("risk_summary") or analysis.get("assessment", ""),
            "score": analysis.get("compliance_score") or analysis.get("score"),
            "risks": risks,
        }
