#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修掉 4 处"把法定免责声明判成违规"的存量误报（旧库 ad_law + 宠物包）。

怎么发现的
----------
2026-09-15 给 5 个新行业包补语料时，新增的 4 条正例（写的都是"合法但容易
踩雷"的写法）在 violation 级被误报，误报率被抬到 4.9%。逐条追下去，
**全部来自旧库 ad_law，与 5 个新包无关**：

* ``治疗功能`` —— 规则的 ``context_excludes`` 只枚举了"不具有疾病预防、
  治疗功能"这一族（《食品安全法》第七十三条那句法定声明的写法），
  漏了"不具有疾病治疗功能"这一族；
* ``治疗`` / ``诊疗`` —— 这两条**一条否定语境都没配**：文案里只要出现
  "治疗""诊疗"就判 critical，于是"本产品不能替代药物治疗"这种标准
  免责话术直接变成违规；
* ``婴幼儿配方食品`` —— 与同文件的 ``保健食品`` 是同一类问题：词本身是
  中性品类名，真正要管的是"有没有注册 / 备案"，却按 critical 判违规。
  而且它引的《广告法》第十八条是**保健食品**条款，对不上。

为什么必须修
------------
合规工具把**法定要求你写的那句话**判成违规，用户会立刻不信这个工具。
这比漏检更致命（``tests/test_false_positive.py`` 的第一原则）。

取舍
----
沿用 ``fix_false_positive_defects.py`` 立下的两条规矩：
1. **豁免只用于"有限可枚举的否定搭配"** —— ``context_excludes`` 的语义是
   "命中必须整段落在这个词组里"才豁免，写不了正则，也不去动全局豁免表
   （``context_guard.EXEMPT_PHRASES`` 是全局旋钮，乱加会漏检）；
2. **词本身中性、违规与否取决于资质的 → 降级，不删** —— 删了就漏检，
   降成提示仍然提醒得到。

顺带修的依据问题（同一批语料暴露出来的）
----------------------------------------
宠物包「处方粮 / 处方猫粮」只写了《饲料和饲料添加剂管理条例》没写条号。
现行版本（2017 年第四次修订）里"禁止对饲料、饲料添加剂作具有预防或者治疗
动物疾病作用的说明或者宣传"是**第三十条**（第二十一条是标签要求）。
补上条号，用户才复核得了。

用法::

    python scripts/fix_medical_negation_defects.py
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: "不具有疾病治疗功能"这一族 —— 三条规则共用（文案里同一段话会同时命中
#: 「治疗功能」与「治疗」，只给一条配豁免会剩下另一条继续误报）
_TREAT_FUNCTION_FAMILY = [
    "不具有疾病治疗功能",
    "不具有疾病治疗的功能",
    "不涉及疾病治疗功能",
    "无疾病治疗功能",
]

#: 规则 keyword → 要补进去的 context_excludes（去重后写入）
_EXTRA_EXCLUDES: dict[str, list[str]] = {
    "治疗功能": _TREAT_FUNCTION_FAMILY + [
        "不具有治疗功能",
        "不涉及治疗功能",
    ],
    "治疗": _TREAT_FUNCTION_FAMILY + [
        "不能替代药物治疗",
        "不能代替药物治疗",
        "不可替代药物治疗",
        "不能替代治疗",
        "不能代替治疗",
        "不能用于治疗",
        "不得用于治疗",
        "不用于治疗",
        "不具有治疗作用",
        "无治疗作用",
        "不以治疗为目的",
        "非治疗用途",
        "不涉及治疗",
    ],
    "诊疗": [
        "不能替代兽医诊疗",
        "不能替代诊疗",
        "不能代替诊疗",
        "不可替代诊疗",
        "不具有诊疗功能",
        "不提供诊疗",
        "不涉及诊疗",
        "不用于诊疗",
        "不以诊疗为目的",
        "非诊疗目的",
    ],
}

