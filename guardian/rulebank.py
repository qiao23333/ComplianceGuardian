#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则库加载：把 rules/ 下各类 JSON 加载为统一的 Rule 对象列表。

**单一数据源**：一律以实时的 ``rules/`` 目录为准。桌面端"词库管理"页面
编辑的也是这同一批文件，因此编辑后 reload 即刻生效，不存在"两份词库"。

结构化替换词（自动改写用）来自 ``rules/overrides/replacements.json``
（关键词 → 替换词列表的覆盖表），由 ``scripts/migrate_from_v24.py`` 从
旧 suggestion 文本中提取生成；加载时按关键词合并进对应 Rule。

加载范围
--------
* ``ad_law.json``            广告法通用极限词（source=ad_law）
* ``platform_rules.json``    按平台分列（source=platform, platform=键名）
* ``blue_v_only.json``       仅蓝V可发（含 blue_v / non_blue_v 双严重度）
* ``user_custom.json``       用户自定义（source=custom）
* ``industry_packs/<id>/rules.json``  行业包（source=industry:<id>）
* ``overrides/replacements.json``     关键词 → 替换词覆盖表（可选）

线程安全：RuleBank 是不可变快照，加载后只读。重新加载请新建实例。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from guardian.schema import Rule, normalize_severity

# 内置词库目录（相对项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUILTIN_RULES_DIR = _PROJECT_ROOT / "rules"
#: 替换词覆盖表相对路径（相对词库目录）
_REPLACEMENTS_OVERRIDE = Path("overrides") / "replacements.json"


def _load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _from_blue_v_entry(raw: dict, source: str, index: int) -> Rule:
    """构造 blue_v_only.json 的特殊规则（双账号严重度）。"""
    keyword = raw.get("keyword", "")
    nbv = raw.get("non_blue_v", raw.get("severity", "violation"))
    bv = raw.get("blue_v", "warning")
    category = raw.get("category", "未分类")
    digest = __import__("hashlib").sha1(keyword.encode("utf-8")).hexdigest()[:6]
    rule_id = f"{source}:{index:04d}:{digest}"
    kv = {"non_blue_v": normalize_severity(nbv, category, len(keyword)),
          "blue_v": normalize_severity(bv, category, len(keyword))}
    return Rule(
        id=rule_id,
        keyword=keyword,
        source=source,
        category=category,
        severity=kv["non_blue_v"],  # 默认以非蓝V严重度兜底
        severity_by_account=kv,
        suggestion=raw.get("suggestion", ""),
        law_ref=raw.get("law_ref", ""),
        note=raw.get("note", ""),
        allow_auto_replace=len(keyword) > 1,
    )


class RuleBank:
    """不可变规则快照（单一数据源：``rules/``）。

    加载顺序：先按来源读 ``rules/`` 各类文件，再套用
    ``rules/overrides/replacements.json`` 覆盖表补全替换词。
    """

    def __init__(self, rules_dir: Optional[Path | str] = None):
        self.rules_dir = Path(rules_dir) if rules_dir else _BUILTIN_RULES_DIR
        self._all: list[Rule] = []
        self._load()
        self._apply_replacement_overrides()
        # ID 索引（去重 / 审计用）
        self._by_id: dict[str, Rule] = {r.id: r for r in self._all}

    # ------------------------------------------------ 替换词覆盖表

    def _apply_replacement_overrides(self) -> None:
        """把 overrides/replacements.json（关键词→替换词）合并进规则。"""
        data = _load_json(self.rules_dir / _REPLACEMENTS_OVERRIDE)
        if not isinstance(data, dict):
            return
        for r in self._all:
            repl = data.get(r.keyword)
            if isinstance(repl, list) and repl and not r.replacements:
                r.replacements = [str(x) for x in repl]

    # ------------------------------------------------ 加载

    def _load(self) -> None:
        d = self.rules_dir
        # 广告法
        data = _load_json(d / "ad_law.json")
        if isinstance(data, list):
            self._all += [Rule.from_legacy(x, "ad_law", i) for i, x in enumerate(data)]
        # 平台规则（dict 按平台分列）
        data = _load_json(d / "platform_rules.json")
        if isinstance(data, dict):
            for platform, items in data.items():
                if isinstance(items, list):
                    self._all += [
                        Rule.from_legacy(x, "platform", i, platform=platform)
                        for i, x in enumerate(items)
                    ]
        # 仅蓝V
        data = _load_json(d / "blue_v_only.json")
        if isinstance(data, list):
            self._all += [_from_blue_v_entry(x, "blue_v", i) for i, x in enumerate(data)]
        # 正则兜底（"最X""极X""第X"等组合型极限词）
        data = _load_json(d / "regex_patterns.json")
        if isinstance(data, list):
            self._all += [Rule.from_legacy(x, "regex", i) for i, x in enumerate(data)]
        # 用户自定义
        data = _load_json(d / "user_custom.json")
        if isinstance(data, list):
            self._all += [Rule.from_legacy(x, "custom", i) for i, x in enumerate(data)]
        # 行业包
        packs = d / "industry_packs"
        if packs.is_dir():
            for pack_dir in sorted(packs.iterdir()):
                rules_file = pack_dir / "rules.json"
                if rules_file.is_file():
                    industry_id = pack_dir.name
                    data = _load_json(rules_file)
                    if isinstance(data, list):
                        self._all += [
                            Rule.from_legacy(x, f"industry:{industry_id}", i,
                                            industry=industry_id)
                            for i, x in enumerate(data)
                        ]

    # ------------------------------------------------ 查询

    @property
    def all(self) -> list[Rule]:
        return self._all

    def __len__(self) -> int:
        return len(self._all)

    def get(self, rule_id: str) -> Optional[Rule]:
        return self._by_id.get(rule_id)

    def filter(self, platform: str = "all",
               account_type: str = "non_blue_v",
               industries: Optional[list[str]] = None,
               min_severity: str = "low") -> list[Rule]:
        """按平台 / 账号类型 / 行业包过滤出"应当参与本次检测"的规则。

        过滤逻辑：
        * 平台：``platform=="all"`` 或规则 ``matches_platform(platform)``
        * 账号：取 ``severity_for(account_type)`` 不为空
        * 行业：``industries is None`` 只取通用（industry 为空）；
                否则叠加指定行业包 + 通用
        * 严重度：>= min_severity
        """
        from guardian.schema import SEVERITY_LEVELS

        min_w = SEVERITY_LEVELS.get(min_severity, ("", "", 2))[2]
        result: list[Rule] = []
        for r in self._all:
            if not r.enabled:
                continue
            if platform != "all" and not r.matches_platform(platform):
                continue
            if account_type and r.severity_for(account_type) == "":
                continue
            # 行业：通用规则（industry 为 None）总参与；指定行业时叠加
            if industries is not None:
                if r.industry is not None and r.industry not in industries:
                    continue
            else:
                if r.industry is not None:
                    continue
            if SEVERITY_LEVELS.get(r.severity_for(account_type), ("", "", 2))[2] < min_w:
                continue
            result.append(r)
        return result
