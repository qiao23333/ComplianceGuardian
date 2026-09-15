"""合规测评语料：用可量化的方式盯住「误报率」与「漏检率」。

设计初衷
--------
工具的可信度不由"规则条数"决定，而由两个数字决定：

* **误报率（False Positive）**：把合规文案判成违规。误报高 → 运营不敢用。
* **漏检率（False Negative）**：把违规文案放过。漏检高 → 工具没价值。

这两个指标互相拉扯，任何"多收词"或"少收词"的动作都会一边降一边升。
所以本语料的作用是：**任何语境规则的改动，都必须用这两个数字验收**，
而不是凭手感。

评测口径：**全部行业包开启**
---------------------------
2026-09-15 修正。此前本模块的 ``detector.detect(...)`` 不传 ``industries``，
于是引擎回退到 ``data/config.json`` 的 ``enabled_industry_packs`` ——
当时那份配置里只写了 ``["immigration"]``。后果是：新加的 7 个行业包
（313 条规则）**从未进入过误报评测**，而 README 把"误报率 0%"当核心卖点。

现在统一按"磁盘上全部行业包"测（最严口径，也与 Web 端默认一致）：
多开行业包只会增加命中，不会减少 —— 全开口径过了，任何子集都过。

语料构成
--------
* ``CLEAN`` / ``RISKY``：通用 + 移民/留学话术（历史语料，保留）。
* ``INDUSTRY_CLEAN`` / ``INDUSTRY_RISKY``：**按行业包分列**。
  正例刻意写"合法但容易踩雷"的内容 —— 持证医美机构的正常项目介绍、
  法定免责声明（"本品为普通食品，不具有疾病预防、治疗功能"）、
  否定语境的风险提示（"本店承诺绝不刷单"）。这些恰恰是误报的重灾区。
  反例写该行业真正的高频违规话术。

``INDUSTRY_*`` 用 dict 按包 id 分列而不是塞进一个大列表，是为了让
"新加了一个行业包，却没人给它写语料"这件事**能被门禁发现**
（见 ``tests/test_false_positive.py::test_every_pack_has_corpus``）。
"""

from __future__ import annotations

#: (文案, 说明) —— 合规文案，期望零违规
CLEAN: list[tuple[str, str]] = [
    ("第一步先准备护照和成绩单，第二步递交EOI，第三步等邀请", "三步流程（序数）"),
    ("第一阶段评估资质，第二阶段准备材料，第三阶段递交申请", "阶段划分（序数）"),
    ("第1步、第2步、第3步我都写在下方清单里了", "阿拉伯数字序数"),
    ("第3点很重要：语言成绩有效期只有两年", "第X点"),
    ("这是我第一次办签证，很多地方不懂", "第一次"),
    ("第一次咨询免费，后续按阶段收费", "第一次咨询"),
    ("最近很多人问我澳洲482签证怎么申请", "最近"),
    ("最后提醒一次：材料一定要真实", "最后"),
    ("最终结果以移民局批复为准", "最终"),
    ("最开始我也以为很难，其实流程很清晰", "最开始"),
    ("第一步先做职业评估，别急着交钱", "第一步"),
    ("我排在第1位等待补料通知", "排队位次"),
    ("第一篇讲签证类型，第二篇讲材料清单", "篇数序数"),
    ("首个工作日收到的回复会统一处理", "首个工作日"),
    ("入学前第一个月建议先适应语言环境", "第一个月"),
    ("我们把申请拆成四步：评估、准备、递交、跟进", "流程描述"),
    ("第二步要注意职业评估的有效期", "第二步"),
    ("2024年第二季度政策有调整", "季度序数"),
    ("第一轮补料通常在一周内完成", "第一轮"),
    ("第2次递交需要重新缴纳申请费", "第X次"),
    ("材料按顺序编号：1号文件、2号文件", "编号"),
    ("建议先确认职业在清单上，再准备材料", "中性建议"),
    ("语言成绩建议提前半年准备", "时间建议"),
    ("雇主需要满足担保资质要求", "中性陈述"),
    ("申请周期通常在6到12个月之间", "区间表述"),
    ("我们提供材料清单模板和填写说明", "服务描述"),
    ("服务内容包括评估、材料审核和递交跟进", "服务内容"),
    ("请以官网公布的最新政策为准", "以官方为准"),
    ("签证结果取决于移民局审核，我们无法干预", "免责声明"),
    ("我们会如实告知风险和不确定性", "如实告知"),
    ("分数不够可以走州担保或偏远地区加分", "方案说明"),
    # —— 底下两条是"警示语境"：讲的是"挂靠违法"，不是在提供挂靠服务 ——
    # 词库里挂靠类规则收窄到"挂靠 + 结果动词"（广告语态）就是为了这个：
    # 裸收「挂靠」二字会把辟谣 / 风险提示内容也判成违规，
    # 而本项目第一原则是误报率必须为 0。
    ("警惕挂靠骗局，签证申请必须基于真实雇佣关系", "警示语境：挂靠骗局"),
    ("挂靠担保资格是违法的，我们会明确拒绝这类要求", "警示语境：挂靠违法"),
]

