#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则校验器：保证 v3 词库 JSON 的合法性与一致性。

用于：
* 迁移脚本产出后的自检
* 外部贡献者提交词库 PR 时的 CI 校验
* 运行时加载前的快速 sanity check

校验项
------
1. id 唯一
2. severity ∈ {critical, high, medium, low}
3. keyword 非空
4. 同 (keyword, source, platform) 不应有重复 exact 规则
5. replacements 为列表；match_mode ∈ {exact, regex, fuzzy}
6. 用户可见文案（note / suggestion / law_ref）不得混入维护者台账
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from guardian.schema import Rule, SEVERITY_LEVELS, VALID_MATCH_MODES

#: 用户可见字段里不该出现的"内部台账"痕迹。
#:
#: 背景：`note` 曾同时被当成两样东西——给用户看的说明，和给维护者看的
#: 定级理由。结果"禁止使用全网最低等极限表述｜严重度校准：《广告法》
#: 第九条：绝对化保证，属明确法律风险"这句会原样出现在用户界面上。
#:
#: 一个字段一物两用，迟早会有一半跑到不该去的地方。定级理由应该写进
#: 提交信息或复核台账，而不是塞进面向用户的文案。
_INTERNAL_MARKERS = re.compile(
    r"[｜|]\s*(?:严重度校准|校准记录|定级理由|内部|维护|TODO|FIXME|@[A-Za-z0-9_]+)"
)


@dataclass
class Issue:
    level: str          # error | warning
    rule_id: Optional[str]
    message: str


def validate_rules(rules: list[Rule]) -> list[Issue]:
    """校验规则列表，返回问题清单（空 = 全部通过）。"""
    issues: list[Issue] = []

    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()

    for r in rules:
        rid = r.id

        # 1. id 唯一
        if r.id in seen_ids:
            issues.append(Issue("error", rid, f"重复的规则 ID：{r.id}"))
        seen_ids.add(r.id)

        # 2. severity 合法
        if r.severity not in SEVERITY_LEVELS:
            issues.append(Issue("error", rid, f"非法严重度：{r.severity}"))

        # 3. keyword 非空
        if not r.keyword or not r.keyword.strip():
            issues.append(Issue("error", rid, "关键词为空"))

        # 4. 同 (keyword, source, platform, match_mode) 重复
        if r.match_mode == "exact":
            key = (r.keyword, r.source, tuple(r.platforms), r.match_mode)
            if key in seen_keys:
                issues.append(Issue("warning", rid,
                                    f"重复规则：{r.keyword} / {r.source} / {r.platforms}"))
            seen_keys.add(key)

        # 5. match_mode 合法
        if r.match_mode not in VALID_MATCH_MODES:
            issues.append(Issue("error", rid, f"非法匹配模式：{r.match_mode}"))

        # 6. replacements 类型
        if not isinstance(r.replacements, list):
            issues.append(Issue("error", rid, "replacements 必须是列表"))

        # 7. 用户可见文案不得混入内部台账（见 _INTERNAL_MARKERS 的说明）
        for fname in ("note", "suggestion", "law_ref"):
            val = getattr(r, fname, "") or ""
            if _INTERNAL_MARKERS.search(val):
                issues.append(Issue(
                    "error", rid,
                    f"{fname} 混入了内部维护痕迹（{val[:40]}…）——"
                    f"定级理由请写进提交信息或复核台账",
                ))

    return issues


def is_clean(rules: list[Rule]) -> bool:
    """无 error 级问题即为通过。"""
    return not any(i.level == "error" for i in validate_rules(rules))
