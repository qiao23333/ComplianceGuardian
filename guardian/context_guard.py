#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反误杀守卫：上下文排除 + 自动改写安全网。

解决的 P0 问题
--------------
词库里存在单字 / 极短关键词（最典型的是 ad_law 第一条 `keyword="最"`），
这类词在正常词组里会大量误判：

    "最近很多人问我…"  →  "最" 被判为极限词违规
    "最后提醒一次"      →  "最" 被判为极限词违规

更严重的是，"修改后文案"功能会把命中的字直接删掉：

    "最近很多人问我…"  →  "近很多人问我…"   ← 原文被改坏，事故级

本模块提供三道防线：

1. **上下文排除**：命中词若落在豁免词组（最近/最后/最终…）内部，直接判定为
   正常用法，不产生违规项。
2. **短词降级**：长度 ≤ `SHORT_KEYWORD_MAX_LEN` 的关键词，即使命中也降级为
   `low`（仅提示，不计入风险分）。
3. **改写安全网**：短词一律禁止自动改写原文（`allow_auto_replace=False`），
   只给提示，绝不改动用户文案。

设计约束
--------
本模块属于内核层，**只允许依赖标准库**，禁止 import tkinter / fastapi 等 UI 框架。

2026-09-14 补充：从「枚举短语」升级为「短语表 + 语法模式」
-----------------------------------------------------------
上一版只靠 `EXEMPT_PHRASES` 枚举豁免词组，遇到"第一步"要手工加一条，
遇到"第二步/第二歩/第3步/第一阶段"就得再加四条 —— 这是在用有限的枚举
对抗无限的语言变体，属于打地鼠。

更根本的问题是：「第 + 序数 + 量词」是中文里最普通的**结构表述**
（流程步骤、阶段划分、章节、次数），它与"宣称排名第一"这种绝对化宣传
毫无关系，却因为字面上包含"第一/第1"而被极限词规则和 `第[X]` 正则
双双误杀。在移民/留学文案里，"第一步 / 第二阶段 / 第3步" 是最高频
句式之一 —— 误报这一类的代价是运营直接弃用工具。

因此本模块现在是两层：

1. `EXEMPT_PHRASES`：**短语表**。处理不成模式的固定搭配
   （最近 / 最后 / 最终 / 顶级域名…）。
2. `EXEMPT_PATTERNS`：**语法模式**。处理可穷举其"骨架"的句式
   （`第X步|阶段|章|篇|次…`、`首个工作日|月|季度…`）。

判定规则不变：命中区间**被豁免区间完全覆盖**时才算豁免，
所以"销量第一"（无豁免区间覆盖）依旧会被报出来。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------- 可调参数

#: 关键词长度 ≤ 此值即视为"短词"，触发降级 + 禁止自动改写
#:
#: ⚠️ 只设为 1（仅保护单字）。广告法里大量真·极限词恰好是 2 字
#:    （最好 / 最佳 / 最优 / 最强 / 首个 / 唯一 / 顶级 / 终身…），
#:    若设为 2 会把这些真违规项一并降级，属于矫枉过正。
SHORT_KEYWORD_MAX_LEN = 1

#: 降级后的严重度（仅提示，不计入风险分）
DOWNGRADED_SEVERITY = "low"

#: 只对这类分类做短词降级（避免误伤行业红线里的短词，如"包过"）
DOWNGRADE_CATEGORIES = frozenset({"极限词"})

# ---------------------------------------------------------------- 豁免词组表
#
# ⚠️ 业务审校提醒：这张表是"误杀 vs 漏检"的核心旋钮，必须保守。
#
#    收录标准（需同时满足）：
#      1. 属于**时间 / 顺序 / 中性叙述**语义，而非绝对化宣传；
#      2. 该词组整体在广告法语境下不构成极限词。
#
#    明确不收录（它们都是真·极限词，放过即漏检）：
#      最新、最好、最佳、最优、最强、最大、最小、最高、最低、最快、最慢、
#      最多、最少、最低价、全网最低、史上最…
#
# 组织方式：{触发关键词: (豁免词组...)}
EXEMPT_PHRASES: dict[str, tuple[str, ...]] = {
    "最": (
        # —— 时间顺序语义（明确中性）——
        "最近", "最后", "最终", "最初", "最迟", "最早", "最先", "最末",
        "最开始", "最末尾", "最初期",
        # —— 常用固定搭配 ——
        "最重要的是", "最近一次", "最后一次", "最后一天", "最后一步",
        "最终答案", "最终结果", "最初印象", "最初版本", "最后期限",
    ),
    "极": (
        "极少数", "极个别",
    ),
    "第一": (
        "第一次", "第一反应", "第一步", "第一天", "第一年", "第一轮", "第一版",
    ),
    "顶级": (
        "顶级域名",  # 技术术语，非宣传用语
    ),
}

