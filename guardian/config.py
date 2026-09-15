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

from guardian.schema import DEFAULT_ACCOUNT_TYPE

DEFAULT_CONFIG = {
    "theme": "light",
    "last_platform": "小红书",
    # 账号类型必须是 blue_v / non_blue_v 之一 —— 这两个值是
    # blue_v_only.json 里 severity_by_account 的键。
    # 历史上这里存的是 "personal"，是个谁都不认识的键，于是
    # （叠加引擎写死 non_blue_v 的 bug）用户在界面上切"蓝V/非蓝V"完全没效果。
    "last_account_type": DEFAULT_ACCOUNT_TYPE,
    "llm_enabled": False,
    "llm_mode": "local",            # local（Ollama）| cloud（OpenAI 兼容）
    "llm_api_key": "",
    "llm_base_url": "https://api.deepseek.com/v1",
    "llm_local_base": "http://localhost:11434",
    "llm_model": "qwen2.5:7b",
    "total_checks": 0,
    "total_violations": 0,
    "appearance_mode": "Light",
    # 启用的行业包。``None`` = 跟随 rules/industry_packs/ 下的**全部**包。
    #
    # 为什么用 None 而不是把 9 个 id 写在这里：写过一次就会漂 —— 加第 10 个
    # 行业包时没人记得回来改这个列表，用户界面上的行业选择器就少一项，
    # 而且是静默的。列表只认磁盘，磁盘上加一个目录就多一个行业。
    #
    # 另：Web 端默认就是"全开"，桌面端曾经默认只开移民包，同一份文案在两个端
    # 得到的命中数不一样 —— 双端口径必须一致。
    "enabled_industry_packs": None,
    "minimize_to_tray": True,
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
