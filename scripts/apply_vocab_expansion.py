#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词库扩充（幂等）：补齐移民行业红线 + 导流联系方式 + 新增留学行业包。

背景
----
2026-09-10 批判性自检发现，原词库虽然"看起来"覆盖了移民行业，但存在三类硬伤：

1. **导流链断裂**：平台词库只有 ``微信号``，没有 ``微信`` 本身。
   于是谐音表里 ``薇→微`` 把 "加我薇信" 归一化成 "加我微信" 之后，
   词库里**没有任何规则能接住**——旗舰级的"谐音抗规避"能力在实际
   最高频的导流场景里收益为零。补 ``微信`` + ``context_excludes``
   排除 "微信支付/微信公众号" 等正常搭配后，整条链路才通。

2. **基础业务词缺失**：``加我微信`` 检不出（原有规则只有非连续的
   ``加微信``）；规避写法 "加卫星/卫星号" 完全空白。

3. **高危误报词**：``有关系`` / ``一步到位`` / ``直签`` / ``保送``
   在正常中文里极其常见（"这个和那个有关系"、"一步到位解决问题"、
   "保送清华"），作为裸关键词会产生大量误报。本次收窄为精确词组。

设计原则
--------
* **幂等**：重复运行不会产生重复规则（按 keyword 去重）。可安全重跑。
* **只做词组，不做裸业务词**：``移民``/``签证``/``PR``/``绿卡`` 是正常
  业务词汇，**绝不**单独入库，否则整个工具不可用。
* **每条规则都要有 suggestion**（给用户可执行的修改建议）与 note（依据）。

用法::

    python scripts/apply_vocab_expansion.py            # 应用
    python scripts/apply_vocab_expansion.py --dry-run  # 只看会改什么
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RULES = _ROOT / "rules"

# ---------------------------------------------------------------- 关键词收窄
#
# 这些裸关键词在正常中文里高频出现，会产生大量误报。
# 直接移除，替换为精确词组（见 NARROW_REPLACEMENTS）。
_TOO_BROAD = {
    "有关系": "正常表述'这个和那个有关系'会被误判，改为精确词组",
    "一步到位": "日常用语（'一步到位解决问题'）会被误判",
    "直签": "旅游/货运/留学场景都出现，语义不唯一",
    "保送": "教育领域'保送清华'是真实存在的正当表述",
    "包送": "语义不唯一（'包送到家'）",
}

#: 豁免词组：命中落在这些搭配里视为正常用法，不报违规
_CONTEXT_EXCLUDES = {
    # 广告法极限词，但日常表述极常见
    "无条件": [
        "无条件支持", "无条件爱你", "无条件接受", "无条件服从",
        "无条件信任", "无条件投降", "无条件退款",
    ],
}

# ---------------------------------------------------------------- 平台层收窄
#
# `关注我` 在小红书是被平台鼓励的正常 CTA，作为裸关键词属明确误报。
# 真正违规的是"关注我 + 给好处"的诱导搭配，因此收窄为具体词组。
_PLATFORM_TOO_BROAD = {
    "关注我": "小红书鼓励'关注我'，属正常 CTA；收窄为诱导性搭配",
}

_PLATFORM_NARROW_ADD = {
    "xiaohongshu": [
        {"keyword": "关注我领取", "category": "内容违规", "severity": "violation",
         "suggestion": "改为'欢迎关注，资料见主页'",
         "note": "以利益诱导关注属违规"},
        {"keyword": "关注我发你", "category": "内容违规", "severity": "violation",
         "suggestion": "改为'欢迎关注'",
         "note": "以利益诱导关注"},
        {"keyword": "关注我就送", "category": "内容违规", "severity": "violation",
         "suggestion": "改为'欢迎关注'",
         "note": "以利益诱导关注"},
        {"keyword": "关注我私信", "category": "导流违规", "severity": "violation",
         "suggestion": "改为'可评论区交流'",
         "note": "引导至私信导流"},
    ],
}

# ---------------------------------------------------------------- 移民行业包