#: 扁平化后的全部豁免词组（用于快速扫描）
_ALL_EXEMPT_PHRASES: tuple[str, ...] = tuple(
    phrase for phrases in EXEMPT_PHRASES.values() for phrase in phrases
)

#: 最长豁免词组的长度，用于限制扫描窗口
_MAX_PHRASE_LEN = max(len(p) for p in _ALL_EXEMPT_PHRASES) if _ALL_EXEMPT_PHRASES else 0


# ---------------------------------------------------------------- 豁免语法模式
#
# 与短语表的区别：这里描述的是**句式的骨架**，一次覆盖整类变体。
#
# 收录标准（与短语表一致，必须同时满足）：
#   1. 该句式在中文里属于**结构与顺序**语义，不是绝对化宣传；
#   2. 整段匹配在广告法语境下不构成极限用语。
#
# ⚠️ 明确**不**豁免（放过即漏检）：
#   销量第一 / 行业第一 / 排名第一 / 全网第一 / 全国第一 / 市场占有率第一
#   —— 这些没有紧跟量词，不会被下面的模式覆盖，仍按绝对化用语报出。
#
# 量词表刻意收得很窄：只取"流程、阶段、章节、次数、时间、编号"这几类
# 纯结构性量词。像"第一选择 / 第一品牌 / 第一方案"这类**可能**带宣传
# 意味的名词一律不收 —— 宁可漏豁免，不可漏检。

#: 序数 + 结构量词：「第X步」「第二阶段」「第3点」「第一篇」「第2次」
#:
#: 说明 `(?:个)?`：兼容"第一个月 / 第一个阶段"这种插入量词"个"的说法。
#:
#: 关于「位」：`第1位` 在中文里主要指**位次/顺序**（"我排在第1位等待补料"），
#: 与"排名第一"这类宣称不同。真正的排名宣称几乎都带限定语（位列/排名/
#: 行业/销量），这些限定语由 ``rules/regex_patterns.json`` 里的
#: ``(位列|排名|位居|荣登)…第X位`` 规则单独捕获，所以豁免单独的"第X位"
#: 不会造成漏检。
#:
#: 关于「名」：与"位"相反，`第3名` 在广告语境里基本就是**排名宣称**
#: （"销量第3名"），所以**不豁免**——宁可让"考了第3名"这种非广告语境
#: 多一条提示，也不能放过排名宣称。
_ORDINAL_PATTERN = re.compile(
    r"第[一二三四五六七八九十百零〇\d]+(?:个)?"
    r"(?:步|阶段|章|节|篇|条|次|天|年|月|周|期|轮|批|版|层面|环节|"
    r"时间|分钟|小时|季度|课|题|项|点|类|组|份|部分|位)"
)

#: 「首个/首次」+ 中性结构名词：首个工作日 / 首个季度
#:
#: 注意：这里**不含**「首款 / 首发 / 首创 / 首家」——
#: 它们本身就是绝对化宣传用语（《广告法》第九条），必须继续报出。
_FIRST_EVER_PATTERN = re.compile(
    r"首(?:个|次)(?:工作日|自然月|月|季度|阶段|环节|版本|批次|申请季)"
)

#: 全部豁免语法模式：(编译后的正则, 人类可读的原因)
EXEMPT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_ORDINAL_PATTERN, "序数+结构量词"),
    (_FIRST_EVER_PATTERN, "首个+中性名词"),
)


# ---------------------------------------------------------------- 核心 API


