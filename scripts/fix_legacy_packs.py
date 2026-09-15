#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 immigration / study_abroad 两个老包补依据、删与旧库撞名的词。

为什么单独写一个一次性脚本而不是手改
------------------------------------
要动 97 条 law_ref + 11 条撞名词，手改必错。而且改完要保证：

* 文件换行风格不变（rules.json 是 CRLF，pack.json 是 LF —— 搞混了整份文件
  都会变成 diff）
* 每类的 law_ref 与 note 一致（同类共享依据，是真事实而不是逐条编）
* 条数变化同步回 pack.json，否则前端选择器上的数字立刻错

用法：python scripts/fix_legacy_packs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BASE = _ROOT / "rules" / "industry_packs"

# ---------------------------------------------------------------- 依据映射
#
# 依据全部来自 2026-09-15 联网核实的现行有效条文：
#
# * 《国务院关于出境入境管理的规定》（国务院令第 841 号）—— 2026-07-22 公布，
#   **2026-09-15 起施行**。它把 2018 年取消资格认定之后一直是空白的出境入境
#   中介服务管了起来：第七条备案、第八条准入（含"境外企业不得在境内提供
#   出境入境中介服务"）、第十条六条禁令、第十一至十三条罚则。
#   旧台账里引的《因私出入境中介活动管理办法》随 2018 年资格认定取消已不再
#   作为准入依据，必须换掉。
# * 《广告法》第二十八条（虚假广告）／第二十四条（教育、培训广告不得对升学、
#   通过考试、获得学位学历或者合格证书作保证性承诺）／第九条（绝对化用语）／
#   第四条（不得含有虚假或引人误解的内容）。
# * 《刑法》第三百一十九条（骗取出境证件罪）、第二百八十四条之一（组织考试
#   作弊罪、代替考试罪）—— 这几类已经不是"违规文案"的问题，是刑事风险，
#   必须在依据里点明。

_IMM = {
    "费用承诺": (
        "《国务院关于出境入境管理的规定》第十条第一项；《广告法》第二十八条",
        "对能否办成、能否退费作保证性承诺，属虚假或引人误解的商业宣传",
    ),
    "时间承诺": (
        "《国务院关于出境入境管理的规定》第十条第一项；《广告法》第二十八条",
        "对办理时限作出保证性承诺，审核进度由主管机关决定，中介无权保证",
    ),
    "雇主担保红线": (
        "《国务院关于出境入境管理的规定》第十条第二项",
        "提供或协助提供虚假材料办理出境入境手续，属明令禁止行为",
    ),
    "违法操作": (
        "《国务院关于出境入境管理的规定》第十条第二项、第五项；"
        "《刑法》第三百一十九条",
        "以弄虚作假手段骗取签证、居留证件，可能构成骗取出境证件罪",
    ),
    "关系暗示": (
        "《国务院关于出境入境管理的规定》第十条第一项；《广告法》第二十八条",
        "暗示与主管机关存在特殊关系以招徕客户，属误导性宣传",
    ),
    "过程简化": (
        "《国务院关于出境入境管理的规定》第十条第一项；《广告法》第二十八条",
        "对办理难度与流程作不实简化承诺，与法定程序不符",
    ),
    "价格宣传": (
        "《广告法》第九条第三项",
        "使用'最低''最便宜'等绝对化用语描述价格，无从核实",
    ),
    "引诱消费": (
        "《广告法》第二十八条",
        "虚构名额紧俏、政策将变等信息诱导成交，属虚假广告",
    ),
}

_STU = {
    "费用承诺": (
        "《广告法》第二十四条第一项；《国务院关于出境入境管理的规定》第十条第一项",
        "对服务结果与退费作保证性承诺，教育服务广告明令禁止",
    ),
    "时间承诺": (
        "《广告法》第二十四条第一项",
        "对录取时限作出保证性承诺，录取由院校独立决定，中介无权保证",
    ),
    "学术不端": (
        "《广告法》第四条；《刑法》第二百八十四条之一",
        "代考、替考、伪造成绩单等属刑事犯罪，不是文案风险",
    ),
    "过程简化": (
        "《广告法》第二十四条第一项；《广告法》第二十八条",
        "对入学条件作不实承诺，误导性宣传",
    ),
}

