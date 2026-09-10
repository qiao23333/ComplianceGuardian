#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据模型：规则（Rule）、命中（Finding）、检测结果（DetectionResult）。

这是内核的"通用语言"——引擎、匹配器、变体检测、LLM、桌面端、Web 端
全部通过这里定义的结构通信。

设计要点
--------
* Rule 用 `to_dict()/from_dict()` 而非直接暴露 dataclass 序列化，
  因为 JSON 规则文件需要长期稳定（外部贡献者按 schema 提 PR）。
* severity 四级对齐竞品的风险分级习惯（高危封号/中危限流/低危建议/提示）。
* `allow_auto_replace=False` 的规则**绝不**进入自动改写——这是
  "最近→近"事故的安全网（见 guardian/context_guard.py 的 docstring）。

设计约束：本模块只依赖标准库。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

# ============================================================ 严重度体系

#: 四级严重度 → (展示名, UI 颜色语义, 风险分权重)
#:
#: ============  ==============  ==========  ======
#: severity      含义            颜色        扣分
#: ============  ==============  ==========  ======
#: critical      高危·封号/违法  红          10
#: high          中危·限流       橙          5
#: medium        低危·建议改     黄          2
#: low           提示·仅供参考   灰蓝        0（不扣分）
#: ============  ==============  ==========  ======
SEVERITY_LEVELS: dict[str, tuple[str, str, int]] = {
    "critical": ("高危", "danger", 10),
    "high": ("中危", "warning", 5),
    "medium": ("低危", "caution", 2),
    "low": ("提示", "info", 0),
}

#: v2.x 旧词库的 severity 值 → 新四级映射表（迁移脚本用）
LEGACY_SEVERITY_MAP: dict[str, str] = {
    "violation": "critical",   # 违规 → 高危（词库多为广告法/行业红线）
    "warning": "medium",       # 警告 → 低危建议
    "info": "low",
    "tip": "low",
}


#: 合法匹配模式
VALID_MATCH_MODES: tuple[str, ...] = ("exact", "regex", "fuzzy")


def normalize_severity(raw: str, category: str = "", keyword_len: int = 99) -> str:
    """把旧词库的 severity 值规范化为四级之一。

    迁移规则：
    1. 已是四级直接返回；
    2. 旧值按 `LEGACY_SEVERITY_MAP` 映射；
    3. **单字极限词强制降为 `low`**——单字（如"最"）误杀面极大，
       且自动改写会破坏原文，只保留提示价值。
    """
    if raw in SEVERITY_LEVELS:
        return raw
    mapped = LEGACY_SEVERITY_MAP.get(raw, "medium")
    # 单字极限词降级（context_guard 会进一步做运行时豁免，这里做词库侧固化）
    if keyword_len <= 1 and "极限" in category:
        return "low"
    return mapped


def severity_weight(severity: str) -> int:
    """取该严重度的风险分权重。"""
    return SEVERITY_LEVELS.get(severity, ("", "", 2))[2]


# ============================================================ 规则