def find_exempt_spans(text: str) -> list[tuple[int, int, str]]:
    """扫描文本中所有豁免区间（短语表 + 语法模式）。

    两层来源说明：
    * 短语表：处理不成模式的固定搭配（最近 / 最后 / 顶级域名…）；
    * 语法模式：处理"第X步 / 第二阶段 / 首个工作日"这类结构性表达，
      一次覆盖整类变体，避免为每种量词单独加一条。

    Args:
        text: 原始文本

    Returns:
        [(start, end, phrase), ...] 按 start 升序，end 为开区间
    """
    spans: list[tuple[int, int, str]] = []

    # —— 第一层：固定短语表 ——
    for phrase in _ALL_EXEMPT_PHRASES:
        pos = text.find(phrase)
        while pos != -1:
            spans.append((pos, pos + len(phrase), phrase))
            pos = text.find(phrase, pos + 1)

    # —— 第二层：语法模式（序数+量词 / 首个+中性名词）——
    for pattern, _reason in EXEMPT_PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), m.group(0)))

    spans.sort(key=lambda x: x[0])
    return spans


def is_context_exempt(
    text: str,
    start: int,
    end: int,
    exempt_spans: list[tuple[int, int, str]] | None = None,
) -> str | None:
    """判断命中区间是否落在豁免词组内部。

    Args:
        text: 原始文本
        start: 命中起始下标（闭）
        end: 命中结束下标（开）
        exempt_spans: 预扫描结果，传入可避免重复扫描（批量场景显著提速）

    Returns:
        命中的豁免词组（如 "最近"），若不属于豁免则返回 None
    """
    if exempt_spans is None:
        exempt_spans = find_exempt_spans(text)

    for phrase_start, phrase_end, phrase in exempt_spans:
        # 命中区间被豁免词组完全覆盖 → 判为正常用法
        if start >= phrase_start and end <= phrase_end:
            return phrase
        # 已扫过命中位置之后的所有词组，可提前退出
        if phrase_start > start:
            break
    return None


def is_short_keyword(violation: dict) -> bool:
    """判断该违规项是否属于需要保护的短关键词。"""
    keyword = violation.get("keyword", "")
    if not keyword or len(keyword) > SHORT_KEYWORD_MAX_LEN:
        return False
    # 只对极限词类目降级；行业红线里的短词（如"包过"）保持原有严重度
    category = violation.get("category", "")
    if DOWNGRADE_CATEGORIES and category not in DOWNGRADE_CATEGORIES:
        return False
    return True


def should_auto_replace(violation: dict) -> bool:
    """判断该违规项是否允许自动改写进"修改后文案"。

    短词一律返回 False —— 这是防止原文被改坏的最后一道安全网。
    """
    if violation.get("allow_auto_replace") is False:
        return False
    return not is_short_keyword(violation)


def apply_guard(
    violations: list[dict],
    text: str,
    exempt_spans: list[tuple[int, int, str]] | None = None,
) -> list[dict]:
    """对检测结果施加反误杀守卫（原地修改并返回）。

    处理顺序：
    1. 移除落在豁免词组内的命中（正常用法，不该报）
    2. 对短词降级为 low
    3. 给短词打上 allow_auto_replace=False 标记

    Args:
        violations: detect() 产出的违规项列表
        text: 原始文本
        exempt_spans: 预扫描的豁免区间（可选）

    Returns:
        处理后的违规项列表（新列表，不修改入参列表本身）
    """
    if exempt_spans is None:
        exempt_spans = find_exempt_spans(text) if text else []

    guarded: list[dict] = []
    for v in violations:
        # --- 防线 1：上下文排除 ---
        exempt_phrase = is_context_exempt(text, v.get("start", 0), v.get("end", 0), exempt_spans)
        if exempt_phrase is not None:
            # 正常用法，静默跳过（可用 exempt_phrase 记日志）
            continue

        v = dict(v)  # 拷贝，避免污染调用方的 dict

        # --- 防线 2 & 3：短词降级 + 禁止自动改写 ---
        if is_short_keyword(v):
            v["severity"] = DOWNGRADED_SEVERITY
            v["allow_auto_replace"] = False
            v["note"] = (v.get("note", "") + "（短词已降级为提示，不自动改写）").strip()

        guarded.append(v)

    return guarded
