#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行业包门禁：可插拔扩展的代价，必须有东西兜住。

行业包是"丢两个文件就成立一个新行业"的设计（``rules/industry_packs/<id>/``
下放 ``pack.json`` 与 ``rules.json`` 即可）。好处是扩行业零成本，代价是
**没有任何东西拦得住一个坏包**：

* 目录名与 pack.json 里的 id 对不上 —— 前端按 id 注册来源标签，对不上就显示不出
* pack.json 手写的 rule_count 与 rules.json 实际条数不符 —— 选择器上一直是错的
* 新包抄了旧库已有的词 —— 同一处命中挂两个来源，用户说不清按哪条算分

这些都不报错，只会安静地把错误结论端给用户。所以在这里逐条守住。

2026-09-15 真踩过第三条的前身：pack.json 写 rule_count=140、实际 179，
前端选择器上的数字一直没人发现是错的。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guardian.rulebank import RuleBank

_ROOT = Path(__file__).resolve().parent.parent
_PACK_DIR = _ROOT / "rules" / "industry_packs"
_REVIEW_LOG = _ROOT / "rules" / "review_log.json"

_PACKS = sorted(p for p in _PACK_DIR.iterdir() if p.is_dir()) if _PACK_DIR.is_dir() else []
_PACK_IDS = [p.name for p in _PACKS]

#: 行业包之外的"旧库"。新包不得与它们撞关键词。
_LEGACY_SOURCES = {
    "ad_law", "regex", "blue_v", "platform", "immigration", "study_abroad",
}
_ALLOWED_SEVERITY = {"critical", "high", "medium", "low"}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _meta(pid: str) -> dict:
    return _read(_PACK_DIR / pid / "pack.json")


def _pack_rules(pid: str) -> list[dict]:
    return _read(_PACK_DIR / pid / _meta(pid)["rules_file"])


def test_pack_dir_is_not_empty():
    assert _PACKS, f"一个行业包都没找到：{_PACK_DIR}"


@pytest.mark.parametrize("pack_dir", _PACKS, ids=_PACK_IDS or ["(无)"])
def test_pack_meta_is_complete_and_consistent(pack_dir: Path):
    """pack.json 字段要齐，且与目录名、实际条数一致。"""
    meta = _read(pack_dir / "pack.json")
    for key in ("id", "name", "short", "industry", "version", "rules_file"):
        assert meta.get(key), f"{pack_dir.name}/pack.json 缺字段 {key}"

    # 目录名就是 source id：前端靠它注册来源标签，台账靠它登记时效
    assert meta["id"] == pack_dir.name, (
        f"pack.json 的 id={meta['id']} 与目录名 {pack_dir.name} 不一致"
    )
    # short 必须显式写进 pack.json，不能靠"名称去掉'合规包'三个字"拼出来 ——
    # 那样改一次名称，界面上所有来源标签都会跟着漂
    assert len(meta["short"]) <= 4, f"短名太长，界面上会挤：{meta['short']}"

    rules = _read(pack_dir / meta["rules_file"])
    assert isinstance(rules, list) and rules, f"{pack_dir.name} 的规则不是非空数组"
    assert meta["rule_count"] == len(rules), (
        f"{pack_dir.name}/pack.json 写 rule_count={meta['rule_count']}，"
        f"实际 {len(rules)} 条"
    )


