#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库时效检查：这是这个项目**最大的真实风险**，所以做成能失败的门禁。

问题
----
检测准确率再高，也只对"词库写下那天"的规则成立。平台规则几个月一改，
行业监管口径随政策走，而词库是个静态文件——它会**安静地过期**。
功能不会报错，测试不会变红，页面照常给出分数，只是这个分数开始失真。

这是所有"规则驱动型工具"共同的死法：不是死于做不出来，是死于没人维护。

做法
----
`rules/review_log.json` 记录每个来源的：依据、上次复核日、复核周期、复核要点。
本脚本把台账与实际词库对账，超期就返回退出码 1，进 CI ——
**不依赖"我记得去复核"这种机制。**

同时检查两类台账本身的腐坏：
* 词库里有、台账里没有的来源（新加词库忘了登记）
* 台账里有、词库里没有的来源（删了词库没销账）

用法::

    python scripts/check_rule_freshness.py            # 检查（CI 用）
    python scripts/check_rule_freshness.py --today 2027-01-01   # 模拟某天
    python scripts/check_rule_freshness.py --json     # 机器可读
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from guardian.rulebank import RuleBank  # noqa: E402

_LOG = _ROOT / "rules" / "review_log.json"

#: 剩余有效期低于此比例时给出"临近复核"提醒（不算失败）
DUE_SOON_RATIO = 0.2


def load_log(path: Path = _LOG) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"找不到复核台账 {path}——请先建立 rules/review_log.json"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def audit(today: date, log_path: Path = _LOG) -> dict:
    """对账并返回结构化结果（不打印、不退出，便于测试直接调用）。"""
    log = load_log(log_path)
    sources_meta = log.get("sources", {})

    # 实际词库里的来源 → 规则条数
    counts: dict[str, int] = {}
    for r in RuleBank().all:
        counts[r.source] = counts.get(r.source, 0) + 1

    rows = []
    for src, meta in sorted(sources_meta.items()):
        reviewed = _parse_day(meta["last_reviewed"])
        interval = int(meta["review_interval_days"])
        elapsed = (today - reviewed).days
        remaining = interval - elapsed
        if remaining < 0:
            status = "overdue"
        elif remaining <= interval * DUE_SOON_RATIO:
            status = "due_soon"
        else:
            status = "ok"
        rows.append({
            "source": src,
            "label": meta.get("label", src),
            "basis": meta.get("basis", ""),
            "note": meta.get("note", ""),
            "last_reviewed": meta["last_reviewed"],
            "review_interval_days": interval,
            "elapsed_days": elapsed,
            "remaining_days": remaining,
            "status": status,
            "rule_count": counts.get(src, 0),
        })

    unregistered = sorted(set(counts) - set(sources_meta))
    orphaned = sorted(s for s, n in counts.items()
                      if s in sources_meta and n == 0)
    return {
        "today": today.isoformat(),
        "rows": rows,
        "unregistered": unregistered,
        "orphaned": orphaned,
        "overdue": [r["source"] for r in rows if r["status"] == "overdue"],
    }


_STATUS_LABEL = {"ok": "有效", "due_soon": "临近复核", "overdue": "已过期"}


def report(result: dict) -> int:
    print(f"=== 词库时效检查（基准日 {result['today']}）===")
    print()
    header = f"{'来源':<26}{'规则':>5}  {'上次复核':<12}{'周期':>5}{'已过':>5}{'剩余':>6}  状态"
    print(header)
    print("-" * len(header))
    for r in result["rows"]:
        mark = {"ok": "✓", "due_soon": "!", "overdue": "✗"}[r["status"]]
        print(f"{r['source']:<26}{r['rule_count']:>5}  {r['last_reviewed']:<12}"
              f"{r['review_interval_days']:>5}{r['elapsed_days']:>5}"
              f"{r['remaining_days']:>6}  {mark} {_STATUS_LABEL[r['status']]}")

    failed = False

    if result["overdue"]:
        failed = True
        print()
        print("[失败] 以下来源已超出复核周期，词库可能已失真：")
        for src in result["overdue"]:
            row = next(r for r in result["rows"] if r["source"] == src)
            print(f"  · {row['label']}（{src}）已超期 {-row['remaining_days']} 天")
            print(f"    依据：{row['basis']}")
            if row["note"]:
                print(f"    复核要点：{row['note']}")
        print()
        print("  复核完成后，更新 rules/review_log.json 里对应来源的 last_reviewed。")

    due = [r for r in result["rows"] if r["status"] == "due_soon"]
    if due:
        print()
        print("[提醒] 以下来源临近复核期：")
        for r in due:
            print(f"  · {r['label']}（{r['source']}）还剩 {r['remaining_days']} 天")

    if result["unregistered"]:
        failed = True
        print()
        print("[失败] 词库里存在但台账未登记的来源（新加词库忘了登记？）：")
        for src in result["unregistered"]:
            print(f"  · {src}")

    if result["orphaned"]:
        print()
        print("[提醒] 台账里登记了但词库中已无规则的来源（删了词库没销账？）：")
        for src in result["orphaned"]:
            print(f"  · {src}")

    if not failed:
        print()
        print("所有来源均在复核周期内。")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="检查词库时效")
    ap.add_argument("--today", help="以指定日期为准（YYYY-MM-DD），便于测试")
    ap.add_argument("--log", default=str(_LOG), help="复核台账路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    today = _parse_day(args.today) if args.today else date.today()
    result = audit(today, Path(args.log))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if (result["overdue"] or result["unregistered"]) else 0
    return report(result)


if __name__ == "__main__":
    sys.exit(main())