_MAPS = {"immigration": _IMM, "study_abroad": _STU}

# ---------------------------------------------------------------- 撞名清理
#
# 这些词旧库（ad_law / blue_v_only）已经收录。行业包再收一遍的后果不是
# "多一条规则"，而是**同一处命中挂两个来源**：用户看到同一个词被判两遍，
# 说不清按哪条算分，依据栏还会给出两条不同法条。
#
# 「不成功退全款」是 immigration 与 study_abroad 之间撞：留移民包
# （那里有「不成功不收费」「拒签退全款」等更细的同族词），从留学包删。
_DROP = {
    "immigration": ["包过", "零风险", "无风险", "保本", "最便宜",
                    "行业领先", "最后一波", "错过再等一年"],
    "study_abroad": ["名校保录", "保分", "不成功退全款"],
}


def _load(path: Path):
    return json.loads(path.read_bytes().decode("utf-8"))


def _dump(path: Path, obj) -> None:
    """按文件原有的换行风格写回。

    rules.json 是 CRLF、pack.json 是 LF —— 统一成一种会让整份文件变成 diff，
    review 时根本看不出真正改了什么。
    """
    raw = path.read_bytes()
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def fix(pack_id: str) -> dict:
    pack_dir = _BASE / pack_id
    pack_path = pack_dir / "pack.json"
    rules_path = pack_dir / "rules.json"

    meta = _load(pack_path)
    rules = _load(rules_path)
    before = len(rules)

    mapping = _MAPS[pack_id]
    drop = set(_DROP[pack_id])

    unknown_cat = set()
    filled = 0
    kept = []
    for r in rules:
        if r["keyword"] in drop:
            continue
        if not r.get("law_ref"):
            cat = r.get("category")
            if cat not in mapping:
                unknown_cat.append(cat)
            else:
                law, note = mapping[cat]
                r["law_ref"] = law
                if not r.get("note"):
                    r["note"] = note
                filled += 1
        kept.append(r)

    if unknown_cat:
        raise SystemExit(
            f"{pack_id}: 这些类别没有依据映射，先补齐再跑：{sorted(set(unknown_cat))}"
        )

    kept.sort(key=lambda r: (r.get("category", ""), r["keyword"]))
    _dump(rules_path, kept)

    # 条数变了必须同步回 pack.json —— 前端选择器上的数字直接来自这里
    meta["rule_count"] = len(kept)
    meta["version"] = "1.1.0"
    meta["updated"] = "2026-09-15"
    if pack_id == "immigration":
        meta["description"] = (
            "移民 / 出境入境中介行业专属合规词库。覆盖费用与时限的保证性承诺、"
            "雇主担保红线、假结婚买签证等违法操作、暗示与主管机关有特殊关系等"
            "高风险表达。依据以 2026-09-15 起施行的《国务院关于出境入境管理的"
            "规定》（国务院令第 841 号）第十条六条禁令为主，涉及刑事风险的"
            "条目同步标注《刑法》条款。"
        )
        meta["version"] = "2.0.0"
    else:
        meta["description"] = (
            "留学 / 升学中介行业专属合规词库。覆盖录取与退费的保证性承诺、"
            "代考替考伪造材料等学术不端、对入学条件的不实承诺等高风险表达。"
            "依据《广告法》第二十四条及《刑法》第二百八十四条之一等现行条文。"
        )
        meta["version"] = "2.0.0"
    _dump(pack_path, meta)

    return {"pack": pack_id, "before": before, "after": len(kept),
            "filled": filled}


def main() -> int:
    for pid in _MAPS:
        res = fix(pid)
        print(f"{res['pack']}: {res['before']} → {res['after']} 条"
              f"（补依据 {res['filled']} 条，删撞名 {res['before'] - res['after']} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