@pytest.mark.parametrize("pack_dir", _PACKS, ids=_PACK_IDS or ["(无)"])
def test_pack_rules_are_well_formed(pack_dir: Path):
    """每条规则的字段、等级、类别都要说得通。"""
    meta = _read(pack_dir / "pack.json")
    rules = _read(pack_dir / meta["rules_file"])
    declared = set(meta.get("categories") or [])

    missing_law, bad_sev, off_cat, dup = [], [], [], []
    seen = set()
    for i, r in enumerate(rules):
        kw = r.get("keyword")
        assert kw, f"{pack_dir.name} 第 {i} 条缺 keyword"
        if kw in seen:
            dup.append(kw)
        seen.add(kw)
        if not r.get("law_ref"):
            missing_law.append(kw)
        if r.get("severity") not in _ALLOWED_SEVERITY:
            bad_sev.append(f"{kw}={r.get('severity')}")
        if declared and r.get("category") not in declared:
            off_cat.append(f"{kw}→{r.get('category')}")

    assert not dup, f"{pack_dir.name} 包内重复关键词：{dup}"
    assert not bad_sev, f"{pack_dir.name} 等级非法：{bad_sev}"
    assert not missing_law, (
        f"{pack_dir.name} 有 {len(missing_law)} 条没写 law_ref：{missing_law[:5]}\n"
        "合规工具说'违规'还不够，得说清违反哪一条 —— 没依据的规则，"
        "用户既没法复核，也没法拿去跟平台或法务对话。"
    )
    assert not off_cat, (
        f"{pack_dir.name} 用了未在 pack.json.categories 里声明的类别：{off_cat[:5]}\n"
        "前端筛选器是照着 categories 渲染的，没声明的类别会筛不到。"
    )


def test_packs_do_not_collide_with_legacy_keywords():
    """新包不得与旧库撞关键词。

    撞词的后果不是"多一条规则"，而是**同一处命中挂两个来源**：界面上同一个
    词被判两遍，用户说不清按哪条算分，依据栏还会给出两条不同的法条。
    """
    bank = RuleBank(_ROOT / "rules")
    legacy: dict[str, str] = {}
    for r in bank.all:
        if r.source in _LEGACY_SOURCES:
            legacy.setdefault(r.keyword, r.source)

    hits = []
    for pid in _PACK_IDS:
        for r in _pack_rules(pid):
            src = legacy.get(r["keyword"])
            if src:
                hits.append(f"{r['keyword']}（{pid} ↔ {src}）")
    assert not hits, (
        f"{len(hits)} 条与旧库撞词：" + "；".join(hits[:10]) + "\n"
        "修法：从行业包里删掉它（旧库已覆盖），或换一条行业特有的说法。"
    )


def test_packs_do_not_collide_with_each_other():
    """行业包彼此也不能撞词 —— 用户可能同时勾选多个行业。"""
    seen: dict[str, str] = {}
    hits = []
    for pid in _PACK_IDS:
        for r in _pack_rules(pid):
            prev = seen.get(r["keyword"])
            if prev:
                hits.append(f"{r['keyword']}（{prev} ↔ {pid}）")
            else:
                seen[r["keyword"]] = pid
    assert not hits, f"行业包之间撞词 {len(hits)} 条：" + "；".join(hits[:10])


def test_every_pack_is_registered_in_review_log():
    """每个包都要在时效性台账里登记。

    没登记的包不会进过期复查清单 —— 它会一直留在词库里，而没人知道它上一次
    被人看过是什么时候。行业监管口径是会变的，不设复查期的规则等于在腐烂。
    """
    log = _read(_REVIEW_LOG)
    sources = log.get("sources") or {}
    assert sources, "review_log.json 里没读到 sources"
    missing = [pid for pid in _PACK_IDS if f"industry:{pid}" not in sources]
    assert not missing, (
        f"这些行业包没登记时效：{missing}\n"
        "补法：在 rules/review_log.json 的 sources 里加 industry:<id>，"
        "写清 basis 与 review_interval_days。"
    )


def test_bank_loads_every_pack():
    """RuleBank 必须真的把每个包都装进来。

    文件名写错、目录层级变了、rules.json 不是数组 —— 这些都会让某个包
    "静默消失"，而页面上只是少了几条规则，不会有任何报错。
    """
    bank = RuleBank(_ROOT / "rules")
    loaded: dict[str, int] = {}
    for r in bank.all:
        if r.source.startswith("industry:"):
            pid = r.source.split(":", 1)[1]
            loaded[pid] = loaded.get(pid, 0) + 1

    assert set(loaded) == set(_PACK_IDS), (
        f"加载到的行业包 {sorted(loaded)} 与磁盘上的 {_PACK_IDS} 不一致"
    )
    for pid in _PACK_IDS:
        assert loaded[pid] == len(_pack_rules(pid)), (
            f"{pid} 加载到 {loaded[pid]} 条，磁盘上有 {len(_pack_rules(pid))} 条"
        )
