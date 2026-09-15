#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库加固（幂等）：救活死规则 + 补齐缺失规则 + 校准明确违法表述的严重度。

为什么需要
----------
用「中立语料误报扫描」把误报从 74% 压到 3% 之后，误报不再是主要矛盾，
**漏检**成了主要矛盾。用 30 条真实违规风格文案实测发现三类问题：

1. **死规则**（最讽刺的一类）：规则库里躺着 6 条含 ``X`` 占位符的规则，
   例如 ``保证X天获批``。它们永远不会匹配任何真实文本，只负责把
   "规则总数"撑好看。而 ``保证3个月出签`` 恰好是移民行业最高频的
   违规表述之一 —— 词库里有它的"影子"，却抓不到它。
2. **缺失规则**：``现成雇主``（README 里宣传过、词库里其实没有）、
   ``最后一波`` / ``名额有限``（稀缺营销话术）在库中完全缺失。
3. **严重度失准**：``全网最低`` / ``百分百`` 这类《广告法》第九条与
   《价格法》明令禁止的表述被标成 ``medium``（低危建议），
   用户会在"中风险 78 分"的宽松观感里忽略真正的红线。

本次操作
--------
* **revive**：把含占位符的死规则改写为等价正则，让它真能命中；
* **add**：补齐上述缺失的高频违规表达（行业包 / 通用营销）；
* **bump**：把有明确法条依据的表述从 medium 提到 high。

设计原则
--------
* **幂等**：可反复运行。已加固过的项不会重复插入（按 keyword 去重）。
* **可追溯**：每条新增/改写都写明理由，见下方常量。
* **可预览**：``--dry-run`` 只打印将要发生的改动，不写文件。

用法::

    python scripts/harden_rulebank.py --dry-run   # 预览
    python scripts/harden_rulebank.py             # 应用
    python scripts/harden_rulebank.py --report    # 只统计死规则
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RULES = _ROOT / "rules"

# ============================================================ 1. 救活死规则
#
# 键 = 原 keyword（含占位符，永不命中）；值 = (正则, 说明, 严重度覆盖)
#
# 正则刻意收窄到"占位符附近的真实表述"，避免复活成新的误报源。
# 例：`保证X天获批` 只覆盖"保证" + 数字 + 时间单位 + 结果动词，
#     不会波及"保证材料真实"这类正常表述。
#
# 严重度覆盖为 None 时保持原值；给出值时一并改写 —— 死规则往往连
# 严重度也是错的（"保证X天获批"原本是提示级，而它对移民行业是
# 虚假承诺，属高危）。
REVIVE: dict[str, tuple[str, str, str | None]] = {
    # —— 移民行业：时间承诺（最高频违规表述之一）——
    "保证X天获批": (
        r"保证\s*[\d一二三四五六七八九十两]+\s*(?:天|周|个?月|年)\s*(?:内)?\s*"
        r"(?:获批|下签|出签|拿到|批下来|搞定|办好|完成)",
        "时间承诺：把'保证X天获批'从占位符死规则改写成等价正则，"
        "覆盖'保证3个月出签'这类真实表述",
        "high",  # 移民语境下承诺获批时间＝虚假承诺，不是"提示"
    ),
    # —— 平台虚假种草：人群 + 夸大推荐 ——
    "我家XX": (
        r"我家\S{0,6}(?:好用到哭|无限回购|闭眼入|必入|吹爆|绝了|yyds)",
        "虚假种草：占位符→正则，覆盖'我家这款好用到哭'类表述",
        None,
    ),
    "学生党XX": (
        r"学生党\S{0,6}(?:必入|必备|神器|闭眼入|平价|宝藏)",
        "虚假种草：占位符→正则",
        None,
    ),
    "上班族XX": (
        r"上班族\S{0,6}(?:必入|必备|神器|闭眼入|平价|宝藏)",
        "虚假种草：占位符→正则",
        None,
    ),
    "宝妈XX": (
        r"宝妈\S{0,6}(?:必入|必备|神器|闭眼入|平价|宝藏)",
        "虚假种草：占位符→正则",
        None,
    ),
    "敏感肌XX": (
        r"敏感肌\S{0,6}(?:必入|必备|可用|闭眼入|平价|宝藏)",
        "虚假种草：占位符→正则",
        None,
    ),
}

# ============================================================ 2. 补齐缺失规则

