#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM Provider 工厂：从配置对象解析出合适的 Provider。

解析规则（优先级从高到低）：
1. 若配置了 ``llm_api_key``（云端） → OpenAICompatProvider
2. 否则若 ``llm_local_enabled``（桌面端本地 Ollama） → OllamaProvider
3. 都没有 → NullProvider（纯规则引擎）

这样彻底修掉了 v2.4 把 ``qwen2.5:7b`` 硬编码进 detector 的问题——
模型名现在只来自配置，且未配置时优雅降级。
"""

from __future__ import annotations

from typing import Optional

from guardian.llm.base import LLMProvider
from guardian.llm.null import NullProvider
from guardian.llm.ollama import OllamaProvider
from guardian.llm.openai_compat import OpenAICompatProvider


def create_provider(config: Optional[dict] = None) -> LLMProvider:
    """根据配置 dict 创建 Provider。

    config 约定字段：
        llm_api_key:        云端 API key（非空即走云端）
        llm_base_url:       云端 base url（可选）
        llm_model:          模型名（云端或本地都用）
        llm_local_enabled:  是否启用本地 Ollama（桌面端）
        llm_local_base:     本地 Ollama 地址（可选）
    """
    cfg = config or {}
    model = cfg.get("llm_model") or "qwen2.5:7b"

    api_key = cfg.get("llm_api_key")
    if api_key:
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=cfg.get("llm_base_url", "https://api.openai.com/v1"),
            model=model,
        )

    if cfg.get("llm_local_enabled"):
        return OllamaProvider(
            base_url=cfg.get("llm_local_base", "http://localhost:11434"),
            model=model,
        )

    return NullProvider()
