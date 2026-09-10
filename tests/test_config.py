#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ConfigManager 配置管理测试"""
import json
import os
import tempfile
import pytest
from guardian.config import ConfigManager, DEFAULT_CONFIG


@pytest.fixture
def tmp_config_path(tmp_path):
    """临时配置文件路径"""
    return str(tmp_path / "config.json")


@pytest.fixture
def config_manager(tmp_config_path):
    """每个测试用独立的 ConfigManager"""
    return ConfigManager(config_path=tmp_config_path)


class TestConfigBasic:
    """基础配置读写"""

    def test_default_config_on_first_run(self, tmp_config_path):
        """首次运行应创建默认配置"""
        cm = ConfigManager(config_path=tmp_config_path)
        for k, v in DEFAULT_CONFIG.items():
            assert cm.get(k) == v

    def test_get_set(self, config_manager):
        """get/set 基本操作"""
        config_manager.set("theme", "dark")
        assert config_manager.get("theme") == "dark"

    def test_get_default(self, config_manager):
        """get 不存在的 key 返回 default"""
        assert config_manager.get("nonexistent_key", "fallback") == "fallback"
        assert config_manager.get("nonexistent_key") is None

    def test_persistence(self, tmp_config_path):
        """配置应持久化到文件"""
        cm1 = ConfigManager(config_path=tmp_config_path)
        cm1.set("total_checks", 42)

        cm2 = ConfigManager(config_path=tmp_config_path)
        assert cm2.get("total_checks") == 42


class TestConfigAtomicWrite:
    """原子写入（不损坏配置）"""

    def test_corrupted_config_recovers(self, tmp_config_path):
        """配置文件损坏时应回退到默认值，不崩溃"""
        # 先写一份正常配置
        cm = ConfigManager(config_path=tmp_config_path)
        cm.set("theme", "dark")

        # 手动损坏配置文件
        with open(tmp_config_path, "w", encoding="utf-8") as f:
            f.write("{invalid json!!!")

        # 重新加载应不崩溃，并回退到合理值
        cm2 = ConfigManager(config_path=tmp_config_path)
        # 损坏后应该能用，且 theme 是默认值或之前的值
        assert cm2.get("theme") is not None

    def test_atomic_write_no_partial_file(self, tmp_config_path):
        """写入过程中不会留下部分写入的文件"""
        cm = ConfigManager(config_path=tmp_config_path)
        cm.set("total_checks", 100)

        # 验证文件是合法 JSON
        with open(tmp_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_checks"] == 100


class TestConfigMigration:
    """配置迁移（旧版本配置缺字段时自动补全）"""

    def test_missing_keys_filled(self, tmp_config_path):
        """旧版本配置缺少的字段应自动补充默认值"""
        # 手动创建一个缺少字段的配置
        old_config = {"theme": "light", "last_platform": "抖音"}
        with open(tmp_config_path, "w", encoding="utf-8") as f:
            json.dump(old_config, f)

        cm = ConfigManager(config_path=tmp_config_path)
        # 旧字段保留
        assert cm.get("theme") == "light"
        assert cm.get("last_platform") == "抖音"
        # 缺失的新字段自动补全默认值
        for k, v in DEFAULT_CONFIG.items():
            assert cm.get(k) is not None
