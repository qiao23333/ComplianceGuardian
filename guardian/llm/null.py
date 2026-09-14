#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Null Provider：未配置任何 AI 服务时的占位实现。

保证"纯规则引擎"路径永不报错——引擎层检测到 ``is_configured()==False``
就直接跳过 AI 环节，用户零感知、功能零缺失。

这体现了本项目的底线：**没有 AI 也必须是完整可用的产品**。
AI 是增强，不是依赖。
"""

from __future__ import annotations

from typing import Optional

from guardian.llm.base import LLMProvider


class NullProvider(LLMProvider):
    name = "null"

    def is_configured(self) -> bool:
        return False

    def complete(self, prompt: str, *, system: Optional[str] = None) -> tuple[bool, str, Optional[str]]:
        return False, "", "未配置 AI 服务（判定与改写的基础能力不受影响）"
