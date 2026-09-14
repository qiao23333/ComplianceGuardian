#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM Provider 抽象层。

设计动机
--------
v2.4 的 LLM 配置是死代码：模型名 ``qwen2.5:7b`` 硬编码在 detector.py 四处，
config 里的 ``llm_model`` 从未被读取，UI 也从不调用 ``detect_with_llm()``。

本层把"语言模型能力"抽象成一个 Provider：

* 桌面端默认走 **本地 Ollama**（隐私、免费，无需联网）
* Web 端走 **云端 OpenAI 兼容 API**（DeepSeek / OpenAI / Claude 等，用户填 key）
* 都不配置时 → **NullProvider**：纯规则引擎完整工作，不报错、不降级体验

职责边界（重要）
----------------
Provider 只会两件事：

1. ``complete(prompt) -> (ok, text, error)`` —— 把一段提示词发给模型，拿回文本。
   这是唯一的**抽象方法**，子类只需要实现它。
2. ``rewrite(req)`` / ``analyze(req)`` —— 两个**模板方法**，负责拼提示词、
   解析返回值。它们不碰网络，所以天然共享给所有后端。

这样加一个新后端（比如换个本地推理框架）只需要写十几行 ``complete``。

同时明确一条产品立场：**模型在本项目里是改写器，不是审核员**。
``rewrite`` 才是主路径，``analyze`` 保留给"让模型给点额外视角"的旧用法。
理由见 ``prompts.py`` 的模块注释。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from guardian.llm.rewrite import RewriteRequest, RewriteResult, parse_rewrite


@dataclass
class LLMRequest:
    """一次语义增强请求。"""
    text: str
    findings: list = field(default_factory=list)   # 规则命中列表（供模型参考）
    prompt_template: Optional[str] = None          # 可覆盖默认提示词


@dataclass
class LLMResult:
    """一次语义增强的返回。"""
    ok: bool
    analysis: Optional[dict] = None    # {risk_summary, suggestions, extra_findings}
    error: Optional[str] = None
    model: Optional[str] = None
    latency_ms: float = 0.0


#: 只输出 JSON 的硬约束，拼在各家提示词末尾。
_JSON_ONLY = "只输出 JSON，不要 markdown 代码块，不要任何额外文字。"

#: analyze 用的通用提示词（保留给"要一点额外视角"的旧路径）。
_ANALYZE_PROMPT = """你是一个中文内容合规审核助手。请审核下面这段文案，重点关注：
1. 广告法极限词（最/第一/唯一/国家级等）
2. 虚假/夸大宣传
3. 导流话术（加微信/私聊/加群等）
4. 医疗/疗效/保证性承诺

已知规则引擎已命中以下词（仅供参考，不要重复列举）：
{findings}

请返回 JSON：
{{"risk_summary": "一句话风险总结", "suggestions": ["修改建议1", "修改建议2"], "extra_findings": ["规则未覆盖但可疑的表述"]}}

文案：
{text}
"""


def extract_json(text: str) -> Optional[object]:
    """从模型输出里尽力抠出 JSON。

    模型常见的不听话写法：套 ```json 代码块、前后加"好的，以下是..."、
    输出里混注释。这里按"直接解析 → 抠代码块 → 抠最外层花括号"三级降级。
    解析不出来返回 None，由调用方决定怎么兜底。
    """
    if not text:
        return None
    s = text.strip()

    try:
        return json.loads(s)
    except Exception:
        pass

    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except Exception:
            pass
    return None


class LLMProvider(ABC):
    """语言模型 Provider 接口。

    子类唯一必须实现的是 ``complete``；其余能力由基类模板方法提供。
    """

    name: str = "abstract"

    # ------------------------------------------------ 必须实现
    @abstractmethod
    def is_configured(self) -> bool:
        """是否可用（本地模型在跑 / 云端 key 已填）。"""

    @abstractmethod
    def complete(self, prompt: str, *, system: Optional[str] = None) -> tuple[bool, str, Optional[str]]:
        """发送原始提示词，返回 ``(ok, raw_text, error)``。

        实现方不得抛异常——网络/解析错误一律转成 ``ok=False`` 返回。
        """

    # ------------------------------------------------ 模板方法
    def rewrite(self, req: RewriteRequest) -> RewriteResult:
        """把文案改写为合规版本（主路径）。

        提示词由 ``prompts.build_rewrite_prompt`` 生成，两端共用同一份，
        保证桌面端与 Web 端（BYO-AI 复制提示词）行为一致。
        """
        from guardian.llm.prompts import REWRITE_SYSTEM, build_rewrite_prompt
        import time as _time

        if not self.is_configured():
            return RewriteResult(ok=False, error="未配置可用的 AI 服务", provider=self.name)

        prompt = req.prompt_override or build_rewrite_prompt(
            text=req.text,
            findings=req.findings,
            platform=req.platform,
            account_type=req.account_type,
            industry_label=req.industry_label,
            must_keep=req.must_keep,
            tone=req.tone,
        )

        t0 = _time.time()
        ok, raw, err = self.complete(prompt, system=REWRITE_SYSTEM)
        ms = (_time.time() - t0) * 1000
        if not ok:
            return RewriteResult(ok=False, error=err or "调用失败",
                                 provider=self.name, latency_ms=ms)
        return parse_rewrite(raw, provider=self.name,
                             model=getattr(self, "model", None), latency_ms=ms)

    def analyze(self, req: LLMRequest) -> LLMResult:
        """旧的"语义增强"路径：让模型给风险总结与额外发现。

        不是主路径——判定归规则引擎。保留它是因为"模型觉得还有哪里可疑"
        偶尔有参考价值，但结果只做提示，绝不参与评分。
        """
        import time as _time

        findings_txt = "\n".join(
            "- %s（%s）" % (f.get("keyword", ""), f.get("category", ""))
            for f in list(req.findings)[:20]
        ) or "（无）"
        prompt = (req.prompt_template or _ANALYZE_PROMPT).format(
            findings=findings_txt, text=req.text)

        t0 = _time.time()
        ok, raw, err = self.complete(prompt)
        ms = (_time.time() - t0) * 1000
        if not ok:
            return LLMResult(ok=False, error=err, model=getattr(self, "model", None),
                             latency_ms=ms)
        return LLMResult(ok=True, analysis=extract_json(raw),
                         model=getattr(self, "model", None), latency_ms=ms)

    @property
    def supports_stream(self) -> bool:
        return False
