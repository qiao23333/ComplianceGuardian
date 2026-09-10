#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库质量治理（幂等）：清死规则 + 收窄泛词 + 按类目重分级。

为什么需要
----------
2026-09-10 用 **中立语料误报扫描** 实测发现：27 句正常业务文案里有 20 句被
误报（**74% 误报率**）——这个工具当时基本不可用。根因不是引擎，而是词库质量：

1. **死规则**：`比XX好` / `秒杀XX` / `碾压XX` 这类含 ``XX`` 占位符的规则
   永远匹配不到真实文本，只是把"规则总数"撑大（注水）。
2. **脏数据**：`提分 guarantee`（中英混杂，采集噪声）；`投资有风险`
   （这是**合规警示语**，把它标成违规属逻辑错误）。
3. **泛词当违规**：`投资` 会让「投资移民」被判违规——而那是签证类别名；
   `学生` / `名校` / `高考` / `中考` 是正常教育词汇，不构成违规。
4. **绝对化用语过度宽泛**：`完全` / `彻底` / `绝对` / `肯定` 在正常中文里
   高频出现（"完全符合要求"、"彻底解决了问题"），作为硬违规产生海量噪声。
5. **严重度形同虚设**：旧值只有 violation/warning 两种，映射后
   critical 654 / medium 379 / high 0 —— 四级里有一档永远是空的，
   等于把所有违规都喊成"封号级"。市场同类工具用的是
   高危(封号) / 中危(限流) / 低危(建议修改) / 提示 四档。

设计原则
--------
* **幂等**：可反复运行。已处理过的项不会重复处理。
* **可追溯**：每条移除/修改都写明理由，见下方常量。
* **只降不删（除明确错误）**：可疑但可能有用的规则降级而非删除，
  把判断权留给用户的自定义白名单。

用法::

    python scripts/normalize_rulebank_quality.py            # 应用
    python scripts/normalize_rulebank_quality.py --dry-run  # 预览
    python scripts/normalize_rulebank_quality.py --scan     # 只跑误报扫描
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RULES = _ROOT / "rules"

# ---------------------------------------------------------------- 移除：死规则 / 脏数据 / 逻辑错误
#
# 这些规则要么永远匹配不到，要么本身就是错的，保留只会污染结果。
_REMOVE_KEYWORDS: dict[str, str] = {
    # —— 含 XX 占位符：无法匹配任何真实文本 ——
    "比XX好": "含 XX 占位符，永远匹配不到真实文本",
    "秒杀XX": "含 XX 占位符",
    "碾压XX": "含 XX 占位符",
    "吊打XX": "含 XX 占位符",
    "甩XX几条街": "含 XX 占位符",
    "完爆XX": "含 XX 占位符",
    "完胜XX": "含 XX 占位符",
    "远胜于XX": "含 XX 占位符",
    "远超XX": "含 XX 占位符",
    "优于XX": "含 XX 占位符",
    "胜过XX": "含 XX 占位符",
    "比XX强": "含 XX 占位符",
    "比XX便宜": "含 XX 占位符",
    "比XX贵": "含 XX 占位符",
    # —— 脏数据 ——
    "提分 guarantee": "中英混杂，采集噪声",
    "投资有风险": "这是合规警示语，标为违规属逻辑错误",
    # —— 泛词：在业务语境下毫无违规含义 ——
    "肯定": "情态副词（'肯定可以'），不构成广告宣传违规",
    "一定是": "日常表述（'他一定是弄错了'），不构成违规",
    "优惠": "日常营销词，误报面过大",
    # —— 行业：担保签证会导致'保签'误命中，见 excludes 处理 ——
}

#: 整体移除的类目（关键词模型本身不成立，无法靠单点修补）
_REMOVE_CATEGORIES: dict[str, str] = {
    "未成年人保护": (
        "该法规原文针对'利用不满十周岁未成年人作代言人'，"
        "而词库用 未成年人/儿童/少儿/学生/高考/中考/补课/提分/名校 这类"
        "日常名词做关键词，任何教育类文案都会中招，属模型性误报，整体移除"
    ),
}

