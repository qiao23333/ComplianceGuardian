"""合规测评语料：用可量化的方式盯住「误报率」与「漏检率」。

设计初衷
--------
工具的可信度不由"规则条数"决定，而由两个数字决定：

* **误报率（False Positive）**：把合规文案判成违规。误报高 → 运营不敢用。
* **漏检率（False Negative）**：把违规文案放过。漏检高 → 工具没价值。

这两个指标互相拉扯，任何"多收词"或"少收词"的动作都会一边降一边升。
所以本语料的作用是：**任何语境规则的改动，都必须用这两个数字验收**，
而不是凭手感。

语料构成
--------
* ``CLEAN``：合规文案，应当**零违规**。含大量行业高频表述
  （第一步 / 第二阶段 / 第3步 / 首个工作日 等序数表达），
  它们正是历史误报的重灾区。
* ``RISKY``：违规文案，应当**至少命中一条**，且注明必须命中的关键词。
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
]


def _platform_of(item: tuple) -> str:
    return item[2] if len(item) > 2 else "xiaohongshu"


def false_positive_rate() -> tuple[float, list[str]]:
    """在 CLEAN 语料上测误报率。

    Returns:
        (误报率, 被误报的文案说明列表)
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    bad: list[str] = []
    for text, note in CLEAN:
        result = detector.detect(text, "xiaohongshu", "blue_v")
        if result["summary"]["violations"] > 0:
            hits = [v["keyword"] for v in result["violations"]]
            bad.append(f"{note}: {hits}")
    return len(bad) / len(CLEAN), bad


def false_negative_rate() -> tuple[float, list[str]]:
    """在 RISKY 语料上测**完全未命中**的比例。

    判定"命中"的口径是"有任意一条 finding"，即 violations + warnings > 0。
    原因：工具的价值不只是"判违规"，还包括"提示可疑"。一条 medium 级的
    提示（如"限时秒杀"）虽然不计入违规数，但用户确实被提醒到了，
    不能算漏检 —— 否则会把严重度设计问题误算成检出能力问题。
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    missed: list[str] = []
    for item in RISKY:
        text, expect = item[0], item[1]
        result = detector.detect(text, _platform_of(item), "blue_v")
        s = result["summary"]
        if s["violations"] + s["warnings"] == 0:
            missed.append(f"漏检[{expect}]: {text}")
    return len(missed) / len(RISKY), missed


def high_risk_miss_rate() -> tuple[float, list[str]]:
    """测"只给了提示、没判为违规"的比例。

    这是比漏检更值得盯的指标：用户看到"中风险 78 分"时，真正会去改的是
    被标为违规的项；如果红线表述只落在提示级，等于没起作用。
    """
    from guardian.detector import ComplianceDetector

    detector = ComplianceDetector.get_instance()
    soft: list[str] = []
    for item in RISKY:
        text, expect = item[0], item[1]
        result = detector.detect(text, _platform_of(item), "blue_v")
        s = result["summary"]
        if s["violations"] == 0 and s["warnings"] > 0:
            hits = [v["keyword"] for v in result["violations"]]
            soft.append(f"仅提示[{expect}]: {text} {hits}")
    return len(soft) / len(RISKY), soft


def report() -> str:
    """生成可读的评测报告。"""
    fp, fp_list = false_positive_rate()
    fn, fn_list = false_negative_rate()
    soft, soft_list = high_risk_miss_rate()
    lines = [
        f"合规语料 {len(CLEAN)} 条 → 误报率 {fp:.1%}   （目标 0%，误报高则运营弃用）",
        f"违规语料 {len(RISKY)} 条 → 漏检率 {fn:.1%}   （连提示都没有，目标 0%）",
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
