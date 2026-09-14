#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 Ollama Provider（桌面端默认，隐私 / 免费 / 离线）。

通过 Ollama 的 REST API（http://localhost:11434）调用本地模型，
如 ``qwen2.5:7b`` / ``llama3``。仅用标准库 urllib，无额外依赖。

只实现 ``complete``：拼提示词与解析结果都交给 ``LLMProvider`` 的模板方法，
所以这里看到的就是"怎么跟 Ollama 说话"这一件事。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Optional

from guardian.llm.base import LLMProvider

_DEFAULT_BASE = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5:7b"

#: 改写会输出整篇文案 + 逐处对照，token 量比"给个总结"大得多；
#: 本地 7B 模型在普通笔记本上跑 60~90 秒是常态，超时给宽松些。
_DEFAULT_TIMEOUT = 120.0


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = _DEFAULT_BASE, model: str = _DEFAULT_MODEL,
                 timeout: float = _DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_configured(self) -> bool:
        # 探测本地服务是否存活 + 模型是否存在
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = {m.get("name") for m in data.get("models", [])}
            return self.model in models
        except Exception:
            return False

    def complete(self, prompt: str, *, system: Optional[str] = None) -> tuple[bool, str, Optional[str]]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",          # 让 Ollama 约束输出为 JSON
            "stream": False,
            "options": {"temperature": 0.3},
        }
        if system:
            payload["system"] = system
        body = json.dumps(payload).encode("utf-8")
        try:
            http_req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(http_req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return True, data.get("response", ""), None
        except Exception as e:
            return False, "", _humanize_error(e, self.base_url)

    def list_models(self) -> list:
        """列出本地已安装模型（设置页用来给下拉框填选项）。"""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []


def _humanize_error(exc: Exception, base_url: str) -> str:
    """把 urllib 的英文异常翻译成用户看得懂的话。

    用户看到 "URLError: [WinError 10061]" 只会懵；看到"本地模型服务没启动"
    才知道该去开 Ollama。
    """
    text = str(exc)
    if "10061" in text or "Connection refused" in text or "ConnectionRefused" in text:
        return f"连不上本地模型服务（{base_url}）。请先启动 Ollama，或改用云端 API。"
    if "timed out" in text.lower():
        return "本地模型响应超时。文案较长或模型较大时容易超时，可换更小的模型或重试。"
    if "404" in text:
        return "本地模型不存在。请在 Ollama 里先 ollama pull 对应模型。"
    return "Ollama 调用失败：%s" % text