#: (文案, 必须命中的关键词[, 检测平台]) —— 违规文案
#:
#: 平台缺省为 xiaohongshu；平台专属规则（如"加群"只在抖音生效）需显式指定，
#: 否则会把"该平台规则本就不覆盖"误记为漏检。
RISKY: list[tuple] = [
    ("我们保证下签，不过全额退款", "保证下签"),
    ("成功率100%，零拒签记录", "100%"),
    ("最快3个月就能获批PR", "最快"),
    ("我们的服务是全网最低价", "全网最低"),
    ("内部关系直通移民局，你懂的", "内部关系"),
    ("现成雇主资源随便挑，随时担保", "现成雇主"),
    ("行业第一的移民机构，值得信赖", "行业第一"),
    ("销量第一的咨询服务，口碑最好", "销量第一"),
    ("本公司首创移民全流程托管模式", "首创"),
    ("我们是首家获批该类资质的机构", "首家"),
    ("这款产品效果最好，绝对有效", "最好"),
    ("国家级资质，绝对权威", "国家级"),
    ("史上最快的审批通道", "史上最快"),
    ("保证3个月出签，否则赔偿", "保证3个月出签"),
    ("百分百通过，无条件退款", "百分百"),
    ("加微信领取详细资料", "加微信"),
    ("私信我获取内部名额", "私信我"),
    ("加群免费领取评估表", "加群", "douyin"),
    ("点击链接直接下单，限时秒杀", "限时秒杀"),
    ("我们是全国排名第一的中介", "排名第一"),
    ("包过，不成功不收费", "包过"),
    ("顶级专家团队全程服务", "顶级"),
    ("唯一官方授权渠道", "唯一"),
    ("绝对有效的移民方案", "绝对有效"),
    ("零风险移民方案，稳赚不赔", "零风险"),
    ("内部渠道办理，无需排队", "内部渠道"),
    ("保证百分百下签，签不下来退全款", "百分百"),
    ("我们承诺包拿PR，不用考英语", "包拿PR"),
    ("最后一波名额，错过再等一年", "最后一波"),
    ("全网首发独家内部名额", "全网首发"),
    # —— 挂靠类：词库原先只有「挂靠雇主 / 挂靠公司」两个字面词组，
    #    只要"挂靠"后面不接这两个词就绕过去了（2026-09-15 补正则覆盖）——
    ("无需英语无需工作经验，挂靠办理，快速拿PR", "挂靠办理"),
    ("支持挂靠服务，随时递交申请", "挂靠服务"),
    ("雇主担保可以挂靠即可递交，名额有限", "挂靠即可递交"),
]