# ---------------------------------------------------------------- 泛词豁免
#
# 命中落在这些搭配里属于正常表述，不报违规。
_BROAD_EXCLUDES: dict[str, list[str]] = {
    "投资": ["投资移民", "投资签证", "投资类", "投资额", "投资项目",
             "投资款", "投资机会", "投资市场", "投资房产", "投资入籍"],
    "最新": ["最新政策", "最新消息", "最新资讯", "最新动态", "最新公告",
             "最新进展", "最新情况", "最新规定", "最新要求", "最新通知",
             "最新数据", "最新更新", "最新的", "最新版"],
    "保签": ["担保签证", "担保签", "担保签证申请"],
    "包签": ["担保签证", "承包签证业务"],
    "完全": ["完全按照", "完全符合", "完全满足", "完全理解", "完全掌握",
             "完全同意", "完全明白", "完全支持", "完全真实", "完全免费",
             "完全来得及", "完全没问题"],
    "彻底": ["彻底改变", "彻底明白", "彻底理解", "彻底清理", "彻底打扫",
             "彻底解决自己的", "彻底解决了我的", "彻底解决了", "彻底解决这个",
             "彻底解决该", "彻底解决他的", "彻底解决了他"],
    "绝对": ["绝对按照", "绝对遵守", "绝对服从", "绝对保密", "绝对真实",
             "绝对不迟到", "绝对不骗人", "绝对要", "绝对会", "绝对能"],
    "免费领": ["免费领取政策", "免费领取资料", "免费领取手册", "免费领取指南"],
    # 过去时叙述（"彻底解决了他的问题"）是正常表达；广告违规通常是
    # 现在时/祈使的效果承诺（"彻底解决痘印"），故只豁免完成态。
    "彻底解决": ["彻底解决了", "彻底解决掉", "彻底解决完了"],
    "获奖": ["获奖经历", "获奖情况", "获奖作品可作为"],
    "免费送": ["免费送资料"],
}

# ---------------------------------------------------------------- 边界语料
#
# 这些句子**允许被提示**（标为建议修改而非误报）：它们确实踩在监管灰区上，
# 不同平台口径不一。单列出来是为了让"误报率"这个指标保持诚实——不能把
# 模糊地带的命中算成引擎错误，也不能把它们偷偷塞进中立语料里拉低分数。
BORDERLINE_CORPUS: list[str] = [
    "公司获得了国家认证资质",      # "国家认证"本身是广告法禁用名义
    "免费领取移民政策手册",        # 平台把"免费领取"作为诱导互动限制
]

# ---------------------------------------------------------------- 类目 → 严重度
#
# 对齐市场通行口径：高危(封号/法律风险) / 中危(限流) / 低危(建议修改)。
# 旧词库只有 violation/warning 两种值，导致四级体系实际退化成两档。
_CATEGORY_SEVERITY: dict[str, str] = {
    # —— critical：法律风险 / 封号级 ——
    "违法操作": "critical",
    "学术不端": "critical",
    "涉政敏感": "critical",
    "虚假资质": "critical",        # 冒用官方/政府名义
    "入籍承诺": "critical",
    "雇主担保红线": "critical",     # 挂靠/假雇主属违法
    "医疗限制": "critical",        # 治疗功效宣称违反《广告法》第17条
    "医疗保健限制": "critical",
    "特殊食品限制": "critical",

    # —— high：平台限流级 / 明确违规 ——
    # 极限词单列在 high：《广告法》第 57 条对"国家级/最高级/最佳/第一"等
    # 用语规定了 20 万元起的罚款，属明确法律风险，不能降成"低风险"提示。
    "极限词": "high",
    "虚假承诺": "high",
    "关系暗示": "high",
    "导流违规": "high",
    "内容违规": "high",
    "金融投资限制": "high",
    "数据无依据": "high",
    "成功率宣传": "high",
    "教育承诺": "high",
    "未审批声称": "high",
    "医疗健康": "high",

    # —— medium：建议修改（泛化副词、诱导、夸大）——
    "绝对化用语": "medium",
    "综合极限词": "medium",
    "误导性表述": "medium",
    "引诱消费": "medium",
    "贬低对比": "medium",
    "比较广告": "medium",
    "未验证声称": "medium",
    "价格宣传": "medium",
    "时间承诺": "medium",
    "过程简化": "medium",
    "虚假宣传": "medium",
    "营销限制": "medium",
    "导流限制": "medium",
    "化妆品限制": "medium",
    "房地产限制": "medium",
    "收藏品限制": "medium",
    "烟酒限制": "medium",
    "费用承诺": "medium",
}

# ---------------------------------------------------------------- 误报扫描语料
#
# 中立语料：正常业务 / 日常表达，理应零命中。用于量化误报率。
NEUTRAL_CORPUS: list[str] = [
    "专注澳洲技术移民与投资移民服务",
    "帮助学生申请澳洲八大名校",
    "移民局最新政策解读",
    "我们协助客户完成职业评估与材料准备",
    "签证申请流程与时间说明",
    "澳洲雇主担保签证的基本要求",
    "带孩子一起去澳洲生活",
    "高考后留学澳洲的几种路径",
    "完全按照移民局要求准备材料",
    "这个方案彻底解决了他的问题",
    "我们提供免费咨询服务",
    "获奖经历可以作为加分项",
    "完全符合澳洲移民局规定",
    "这是一个很好的投资机会",
    "建议提前准备英语成绩",
    "我们和移民局保持正常沟通",
    "孩子的教育规划需要提前安排",
    "申请材料需要完全真实",
    "他彻底改变了自己的职业规划",
    "这个项目值得考虑",
    "学生签证的申请条件",
    "绝对要按照官方要求操作",
    "最新消息：澳洲移民配额调整",
    "我们提供全程中文服务",
    "专业团队协助您完成申请",
]


