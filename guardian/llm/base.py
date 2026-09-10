#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM Provider 抽象层。

设计动机
--------
v2.4 的 LLM 配置是死代码：模型名 ``qwen2.5:7b`` 硬编码在 detector.py 四处，
config 里的 ``llm_model`` 从未被读取，UI 也从不调用 ``detect_with_llm()``。

本层把"语义增强"抽象成一个 Provider：
* 桌面端默认走 **本地 Ollama**（隐私、免费，无需联网）
* Web 端走 **云端 OpenAI 兼容 API**（DeepSeek / OpenAI / Claude 等，用户填 key）
* 都不配置时 → **NullProvider**：纯规则引擎完整工作，不报错、不降级体验

所有 Provider 实现同一个接口，引擎层只认 ``LLMProvider``，不关心后端。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


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


class LLMProvider(ABC):
    """语义增强 Provider 接口。"""

    name: str = "abstract"

    @abstractmethod
    def is_configured(self) -> bool:
        """是否可用（本地模型在跑 / 云端 key 已填）。"""

    @abstractmethod
    def analyze(self, req: LLMRequest) -> LLMResult:
        """对文本做语义级合规分析。"""

    @property
    def supports_stream(self) -> bool:
        return False