_IMMIGRATION_NEW = [
    # —— 虚假承诺（签证结果不可承诺，澳洲 MARA 执业守则明令禁止）——
    {"keyword": "保证通过", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助准备材料'，签证结果由移民局决定",
     "note": "签证审批权在移民局，任何机构无权保证结果"},
    {"keyword": "包获批", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助递交并跟进'",
     "note": "承诺获批属虚假宣传"},
    {"keyword": "必获批", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'按流程递交申请'",
     "note": "绝对化结果承诺"},
    {"keyword": "稳获批", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'协助提高材料完整度'",
     "note": "'稳'字暗示结果可控，与事实不符"},
    {"keyword": "百分百下签", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'协助递交签证申请'",
     "note": "百分百承诺违反广告法绝对化用语规定"},
    {"keyword": "100%下签", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "结果性保证"},
    {"keyword": "百分百获批", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "结果性保证"},
    {"keyword": "保证签证", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助办理签证'",
     "note": "不能对签证结果做保证"},
    {"keyword": "包签证", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助办理签证'",
     "note": "包办承诺"},
    {"keyword": "一次过签", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'协助准备签证材料'",
     "note": "一次过签不可承诺"},
    {"keyword": "一签过", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "结果性保证的变体写法"},

    # —— 关系 / 名额暗示 ——
    {"keyword": "跟移民局有关系", "category": "关系暗示", "severity": "violation",
     "suggestion": "删除，改为'熟悉签证政策与流程'",
     "note": "暗示与官方有特殊关系属误导"},
    {"keyword": "有关系好办事", "category": "关系暗示", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "暗示非正常渠道"},
    {"keyword": "内部名额", "category": "关系暗示", "severity": "violation",
     "suggestion": "删除，改为'按官方配额正常申请'",
     "note": "签证不存在'内部名额'"},
    {"keyword": "内定名额", "category": "关系暗示", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "虚假的特殊通道暗示"},
    {"keyword": "内部指标", "category": "关系暗示", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "签证无内部指标"},
    {"keyword": "走后门", "category": "违法操作", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "暗示违规操作"},
    {"keyword": "打点关系", "category": "违法操作", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "暗示行贿等违法行为"},

    # —— 伪造材料（刑事风险）——
    {"keyword": "假流水", "category": "违法操作", "severity": "violation",
     "suggestion": "删除；材料造假将导致拒签并可能触犯刑律",
     "note": "伪造银行流水属违法"},
    {"keyword": "假学历", "category": "违法操作", "severity": "violation",
     "suggestion": "删除；学历造假会被取消签证",
     "note": "伪造学历属违法"},
    {"keyword": "假雇佣", "category": "违法操作", "severity": "violation",
     "suggestion": "删除；虚假雇佣关系违法",
     "note": "雇主担保必须真实雇佣"},
    {"keyword": "买工作", "category": "违法操作", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "买卖工作offer属违法"},
    {"keyword": "卖工作", "category": "违法操作", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "买卖工作offer属违法"},
    {"keyword": "挂靠公司", "category": "违法操作", "severity": "violation",
     "suggestion": "删除；挂靠属虚假雇佣",
     "note": "挂靠雇主违法"},
    {"keyword": "买卖签证", "category": "违法操作", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "签证不可买卖"},

    # —— 价格宣传（绝对化）——
    {"keyword": "全澳最低价", "category": "价格宣传", "severity": "violation",
     "suggestion": "改为'收费透明'或明示具体价格",
     "note": "'最低价'属广告法绝对化用语"},
    {"keyword": "澳洲最低价", "category": "价格宣传", "severity": "violation",
     "suggestion": "改为'收费透明'",
     "note": "绝对化价格宣传"},
    {"keyword": "全行业最低", "category": "价格宣传", "severity": "violation",
     "suggestion": "改为'性价比高'",
     "note": "绝对化用语"},
    {"keyword": "价格最低", "category": "价格宣传", "severity": "violation",
     "suggestion": "改为'收费合理'",
     "note": "绝对化用语"},

    # —— 综合极限词（地域版）——
    {"keyword": "澳洲第一", "category": "综合极限词", "severity": "violation",
     "suggestion": "改为'服务多年的持牌机构'",
     "note": "'第一'属广告法禁用绝对化用语"},
    {"keyword": "全澳第一", "category": "综合极限词", "severity": "violation",
     "suggestion": "改为'服务多年的持牌机构'",
     "note": "绝对化用语"},
    {"keyword": "移民行业第一", "category": "综合极限词", "severity": "violation",
     "suggestion": "改为'专注移民服务'",
     "note": "绝对化用语"},
    {"keyword": "澳洲唯一", "category": "综合极限词", "severity": "violation",
     "suggestion": "改为'具备相关资质的机构'",
     "note": "'唯一'属绝对化用语"},

    # —— 费用承诺 ——
    {"keyword": "不成功退全款", "category": "费用承诺", "severity": "warning",
     "suggestion": "改为'按合同约定退费'，并明确退费条件",
     "note": "退费承诺需与合同一致，避免无法兑现"},
    {"keyword": "失败全赔", "category": "费用承诺", "severity": "warning",
     "suggestion": "改为'按合同约定处理'",
     "note": "赔偿承诺需谨慎"},
]

