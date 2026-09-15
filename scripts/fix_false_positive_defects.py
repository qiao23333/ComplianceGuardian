#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修掉 8 处"把合规文案判成违规"的真误报。

怎么发现的
----------
给 9 个行业包补真实语料时（持证医美机构的正常项目介绍、法定免责声明、
否定语境的风险提示），跑出来 8 个 violation 级误报。分两类：

**A 类 · 本轮新增词库引入（5 个）**

* 医美包 ``光子嫩肤 / 注射美容 / 割双眼皮 / 线雕``（high，类别"违法操作"）
  规则自己的 note 写的是"**非医疗机构**不得开展或宣传"，suggestion 写的是
  "**非医疗机构**删除" —— 也就是说**规则的意图是有条件的**。但实现是无条件
  关键词匹配 + high，于是持证医美机构写"光子嫩肤项目由执业医师操作"被判违规。
  这个包的目标用户恰恰是医美机构，等于对目标用户 100% 误报。

* 电商包 ``刷单``（critical）在"本店承诺不刷单"这种否定语境里被判违规。
  （与挂靠类同一个病：规则只匹配字面，不看语态。挂靠那批最后是用
  "挂靠 + 结果动词"的正则收住的；这里用规则级 ``context_excludes`` 更省事，
  因为否定搭配是有限枚举。）

**B 类 · 旧库存量问题（5 个，顺手修）**

* ``治疗功能 / 医疗作用 / 疗效``（ad_law，critical）把**法定免责声明与否定式**
  判成违规："本品为普通食品，不具有疾病预防、治疗功能"——《食品安全法》
  第七十三条要求写的这句话，被判"critical 违规"；"我们不承诺疗效"同理。
  合规工具把法定声明判违规，用户会立刻不信这个工具。
* ``保健食品 / 理财产品``把**中性行业术语**判成 critical / high。
  这两个词本身不是违规词（广告法管的是"保健食品广告不得含有…"，
  不是禁止提"保健食品"三个字），无条件匹配必然大面积误报。
  它们真正的价值是"提醒你确认资质/标注"，属于 warning 级。

取舍原则
--------
1. **降级用于"词本身中性、违规与否取决于资质/语境"** → 降 medium（warning），
   提示仍然给出，但不再计为违规；
2. **豁免只用于"有限可枚举的否定搭配"** → 加 ``context_excludes``，
   不动全局豁免表（``context_guard.EXEMPT_PHRASES`` 是全局旋钮，乱加会漏检）；
3. **真·违规词一概不降级**：``永久脱毛``（"永久"是绝对化用语）、
   ``100%``、``保本高息`` 这类保持不变。

写法说明
--------
不手改 JSON：要动 8 条规则、跨 4 个文件，且各文件换行风格不同
（行业包 rules.json 是 CRLF，ad_law.json 是 LF），手改必错。

用法：python scripts/fix_false_positive_defects.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PACKS = _ROOT / "rules" / "industry_packs"

# ---------------------------------------------------------------- A 类：行业包

#: 医美包：把纯项目名从 high 降到 medium，并改写建议文案。
#:
#: 为什么不是删掉：对**没有**《医疗机构执业许可证》的生活美容账号来说，
#: 宣传这些项目确实违规，删了就漏检。降级 + 写清条件，是这两头都顾上的做法。
_BEAUTY_DOWNGRADE = {
    "光子嫩肤": "医疗美容光电项目，需由具备资质的医疗机构开展",
    "注射美容": "属医疗美容范畴，需医疗机构执业许可与执业医师操作",
    "割双眼皮": "医疗美容手术项目，需医疗机构执业许可",
    "线雕": "医疗美容项目，需由具备资质的医疗机构开展",
}

_BEAUTY_SUGGESTION = "非医疗机构请删除；持证医美机构请补充《医疗机构执业许可证》与主诊医师信息"

#: 电商包：否定义务/警示语境的豁免搭配。
#:
#: 只收"**否定词与'刷单'紧邻**"这一种有限枚举。
#:
#: 刻意不收的三类：
#: * ``刷单返利 / 刷单骗局 / 刷单诈骗`` —— 既出现在反诈科普里，也是刷单招揽
#:   话术本身的高频写法，收进去就是拿漏检换误报（"刷单返利日结300"会整条绕过）；
#: * ``任何刷单`` 这类**中间夹词**的搭配 —— 它同样能是"满足任何刷单需求"，
#:   收进去会放过真招揽；
#: * 单独的 ``刷单`` 前后缀（如 ``刷单``+任意字）—— 无边界可靠。
#:
#: ⚠️ 已知边界：``context_excludes`` 的判定是"命中区间被豁免词组完全覆盖"，
#: 所以中间夹词的否定式（"不使用任何刷单手段"）覆盖不到，仍会报出。
#: 通用否定守卫（命中前 N 字出现否定词即豁免）风险更大 —— 会放过
#: "全网最低价，不满意不收费" 这类真违规，故不做。
_ECOMMERCE_EXCLUDES = {
    "刷单": [
        # —— 否定 ——
        "不刷单", "没有刷单", "不是刷单", "不做刷单", "无刷单", "零刷单",
        "绝不刷单", "永不刷单", "从不刷单", "从未刷单", "不会刷单",
        "不参与刷单",
        # —— 禁止 / 打击 ——
        "禁止刷单", "严禁刷单", "打击刷单", "抵制刷单", "拒绝刷单",
        "反对刷单", "杜绝刷单", "严查刷单", "反刷单",
        # —— 定性 ——
        "刷单违法", "刷单是违法",
    ],
}

