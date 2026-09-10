#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端 OpenAI 兼容 API Provider（Web 端 / 用户填 key 的桌面端）。

支持 DeepSeek / OpenAI / Claude(通过兼容网关) 等任何
``/v1/chat/completions`` 接口。纯标准库 urllib 实现，无额外依赖。
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Optional

from guardian.llm.base import LLMProvider, LLMRequest, LLMResult

_SYSTEM = (
    "你是中文内容合规审核助手。请指出文案中广告法极限词、虚假夸大宣传、"
    "导流话术、疗效/保证性承诺等风险，并给出可执行的修改建议。"
)


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o-mini", timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def analyze(self, req: LLMRequest) -> LLMResult:
        t0 = time.time()
        user = (
            "请审核这段文案，返回 JSON："
            '{"risk_summary": str, "suggestions": [str], "extra_findings": [str]}\n\n'
            f"文案：{req.text}"
        )
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }).encode("utf-8")
        try:
            http_req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urllib.request.urlopen(http_req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            analysis = json.loads(content)
            return LLMResult(ok=True, analysis=analysis, model=self.model,
                             latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return LLMResult(ok=False, error=f"云端 API 调用失败：{e}", model=self.model,
                             latency_ms=(time.time() - t0) * 1000)
