#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 能力层（Provider 抽象）。

模块分工
--------
* ``base``：``LLMProvider`` 抽象（唯一必实现 ``complete``）+ 模板方法
* ``prompts``：提示词构建（纯函数，桌面端与 Web 端共用同一份）
* ``rewrite``：改写请求/返回契约与容错解析
* ``ollama``：本地 Ollama（桌面端默认，隐私 / 免费 / 离线）
* ``openai_compat``：云端 OpenAI 兼容 API（填 key 后可用）
* ``null``：未配置时的占位（纯规则引擎永不报错）
* ``factory``：从配置解析 Provider

产品立场
--------
**判定归规则引擎，改写才用模型。** 详见 ``prompts`` 的模块注释。
"""

from guardian.llm.base import LLMProvider, LLMRequest, LLMResult, extract_json
from guardian.llm.factory import create_provider
from guardian.llm.null import NullProvider
from guardian.llm.ollama import OllamaProvider
from guardian.llm.openai_compat import OpenAICompatProvider
from guardian.llm.prompts import build_rewrite_prompt, format_findings
from guardian.llm.rewrite import RewriteRequest, RewriteResult, parse_rewrite

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "RewriteRequest",
    "RewriteResult",
    "build_rewrite_prompt",
    "create_provider",
    "extract_json",
    "format_findings",
    "parse_rewrite",
    "NullProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
]
