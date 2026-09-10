#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""替换词覆盖表生成脚本。

扫描 rules/ 词库（ad_law / platform_rules / blue_v_only / user_custom /
industry_packs），从每条规则的 suggestion 文本中解析出**显式替换词**，
汇总成 `rules/overrides/replacements.json`（关键词 → 替换词列表）。

为什么不改词库本体
------------------
`rules/` 是运行时唯一数据源（桌面端"词库管理"直接编辑它）。
替换词属"派生数据"，单独放覆盖表，重新生成不会覆盖用户对词库的编辑。

安全策略
--------
* 只有能从 suggestion 解析出**显式替换**且规则允许自动改写时才收录，
  否则不收录 → 引擎绝不自动改写（与 P0 防线一致）。
* 单字极限词 allow_auto_replace=False（Rule.from_legacy 已处理）→ 跳过。

用法
----
    python scripts/migrate_from_v24.py
    python scripts/migrate_from_v24.py --src rules
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guardian.rulebank import RuleBank
from guardian.rules.validate import validate_rules


# 从 suggestion 文本提取显式替换词：改为'X' / 替换为"X" / 替换成X
_REPL_PATTERNS = [
    re.compile(r"改为['\"](.+?)['\"]"),
    re.compile(r"替换[为成]['\"]?(.+?)['\"]?"),
    re.compile(r"建议[用采使]['\"]?(.+?)['\"]?"),
]


def extract_replacement(suggestion: str) -> list[str]:
    if not suggestion:
        return []
    for pat in _REPL_PATTERNS:
        m = pat.search(suggestion)
        if m:
            cand = m.group(1).strip().strip("'\"。，,.").strip()
            # 只接受短替换（避免把整句建议当替换词）
            if 0 < len(cand) <= 8:
                return [cand]
    return []


def migrate(rules_dir: Path) -> dict:
    """扫描 rules/ 词库，从 suggestion 提取替换词，写出覆盖表。"""
    bank = RuleBank(rules_dir)

    # 提取每个关键词的显式替换词（仅当规则允许自动改写）
    replacements: dict[str, list] = {}
    for r in bank.all:
        if not r.allow_auto_replace:
            continue
        repl = extract_replacement(r.suggestion)
        if repl:
            # 同关键词保留首个非空（冲突时以先出现者为准）
            replacements.setdefault(r.keyword, repl)

    # 校验
    issues = validate_rules(bank.all)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    # 写出覆盖表：rules/overrides/replacements.json
    out_dir = rules_dir / "overrides"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "replacements.json"
    out.write_text(json.dumps(replacements, ensure_ascii=False, indent=2,
                              sort_keys=True), encoding="utf-8")

    return {
        "total": len(bank.all),
        "errors": len(errors),
        "warnings": len(warnings),
        "with_replacements": len(replacements),
        "out": out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从 rules/ 旧词库的 suggestion 提取替换词覆盖表")
    ap.add_argument("--src", default="rules", help="词库目录（默认 rules/）")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    src = (root / args.src) if not Path(args.src).is_absolute() else Path(args.src)

    if not src.is_dir():
        print(f"[错误] 源目录不存在：{src}", file=sys.stderr)
        return 1

    report = migrate(src)

    print("=== 替换词覆盖表生成完成 ===")
    print(f"规则总数：{report['total']}")
    print(f"带自动替换词：{report['with_replacements']}")
    print(f"校验错误：{report['errors']}  警告：{report['warnings']}")
    print(f"输出：{report['out']}")

    if report["errors"]:
        print("\n[校验未通过] 存在 error 级问题，请检查后再启用。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
