#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改写提示词构建器（纯函数，无 IO）。

设计立场
--------
**判定不交给模型，改写才交给模型。**

这是本项目对"AI 该用在哪"的明确回答：

* **判定**（这句话违不违规、算哪一级）→ 规则引擎。理由是判定要求
  *确定、可复现、可解释、有法条依据*：同一条文案今天判 78 分，明天还得
  是 78 分，且要能说清"扣在哪条规则上"。模型做不到——它会漏、会编出
  根本不存在的违规，而且同一句话问两次可能给两个答案。让模型做判定，
  等于把一个需要出庭作证的岗位交给一个每次都临场发挥的人。
* **改写**（把违规的话换个说法说）→ 模型。理由是这活儿需要语言能力而
  不是查表能力：规则库能告诉你"《广告法》第九条禁用『最』字"，但它给不
  出"既保住卖点、又不踩线"的那句话。这正是模型的主场。

因此 LLM 在本项目里是**改写器**，不是**审核员**。提示词的核心工作就是
把这个边界说死，防止模型越界去"帮忙"多做判定——那只会引入不稳定。

本模块被两端共用：
* 桌面端 → 拼好后交给 Ollama / 云端 API
* Web 端 → 拼成文本让用户一键复制，粘到任意 AI 里用（BYO-AI，零配置）
两边用同一份提示词，行为才一致。
"""

from __future__ import annotations

from typing import Optional, Sequence

#: 改写场景的系统提示词。
REWRITE_SYSTEM = (
    "你是中文商业文案的合规改写专家。你的职责是改写，不是判定。"
    "你只按给定的违规清单逐处改写，不自行新增或删除判定结论。"
    "输出必须是严格 JSON，不要 markdown 代码块，不要额外解释。"
)

#: 平台口语化名称，用于提示词里让模型知道改写后要投放到哪。
_PLATFORM_NAME = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "weixin": "微信",
    "weixin_gzh": "微信公众号",
    "all": "多平台通用",
}


def platform_label(platform: Optional[str]) -> str:
    return _PLATFORM_NAME.get(platform or "", platform or "多平台通用")


def _pick(d: dict, *keys, default=""):
    """按优先级取值 —— 兼容内核蛇形字段与 UI/Web 驼峰字段两种来源。

    内核 ``Finding`` 是 ``matched_text``，Web 端导出的是 ``matchedText``，
    UI 转换后的 dict 又可能只有 ``keyword``。与其在三处各写一遍转换、
    将来改字段名漏掉一处，不如在这里一次性宽容掉。
    """
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return default


def format_findings(findings: Sequence[dict], limit: int = 40) -> str:
    """把规则命中清单渲染成提示词里的条目列表。

    每条都带上：命中片段、对应词条、类别、严重度、来源、法条/建议、可替换词。
    信息给足，模型才可能给出"贴着规则"的改写，而不是泛泛而谈。
    """
    if not findings:
        return "（规则引擎未命中任何违规项）"

    lines = []
    for i, f in enumerate(findings[:limit], 1):
        matched = _pick(f, "matchedText", "matched_text", "original", "keyword")
        keyword = _pick(f, "keyword", "matched_text")
        parts = ["%d. 命中「%s」" % (i, matched)]
        detail = []
        if keyword and keyword != matched:
            detail.append("词条：%s" % keyword)
        if _pick(f, "category"):
            detail.append("类别：%s" % f["category"])
        if _pick(f, "severity"):
            detail.append("等级：%s" % f["severity"])
        if _pick(f, "source"):
            detail.append("来源：%s" % f["source"])
        if _pick(f, "matchType", "match_type") in ("variant", "llm"):
            detail.append("疑似规避写法（谐音/跳字/全角/繁体）")
        if _pick(f, "suggestion"):
            detail.append("规则建议：%s" % f["suggestion"])
        reps = _pick(f, "replacements", default=[])
        if reps:
            detail.append("可用替换词：%s" % " / ".join(str(r) for r in reps))
        if detail:
            parts.append("（" + "；".join(detail) + "）")
        lines.append("".join(parts))

    if len(findings) > limit:
        lines.append("……（另有 %d 处未列出）" % (len(findings) - limit))
    return "\n".join(lines)


#: 改写任务说明。刻意把"不要做什么"写得比"要做什么"更详细——
#: 模型越界的成本远高于它少做一点。
_REWRITE_TASK = """## 你的唯一任务

