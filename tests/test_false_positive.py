#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反误报 / 反漏检回归门禁。

为什么单独建一个文件
--------------------
合规工具的成败不看"规则条数"，只看两个数字：误报率与漏检率。
而这两个数字极容易被后续改动悄悄弄坏 —— 加一条词可能救回一个漏检，
同时引入三个误报；改一条语境规则可能压掉误报，同时放走红线。

所以这里用**语料级断言**把两条底线钉死：

1. 误报率 ≤ 5%（合规文案被误判 → 运营直接弃用工具）；
2. 漏检率为 0%（违规文案连提示都没有 → 工具没有价值）。

评测口径
--------
``tests.corpus`` 里的三个指标默认按 **磁盘上全部行业包开启** 测
（最严口径，与 Web 端默认一致）。2026-09-15 修正前，这个评测退回到了
``data/config.json`` 里写死的 ``["immigration"]``，导致新加的 7 个行业包
（313 条规则）**从未被评测过**，而 README 把"误报率 0%"当核心卖点。

本文件除底线断言外，还加了三条"防静默退化"的守卫：

* ``test_corpus_covers_every_industry_pack`` —— 新加行业包必须配语料，
  否则它就是"没被验证过"的规则集；
* ``test_industry_packs_carry_real_detection_weight`` —— 行业包全关时漏检率
  必须变差。不成立就说明行业包在承重上是摆设（规则被搬去通用库、
  或包加载失败却没人发现）；
* ``test_known_false_positive_defects_stay_fixed`` —— 把实测修掉的 12 处
  真误报逐句钉住，防止后继改动把它们放回来。

同时补充两组"结构性"用例，锁住容易退化的两类具体行为：

* 序数表达必须豁免（``第一步 / 第二阶段 / 第3步 / 首个工作日``）；
* 真极限词必须报出（``销量第一 / 行业第一 / 首家 / 首创 / 国家级``）。