#: 婴幼儿配方食品：中性品类名 + 依资质判断，按「保健食品」的先例降为提示，
#: 并把依据从《广告法》第十八条（保健食品条款）改成对得上的《食品安全法》。
_POWDER_SUGGESTION = (
    "婴幼儿配方乳粉须有产品配方注册号（国食注字 YP）；"
    "其他婴幼儿配方食品须完成配方、原料与标签备案"
)
_POWDER_NOTE = (
    "「婴幼儿配方食品」是中性品类名，本身不违规。本项提示你确认："
    "已取得婴幼儿配方乳粉产品配方注册号，或已完成配方与标签备案，"
    "且文案未涉及疾病预防、治疗功能或益智、增强抵抗力等功能性表述。"
)
_POWDER_LAW_REF = "《食品安全法》第八十一条"

#: 宠物包「处方粮」：条例名 → 条例名 + 条号
_FEED_LAW_REF = "《饲料和饲料添加剂管理条例》第三十条"


# ---------------------------------------------------------------- 读写工具

def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data) -> None:
    """按文件**原有**换行风格写回。

    词库里的换行是混的（旧库 CRLF、多数行业包 LF），统一转换会造成
    整文件 diff 噪音，把真正的改动埋掉。
    """
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _patch_rules(path: Path, patcher) -> list[str]:
    """对某个规则文件里的每条规则调用 ``patcher``，返回改动说明。"""
    data = _load(path)
    rules = data if isinstance(data, list) else data.get("rules", [])
    changed: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        msg = patcher(rule)
        if msg:
            changed.append(msg)
    if changed:
        _dump(path, data)
    return changed


# ---------------------------------------------------------------- 三处修法

def _fix_negation_excludes(rule: dict) -> str | None:
    kw = rule.get("keyword")
    extra = _EXTRA_EXCLUDES.get(kw)
    if not extra:
        return None
    existing = list(rule.get("context_excludes") or [])
    merged = existing + [p for p in extra if p not in existing]
    if merged == existing:
        return None
    rule["context_excludes"] = merged
    return f"  豁免 +{len(merged) - len(existing)} 条：{kw}"


def _fix_infant_formula(rule: dict) -> str | None:
    if rule.get("keyword") != "婴幼儿配方食品":
        return None
    if (rule.get("severity") == "medium"
            and rule.get("law_ref") == _POWDER_LAW_REF
            and rule.get("note") == _POWDER_NOTE):
        return None
    old_sev, old_law = rule.get("severity"), rule.get("law_ref")
    rule["severity"] = "medium"
    rule["law_ref"] = _POWDER_LAW_REF
    rule["suggestion"] = _POWDER_SUGGESTION
    rule["note"] = _POWDER_NOTE
    return f"  降级 {old_sev}→medium 且改依据 {old_law} → {_POWDER_LAW_REF}"

def _fix_feed_law_ref(rule: dict) -> str | None:
    if rule.get("law_ref") != "《饲料和饲料添加剂管理条例》":
        return None
    rule["law_ref"] = _FEED_LAW_REF
    return f"  补条号：{rule.get('keyword')} → {_FEED_LAW_REF}"


def main() -> int:
    total = 0

    print("[1/2] rules/ad_law.json")
    for msg in _patch_rules(_ROOT / "rules" / "ad_law.json", _fix_negation_excludes):
        print(msg)
        total += 1
    for msg in _patch_rules(_ROOT / "rules" / "ad_law.json", _fix_infant_formula):
        print(msg)
        total += 1

    print("[2/2] rules/industry_packs/pet/rules.json")
    for msg in _patch_rules(
        _ROOT / "rules" / "industry_packs" / "pet" / "rules.json", _fix_feed_law_ref
    ):
        print(msg)
        total += 1

    print(f"\n共 {total} 处改动" + ("（已是目标状态，无改动）" if total == 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