# ============================================================ 分行业语料
#
# 正例的设计原则：写**合法的、真实存在的**行业文案，特别是三类历史误报高发区 ——
#   1. 持证机构的正常业务描述（医美机构说"光子嫩肤由执业医师操作"）；
#   2. 法定免责声明（"本品为普通食品，不具有疾病预防、治疗功能"）；
#   3. 否定/警示语境（"本店承诺绝不刷单"、"警惕刷单骗局"）。
# 这些句子如果被判违规，工具就会去罚最守规矩的那批人。

#: {行业包 id: [(文案, 说明), ...]} —— 期望零违规
INDUSTRY_CLEAN: dict[str, list[tuple[str, str]]] = {
    "immigration": [
        ("签证结果由移民局依据材料真实性审核决定", "免责声明"),
        ("费用按合同约定分阶段收取，签约前给到费用清单", "收费披露"),
        ("我们不做任何结果承诺，只对材料准备质量负责", "如实告知"),
    ],
    "study_abroad": [
        ("录取结果由学校审核决定，我们不承诺录取", "免责声明"),
        ("语言成绩需达到学校要求，具体以院校官网为准", "以官方为准"),
        ("我们提供选校建议、文书修改和递交跟进", "服务内容"),
    ],
    "medical_beauty": [
        ("本机构持有《医疗机构执业许可证》，光子嫩肤与注射美容项目均由执业医师操作",
         "持证医美：项目名 + 资质说明"),
        ("割双眼皮属于医疗美容手术，需术前面诊并签署知情同意书",
         "持证医美：手术项目名"),
        ("效果因人而异，我们不承诺疗效", "免责声明（否定语境：不承诺疗效）"),
        ("项目价格已公示，最终以面诊评估后的方案为准", "价格公示"),
    ],
    "education": [
        ("本课程由持有教师资格证的老师授课，具体师资以开班通知为准", "师资披露"),
        ("考试成绩取决于个人努力，我们不承诺提分幅度", "免责声明"),
        ("课程含 12 次直播和课后答疑，支持先试听后报名", "服务内容"),
        ("考纲以教育考试院公布的最新版本为准", "以官方为准"),
    ],
    "finance": [
        ("本产品为净值型理财产品，收益随市场波动，历史业绩不代表未来表现",
         "风险提示（含中性术语「理财产品」）"),
        ("投资有风险，请根据自身风险承受能力选择", "法定风险提示"),
        ("年化收益率区间为 2.5%-4.2%，不保证达到上限", "收益区间披露"),
    ],
    "real_estate": [
        ("项目距地铁站约 1.2 公里，具体以实测为准", "距离披露"),
        ("学区划分以教育部门当年公布的政策为准", "以官方为准"),
        ("房价受市场影响存在波动，我们不承诺升值", "免责声明"),
    ],
    "food_health": [
        ("本品为普通食品，不具有疾病预防、治疗功能", "《食品安全法》第七十三条法定声明"),
        ("本品不能代替药物", "法定声明"),
        ("本品为非保健食品，未取得保健功能注册", "资质说明"),
    ],
    "beauty_cosmetics": [
        ("本品为普通化妆品，备案编号可在国家药监局网站查询", "备案披露"),
        ("使用前建议在耳后小面积试用，如有不适请停用", "使用提示"),
        ("妆字号产品，不具备医疗作用", "法定说明"),
    ],
    "ecommerce": [
        ("本商品支持 7 天无理由退换，运费险由商家承担", "售后说明"),
        ("库存以实际下单为准，页面显示数量仅供参考", "库存说明"),
        # 否定语境的"刷单"：规则里配了 context_excludes 覆盖"不刷单"等
        # 否定搭配。刻意收窄到"否定词与刷单紧邻"，不收"刷单骗局/返利"
        # 这类既见于反诈科普、又是招揽话术本身的词组。
        ("本店承诺绝不刷单，所有评价均来自真实买家", "合规声明：否定语境"),
        ("直播间价格与店铺价一致，优惠以结算页为准", "价格说明"),
    ],
}

