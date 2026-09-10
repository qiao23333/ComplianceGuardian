#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 配置桥接：把 ConfigManager 里的持久化设置翻译成引擎可用的 dict。

解决两套键名不一致的问题：
* ConfigManager 用 ``llm_enabled`` / ``llm_api_key`` / ``llm_model`` 等
* 引擎工厂（llm/factory.create_provider）用
  ``llm_api_key`` / ``llm_base_url`` / ``llm_model`` / ``llm_local_enabled`` / ``llm_local_base``

本模块统一出口，让设置页只跟"人类语言"配置打交道，引擎只吃工厂契约 dict。
纯 stdlib + 内核层，可独立测试（探测 Ollama 走 urllib，测试可 mock）。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Optional

# 默认 LLM 相关配置（合并进 guardian.config.DEFAULT_CONFIG 时使用）
LLM_DEFAULTS = {
    "llm_enabled": False,
    "llm_mode": "local",            # local | cloud
    "llm_api_key": "",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_model": "qwen2.5:7b",
    "llm_local_base": "http://localhost:11434",
}


def load_llm_config(cm) -> dict:
    """从 ConfigManager 读取并翻译成引擎工厂契约 dict。

    返回空 dict 表示"不启用 LLM"（引擎会用 NullProvider，纯规则）。
    """
    if not cm.get("llm_enabled"):
        return {}
    mode = cm.get("llm_mode", "local")
    model = cm.get("llm_model") or "qwen2.5:7b"
    if mode == "cloud":
        api_key = cm.get("llm_api_key") or ""
        if not api_key:
            return {}  # 云端模式但没填 key → 视为未启用
        return {
            "llm_api_key": api_key,
            "llm_base_url": cm.get("llm_base_url", "https://api.openai.com/v1"),
            "llm_model": model,
        }
    # 本地 Ollama
    return {
        "llm_local_enabled": True,
        "llm_local_base": cm.get("llm_local_base", "http://localhost:11434"),
        "llm_model": model,
    }


def save_llm_config(cm, *,
                    enabled: bool = False,
                    mode: str = "local",
                    api_key: str = "",
                    base_url: Optional[str] = None,
                    model: Optional[str] = None,
                    local_base: Optional[str] = None) -> dict:
    """把设置写回 ConfigManager，并返回引擎契约 dict。"""
    cm.set("llm_enabled", bool(enabled))
    cm.set("llm_mode", mode)
    if api_key is not None:
        cm.set("llm_api_key", api_key)
    if base_url is not None:
        cm.set("llm_base_url", base_url)
    if model is not None:
        cm.set("llm_model", model)
    if local_base is not None:
        cm.set("llm_local_base", local_base)
    return load_llm_config(cm)


def probe_ollama(base_url: str = "http://localhost:11434") -> tuple[bool, list]:
    """探测本地 Ollama 是否可用，返回 (可用, 模型名列表)。"""
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/tags",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name") for m in data.get("models", [])]
        return (bool(models), models)
    except Exception:
        return (False, [])