把下面这段文案**改写**到合规。**不要做合规判定**——违规点已由规则引擎
精确找出并列在下方，你只需要按清单逐处改写。

## 为什么判定不交给你

规则引擎的判定确定、可复现、每条都能追溯到法条；模型做判定会漏检、会
凭空发明违规、同一句话问两次给两个答案。所以：

* **不要**新增清单以外的"我觉着也违规"的判断
* **不要**删除清单以外的任何内容
* **不要**在输出里讨论这段文案合不合规，只给改写结果

## 改写铁律

1. **最小改动**：只动清单命中的片段及其必要上下文，其余原文一字不改（含换行、标点、emoji）
2. **保住卖点**：原文想传达的信息（项目优势、服务内容、目标客户）必须留住，只是换个说法
3. **不编事实**：不得新增原文没有的数字、资质、年限、成功率、客户数量、结论
4. **不弱化到废话**：把"保签"改成"提供签证材料协助"可以，改成"我们做移民的"不行——
   改写后仍要是一句能用的商业文案，否则这次改写没有意义
5. **程序化表述**：结果承诺（保过/包成功）改为过程性表述（协助准备、评估可行路径、
   按流程递交）；医疗健康类改为"通常""因人而异"或直接删除效果承诺
6. **导流话术**：平台禁止的导流说法（加微信/私信我）改为平台内的合规动作
   （点击主页咨询、评论区留言、联系官方渠道）

## 拿不准的时候

如果某处无法在不失真的前提下改写（例如改了就构成虚假宣传、或必须补充真实
资质才能说清），把它如实写进 `unresolved`，说明**为什么改不了**和**需要补充
什么信息**。**不要硬凑一个假方案**——一个诚实的"这句需要人工确认"比一个
编出来的合规说法有用得多。

## 输出格式

只输出如下 JSON，不要 markdown 代码块，不要任何额外文字：

{"rewritten": "改写后的完整文案（含未改动部分）",
 "changes": [{"before": "原文片段", "after": "改后片段", "reason": "为什么这么改", "rule": "对应清单第几条"}],
 "kept": ["保留下来的核心卖点，逐条列出"],
 "unresolved": [{"text": "无法处理的原句", "why": "为什么改不了", "need": "需要补充什么信息"}]}
"""


def build_rewrite_prompt(
    text: str,
    findings: Sequence[dict],
    platform: Optional[str] = None,
    account_type: Optional[str] = None,
    industry_label: Optional[str] = None,
    must_keep: Optional[Sequence[str]] = None,
    tone: Optional[str] = None,
) -> str:
    """拼出完整的改写提示词（用户消息部分）。

    Web 端「复制提示词」按钮与桌面端调用的是同一个构建逻辑，
    只是 Web 端把结果放进剪贴板，桌面端把它发给模型。
    """
    ctx = ["目标平台：%s" % platform_label(platform)]
    if account_type:
        ctx.append("账号类型：%s" % ("蓝V 认证账号" if account_type == "blue_v" else "普通账号"))
    if industry_label:
        ctx.append("行业词库：%s" % industry_label)
    if tone:
        ctx.append("风格要求：%s" % tone)

    keep_block = ""
    if must_keep:
        keep_block = (
            "\n## 必须保留的信息（用户指定，改写时不得丢失）\n"
            + "\n".join("- %s" % k for k in must_keep)
            + "\n"
        )

    return (
        _REWRITE_TASK
        + "\n## 本次上下文\n"
        + "\n".join(ctx)
        + "\n"
        + keep_block
        + "\n## 规则引擎命中的违规清单（共 %d 处）\n" % len(findings)
        + format_findings(findings)
        + "\n\n## 待改写原文\n<<<\n"
        + text
        + "\n>>>\n"
    )