# ---------------------------------------------------------------- 导流联系方式

#: 微信类关键词的豁免搭配（正常表述，不该报）
_WECHAT_EXCLUDES = [
    "微信支付", "微信公众号", "微信视频号", "微信读书", "微信红包",
    "微信表情", "微信运动", "微信小程序", "微信商城", "微信登录",
    "微信好友", "微信朋友圈", "微信客服", "微信扫码", "微信扫一扫",
]

_PLATFORM_NEW = {
    "xiaohongshu": [
        {"keyword": "微信", "category": "导流违规", "severity": "violation",
         "suggestion": "改为'主页有联系方式'或引导至平台内沟通",
         "note": "小红书禁止站外导流；已排除'微信支付'等正常搭配",
         "context_excludes": _WECHAT_EXCLUDES},
        {"keyword": "加我微信", "category": "导流违规", "severity": "violation",
         "suggestion": "删除，改为'可私信咨询'",
         "note": "站外导流违规"},
        {"keyword": "加个微信", "category": "导流违规", "severity": "violation",
         "suggestion": "删除，改为'可私信咨询'",
         "note": "站外导流违规"},
        {"keyword": "加我好友", "category": "导流违规", "severity": "warning",
         "suggestion": "改为'关注账号'",
         "note": "引导站外建立联系"},
        {"keyword": "加卫星", "category": "导流违规", "severity": "violation",
         "suggestion": "删除该表述（'卫星'是微信的规避写法）",
         "note": "常见规避写法，与'微信'同义"},
        {"keyword": "卫星号", "category": "导流违规", "severity": "violation",
         "suggestion": "删除该表述",
         "note": "'卫星号'即微信号的规避说法"},
        {"keyword": "私聊我", "category": "导流违规", "severity": "warning",
         "suggestion": "改为'可评论区交流'",
         "note": "引导私域"},
        {"keyword": "主页联系", "category": "导流违规", "severity": "warning",
         "suggestion": "改为'见平台内主页简介'",
         "note": "引导站外联系"},
        {"keyword": "戳我头像", "category": "导流违规", "severity": "warning",
         "suggestion": "改为'关注主页'",
         "note": "变相引导站外联系"},
        {"keyword": "站外联系", "category": "导流违规", "severity": "violation",
         "suggestion": "删除该表述",
         "note": "明示站外导流"},
    ],
    "douyin": [
        {"keyword": "微信", "category": "导流违规", "severity": "violation",
         "suggestion": "改为'主页可见'或平台内沟通",
         "note": "抖音限制站外导流；已排除正常搭配",
         "context_excludes": _WECHAT_EXCLUDES},
        {"keyword": "加我微信", "category": "导流违规", "severity": "violation",
         "suggestion": "删除，改为'私信咨询'",
         "note": "站外导流违规"},
        {"keyword": "加卫星", "category": "导流违规", "severity": "violation",
         "suggestion": "删除该表述",
         "note": "微信的规避写法"},
        {"keyword": "卫星号", "category": "导流违规", "severity": "violation",
         "suggestion": "删除该表述",
         "note": "微信号的规避写法"},
        {"keyword": "私聊我", "category": "导流违规", "severity": "warning",
         "suggestion": "改为'可评论区交流'",
         "note": "引导私域"},
    ],
    "weixin": [
        {"keyword": "微信", "category": "导流限制", "severity": "warning",
         "suggestion": "视频号内可直接引导，但避免出现具体微信号",
         "note": "视频号对站外导流限制相对宽松，标为提示",
         "context_excludes": _WECHAT_EXCLUDES},
        {"keyword": "加我微信", "category": "导流限制", "severity": "warning",
         "suggestion": "改为'微信内搜索关注'",
         "note": "视频号导流限制"},
        {"keyword": "加卫星", "category": "导流限制", "severity": "warning",
         "suggestion": "删除该表述",
         "note": "规避写法"},
    ],
}