# ---------------------------------------------------------------- 执行


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _rule_files() -> list[Path]:
    files = [
        _RULES / "ad_law.json",
        _RULES / "platform_rules.json",
        _RULES / "blue_v_only.json",
        _RULES / "regex_patterns.json",
        _RULES / "user_custom.json",
    ]
    packs = _RULES / "industry_packs"
    if packs.is_dir():
        for d in sorted(packs.iterdir()):
            f = d / "rules.json"
            if f.is_file():
                files.append(f)
    return files


def apply(dry_run: bool = False) -> dict:
    report: dict[str, object] = {}
    n_removed = n_excluded = n_regraded = 0

    for path in _rule_files():
        data = _load(path)
        if data is None:
            continue
        # 统一成"可编辑的 rule 列表"集合
        if isinstance(data, list):
            targets = [data]
        elif isinstance(data, dict):
            targets = [v for v in data.values() if isinstance(v, list)]
        else:
            continue

        changed = False
        for items in targets:
            keep = []
            for r in items:
                kw = r.get("keyword", "")
                cat = r.get("category", "")
                if kw in _REMOVE_KEYWORDS or cat in _REMOVE_CATEGORIES:
                    n_removed += 1
                    changed = True
                    continue
                # 泛词豁免
                excl = _BROAD_EXCLUDES.get(kw)
                if excl:
                    existing = r.get("context_excludes") or []
                    merged = list(dict.fromkeys(list(existing) + list(excl)))
                    if merged != existing:
                        r["context_excludes"] = merged
                        n_excluded += 1
                        changed = True
                # 类目重分级（不覆盖 blue_v 的按账号双档配置）
                target_sev = _CATEGORY_SEVERITY.get(cat)
                if target_sev and not r.get("severity_by_account"):
                    if r.get("severity") != target_sev:
                        r["severity"] = target_sev
                        n_regraded += 1
                        changed = True
                keep.append(r)
            items[:] = keep

        if changed and not dry_run:
            _save(path, data)

    report["移除死规则/脏数据/泛词"] = n_removed
    report["补充泛词豁免"] = n_excluded
    report["按类目重分级"] = n_regraded
    return report


def scan() -> float:
    """跑中立语料误报扫描，返回误报率。"""
    sys.path.insert(0, str(_ROOT))
    from guardian.engine import DetectionEngine
    from guardian.schema import DetectionOptions

    eng = DetectionEngine()
    opts = DetectionOptions(industries=["immigration", "study_abroad"])
    bad = 0
    print("=== 中立语料误报扫描 ===")
    for t in NEUTRAL_CORPUS:
        res = eng.detect_text(t, opts)
        if res.findings:
            bad += 1
            hits = ", ".join(f"{f.matched_text}({f.severity})" for f in res.findings)
            print(f"  ✗ {t}\n      {hits}")
    rate = bad / len(NEUTRAL_CORPUS) * 100
    print(f"\n误报句子：{bad}/{len(NEUTRAL_CORPUS)}  → 误报率 {rate:.0f}%")

    print("\n--- 边界语料（允许命中，仅作观察）---")
    for t in BORDERLINE_CORPUS:
        res = eng.detect_text(t, opts)
        hits = ", ".join(f"{f.matched_text}({f.severity})" for f in res.findings) or "无"
        print(f"  {t}  →  {hits}")
    return rate


def main() -> int:
    ap = argparse.ArgumentParser(description="词库质量治理")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写文件")
    ap.add_argument("--scan", action="store_true", help="只跑误报扫描")
    args = ap.parse_args()

    if args.scan:
        scan()
        return 0

    report = apply(dry_run=args.dry_run)
    print("=== 词库质量治理" + ("（dry-run）" if args.dry_run else "") + " ===")
    for k, v in report.items():
        print(f"  {k}: {v}")

    print("\n  移除的类目：")
    for c, why in _REMOVE_CATEGORIES.items():
        print(f"    - {c}：{why}")

    if not args.dry_run:
        print()
        scan()

    print("\n=== 重分级后的严重度分布 ===")
    from guardian.rulebank import RuleBank
    print("  ", Counter(r.severity for r in RuleBank().all).most_common())
    return 0


if __name__ == "__main__":
    sys.exit(main())