#: {行业包 id: [(文案, 必须命中的关键词), ...]} —— 期望至少一条违规
INDUSTRY_RISKY: dict[str, list[tuple[str, str]]] = {
    "immigration": [
        ("保证下签，不过全额退款", "保证下签"),
        ("零拒签记录，百分百获批", "百分百获批"),
        ("挂靠办理，快速拿 PR", "挂靠办理"),
        ("假结婚买签证，花钱买 PR", "假结婚"),
    ],
    "study_abroad": [
        ("保录取，不成功退全款", "保录取"),
        ("免语言成绩直接入学", "免语言成绩"),
        ("内部招生名额，招生官推荐", "内部招生名额"),
        ("一周下 offer，留学行业领先", "一周下offer"),
    ],
    "medical_beauty": [
        ("一次见效，百分百见效，无痛无痕", "百分百见效"),
        ("患者对比照：术前术后对比一目了然", "术前术后对比"),
        ("治愈率 98%，有效率行业领先", "治愈率"),
        ("三甲专家亲诊，包治颈椎病", "包治颈椎病"),
    ],
    "education": [
        ("签约保过班，考不过退全款", "签约保过"),
        ("原命题教师授课，内部题库精准押题", "原命题教师"),
        ("别让孩子输在起跑线", "输在起跑线"),
        ("9.9元体验课，名师推荐零基础速成", "名师推荐"),
    ],
    "finance": [
        ("保本高息，本金安全无忧", "保本高息"),
        ("无视征信，黑户可贷，秒放款", "黑户可贷"),
        ("带你炒股，必涨牛股，有内幕消息", "内幕消息"),
        ("躺赚睡后收入，一夜暴富不是梦", "躺赚"),
    ],
    "real_estate": [
        ("买到即赚，投资回报率高达 30%", "买到即赚"),
        ("名校学区，签约入学，对口名校学位房", "签约入学"),
        ("首付贷 + 售后返租，以租养贷零压力", "售后返租"),
        ("步行 5 分钟直达商圈，绝版房源", "分钟直达"),
    ],
    "food_health": [
        ("纯天然零添加，100% 安全，孕妇可用", "100%安全"),
        ("降三高、防癌，能杀死癌细胞", "杀死癌细胞"),
        ("食补治病，胜过药物", "胜过药物"),
        ("提高免疫力，延年益寿", "提高免疫力"),
    ],
    "beauty_cosmetics": [
        ("药妆级，医学护肤品，抗炎抗过敏", "药妆"),
        ("七天祛痘，根治敏感肌，彻底修复皮肤屏障", "根治敏感肌"),
        ("速效美白，一洗白，三天祛斑", "一洗白"),
        ("不含任何化学物质，零刺激", "不含任何化学物质"),
    ],
    "ecommerce": [
        ("全网最低价，史上最低价，亏本清仓", "全网最低价"),
        ("好评返现，晒图返现，虚拟发货秒好评", "好评返现"),
        ("万人疯抢，仅此一天，错过再无", "万人疯抢"),
        ("军供品质，殿堂级，yyds", "军供"),
    ],
}


# ============================================================ 口径

def all_industry_ids() -> list[str]:
    """磁盘上的全部行业包 id —— 评测口径的唯一来源。

    不在这里写死 9 个 id：写过一次就会漂，而且漂法是"新包不进评测"，
    正是本模块 2026-09-15 修掉的那个坑。
    """
    from guardian.rulebank import list_industry_packs

    return [p["id"] for p in list_industry_packs()]


def _platform_of(item: tuple) -> str:
    return item[2] if len(item) > 2 else "xiaohongshu"


def _clean_items(industries: list[str] | None) -> list[tuple[str, str]]:
    """(文案, 说明)，含通用语料与选中行业的正例。"""
    items = list(CLEAN)
    for pid in (all_industry_ids() if industries is None else industries):
        items += list(INDUSTRY_CLEAN.get(pid, []))
    return items