# ---------------------------------------------------------------- 留学行业包（新增）

_STUDY_ABROAD = [
    # 虚假承诺
    {"keyword": "保录取", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助提升申请竞争力'",
     "note": "录取决定权在学校，机构无法保证"},
    {"keyword": "包录取", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助提交申请材料'",
     "note": "录取结果不可承诺"},
    {"keyword": "保证录取", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助提升申请通过率'",
     "note": "结果性保证"},
    {"keyword": "保offer", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助准备申请材料'",
     "note": "offer 由学校发放，不可保证"},
    {"keyword": "包offer", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "结果性保证"},
    {"keyword": "名校保录", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'协助申请目标院校'",
     "note": "'保录'属虚假承诺"},
    {"keyword": "100%录取", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "绝对化承诺"},
    {"keyword": "百分百录取", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "绝对化承诺"},
    {"keyword": "保入学", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助办理入学申请'",
     "note": "入学结果不可保证"},
    {"keyword": "包入学", "category": "虚假承诺", "severity": "violation",
     "suggestion": "改为'协助办理入学申请'",
     "note": "结果性保证"},
    {"keyword": "保毕业", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除，改为'提供学业辅导'",
     "note": "毕业由学校按学业标准决定"},
    {"keyword": "包毕业", "category": "虚假承诺", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "结果性保证"},

    # 虚假资质 / 名额
    {"keyword": "内部招生名额", "category": "虚假资质", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "不存在所谓内部招生名额"},
    {"keyword": "内推名额", "category": "虚假资质", "severity": "warning",
     "suggestion": "改为'校友推荐渠道'并明确真实性",
     "note": "需核实真实性，避免误导"},
    {"keyword": "招生官推荐", "category": "虚假资质", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "冒充与招生官的关系属误导"},

    # 费用承诺
    {"keyword": "不成功退全款", "category": "费用承诺", "severity": "warning",
     "suggestion": "改为'按合同约定退费'",
     "note": "退费承诺须与合同一致"},
    {"keyword": "保过退款", "category": "费用承诺", "severity": "warning",
     "suggestion": "改为'按合同约定处理'",
     "note": "避免无法兑现的承诺"},

    # 时间承诺
    {"keyword": "一周下offer", "category": "时间承诺", "severity": "violation",
     "suggestion": "改为'尽早递交，缩短审理等待'",
     "note": "审理周期由学校决定"},
    {"keyword": "一个月出offer", "category": "时间承诺", "severity": "warning",
     "suggestion": "改为'尽快递交申请'",
     "note": "时间承诺不可控"},

    # 学术不端（刑事/学术风险）
    {"keyword": "代考", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "代考属严重学术不端与违法行为"},
    {"keyword": "替考", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "替考违法"},
    {"keyword": "代写", "category": "学术不端", "severity": "violation",
     "suggestion": "删除，改为'提供写作辅导'",
     "note": "代写论文属学术不端"},
    {"keyword": "保分", "category": "学术不端", "severity": "violation",
     "suggestion": "改为'提分课程'",
     "note": "'保分'承诺违反考试机构规定"},
    {"keyword": "买论文", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "买卖论文违法"},
    {"keyword": "假成绩单", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述；材料造假将被取消录取",
     "note": "伪造成绩单违法"},
    {"keyword": "假推荐信", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "伪造推荐信违法"},
    {"keyword": "假实习", "category": "学术不端", "severity": "violation",
     "suggestion": "删除该表述",
     "note": "伪造实习经历属造假"},

    # 过程简化
    {"keyword": "免语言成绩", "category": "过程简化", "severity": "warning",
     "suggestion": "改为'部分院校可凭语言内测申请'",
     "note": "需说明具体适用条件，避免以偏概全"},
    {"keyword": "免雅思入学", "category": "过程简化", "severity": "warning",
     "suggestion": "改为'部分院校接受内测或语言班'",
     "note": "以免误导"},
    {"keyword": "无需高考成绩", "category": "过程简化", "severity": "warning",
     "suggestion": "改为'部分院校可用高中成绩申请'",
     "note": "需注明适用范围"},
    {"keyword": "免高考", "category": "过程简化", "severity": "warning",
     "suggestion": "改为'部分院校接受高中成绩申请'",
     "note": "需注明适用范围"},

    # 综合极限词
    {"keyword": "留学第一", "category": "综合极限词", "severity": "violation",
     "suggestion": "改为'专注留学服务'",
     "note": "绝对化用语"},
    {"keyword": "留学行业领先", "category": "综合极限词", "severity": "warning",
     "suggestion": "改为'服务多年的留学机构'",
     "note": "绝对化用语需审慎"},
]


