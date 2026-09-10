#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 语义增强 Provider 抽象层。

* ``base``：LLMProvider 抽象 + LLMRequest / LLMResult
* ``ollama``：本地 Ollama（桌面端默认）
* ``openai_compat``：云端 OpenAI 兼容 API（Web / 填 key）
* ``null``：未配置时的占位（纯规则引擎永不报错）
* ``factory``：从配置解析 Provider，修掉 qwen2.5:7b 硬编码
"""

from guardian.llm.base import LLMProvider, LLMRequest, LLMResult
from guardian.llm.factory import create_provider
from guardian.llm.null import NullProvider
from guardian.llm.ollama import OllamaProvider
from guardian.llm.openai_compat import OpenAICompatProvider

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "create_provider",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
]