#: 移民行业包新增规则：雇主担保红线 + 稀缺营销
ADD_IMMIGRATION: list[dict] = [
    # —— 雇主担保红线：'现成雇主'是行业黑话，暗示挂靠/买卖担保资格 ——
    {
        "keyword": "现成雇主",
        "category": "雇主担保红线",
        "severity": "critical",
        "suggestion": "删除'现成雇主'表述，改为'协助匹配合规雇主'",
        "note": "补充规则：现成雇主暗示挂靠担保资格，属违法操作",
    },
    {
        "keyword": "现成岗位",
        "category": "雇主担保红线",
        "severity": "critical",
        "suggestion": "删除'现成岗位'表述",
        "note": "补充规则：暗示买卖担保资格",
    },
    {
        "keyword": "现成担保",
        "category": "雇主担保红线",
        "severity": "critical",
        "suggestion": "删除'现成担保'表述",
        "note": "补充规则：暗示买卖担保资格",
    },
    # —— 稀缺营销：制造名额紧张感，属引诱消费 ——
    {
        "keyword": "名额有限",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "改为客观说明剩余名额或删除紧迫感话术",
        "note": "补充规则：稀缺营销话术",
    },
    {
        "keyword": "最后一波",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除稀缺营销话术",
        "note": "补充规则：稀缺营销话术",
    },
    {
        "keyword": "最后一轮",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除稀缺营销话术",
        "note": "补充规则：稀缺营销话术",
    },
    {
        "keyword": "错过再等一年",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除紧迫感话术",
        "note": "补充规则：稀缺营销话术",
    },
    {
        "keyword": r"仅剩\s*\d+\s*个?名额",
        "match_mode": "regex",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除稀缺营销话术",
        "note": "补充规则：正则覆盖'仅剩3个名额'类表述",
    },
    # —— 挂靠类：字面词「挂靠雇主 / 挂靠公司」抓不到广告式表述 ——
    #
    # 发现路径：2026-09-15 写 Web 冒烟测试时用了一条真实语料
    # 「现成雇主资源，挂靠即可递交，内部名额还剩几个」，结果只报 1 处。
    # 根因是词库里的挂靠规则是**词组精确匹配**（挂靠雇主 / 挂靠公司），
    # 只要"挂靠"后面不接这两个词就绕过去了 —— 而这恰恰是最常见的写法。
    #
    # 刻意**不裸收「挂靠」二字**：那样"警惕挂靠骗局""挂靠是违法的"
    # 这类警示内容也会被误报，而本项目的第一原则是误报率必须为 0
    # （误报高的工具运营第三天就不用了）。所以收窄到"挂靠 + 结果动词"，
    # 即广告语态才命中。
    {
        "keyword": (
            r"挂靠(?:即可|就能|就?可以|马上|直接)?"
            # 交替项按"长词在前"排列：Python/JS 的正则交替是取首个匹配，
            # 若把「办」排在「办理」前面，只会highlight到"挂靠办"这种截断结果。
            r"(?:递交|申请|移民|获得|办理|服务|通道|名额|获批|拿|办)"
        ),
        "match_mode": "regex",
        "category": "雇主担保红线",
        "severity": "critical",
        "suggestion": "删除'挂靠'相关表述，改为'协助匹配合规雇主并全程跟进'",
        "note": "补充规则：挂靠担保资格属违法操作。用正则覆盖'挂靠即可递交'"
                "这类不接'雇主/公司'的广告式表述",
    },
]

#: 通用广告法新增规则（行业无关的稀缺营销）
ADD_AD_LAW: list[dict] = [
    {
        "keyword": "最后一波",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除稀缺营销话术",
        "note": "补充规则：稀缺营销话术（通用）",
    },
    {
        "keyword": "错过再等一年",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "删除紧迫感话术",
        "note": "补充规则：稀缺营销话术（通用）",
    },
    {
        "keyword": r"限时\s*[\d一二三四五六七八九十]+\s*(?:小时|天|分钟)",
        "match_mode": "regex",
        "category": "引诱消费",
        "severity": "medium",
        "suggestion": "改为客观的活动时间说明",
        "note": "补充规则：正则覆盖'限时24小时'类紧迫感表述",
    },
]

# ============================================================ 3. 严重度校准
#
# 只收录**有明确法条依据**的表述，不做主观提级。
# 《广告法》第九条：禁止"国家级、最高级、最佳"等用语；
# 《价格法》第十四条 / 《反不正当竞争法》第八条：禁止虚假的"最低价"宣称。
BUMP_TO_HIGH: dict[str, str] = {
    "全网最低": "《广告法》第九条 + 《价格法》：虚假最低价宣称，属明确法律风险",
    "全国最低": "《广告法》第九条 + 《价格法》：虚假最低价宣称",
    "史上最低": "《广告法》第九条：绝对化用语",
    "百分百": "《广告法》第九条：绝对化保证，属明确法律风险",
}