# ---------------------------------------------------------------- 执行


def _load(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _append_unique(entries: list[dict], new_items: list[dict]) -> int:
    """按 keyword 去重追加，返回新增条数。"""
    have = {e.get("keyword") for e in entries}
    added = 0
    for item in new_items:
        if item["keyword"] in have:
            continue
        entries.append(dict(item))
        have.add(item["keyword"])
        added += 1
    return added


def apply(dry_run: bool = False) -> dict:
    report: dict[str, int] = {}

    # ---- 1) 移民行业包：收窄 + 扩充 ----
    path = _RULES / "industry_packs" / "immigration" / "rules.json"
    data = _load(path)
    if not isinstance(data, list):
        raise SystemExit(f"[错误] 找不到或格式错误：{path}")

    before = len(data)
    removed = [r for r in data if r.get("keyword") in _TOO_BROAD]
    data = [r for r in data if r.get("keyword") not in _TOO_BROAD]
    report["移民·移除高危误报词"] = len(removed)

    for r in data:
        excl = _CONTEXT_EXCLUDES.get(r.get("keyword"))
        if excl and not r.get("context_excludes"):
            r["context_excludes"] = list(excl)

    added = _append_unique(data, _IMMIGRATION_NEW)
    report["移民·新增"] = added
    if not dry_run:
        _save(path, data)
    report["移民·总数"] = f"{before} → {len(data)}"

    # ---- 2) 平台词库：收窄 + 导流联系方式 ----
    path = _RULES / "platform_rules.json"
    plat = _load(path)
    if isinstance(plat, dict):
        removed = 0
        for platform, items in plat.items():
            if not isinstance(items, list):
                continue
            keep = [r for r in items if r.get("keyword") not in _PLATFORM_TOO_BROAD]
            removed += len(items) - len(keep)
            plat[platform] = keep
        report["平台·移除高危误报词"] = removed

        total_added = 0
        for platform, items in _PLATFORM_NEW.items():
            if isinstance(plat.get(platform), list):
                total_added += _append_unique(plat[platform], items)
        for platform, items in _PLATFORM_NARROW_ADD.items():
            if isinstance(plat.get(platform), list):
                total_added += _append_unique(plat[platform], items)
        report["平台·新增导流/诱导规则"] = total_added
        if not dry_run:
            _save(path, plat)

    # ---- 3) 新增留学行业包 ----
    path = _RULES / "industry_packs" / "study_abroad" / "rules.json"
    study = _load(path)
    if not isinstance(study, list):
        study = []
    n = _append_unique(study, _STUDY_ABROAD)
    report["留学包·新增"] = n
    report["留学包·总数"] = len(study)
    if not dry_run:
        _save(path, study)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="合规卫士词库扩充（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    report = apply(dry_run=args.dry_run)
    print("=== 词库扩充" + ("（dry-run）" if args.dry_run else "") + " ===")
    for k, v in report.items():
        print(f"  {k}: {v}")
    if report.get("移民·移除高危误报词"):
        print("\n  已移除的高危误报词：")
        for k, why in _TOO_BROAD.items():
            print(f"    - {k}：{why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