@dataclass
class Rule:
    """一条合规规则（词库 JSON 中的一条记录）。

    与 v2.x 的裸 dict 相比新增的关键能力：
    * ``id``            稳定 ID（"ad_law:0001"），外部贡献 / 去重 / 审计都靠它
    * ``version``       规则版本，未来做词库热更新 diff 用
    * ``platforms``     适用的平台列表，["*"] 表示通用
    * ``severity``      四级严重度（见 SEVERITY_LEVELS）
    * ``context_excludes``  上下文排除词组——命中词落在这些词组内则不算违规
    * ``replacements``  结构化替换建议（取代 v2.x 用正则解析 suggestion 文本的脆弱做法）
    * ``allow_auto_replace``  False = 只提示、绝不改写原文
    * ``enabled``       生效开关（无需删词即可临时停用）
    """

    # ---- 身份 ----
    id: str
    version: int = 1

    # ---- 匹配 ----
    keyword: str = ""
    match_mode: str = "exact"          # exact | regex | fuzzy

    # ---- 归属 ----
    source: str = "custom"             # ad_law | platform | blue_v | custom | industry
    industry: Optional[str] = None     # None=通用；如 "immigration"
    platforms: list[str] = field(default_factory=lambda: ["*"])
    category: str = "未分类"

    # ---- 分级 ----
    severity: str = "medium"
    severity_by_account: Optional[dict] = None   # 如 {"blue_v": "medium", "non_blue_v": "critical"}

    # ---- 反误杀 ----
    context_excludes: list[str] = field(default_factory=list)

    # ---- 改写 ----
    suggestion: str = ""
    replacements: list[str] = field(default_factory=list)
    allow_auto_replace: bool = True

    # ---- 元信息 ----
    law_ref: str = ""
    note: str = ""
    enabled: bool = True
    updated: str = ""

    # ------------------------------------------------ 工厂

    @classmethod
    def from_legacy(cls, raw: dict, source: str, index: int,
                    industry: Optional[str] = None,
                    platform: Optional[str] = None) -> "Rule":
        """从 v2.x 裸 dict 规则构造（迁移期兼容层）。

        Args:
            raw: 旧规则 dict（含 keyword/category/severity/suggestion/...）
            source: 词库来源标识（ad_law / platform / blue_v / industry:<id>）
            index: 在词库中的序号，用于生成稳定 ID
            industry: 行业包 ID（行业包规则用）
            platform: 平台标识（平台规则用）
        """
        keyword = raw.get("keyword", "")
        category = raw.get("category", "未分类")
        match_mode = raw.get("match_mode", "exact") or "exact"
        if match_mode not in VALID_MATCH_MODES:
            match_mode = "exact"
        severity = normalize_severity(
            raw.get("severity", "violation"), category, len(keyword)
        )

        # 稳定 ID：source + 序号 + 关键词哈希前 6 位（词库重排也不会错位）
        digest = hashlib.sha1(keyword.encode("utf-8")).hexdigest()[:6]
        # 前缀须包含区分维度，避免跨平台同关键词撞 ID：
        #   industry 包 → industry:<id>；平台规则 → platform:<plat>；其余 → source
        if industry:
            prefix = f"industry:{industry}"
        elif platform:
            prefix = f"platform:{platform}"
        else:
            prefix = source
        rule_id = f"{prefix}:{index:04d}:{digest}"

        platforms = [platform] if platform else ["*"]

        return cls(
            id=rule_id,
            keyword=keyword,
            match_mode=match_mode,
            source=source,
            industry=industry,
            platforms=platforms,
            category=category,
            severity=severity,
            severity_by_account=raw.get("severity_by_account"),
            suggestion=raw.get("suggestion", ""),
            # 结构化替换词：优先取规则自带的 replacements 字段
            # （迁移/词库维护可写入；旧词库无此字段则为空 → 不自动改写）
            replacements=list(raw.get("replacements") or []),
            law_ref=raw.get("law_ref", ""),
            note=raw.get("note", ""),
            # 单字极限词不允许自动改写（与 context_guard 的运行时防线呼应）
            allow_auto_replace=len(keyword) > 1 or "极限" not in category,
        )

    # ------------------------------------------------ 序列化

    def to_dict(self) -> dict:
        """转成可写入 JSON 的 dict（只保留非默认值以外仍全量输出，保持格式可读）。"""
        return {
            "id": self.id,
            "version": self.version,
            "keyword": self.keyword,
            "match_mode": self.match_mode,
            "source": self.source,
            "industry": self.industry,
            "platforms": self.platforms,
            "category": self.category,
            "severity": self.severity,
            "severity_by_account": self.severity_by_account,
            "context_excludes": self.context_excludes,
            "suggestion": self.suggestion,
            "replacements": self.replacements,
            "allow_auto_replace": self.allow_auto_replace,
            "law_ref": self.law_ref,
            "note": self.note,
            "enabled": self.enabled,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        """从 JSON dict 构造；未知字段忽略（向前兼容）。"""
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})

    def severity_for(self, account_type: str) -> str:
        """按账号类型（blue_v / non_blue_v）取实际严重度。"""
        if self.severity_by_account:
            return self.severity_by_account.get(account_type, self.severity)
        return self.severity

    def matches_platform(self, platform: str) -> bool:
        """判断该规则是否适用于指定平台（"all" 视为全平台）。"""
        if platform == "all" or "*" in self.platforms:
            return True
        return platform in self.platforms


