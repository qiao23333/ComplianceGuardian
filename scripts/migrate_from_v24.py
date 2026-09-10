#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则迁移脚本：v2.4 遗留词库 → v3 新 schema。

读取 rules/ 下的遗留 JSON（ad_law / platform_rules / blue_v_only /
user_custom / industry_packs），经 Rule.from_legacy 统一转换成带稳定 ID、
四级严重度、结构化 replacements 的 v3 规则，按来源写入 rules_v3/。

安全策略
--------
* 自动改写只在校验器能从 suggestion 中解析出**显式单替换**时才开启，
  否则 replacements 留空 → 引擎绝不自动改写（与 P0 防线一致，避免"近很多人"事故）。
* 单字极限词强制 allow_auto_replace=False（Rule.from_legacy 已处理）。

用法
----
    python scripts/migrate_from_v24.py            # 默认从 rules/ 迁移到 rules_v3/
    python scripts/migrate_from_v24.py --src rules --dst rules_v3

仅生成文件、不改动线上词库；迁移后可人工 diff，确认无误再替换。
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
from guardian.schema import Rule


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


def migrate(src: Path, dst: Path) -> dict:
    """执行迁移，返回统计信息。"""
    bank = RuleBank(src)

    # 补全 replacements（来自 suggestion），写回 Rule 对象
    enriched: list[Rule] = []
    for r in bank.all:
        repl = extract_replacement(r.suggestion)
        # 只有在确实存在显式替换，且原文未被标记禁止改写时才启用
        if repl and r.allow_auto_replace:
            r = Rule(**{**r.__dict__, "replacements": repl})
        enriched.append(r)

    # 校验
    issues = validate_rules(enriched)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    # 按 source 分组写出
    dst.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[Rule]] = {}
    for r in enriched:
        key = r.source if not r.source.startswith("industry:") else "industry_packs"
        by_source.setdefault(key, []).append(r)

    written = []
    for source, rules in sorted(by_source.items()):
        out = dst / f"{source}.json"
        payload = [r.to_dict() for r in rules]
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        written.append((out.name, len(payload)))

    report = {
        "total": len(enriched),
        "files": written,
        "errors": len(errors),
        "warnings": len(warnings),
        "with_replacements": sum(1 for r in enriched if r.replacements),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="v2.4 词库 → v3 schema 迁移")
    ap.add_argument("--src", default="rules", help="源词库目录（默认 rules/）")
    ap.add_argument("--dst", default="rules_v3", help="目标目录（默认 rules_v3/）")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    src = (root / args.src) if not Path(args.src).is_absolute() else Path(args.src)
    dst = (root / args.dst) if not Path(args.dst).is_absolute() else Path(args.dst)

    if not src.is_dir():
        print(f"[错误] 源目录不存在：{src}", file=sys.stderr)
        return 1

    report = migrate(src, dst)

    print("=== 迁移完成 ===")
    print(f"规则总数：{report['total']}")
    print(f"带自动替换词：{report['with_replacements']}")
    print(f"校验错误：{report['errors']}  警告：{report['warnings']}")
    print("产出文件：")
    for name, n in report["files"]:
        print(f"  - {name} ({n} 条)")
    print(f"输出目录：{dst}")

    if report["errors"]:
        print("\n[校验未通过] 存在 error 级问题，请检查后再启用。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
