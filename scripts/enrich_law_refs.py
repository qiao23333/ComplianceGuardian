#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给行业词库补上法规条款号（law_ref）。

为什么需要一个脚本而不是手改 JSON
--------------------------------
合规工具说"这个词违规"却不给条款号，等于把举证责任推回给用户。
但**补条款号不等于随手补**：给错法条比不给我更糟——用户拿着错的
依据去跟平台/法务对话，会把事情办坏。

所以这里的做法是：把"哪个类别对应哪一条"写成一张**显式映射表**，
连同判定理由一起放在代码里，可审阅、可追溯、可复跑（幂等）。
映射表之外的类别一律留空，宁可显示"该来源暂无条款依据"，
也不猜。

映射依据
--------
主词库 `rules/ad_law.json` 里已经存在"类别 → 条款"的既有口径，
本脚本只做**对齐**，不发明新映射：

* 极限词        → 《广告法》第九条       （主词库该类别 99% 指向此条）
* 虚假宣传      → 《广告法》第二十八条   （主词库该类别 100% 指向此条）

行业包里的 虚假承诺 / 成功率宣传 / 虚假资质 / 入籍承诺 等类别，
语义上都落在"以虚假或引人误解的内容欺骗、误导消费者"上，
即《广告法》第二十八条对"虚假广告"的定义，故并入同一映射。
特指医疗效果的承诺不在此列（行业包不含该类）。

刻意留空的类别
--------------
* 雇主担保红线 / 违法操作 / 关系暗示：指向买卖 offer、挂靠、走后门等
  行为，性质更接近未经许可经营或欺诈，不属于广告法调整范围。
  给它们挂一条广告法条款反而是错的。
* 学术不端 / 引诱消费 / 费用承诺 / 时间承诺 / 过程简化：跨类别语义分散，
  无法安全地归到单一条款。

用法::

    python scripts/enrich_law_refs.py --dry-run   # 预览
    python scripts/enrich_law_refs.py             # 写入
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PACKS_DIR = _ROOT / "rules" / "industry_packs"

#: 类别 → 条款号。只收录语义单一、能对上主词库既有口径的类别。
CATEGORY_LAW_REF: dict[str, str] = {
    # —— 与主词库既有口径直接对齐 ——
    "综合极限词": "《广告法》第九条",
    "极限词": "《广告法》第九条",
    "虚假宣传": "《广告法》第二十八条",
    # —— 语义落入"虚假广告"定义的行业专有类别 ——
    "虚假承诺": "《广告法》第二十八条",
    "成功率宣传": "《广告法》第二十八条",
    "虚假资质": "《广告法》第二十八条",
    "入籍承诺": "《广告法》第二十八条",
}

#: 明确不补的类别 + 理由（打印在报告里，避免下次又有人来补）
INTENTIONALLY_EMPTY: dict[str, str] = {
    "雇主担保红线": "指向买卖 offer / 挂靠，属经营许可与欺诈范畴，非广告法调整对象",
    "违法操作": "同上",
    "关系暗示": "指向「走后门」，性质是欺诈而非广告表述",
    "学术不端": "跨代写 / 保过 / 篡改成绩等多类，无法归到单一条款",
    "引诱消费": "跨类别语义分散",
    "费用承诺": "跨类别语义分散",
    "时间承诺": "跨类别语义分散",
    "过程简化": "跨类别语义分散",
}


def enrich_file(path: Path, dry_run: bool) -> tuple[int, int, Counter]:
    """给单个 rules.json 补 law_ref。返回 (补充条数, 跳过条数, 各类别计数)。"""
    raw = path.read_text(encoding="utf-8")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        return 0, 0, Counter()

    filled = 0
    skipped = 0
    stats: Counter = Counter()

    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("law_ref"):
            skipped += 1                      # 已有依据，绝不覆盖
            continue
        law = CATEGORY_LAW_REF.get(r.get("category", ""))
        if not law:
            skipped += 1
            continue
        r["law_ref"] = law
        filled += 1
        stats[r.get("category", "?")] += 1

    if filled and not dry_run:
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return filled, skipped, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="给行业词库补法规条款号")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写入")
    args = ap.parse_args()

    targets = sorted(_PACKS_DIR.rglob("rules.json"))
    if not targets:
        print(f"[失败] 在 {_PACKS_DIR} 下没找到 rules.json")
        return 1

    total_filled = 0
    for path in targets:
        filled, skipped, stats = enrich_file(path, args.dry_run)
        total_filled += filled
        rel = path.relative_to(_ROOT)
        print(f"--- {rel} ---")
        print(f"    补充 {filled} 条 / 跳过 {skipped} 条（已有依据或无可安全映射）")
        for cat, n in stats.most_common():
            print(f"      {cat:<12} +{n}  → {CATEGORY_LAW_REF[cat]}")

    print()
    if args.dry_run:
        print(f"[预览] 共可补充 {total_filled} 条（未写入，去掉 --dry-run 生效）")
    else:
        print(f"[完成] 共补充 {total_filled} 条")

    print("\n以下类别刻意留空（不猜法条）：")
    for cat, why in INTENTIONALLY_EMPTY.items():
        print(f"  · {cat}：{why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