这两组互为对照：只有"该豁免的豁免、该报的报"同时成立，
才说明语境守卫是在做判断，而不是在无脑放宽或收紧。
"""

from __future__ import annotations

import pytest

from guardian.detector import ComplianceDetector
from tests.corpus import (
    CLEAN,
    INDUSTRY_CLEAN,
    INDUSTRY_RISKY,
    RISKY,
    all_industry_ids,
    false_negative_rate,
    false_positive_rate,
    high_risk_miss_rate,
)

#: 全部行业包 —— 所有断言都显式按这个口径跑，不依赖配置文件当前状态
ALL_PACKS = all_industry_ids()


@pytest.fixture(scope="module")
def detector():
    return ComplianceDetector.get_instance()


# ============================================================ 语料级底线


def test_false_positive_rate_under_5_percent():
    """合规语料误报率必须 ≤ 5%（全行业包口径）。

    历史对照：语境守卫只覆盖固定短语时，这个数字是 35.5%
    （31 条里 11 条被误报，全部是"第一步 / 第二阶段 / 第2次"这类序数表达）。
    """
    rate, bad = false_positive_rate()
    assert rate <= 0.05, "误报率超标：\n" + "\n".join(bad)


def test_false_negative_rate_is_zero():
    """违规语料必须全部被提示到（不允许连提示都没有）。"""
    rate, missed = false_negative_rate()
    assert rate == 0.0, "存在漏检：\n" + "\n".join(missed)


def test_high_risk_miss_rate_under_threshold():
    """红线话术不能只落在"提示"级。

    只看漏检率会漏掉一类退化：规则还在、也命中了，但严重度被改低到
    warning —— 用户看到"中风险"不会去改，等于没起作用。
    阈值取得比现状宽松（实测 7.2%），是为了让它能拦住**退化**，
    而不是逼着每次调词都去改这个数字。
    """
    rate, soft = high_risk_miss_rate()
    assert rate <= 0.15, (
        f"仅提示率 {rate:.1%} 超标（红线话术只给警告、不判违规）：\n"
        + "\n".join(soft)
    )


def test_corpus_sizes_are_meaningful():
    """语料规模守卫：防止有人为了"让测试过"而删语料。"""
    assert len(CLEAN) >= 25
    assert len(RISKY) >= 25
    # 分行业语料是为了让新行业包真的被评测到，规模不能缩回去
    assert sum(len(v) for v in INDUSTRY_CLEAN.values()) >= 25
    assert sum(len(v) for v in INDUSTRY_RISKY.values()) >= 25


# ============================================================ 口径守卫


def test_corpus_covers_every_industry_pack():
    """磁盘上每个行业包都必须有正反语料。

    没有语料的行业包 = 从未被评测过的规则集。它能被结构门禁（字段齐全、
    不撞词、条数对账）全部放行，却可能把该行业的合法文案整片判违规 ——
    2026-09-15 实测就是如此：医美包把「光子嫩肤」「割双眼皮」判成
    high 级违规，而这两句是持证医美机构最正常的业务描述。
    """
    missing_clean = [pid for pid in ALL_PACKS if not INDUSTRY_CLEAN.get(pid)]
    missing_risky = [pid for pid in ALL_PACKS if not INDUSTRY_RISKY.get(pid)]
    assert not missing_clean, (
        f"这些行业包缺合规语料（无法验证是否误报）：{missing_clean}\n"
        "修法：在 tests/corpus/__init__.py 的 INDUSTRY_CLEAN 里补 2-3 条"
        "该行业的**合法但容易踩雷**的文案（持证机构的正常描述、法定声明、"
        "否定语境的风险提示）。"
    )
    assert not missing_risky, (
        f"这些行业包缺违规语料（无法验证是否漏检）：{missing_risky}\n"
        "修法：在 INDUSTRY_RISKY 里补 2-3 条该行业的高频违规话术。"
    )
    # 语料里提到的包 id 必须真实存在 —— 防止写错 id 导致"看起来有覆盖、
    # 实际挂在一个不存在的包上"
    unknown = (set(INDUSTRY_CLEAN) | set(INDUSTRY_RISKY)) - set(ALL_PACKS)
    assert not unknown, f"语料里出现磁盘上不存在的行业包 id：{sorted(unknown)}"


def test_industry_packs_carry_real_detection_weight():
    """行业包必须真的在承重（反证法）。

    把行业包全关，漏检率必须**变差**。如果关掉之后漏检率还是 0，
    说明这些红线其实躺在通用词库里、行业包只是重复记账 ——
    那时"9 大行业词库"就是个装饰性数字。
    """
    _, missed_all_off = false_negative_rate(industries=[])
    assert missed_all_off, (
        "关掉全部行业包后漏检率仍然是 0 —— 行业包没有承担任何检出职责。\n"
        "要么规则被搬进了通用库（行业包成了空壳），要么包根本没被加载。"
    )


# ============================================================ 已修真误报（逐句钉住）


#: (文案, 说明) —— 这些句子都曾在 violation 级被误报，2026-09-15 修掉。
#:
#: 两类成因：
#: * **条件违规被实现成无条件匹配** —— "光子嫩肤"这类项目名，规则自己的
#:   note 都写着"非医疗机构不得开展"，说明意图是有条件的，但实现是无条件
#:   high，于是持证医美机构写正常业务介绍就被判违规。同一类的还有
#:   "婴幼儿配方食品 / 保健食品"这类**中性品类名**：真正要管的是"有没有
#:   注册备案"，词本身不违规；
#: * **否定/法定声明语境被判违规** —— "本品为普通食品，不具有疾病预防、
#:   治疗功能"是《食品安全法》第七十三条要求写的法定声明。
_KNOWN_FP_FIXED: list[tuple[str, str]] = [
    ("本机构持有《医疗机构执业许可证》，光子嫩肤与注射美容项目均由执业医师操作",
     "持证医美：项目名（条件违规降为提示）"),
    ("割双眼皮属于医疗美容手术，需术前面诊并签署知情同意书", "持证医美：手术项目名"),
    ("效果因人而异，我们不承诺疗效", "否定语境：不承诺疗效"),
    ("本品为普通食品，不具有疾病预防、治疗功能", "法定声明：不具有治疗功能"),
    ("妆字号产品，不具备医疗作用", "法定声明：不具备医疗作用"),
    ("本品为非保健食品，未取得保健功能注册", "中性术语：保健食品"),
    ("本产品为净值型理财产品，收益随市场波动", "中性术语：理财产品"),
    ("本店承诺绝不刷单，所有评价均来自真实买家", "否定语境：绝不刷单"),
    # —— 2026-09-15 扩 5 个新行业包时补语料暴露的第二批（都在旧库 ad_law）——
    ("母乳是婴儿理想的天然食物，本产品为婴幼儿配方食品，请在儿科医生指导下选用",
     "中性术语：婴幼儿配方食品（资质提醒，降为提示）"),
    ("宝宝发育情况请以儿科医生评估为准，本产品不能替代药物治疗",
     "否定语境：不能替代药物治疗"),
    ("本品为宠物配合饲料，不具有疾病治疗功能，请在执业兽医指导下使用",
     "法定声明：不具有疾病治疗功能"),
    ("本产品非兽药，不能替代兽医诊疗", "否定语境：不能替代兽医诊疗"),
]


@pytest.mark.parametrize("text,note", _KNOWN_FP_FIXED, ids=[n for _, n in _KNOWN_FP_FIXED])
def test_known_false_positive_defects_stay_fixed(detector, text, note):
    """这些句子不得再被判违规（回归锁）。"""
    result = detector.detect(text, "xiaohongshu", "blue_v", industries=ALL_PACKS)
    hits = [v["keyword"] for v in result["violations"] if v["severity"] == "violation"]
    assert not hits, f"误报回归（{note}）：{text} → {hits}"


# ============================================================ 结构性用例

#: 必须被判为**合规**的序数表达 —— 中文里最普通的流程/结构描述
ORDINAL_SAFE = [
    "第一步先准备护照，第二步递交EOI",
    "第一阶段评估资质，第二阶段准备材料",
    "第1步、第2步、第3步我都列好了",
    "第3点是语言成绩有效期",
    "第一篇讲签证类型，第二篇讲材料",
    "我排在第1位等待补料通知",
    "首个工作日收到的回复会统一处理",
    "这是我第一次办签证",
    "最近很多人问我482签证",
    "最后提醒一次：材料要真实",
]

#: 必须被判为**违规**的绝对化/排名宣称 —— 与上面的语料只差一个词
EXTREME_RISKY = [
    "行业第一的移民机构",
    "销量第一的咨询服务",
    "全网销量第一的品牌",
    "我们是首家获批的机构",
    "本公司首创全流程托管",
    "全网最低价的移民服务",
    "国家级资质认证",
    "唯一官方授权渠道",
    "史上最快的审批通道",
    "这款产品效果最好",
]


@pytest.mark.parametrize("text", ORDINAL_SAFE)
def test_ordinal_expressions_are_exempt(detector, text):
    """序数/结构表达不得被判违规（误报会直接毁掉工具可用性）。"""
    result = detector.detect(text, "xiaohongshu", "blue_v", industries=ALL_PACKS)
    hits = [v["keyword"] for v in result["violations"]]
    assert not hits, f"序数表达被误报：{text} → {hits}"


@pytest.mark.parametrize("text", EXTREME_RISKY)
def test_real_extremes_still_reported(detector, text):
    """真·绝对化用语必须继续报出（豁免不能过度，否则变漏检）。"""
    result = detector.detect(text, "xiaohongshu", "blue_v", industries=ALL_PACKS)
    hits = [v["keyword"] for v in result["violations"]]
    assert hits, f"极限词漏检：{text}"


# ============================================================ 死规则复活


def test_placeholder_rules_are_gone():
    """词库里不得再有含 X 占位符的死规则（永不命中的"注水"规则）。"""
    from scripts.harden_rulebank import find_dead_rules

    dead = find_dead_rules()
    assert not dead, "存在死规则：" + str(dead)


@pytest.mark.parametrize(
    "text,expect",
    [
        ("保证3个月出签，否则赔偿", "保证3个月出签"),
        ("保证30天内获批", "保证30天内获批"),
        ("保证两周拿到PR", "保证两周拿到"),
        ("现成雇主资源随便挑", "现成雇主"),
        ("最后一波名额，错过再等一年", "最后一波"),
    ],
)
def test_previously_missed_expressions_now_detected(detector, text, expect):
    """原先因"死规则 / 词库缺失"而漏掉的行业高频违规表达，现已能命中。"""
    result = detector.detect(text, "xiaohongshu", "blue_v")
    hits = [v["keyword"] for v in result["violations"] + result.get("warnings_list", [])]
    s = result["summary"]
    assert s["violations"] + s["warnings"] > 0, f"仍未命中：{text}"
    assert any(expect in h for h in hits) or s["violations"] > 0, f"命中但非预期：{text} → {hits}"


# ============================================================ 挂靠类：宽严成对


#: (文案, 说明) —— 广告语态，必须命中
GUAKAO_RISKY = [
    ("无需英语无需工作经验，挂靠办理，快速拿PR", "挂靠 + 结果动词（不接'雇主'）"),
    ("支持挂靠服务，随时递交申请", "挂靠 + 服务"),
    ("现成雇主资源，挂靠即可递交，内部名额有限", "挂靠 + 即可 + 递交"),
    ("我司可挂靠公司，随时安排", "已有字面规则仍要生效"),
]

#: (文案, 说明) —— 警示 / 无关语境，必须不命中
GUAKAO_CLEAN = [
    ("警惕挂靠骗局，签证申请必须基于真实雇佣关系", "风险提示"),
    ("挂靠担保资格是违法的，我们会明确拒绝这类要求", "合规声明"),
    ("社保挂靠政策解读，本文讲的是养老金计算", "无关语境"),
]


@pytest.mark.parametrize("text,reason", GUAKAO_RISKY)
def test_guakao_advertising_forms_are_caught(detector, text, reason):
    """广告语态的'挂靠'必须被抓到。

    历史缺口：词库里只有 ``挂靠雇主 / 挂靠公司`` 两个字面词组，而字面匹配
    要求"雇主/公司"紧跟在"挂靠"后面 —— 写成"挂靠即可递交""挂靠办理"
    就整条绕过去了，这恰恰是最常见的广告写法。
    """
    result = detector.detect(text, "xiaohongshu", "non_blue_v", industries=ALL_PACKS)
    assert result["summary"]["violations"] > 0, f"漏检（{reason}）：{text}"


@pytest.mark.parametrize("text,reason", GUAKAO_CLEAN)
def test_guakao_warning_context_is_not_flagged(detector, text, reason):
    """警示语境的'挂靠'不能被判违规。

    这是补规则时的**收紧项**：如果偷懒直接收「挂靠」二字，下面这些
    "挂靠是违法的、请警惕"的内容会被误报 —— 而写这类内容的人恰恰是
    最守规矩的那批运营。宽一条必须同时收紧一条，否则就是把误报
    从漏检手里换回来。
    """
    result = detector.detect(text, "xiaohongshu", "non_blue_v", industries=ALL_PACKS)
    hits = [v["keyword"] for v in result["violations"]]
    assert result["summary"]["violations"] == 0, f"误报（{reason}）：{text} → {hits}"
