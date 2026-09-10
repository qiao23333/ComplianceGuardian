#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置管理

优化说明：
- 原子写入：先写临时文件再 rename，避免崩溃时配置损坏
"""
import json
import os
import tempfile
from pathlib import Path

DEFAULT_CONFIG = {
    "theme": "light",
    "last_platform": "小红书",
    "last_account_type": "personal",
    "llm_enabled": False,
    "llm_api_key": "",
    "llm_model": "qwen2.5:7b",
    "total_checks": 0,
    "total_violations": 0,
    "appearance_mode": "Light",
    "enabled_industry_packs": ["immigration"],
}


class ConfigManager:
    def __init__(self, config_path=None):
        if config_path is None:
            root = Path(__file__).parent.parent
            self.config_path = root / "data" / "config.json"
        else:
            self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                # 配置文件损坏时回退到默认值，不崩溃
                config = DEFAULT_CONFIG.copy()
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
        self.save(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    def save(self, config=None):
        """原子写入：先写临时文件，再 rename 替换，确保不会写坏配置"""
        if config is None:
            config = self.config

        # 在同一目录下创建临时文件（保证 rename 是原子操作）
        dir_name = os.path.dirname(str(self.config_path))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            # 原子替换（Windows 上 os.replace 也能工作）
            os.replace(tmp_path, str(self.config_path))
        except Exception:
            # 出错时清理临时文件
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        self.config = config

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()
