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

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from guardian.engine import DetectionEngine, get_engine, reset_engine
from guardian.schema import DetectionOptions

# 旧 UI 使用的平台键
_PLATFORMS = ["xiaohongshu", "douyin", "weixin"]

# 词库目录默认位置（与 RuleBank 单一数据源一致）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RULES_DIR = _PROJECT_ROOT / "rules"

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

#: 默认启用的行业包（与 guardian.config.DEFAULT_CONFIG 保持一致）
_DEFAULT_INDUSTRY_PACKS = ["immigration"]


def _configured_industry_packs() -> list[str]:
    """读取用户启用的行业包，读不到则回退默认（移民包）。

    为什么需要
    ----------
    桌面端 ``detect`` 此前**从不传** ``industries``，而 ``DetectionOptions``
    的默认是 ``None``（仅通用词库）——结果是 ``rules/industry_packs/immigration``
    里 140 条行业红线（保证下签 / 零拒签 / 移民局认证…）在 App 内全部失效。
    行业词库恰恰是本工具区别于通用违禁词工具的核心，不能默认关掉。

    直接读配置文件而不用 ``ConfigManager``：后者在文件缺失时会**写出**默认配置，
    在只读场景（打包 exe、测试）引入副作用。
    """
    try:
        cfg_file = _PROJECT_ROOT / "data" / "config.json"
        if cfg_file.is_file():
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            packs = data.get("enabled_industry_packs")
            if isinstance(packs, list):
                return [str(p) for p in packs]
    except (OSError, json.JSONDecodeError):
        pass
    return list(_DEFAULT_INDUSTRY_PACKS)


