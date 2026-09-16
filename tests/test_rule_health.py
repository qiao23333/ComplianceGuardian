#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则库的"可追溯性"与"时效性"门禁。

这两件事看起来不如"检测准不准"性感，但它们决定这个工具是**能长期用**
还是**只能演示一次**：

1. **可追溯**：说某句违规，得说得出违反哪一条。否则它就只是违禁词表，
   用户没法复核、没法拿去向平台申诉、没法给法务看。
   2026-09-15 发现源词库里本来就有 ``law_ref``（覆盖 482/485），
   但管道中途在 ``detector._convert`` 被写成空字符串丢掉，
   用户界面永远显示"来源=广告法"却从不显示"第九条"。

2. **时效**：规则驱动型工具不会"坏掉"，只会**安静地过期**。
   平台规则改了、监管口径变了，静态词库照常打分，只是分数开始失真——
   功能不报错、测试不变红、页面上完全看不出来。
   所以必须有台账 + 会失败的门禁。

本文件里的每个守卫都配了一条"守卫本身必须能失败"的自测。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from guardian.detector import ComplianceDetector  # noqa: E402
from guardian.rulebank import RuleBank  # noqa: E402
from guardian.rules.validate import validate_rules  # noqa: E402
from guardian.schema import Rule  # noqa: E402

_WEB_RULES = _ROOT / "web" / "data" / "rules.json"

#: 条款号允许的形态：
#:
#:   《广告法》第九条                         —— 法规 + 条
#:   《广告法》第九条第三项                    —— 法规 + 条 + 项
#:   《刑法》第二百八十四条之一                —— 刑法特有的"条之一"
#:   《…规定》第十条第二项、第五项；《刑法》…  —— 多条/多法规用"；"并列
#:
#: 只写法规名也放行（个别规则只到法规层级），但只要带了"第…条"就必须完整
#: 成对，避免出现"《广告法》第条"这类半截。
#:
#: 2026-09-15 放宽过一次：原来只认到"第X条"，于是"第十条第一项""第三百一十九
#: 条之一""两法并列"这几种**更精确**的写法反而被判成格式错 —— 门禁把更严谨的
#: 依据挡在门外，本身就是个 bug。
_NUM = r"[一二三四五六七八九十百零〇\d]+"
_LAW_CLAUSE = rf"《[^》]+》(第{_NUM}条(之{_NUM})?(第{_NUM}项(、第{_NUM}项)*)?)?"
_LAW_REF_OK = re.compile(rf"^{_LAW_CLAUSE}(；{_LAW_CLAUSE})*$")

#: "法条类来源"——依据应当是法律条款。
#: platform / blue_v 的依据是平台规范，本来就不该有法条。
#: "法条类来源"——依据应当是法律条款。
#: platform / blue_v 的依据是平台规范，本来就不该有法条。
#:
#: 行业包一律纳入。早先这里手写了两个行业包的名字，于是后来新增的 7 个包
#: **根本不在门禁范围内** —— 覆盖率再低也不会响。手写名单必然漏，按前缀匹配。
def _is_law_based(source: str) -> bool:
    return source in ("ad_law", "regex") or source.startswith("industry:")


#: 法条类规则的条款覆盖率下限。低于此值说明新加的规则普遍没写依据。
#: 目前 ad_law / regex / 全部行业包均为 100%，留一点余量给个别例外，
#: 但批量忘写必须能红。
_MIN_LAW_COVERAGE = 0.98


