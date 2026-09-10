#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 Ollama Provider（桌面端默认，隐私 / 免费 / 离线）。

通过 Ollama 的 REST API（http://localhost:11434）调用本地模型，
如 ``qwen2.5:7b`` / ``llama3``。仅用标准库 urllib，无额外依赖。
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Optional

from guardian.llm.base import LLMProvider, LLMRequest, LLMResult

_DEFAULT_BASE = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5:7b"

_PROMPT = """你是一个中文内容合规审核助手。请审核下面这段文案，重点关注：
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


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = _DEFAULT_BASE, model: str = _DEFAULT_MODEL,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_configured(self) -> bool:
        # 探测本地服务是否存活 + 模型是否存在
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags",
                                          headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = {m.get("name") for m in data.get("models", [])}
            return self.model in models
        except Exception:
            return False

    def analyze(self, req: LLMRequest) -> LLMResult:
        t0 = time.time()
        findings_txt = "\n".join(f"- {f.get('keyword', '')}（{f.get('category', '')}）"
                                 for f in req.findings[:20]) or "（无）"
        prompt = (req.prompt_template or _PROMPT).format(
            findings=findings_txt, text=req.text)
        payload = json.dumps({"model": self.model, "prompt": prompt,
                              "format": "json", "stream": False}).encode("utf-8")
        try:
            http_req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(http_req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            analysis = _safe_parse(data.get("response", ""))
            return LLMResult(ok=True, analysis=analysis, model=self.model,
                             latency_ms=(time.time() - t0) * 1000)
        except Exception as e:  # 网络/解析失败
            return LLMResult(ok=False, error=f"Ollama 调用失败：{e}", model=self.model,
                             latency_ms=(time.time() - t0) * 1000)


def _safe_parse(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        # 模型可能返回带 markdown 代码块的 JSON
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None