class ComplianceDetector:
    """兼容旧 UI 的检测器门面（内部委托 DetectionEngine 单例）。

    除检测外，还保留旧 UI「词库管理」所需的原始词库读写接口
    （``ad_law`` / ``platform_rules`` / ``blue_v_only`` / ``user_custom`` 等
    及增删改 / 备份 / 还原），与引擎共用同一 ``rules/`` 目录（单一数据源）。
    """

    _instance: Optional["ComplianceDetector"] = None
    _lock = threading.Lock()

    PLATFORM_NAMES = {
        "xiaohongshu": "小红书",
        "douyin": "抖音",
        "weixin": "微信视频号",
    }

    def __init__(self, rules_dir: Optional[str] = None):
        self.rules_dir = Path(rules_dir) if rules_dir else _DEFAULT_RULES_DIR
        self._engine = get_engine(str(self.rules_dir))
        # 原始词库结构（供词库管理页读写，保留旧 dict 格式）
        self.ad_law: list = []
        self.platform_rules: dict = {}
        self.blue_v_only: list = []
        self.user_custom: list = []
        self.REGEX_PATTERNS: list = []
        self.load_rules()

    # ------------------------------------------------ 单例

    @classmethod
    def get_instance(cls, rules_dir: Optional[str] = None) -> "ComplianceDetector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ComplianceDetector(rules_dir)
            return cls._instance

    # ------------------------------------------------ 核心检测

    def detect(self, text: str, platform: str = "all",
               account_type: str = "non_blue_v",
               auto_replace: bool = False,
               industries: Optional[list[str]] = None) -> dict:
        options = DetectionOptions(
            platform=platform,
            account_type=account_type,
            # 未显式指定时按用户配置启用行业包（默认含 immigration）
            industries=(industries if industries is not None
                        else _configured_industry_packs()),
            use_variants=True,    # 变体抗规避：默认开启（已修误报）
            use_llm=False,        # 语义增强走独立 _llm_analyze
            auto_replace=auto_replace,  # 一键改写时开启
        )
        return self._convert(self._engine.detect_text(text, options), text)

    def detect_all_platforms(self, text: str,
                             account_type: str = "non_blue_v") -> dict:
        out = {}
        for plat in _PLATFORMS:
            out[plat] = self.detect(text, plat, account_type)
        return out

    def reload_rules(self) -> None:
        """重建内核 + 重新读取原始词库（词库热更新）。"""
        reset_engine(str(self.rules_dir))          # 只失效本目录缓存
        self._engine = get_engine(str(self.rules_dir))
        self.load_rules()

    # ------------------------------------------------ 原始词库读写（兼容旧 UI）

    @staticmethod
    def _read_json(path: Path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_rules(self) -> None:
        """从 ``rules/`` 读取原始词库结构（旧 dict 格式，供管理页编辑）。"""
        d = Path(self.rules_dir)
        self.ad_law = self._read_json(d / "ad_law.json", [])
        self.platform_rules = self._read_json(d / "platform_rules.json", {})
        self.blue_v_only = self._read_json(d / "blue_v_only.json", [])
        self.user_custom = self._read_json(d / "user_custom.json", [])
        self.REGEX_PATTERNS = self._read_json(d / "regex_patterns.json", [])
        # 容错：类型异常时回退到空结构，避免管理页崩溃
        if not isinstance(self.ad_law, list):
            self.ad_law = []
        if not isinstance(self.platform_rules, dict):
            self.platform_rules = {}
        if not isinstance(self.blue_v_only, list):
            self.blue_v_only = []
        if not isinstance(self.user_custom, list):
            self.user_custom = []
        if not isinstance(self.REGEX_PATTERNS, list):
            self.REGEX_PATTERNS = []

    def get_rules_summary(self) -> dict:
        """词库统计摘要（兼容旧 dashboard / 设置页字段名）。"""
        plat_counts = {}
        for plat, rules in self.platform_rules.items():
            name = self.PLATFORM_NAMES.get(plat, plat)
            plat_counts[name] = len(rules) if isinstance(rules, list) else 0

        industry_pack_counts: dict[str, int] = {}
        total_industry = 0
        packs_dir = Path(self.rules_dir) / "industry_packs"
        if packs_dir.is_dir():
            for pack_dir in sorted(packs_dir.iterdir()):
                rules_file = pack_dir / "rules.json"
                if not rules_file.is_file():
                    continue
                raw = self._read_json(rules_file, [])
                n = len(raw) if isinstance(raw, list) else 0
                meta_file = pack_dir / "meta.json"
                meta = self._read_json(meta_file, {})
                name = (meta or {}).get("name", pack_dir.name)
                industry_pack_counts[name] = n
                total_industry += n

        total = (len(self.ad_law)
                 + sum(len(r) for r in self.platform_rules.values()
                       if isinstance(r, list))
                 + len(self.blue_v_only)
                 + len(self.user_custom)
                 + total_industry)

        return {
            "广告法违禁词": len(self.ad_law),
            "平台规则": plat_counts,
            "蓝V专属限制": len(self.blue_v_only),
            "行业红线": len(self.user_custom),
            "行业词库包": industry_pack_counts,
            "正则模式": len(self.REGEX_PATTERNS),
            "总计": total,
        }

    # ---- 增删改

    def add_custom_rule(self, keyword, category, severity, suggestion, note="") -> dict:
        """添加自定义规则到 user_custom.json。"""
        rule = {
            "keyword": keyword,
            "category": category or "行业红线",
            "severity": severity or "violation",
            "suggestion": suggestion or "根据公司规定修改",
            "note": note or "",
        }
        self.user_custom.append(rule)
        self._save_user_custom()
        return rule

    def add_rule_to_category(self, tab_name, keyword, category, severity,
                             suggestion, note="") -> dict:
        """按标签页分流保存规则（广告法 / 蓝V限制 / 行业红线）。"""
        rule = {
            "keyword": keyword,
            "category": category or "",
            "severity": severity or "violation",
            "suggestion": suggestion or "",
            "note": note or "",
        }
        if tab_name == "广告法":
            rule["source"] = "广告法"
            rule["law_ref"] = "《广告法》第九条"
            self.ad_law.append(rule)
            self._save_rules("广告法")
        elif tab_name == "蓝V限制":
            rule["blue_v"] = "warning"
            rule["non_blue_v"] = "violation"
            self.blue_v_only.append(rule)
            self._save_rules("蓝V限制")
        else:  # 行业红线 / 其他
            rule["category"] = category or "行业红线"
            rule["suggestion"] = suggestion or "根据公司规定修改"
            self.user_custom.append(rule)
            self._save_user_custom()
        return rule

    def remove_custom_rule(self, index: int) -> None:
        """删除自定义规则（按 user_custom 中的下标）。"""
        if 0 <= index < len(self.user_custom):
            self.user_custom.pop(index)
            self._save_user_custom()

    def _save_user_custom(self) -> None:
        self._write_json(Path(self.rules_dir) / "user_custom.json", self.user_custom)

    def _save_rules(self, tab_name: str) -> None:
        """把指定标签页的词库写回 JSON。"""
        d = Path(self.rules_dir)
        if tab_name == "广告法":
            self._write_json(d / "ad_law.json", self.ad_law)
        elif tab_name == "平台规则":
            self._write_json(d / "platform_rules.json", self.platform_rules)
        elif tab_name == "蓝V限制":
            self._write_json(d / "blue_v_only.json", self.blue_v_only)
        elif tab_name == "行业红线":
            self._save_user_custom()

    # ---- 备份 / 还原

    def backup_rules(self) -> str:
        """备份当前词库到 ``rules/backup/YYYY-MM-DD_HHMM/``。"""
        backup_dir = Path(self.rules_dir) / "backup" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in ("ad_law.json", "platform_rules.json", "blue_v_only.json",
                     "user_custom.json", "regex_patterns.json"):
            src = Path(self.rules_dir) / name
            if src.exists():
                shutil.copy2(src, backup_dir / name)
        packs_dir = Path(self.rules_dir) / "industry_packs"
        if packs_dir.is_dir():
            shutil.copytree(packs_dir, backup_dir / "industry_packs", dirs_exist_ok=True)
        return str(backup_dir)

    def list_backups(self) -> list[dict]:
        """列出所有备份（时间倒序）。"""
        root = Path(self.rules_dir) / "backup"
        if not root.is_dir():
            return []
        backups = []
        for d in sorted(root.iterdir(), reverse=True):
            if d.is_dir():
                file_count = sum(1 for f in d.iterdir() if f.is_file())
                backups.append({
                    "name": d.name,
                    "path": str(d),
                    "file_count": file_count,
                    "timestamp": d.name,
                })
        return backups

    def restore_backup(self, backup_name: str) -> None:
        """从指定备份恢复词库并热重载。"""
        backup_dir = Path(self.rules_dir) / "backup" / backup_name
        if not backup_dir.is_dir():
            raise FileNotFoundError(f"备份不存在：{backup_name}")
        for name in ("ad_law.json", "platform_rules.json", "blue_v_only.json",
                     "user_custom.json", "regex_patterns.json"):
            src = backup_dir / name
            if src.exists():
                shutil.copy2(src, Path(self.rules_dir) / name)
        backup_packs = backup_dir / "industry_packs"
        if backup_packs.is_dir():
            packs_dir = Path(self.rules_dir) / "industry_packs"
            if packs_dir.is_dir():
                shutil.rmtree(packs_dir)
            shutil.copytree(backup_packs, packs_dir)
        self.reload_rules()

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

    def apply_llm_config(self, config: dict) -> None:
        """把 LLM 工厂契约 dict 注入引擎（设置页保存后调用）。"""
        self._engine.set_llm_config(config or {})

    # ------------------------------------------------ AI 改写

    def rewrite(self, text: str, findings: Optional[list] = None, **kwargs):
        """用 AI 把文案改写成合规版本（判定已完成，模型只负责改写）。

        ``findings`` 可直接传 ``detect()`` 结果里的 ``violations``。
        AI 不可用时返回 ``ok=False``，调用方保留规则结果即可。
        """
        return self._engine.rewrite(text, list(findings or []), **kwargs)

    def build_rewrite_prompt(self, text: str, findings: Optional[list] = None, **kwargs) -> str:
        """只生成改写指令文本，不调用模型。

        给"复制到任意 AI"的零配置路径用——用户不需要在本工具里配任何 key，
        照样能借外部 AI 完成改写。
        """
        return self._engine.build_rewrite_prompt(text, list(findings or []), **kwargs)

    @classmethod
    def check_ollama_available(cls, base_url: Optional[str] = None) -> tuple[bool, list]:
        """探测本地 Ollama 是否可用，返回 (available, 模型名列表)。

        ``base_url`` 可选（设置页自定义地址）；默认用 OllamaProvider 的默认地址。
        """
        from guardian.llm_config import probe_ollama
        from guardian.llm.ollama import OllamaProvider

        url = base_url or OllamaProvider().base_url
        return probe_ollama(url)

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
