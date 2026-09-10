#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 配置桥接单元测试。"""

import tempfile
from pathlib import Path

from guardian.config import ConfigManager
from guardian.llm_config import (
    LLM_DEFAULTS, load_llm_config, probe_ollama, save_llm_config,
)


def _cm():
    d = Path(tempfile.mkdtemp())
    return ConfigManager(d / "config.json")


def test_disabled_returns_empty():
    cm = _cm()
    assert load_llm_config(cm) == {}


def test_local_mode_builds_engine_dict():
    cm = _cm()
    eng = save_llm_config(cm, enabled=True, mode="local",
                          model="qwen2.5:7b", local_base="http://localhost:11434")
    assert eng == {
        "llm_local_enabled": True,
        "llm_local_base": "http://localhost:11434",
        "llm_model": "qwen2.5:7b",
    }
    # 再次读取应一致
    assert load_llm_config(cm) == eng


def test_cloud_mode_with_key():
    cm = _cm()
    eng = save_llm_config(cm, enabled=True, mode="cloud",
                          api_key="sk-abc", base_url="https://api.deepseek.com/v1",
                          model="deepseek-chat")
    assert eng["llm_api_key"] == "sk-abc"
    assert eng["llm_base_url"] == "https://api.deepseek.com/v1"
    assert eng["llm_model"] == "deepseek-chat"


def test_cloud_mode_without_key_is_disabled():
    cm = _cm()
    save_llm_config(cm, enabled=True, mode="cloud", api_key="")
    assert load_llm_config(cm) == {}  # 没 key → 视为未启用


def test_toggle_off_returns_empty():
    cm = _cm()
    save_llm_config(cm, enabled=True, mode="local")
    save_llm_config(cm, enabled=False)
    assert load_llm_config(cm) == {}


def test_probe_ollama_unreachable():
    # 一个必然不可达的端口 → 优雅返回 False
    ok, models = probe_ollama("http://localhost:59999")
    assert ok is False
    assert models == []


def test_defaults_mergeable():
    # LLM_DEFAULTS 的键应都能被 ConfigManager 接受（无异常）
    cm = _cm()
    for k, v in LLM_DEFAULTS.items():
        cm.set(k, v)
    assert cm.get("llm_mode") == "local"