def _risky_items(industries: list[str] | None) -> list[tuple[str, str, str]]:
    """(平台, 文案, 必须命中的关键词)。"""
    items = [(_platform_of(it), it[0], it[1]) for it in RISKY]
    for pid in (all_industry_ids() if industries is None else industries):
        for text, expect in INDUSTRY_RISKY.get(pid, []):
            items.append(("xiaohongshu", text, expect))
    return items


def _scoped(industries: list[str] | None):
    return all_industry_ids() if industries is None else list(industries)


def false_positive_rate(industries: list[str] | None = None) -> tuple[float, list[str]]:
    """在合规语料上测误报率。

    Args:
        industries: 参与检测的行业包；``None`` = 全部（默认口径）。

    Returns:
        (误报率, 被误报的文案说明列表)
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    scope = _scoped(industries)
    items = _clean_items(industries)
    bad: list[str] = []
    for text, note in items:
        result = detector.detect(text, "xiaohongshu", "blue_v", industries=scope)
        if result["summary"]["violations"] > 0:
            hits = [v["keyword"] for v in result["violations"]
                    if v["severity"] == "violation"]
            bad.append(f"{note}: {hits}")
    return len(bad) / len(items), bad


def false_negative_rate(industries: list[str] | None = None) -> tuple[float, list[str]]:
    """在违规语料上测**完全未命中**的比例。

    判定"命中"的口径是"有任意一条 finding"，即 violations + warnings > 0。
    原因：工具的价值不只是"判违规"，还包括"提示可疑"。一条 medium 级的
    提示（如"限时秒杀"）虽然不计入违规数，但用户确实被提醒到了，
    不能算漏检 —— 否则会把严重度设计问题误算成检出能力问题。

    Args:
        industries: 参与检测的行业包；``None`` = 全部（默认口径）。
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    scope = _scoped(industries)
    missed: list[str] = []
    items = _risky_items(industries)
    for platform, text, expect in items:
        result = detector.detect(text, platform, "blue_v", industries=scope)
        s = result["summary"]
        if s["violations"] + s["warnings"] == 0:
            missed.append(f"漏检[{expect}]: {text}")
    return len(missed) / len(items), missed


def high_risk_miss_rate(industries: list[str] | None = None) -> tuple[float, list[str]]:
    """测"只给了提示、没判为违规"的比例。

    这是比漏检更值得盯的指标：用户看到"中风险 78 分"时，真正会去改的是
    被标为违规的项；如果红线表述只落在提示级，等于没起作用。
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    scope = _scoped(industries)
    soft: list[str] = []
    items = _risky_items(industries)
    for platform, text, expect in items:
        result = detector.detect(text, platform, "blue_v", industries=scope)
        s = result["summary"]
        if s["violations"] == 0 and s["warnings"] > 0:
            hits = [v["keyword"] for v in result["violations"]]
            soft.append(f"仅提示[{expect}]: {text} {hits}")
    return len(soft) / len(items), soft


def report() -> str:
    """生成可读的评测报告。"""
    fp, fp_list = false_positive_rate()
    fn, fn_list = false_negative_rate()
    soft, soft_list = high_risk_miss_rate()
    n_clean = len(_clean_items(None))
    n_risky = len(_risky_items(None))
    lines = [
        f"行业包口径：{len(all_industry_ids())} 个（全部开启）",
        f"合规语料 {n_clean} 条 → 误报率 {fp:.1%}   （目标 0%，误报高则运营弃用）",
        f"违规语料 {n_risky} 条 → 漏检率 {fn:.1%}   （连提示都没有，目标 0%）",
        f"                       仅提示率 {soft:.1%}   （只算警告未判违规）",
    ]
    if fp_list:
        lines.append("—— 误报明细 ——")
        lines.extend("  " + x for x in fp_list)
    if fn_list:
        lines.append("—— 漏检明细 ——")
        lines.extend("  " + x for x in fn_list)
    if soft_list:
        lines.append("—— 仅提示明细 ——")
        lines.extend("  " + x for x in soft_list)
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