# ---------------------------------------------------------------- B 类：旧库

#: ad_law：法定免责声明里出现的词，命中落在这些搭配内不算违规。
#:
#: 只覆盖"否定式"的有限枚举；"本品具有治疗功能"这种正向声称照旧报 critical。
_AD_LAW_EXCLUDES = {
    "治疗功能": [
        "不具有疾病预防、治疗功能",
        "不具有疾病预防和治疗功能",
        "不涉及疾病预防、治疗功能",
        "不涉及疾病预防和治疗功能",
        "无治疗功能",
        "不宣称治疗功能",
        "不声称治疗功能",
    ],
    "医疗作用": [
        "不具备医疗作用",
        "不具有医疗作用",
        "无医疗作用",
        "不宣称医疗作用",
        "不声称医疗作用",
    ],
    # 「疗效」同理：广告法禁止的是"声称疗效"，不是"提到疗效二字"。
    # "我们不承诺疗效"这种免责声明被判 critical，罚的是最守规矩的那批人。
    "疗效": [
        "不承诺疗效",
        "不承诺任何疗效",
        "不保证疗效",
        "无疗效",
        "没有疗效",
        "不具有疗效",
        "不宣称疗效",
        "不声称疗效",
        "不代表疗效",
    ],
}

#: ad_law：中性术语降为 medium（提示级）。
#:
#: 这两个词被判 critical/high 的根因是"把术语当违规词"：
#: 广告法约束的是**怎么描述**保健食品/理财产品，不是禁止提及它们。
#: 降级后仍会产出 warning，suggestion 里的资质/标注提醒照常给到用户。
_AD_LAW_DOWNGRADE = {
    "保健食品": (
        "medium",
        "「保健食品」是中性术语，本身不违规。本项提示你确认："
        "广告已标注「本品不能代替药物」，且未暗示疾病预防、治疗功能。",
    ),
    "理财产品": (
        "medium",
        "「理财产品」是中性术语，本身不违规。本项提示你确认："
        "具备相应金融资质，且已按规定作出风险提示。",
    ),
}


# ---------------------------------------------------------------- 工具


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, obj) -> None:
    """按文件原有换行风格写回。

    行业包的 rules.json 是 CRLF、仓库根的 ad_law.json 是 LF ——
    统一成一种会让整份文件变成 diff，review 时看不出真正改了什么。
    """
    raw = path.read_bytes()
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _fix_pack_rules(pack_id: str) -> list[str]:
    """改行业包里的规则，返回改动说明。"""
    path = _PACKS / pack_id / "rules.json"
    rules = _load(path)
    log: list[str] = []

    for r in rules:
        kw = r.get("keyword")
        if kw in _BEAUTY_DOWNGRADE and r.get("severity") != "medium":
            r["severity"] = "medium"
            r["suggestion"] = _BEAUTY_SUGGESTION
            r["note"] = (
                f"{_BEAUTY_DOWNGRADE[kw]}。项目名本身不违规，"
                "违规的是无资质主体开展或宣传；持证机构可保留，"
                "但医疗广告需经审查。"
            )
            log.append(f"{pack_id}: {kw} high → medium（项目名，条件违规）")

        if kw in _ECOMMERCE_EXCLUDES:
            want = _ECOMMERCE_EXCLUDES[kw]
            if r.get("context_excludes") != want:
                r["context_excludes"] = want
                log.append(f"{pack_id}: {kw} 增加 {len(want)} 条否定语境豁免")

    _dump(path, rules)
    return log


def _fix_ad_law() -> list[str]:
    """改仓库根的核心广告法词库，返回改动说明。"""
    path = _ROOT / "rules" / "ad_law.json"
    rules = _load(path)
    log: list[str] = []

    for r in rules:
        kw = r.get("keyword")

        if kw in _AD_LAW_EXCLUDES:
            want = _AD_LAW_EXCLUDES[kw]
            if r.get("context_excludes") != want:
                r["context_excludes"] = want
                log.append(f"ad_law: {kw} 增加 {len(want)} 条法定声明豁免")

        if kw in _AD_LAW_DOWNGRADE:
            sev, note = _AD_LAW_DOWNGRADE[kw]
            if r.get("severity") != sev:
                old = r.get("severity")
                r["severity"] = sev
                r["note"] = note
                log.append(f"ad_law: {kw} {old} → {sev}（中性术语）")

    _dump(path, rules)
    return log


def main() -> int:
    log: list[str] = []
    log += _fix_pack_rules("medical_beauty")
    log += _fix_pack_rules("ecommerce")
    log += _fix_ad_law()

    if not log:
        print("无改动（已经是修好的状态）")
        return 0
    print(f"共 {len(log)} 处改动：")
    for line in log:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