# ============================================================ 检测结果


@dataclass
class DetectionOptions:
    """一次检测的参数。"""

    platform: str = "all"               # all | xiaohongshu | douyin | weixin
    account_type: str = "non_blue_v"    # blue_v | non_blue_v
    industries: Optional[list[str]] = None   # None=仅通用词库；["immigration"]=叠加行业包
    use_variants: bool = True           # 变体抗规避检测
    use_llm: bool = False               # LLM 语义增强（无可用 Provider 时自动跳过）
    auto_replace: bool = False          # 自动改写：默认关闭（保守，只高亮不改动原文）
    min_severity: str = "low"           # 低于此严重度的命中不返回
    max_text_len: int = 20000           # 超长文本截断保护（Web 端会设更小）


@dataclass
class Finding:
    """一处命中。

    坐标约定：``start``/``end`` 指向**原始文本**（左闭右开），
    归一化/变体命中的位置通过 index_map 回映射到原文，
    UI 高亮与自动改写都以此为准。
    """

    id: int
    start: int
    end: int
    matched_text: str            # 原文中实际匹配到的片段
    rule_id: str
    keyword: str                 # 规则词（变体命中时为原词，如"微信"）
    category: str
    severity: str                # critical | high | medium | low
    source: str                  # 广告法 / 小红书 / 移民行业包 ...
    platform: str
    suggestion: str = ""
    replacements: list[str] = field(default_factory=list)
    allow_auto_replace: bool = True
    match_type: str = "keyword"  # keyword | regex | variant | llm
    variant_of: Optional[str] = None   # 变体命中时的原词
    confidence: float = 1.0            # variant=0.8 / llm=模型自评
    context: str = ""                  # 前后各 ~10 字，供 UI 展示

    def excerpt(self, text: str, radius: int = 10) -> str:
        """从原文截取命中位置的上下文片段（首次调用时填充 context）。"""
        if not self.context:
            lo = max(0, self.start - radius)
            hi = min(len(text), self.end + radius)
            prefix = "…" if lo > 0 else ""
            suffix = "…" if hi < len(text) else ""
            self.context = f"{prefix}{text[lo:hi]}{suffix}"
        return self.context


@dataclass
class DetectionResult:
    """一次检测的完整结果。

    ``summary`` 结构::

        {
            "score": 85,            # 0-100 合规分
            "risk_level": "低风险",  # 低/中/高
            "counts": {"critical": 0, "high": 1, "medium": 2, "low": 3},
            "text_length": 120,
            "elapsed_ms": 12.3,
        }

    ``safe_text``：自动改写后的文案。**只替换 allow_auto_replace=True 的项**，
    短词/被标记保护的命中绝不动原文。
    """

    text: str
    findings: list[Finding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    safe_text: str = ""                 # 默认=原文（无任何自动改写时）
    llm_analysis: Optional[dict] = None
    meta: dict = field(default_factory=dict)   # engine_version / rule_count / matcher_backend / degraded ...

    # ------------------------------------------------ 便捷查询

    def by_severity(self, severity: str) -> list["Finding"]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    def to_dict(self) -> dict:
        """转 dict（供 Web API / 报告导出 / JSON 序列化）。"""
        return {
            "text": self.text,
            "findings": [f.__dict__ for f in self.findings],
            "summary": self.summary,
            "safe_text": self.safe_text,
            "llm_analysis": self.llm_analysis,
            "meta": self.meta,
        }