# ============================================================ 执行


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _is_regex_rule(rule: dict) -> bool:
    return rule.get("match_mode") == "regex"


def find_dead_rules() -> list[tuple[Path, str]]:
    """扫描全部规则文件，列出含 X 占位符的死规则。"""
    dead: list[tuple[Path, str]] = []
    for path in sorted(_RULES.rglob("*.json")):
        if path.name == "pack.json":
            continue
        data = _load(path)
        groups = (
            [data]
            if isinstance(data, list)
            else [v for v in data.values() if isinstance(v, list)]
        )
        for group in groups:
            for rule in group:
                if not isinstance(rule, dict) or _is_regex_rule(rule):
                    continue
                if re.search(r"X{1,2}", rule.get("keyword", "")):
                    dead.append((path, rule["keyword"]))
    return dead


def _iter_groups(path: Path, data):
    """统一迭代：(容器, 索引或键, 规则 dict)。"""
    if isinstance(data, list):
        for i, rule in enumerate(data):
            yield data, i, rule
    else:
        for key, group in data.items():
            if isinstance(group, list):
                for i, rule in enumerate(group):
                    yield group, i, rule


def apply(dry_run: bool = False) -> dict:
    """执行加固。返回统计结果。"""
    stats = {"revived": 0, "added": 0, "bumped": 0, "files": 0}

    for path in sorted(_RULES.rglob("*.json")):
        if path.name == "pack.json":
            continue
        data = _load(path)
        changed = False
        filename = path.name

        # ---- 1) 救活死规则：改写为等价正则 ----
        for group, i, rule in list(_iter_groups(path, data)):
            if not isinstance(rule, dict) or _is_regex_rule(rule):
                continue
            kw = rule.get("keyword", "")
            if kw in REVIVE:
                pattern, reason, sev = REVIVE[kw]
                rule["keyword"] = pattern
                rule["match_mode"] = "regex"
                rule["note"] = f"{rule.get('note', '')}｜{reason}".strip("｜")
                if sev:
                    rule["severity"] = sev
                stats["revived"] += 1
                changed = True

        # ---- 2) 补齐缺失规则 ----
        additions: list[dict] = []
        if filename == "rules.json" and path.parent.name == "immigration":
            additions = ADD_IMMIGRATION
        elif filename == "ad_law.json":
            additions = ADD_AD_LAW

        if additions and isinstance(data, list):
            existing = {r.get("keyword") for r in data if isinstance(r, dict)}
            for rule in additions:
                if rule["keyword"] in existing:
                    continue
                data.append(json.loads(json.dumps(rule)))  # 深拷贝，避免共享引用
                existing.add(rule["keyword"])
                stats["added"] += 1
                changed = True

        # ---- 3) 严重度校准 ----
        for _group, _i, rule in _iter_groups(path, data):
            if not isinstance(rule, dict):
                continue
            kw = rule.get("keyword", "")
            if kw in BUMP_TO_HIGH and rule.get("severity") != "high":
                rule["severity"] = "high"
                rule["note"] = (
                    f"{rule.get('note', '')}｜严重度校准：{BUMP_TO_HIGH[kw]}"
                ).strip("｜")
                stats["bumped"] += 1
                changed = True

        if changed:
            stats["files"] += 1
            print(f"  {'（预览）' if dry_run else ''}更新 {path.relative_to(_ROOT)}")
            if not dry_run:
                _save(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="词库加固（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    parser.add_argument("--report", action="store_true", help="只报告死规则")
    args = parser.parse_args()

    if args.report:
        dead = find_dead_rules()
        print(f"死规则（含 X 占位符，永不命中）：{len(dead)} 条")
        for path, kw in dead:
            print(f"  {path.relative_to(_ROOT)}  ::  {kw}")
        return 0

    print("词库加固" + ("（预览模式）" if args.dry_run else ""))
    stats = apply(dry_run=args.dry_run)
    print(
        f"完成：救活死规则 {stats['revived']} 条 · "
        f"新增规则 {stats['added']} 条 · 严重度校准 {stats['bumped']} 条 · "
        f"涉及文件 {stats['files']} 个"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
