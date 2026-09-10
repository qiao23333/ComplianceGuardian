#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Null Provider：未配置任何 LLM 时的占位实现。

保证"纯规则引擎"路径永不报错——引擎层检测到 ``is_configured()==False``
就直接跳过语义增强，用户零感知。
"""

from __future__ import annotations

from guardian.llm.base import LLMProvider, LLMRequest, LLMResult


class NullProvider(LLMProvider):
    name = "null"

    def is_configured(self) -> bool:
        return False

    def analyze(self, req: LLMRequest) -> LLMResult:
        return LLMResult(ok=False, error="未配置 LLM Provider", model=None)