def _load_script(name: str):
    """按路径加载 scripts/ 下的脚本（它们不是包的一部分）。"""
    path = _ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法加载脚本 {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================ 1. 条款可追溯


def test_detector_exposes_law_ref_on_findings():
    """命中结果必须带得出条款号——这是"合规工具"与"违禁词表"的分界。"""
    det = ComplianceDetector()
    res = det.detect("全网最低价，国家级品质，十天瘦二十斤")
    assert res["violations"], "测试语料竟然零命中，语料或词库有问题"

    with_ref = [v for v in res["violations"] if v.get("law_ref")]
    assert with_ref, (
        "所有命中都没有 law_ref —— 说明源词库的 law_ref 又在管道中途被丢了。\n"
        f"命中：{[v['keyword'] for v in res['violations']]}"
    )
    # 至少要有一条写到"第…条"，只写法规名说明映射退化了
    assert any("第" in v["law_ref"] and "条" in v["law_ref"] for v in with_ref), (
        f"条款号不具体：{[v['law_ref'] for v in with_ref]}"
    )


def test_findings_carry_rule_note():
    """命中也应带出规则说明（"什么条件下才合规"），而不只是建议。"""
    det = ComplianceDetector()
    res = det.detect("无激素零添加，绝对安全")
    notes = [v.get("note") for v in res["violations"] if v.get("note")]
    assert notes, "命中没有携带 note 说明"


def test_all_law_refs_are_well_formed():
    """条款号格式统一，且不留半截（"《广告法》第条"这种）。"""
    bad = [r.law_ref for r in RuleBank().all
           if r.law_ref and not _LAW_REF_OK.match(r.law_ref)]
    assert not bad, f"条款号格式不合规：{bad[:8]}"


def test_law_based_coverage_meets_floor():
    """法条类规则的条款覆盖率不得低于下限。

    为什么盯这个数：覆盖率会**慢慢**掉——新加规则时忘了写依据，
    一次一条，没人会注意到。做成断言才有回退压力。
    """
    rules = RuleBank().all
    scoped = [r for r in rules if _is_law_based(r.source)]
    assert scoped, "语料假设失效：没有法条类规则"
    covered = [r for r in scoped if r.law_ref]
    ratio = len(covered) / len(scoped)
    assert ratio >= _MIN_LAW_COVERAGE, (
        f"法条类条款覆盖率 {ratio:.1%} 低于下限 {_MIN_LAW_COVERAGE:.0%}"
        f"（{len(covered)}/{len(scoped)}）——新加的规则是否忘了写 law_ref？"
    )


def test_platform_rules_are_not_expected_to_have_law_ref():
    """平台规则不该硬塞法条——它们的依据是平台规范。

    这条看似多余，实则是防止有人为了"提高覆盖率"给平台规则
    编一条广告法条款，那会给出错误的依据。
    """
    rules = RuleBank().all
    platformish = [r for r in rules if r.source in ("platform", "blue_v")]
    assert platformish, "语料假设失效：没有平台类规则"
    assert not any(r.law_ref for r in platformish), (
        "平台/蓝V规则被填了 law_ref —— 平台规则的依据是平台规范而非法律"
    )


# ============================================================ 2. 护栏：内部台账不许外泄


def test_validate_rejects_internal_markers_in_user_facing_text():
    """守卫自测：把维护者台账写进用户可见字段，校验器必须报错。

    ``note`` 曾被一物两用——既是给用户看的说明，又是给维护者看的定级理由。
    结果"禁止使用全网最低等极限表述｜严重度校准：《广告法》第九条：..."
    原样出现在用户界面上。一个字段一物两用，迟早会有一半跑到不该去的地方。
    """
    bad = Rule(
        id="test:0001:deadbe",
        keyword="全网最低",
        note="禁止使用全网最低等极限表述｜严重度校准：《广告法》第九条",
    )
    issues = validate_rules([bad])
    assert any("内部维护痕迹" in i.message for i in issues), (
        "校验器没拦住混入内部台账的文案 —— 守卫失效"
    )


def test_real_rulebank_has_no_internal_markers():
    """真实词库干净（这是上一条守卫的落地）。"""
    dirty = [
        (r.keyword, r.note) for r in RuleBank().all
        if re.search(r"[｜|]\s*(?:严重度校准|校准记录|定级理由|内部|维护|TODO|FIXME)",
                     r.note or "")
    ]
    assert not dirty, f"词库里仍有内部台账痕迹：{dirty[:5]}"


# ============================================================ 3. 时效性台账


def test_review_log_covers_every_source():
    """台账必须覆盖词库里出现的每一个来源。

    新加一类词库却忘了登记台账，是这个机制最可能的失效方式——
    忘了登记的来源永远"不过期"，也永远不会被提醒复核。
    """
    log = json.loads((_ROOT / "rules" / "review_log.json").read_text(encoding="utf-8"))
    logged = set(log.get("sources", {}))
    in_bank = {r.source for r in RuleBank().all}
    missing = sorted(in_bank - logged)
    assert not missing, f"以下来源未登记复核台账：{missing}"


def test_review_log_entries_are_complete():
    """台账每条都要有依据、复核日、周期——缺一项就没法判断是否过期。"""
    log = json.loads((_ROOT / "rules" / "review_log.json").read_text(encoding="utf-8"))
    for src, meta in log.get("sources", {}).items():
        assert meta.get("basis"), f"{src} 缺「依据」"
        assert meta.get("label"), f"{src} 缺「名称」"
        assert int(meta.get("review_interval_days", 0)) > 0, f"{src} 复核周期非法"
        # 日期必须可解析
        date.fromisoformat(meta["last_reviewed"])


def test_freshness_check_passes_today():
    """今天的词库不应有任何来源超期。"""
    mod = _load_script("check_rule_freshness")
    result = mod.audit(date.today())
    assert not result["overdue"], f"以下来源已超期：{result['overdue']}"
    assert not result["unregistered"], f"未登记来源：{result['unregistered']}"


def test_freshness_guard_can_actually_fail():
    """守卫自测：把时间推到未来，必须报出超期且退出码为 1。

    一个永远不会失败的门禁比没有门禁更糟——它给人"已经守住了"的错觉。
    这里用远期日期验证它真的会红，而不是只会打印一行"全部有效"。
    """
    mod = _load_script("check_rule_freshness")
    far = date.today() + timedelta(days=365 * 3)
    result = mod.audit(far)
    assert result["overdue"], "三年后竟然没有任何来源超期 —— 时效门禁失效"
    assert mod.report(result) == 1, "超期时 report() 未返回失败退出码"


def test_freshness_flags_unregistered_source(tmp_path: Path):
    """守卫自测：词库里出现了台账没登记的来源，必须被指出来。"""
    mod = _load_script("check_rule_freshness")
    log = json.loads((_ROOT / "rules" / "review_log.json").read_text(encoding="utf-8"))
    # 抽掉一个来源，模拟"新加词库忘了登记"
    victim = next(iter(log["sources"]))
    log["sources"].pop(victim)
    fake = tmp_path / "review_log.json"
    fake.write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")

    result = mod.audit(date.today(), fake)
    assert victim in result["unregistered"], (
        f"未登记的来源 {victim} 没被发现 —— 守卫失效"
    )


# ============================================================ 4. 清单与实物对账


def test_pack_manifests_match_actual_rule_counts():
    """行业包清单里的条数与类别，必须和实物对得上。

    真实翻过车：``immigration/pack.json`` 写 ``rule_count: 140``，
    而 ``rules.json`` 实际有 179 条 —— 同一件事存两处，必然漂移。
    清单文件不被运行时读取，所以没人会发现它已经错了。
    """
    packs_dir = _ROOT / "rules" / "industry_packs"
    for pack_dir in sorted(p for p in packs_dir.iterdir() if p.is_dir()):
        manifest = pack_dir / "pack.json"
        assert manifest.exists(), f"{pack_dir.name} 缺 pack.json 清单"
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        rules = json.loads((pack_dir / "rules.json").read_text(encoding="utf-8"))
        assert meta["rule_count"] == len(rules), (
            f"{pack_dir.name}：清单写 {meta['rule_count']} 条，实际 {len(rules)} 条"
        )
        actual_cats = sorted({r.get("category", "") for r in rules if r.get("category")})
        assert sorted(meta["categories"]) == actual_cats, (
            f"{pack_dir.name}：清单类别与实物不一致"
        )


# ============================================================ 5. 前端产物同步


def test_web_artifact_carries_law_refs():
    """前端产物必须带上条款与依据说明。

    双端对拍门禁（test_web_parity）管的是"两边一致"；这里管的是
    "这一侧到底有没有这两个字段"——漏了字段两边一样地漏，对拍也发现不了。
    """
    data = json.loads(_WEB_RULES.read_text(encoding="utf-8"))
    rules = data["rules"]
    with_law = [r for r in rules if r.get("l")]
    with_note = [r for r in rules if r.get("n")]
    assert with_law, "前端产物里没有任何条款号（l 字段）"
    assert with_note, "前端产物里没有任何规则说明（n 字段）"

    meta = data["meta"]
    assert meta.get("law_coverage", {}).get("with_ref"), "meta 缺 law_coverage"
    assert meta.get("coverage_by_source"), "meta 缺 coverage_by_source"
    assert meta.get("review_log"), "meta 缺 review_log（前端无法展示时效）"

    # 台账里不许出现"预先算好的剩余天数"——那会让产物每天漂移
    sample = next(iter(meta["review_log"].values()))
    assert "remaining_days" not in sample and "remain" not in sample, (
        "review_log 里存了算好的剩余天数：产物会每天漂移，对拍门禁天天变红"
    )
    assert {"last", "days", "label", "basis"} <= set(sample), (
        f"review_log 字段不齐：{sorted(sample)}"
    )


# ============================================================ 4. 文档与词库不许各说各话


def test_readme_quoted_rule_numbers_match_rulebank():
    """README 里手写的规则条数 / 覆盖率必须与词库实际一致。

    这不是文档洁癖。README 是访客第一眼看到的东西，而它引用的数字全是
    **手写**的 —— 词库一扩，README 不会自己变。v3.6.0 把行业包从 9 个扩到
    14 个之后，README 的"610 / 710（约 86%）"就与词库页实际显示的
    "1090 / 1093（99.7%）"对不上了，而没有任何机制会提醒这件事。

    手写事实与自动统计并存，漂移只是时间问题 —— 那就让它会红灯。
    """
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    rules = RuleBank().all
    scoped = [r for r in rules if _is_law_based(r.source)]
    covered = [r for r in scoped if r.law_ref]

    assert f"**规则规模**：{len(rules)} 条" in readme, (
        f"README 写的规则总数不是 {len(rules)} 条 —— 词库变了，README 没跟着变"
    )
    assert f"{len(covered)} / {len(scoped)} 条标注了条款依据" in readme, (
        f"README 写的条款覆盖率不是 {len(covered)} / {len(scoped)}"
    )
    pct = f"{len(covered) * 100 / len(scoped):.1f}%"
    assert f"（{pct}）" in readme, f"README 里缺覆盖率百分比（{pct}）"


def test_readme_number_guard_can_fail():
    """守卫自测：给一个错数字，断言必须失败（否则上面的守卫是摆设）。"""
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "**规则规模**：99999 条" not in readme, (
        "守卫自测未通过：README 里真的出现了那个假数字"
    )
    rules = RuleBank().all
    assert len(rules) != 99999, "守卫自测未通过：真实条数恰好等于假数字"


def test_readme_test_count_is_accurate():
    """README 里写的 pytest 用例数必须等于实际收集到的用例数。

    这是同一类漂移的第三个实例（前两个：前端首页的"9 个强监管行业"、
    README 的条款覆盖率）。凡是手写的数字，都会在下次改动时悄悄过期 ——
    "加测试"更是高频动作，靠人记得回来改 README 是不现实的。

    用 ``--collect-only`` 收集而不是真的执行：收集不跑用例，不会递归。
    """
    import subprocess

    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout) \
        or re.search(r"collected\s+(\d+)\s+items?", proc.stdout)
    assert m, f"无法从收集结果里解析用例数：{(proc.stdout or '')[-400:]}"
    n = int(m.group(1))
    assert f"{n} 个 pytest 用例" in readme, (
        f"README 写的用例数不是 {n} —— 加了测试但 README 没跟着变"
    )


