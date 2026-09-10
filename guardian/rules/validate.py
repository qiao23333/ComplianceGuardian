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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from guardian.schema import Rule, SEVERITY_LEVELS, VALID_MATCH_MODES


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

    return issues


def is_clean(rules: list[Rule]) -> bool:
    """无 error 级问题即为通过。"""
    return not any(i.level == "error" for i in validate_rules(rules))
