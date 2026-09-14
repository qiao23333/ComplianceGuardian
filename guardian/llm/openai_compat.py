#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端 OpenAI 兼容 API Provider。

支持 DeepSeek / OpenAI / 通义 / 月之暗面 等任何 ``/v1/chat/completions``
接口。纯标准库 urllib 实现，无额外依赖。

只实现 ``complete``，其余能力由 ``LLMProvider`` 模板方法提供。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from guardian.llm.base import LLMProvider

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT = 120.0


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE,
                 model: str = _DEFAULT_MODEL, timeout: float = _DEFAULT_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str, *, system: Optional[str] = None) -> tuple[bool, str, Optional[str]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        body = json.dumps(payload).encode("utf-8")
        try:
            http_req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urllib.request.urlopen(http_req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return True, data["choices"][0]["message"]["content"], None
        except Exception as e:
            return False, "", _humanize_error(e)

    def list_models(self) -> list:
        """拉取账号可用的模型列表（设置页给下拉框用，失败返回空）。"""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
        except Exception:
            return []


def _humanize_error(exc: Exception) -> str:
    """把 HTTP 错误翻译成用户能据以行动的话。"""
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 401:
            return "API Key 无效或已过期（401）。请到设置页重新填写。"
        if code == 402 or code == 403:
            return "账号余额不足或无该模型权限（%d）。请检查账户状态。" % code
        if code == 429:
            return "请求过于频繁或超出配额（429）。稍后重试，或换一个模型。"
        if code == 404:
            return "模型不存在（404）。请确认模型名与接口地址是否匹配。"
        try:
            detail = exc.read().decode("utf-8", "ignore")[:200]
        except Exception:
            detail = ""
        return "云端接口返回 %d。%s" % (code, detail)
    text = str(exc)
    if "timed out" in text.lower():
        return "云端接口响应超时。可稍后重试，或把模型换成响应更快的。"
    if "getaddrinfo" in text or "Name or service not known" in text:
        return "接口地址解析失败。请检查 Base URL 是否填写正确、网络是否可用。"
    return "云端 API 调用失败：%s" % text
