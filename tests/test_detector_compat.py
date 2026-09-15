#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ComplianceDetector 兼容门面测试。

旧桌面 UI（词库管理 / 仪表盘 / 设置页）依赖这些方法的返回结构与副作用，
v3 重构后它们由 shim 在 ``rules/`` 单一数据源上提供。此测试确保：

1. ``get_rules_summary`` 返回旧 UI 期望的字段名与嵌套结构；
2. 词库增删改会真正落盘并可被重新加载；
3. 备份 / 还原闭环可用；
4. 检测接口仍返回旧 ``violations/summary/modified_text`` 结构。
"""

from __future__ import annotations

import json

import pytest

from guardian.detector import ComplianceDetector


@pytest.fixture
def rules_dir(tmp_path):
    """构造一个最小可用的 rules/ 目录。"""
    d = tmp_path / "rules"
    d.mkdir()
    (d / "ad_law.json").write_text(json.dumps([
        {"keyword": "最好", "category": "极限词", "severity": "violation",
         "suggestion": "改为'良好'"},
    ], ensure_ascii=False), encoding="utf-8")
    (d / "platform_rules.json").write_text(json.dumps({
        "xiaohongshu": [
            {"keyword": "加微信", "category": "导流", "severity": "violation",
             "suggestion": "删除"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (d / "blue_v_only.json").write_text(json.dumps([
        {"keyword": "抽奖", "category": "蓝V", "non_blue_v": "violation",
         "blue_v": "warning"},
    ], ensure_ascii=False), encoding="utf-8")
    (d / "user_custom.json").write_text("[]", encoding="utf-8")
    (d / "regex_patterns.json").write_text(json.dumps([
        {"keyword": r"最[^\W\s]", "match_mode": "regex", "category": "极限词",
         "severity": "critical", "suggestion": "删除"},
    ], ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def detector(rules_dir):
    return ComplianceDetector(str(rules_dir))


# ---------------------------------------------------------------- 摘要


def test_summary_shape(detector):
    s = detector.get_rules_summary()
    # 旧 dashboard / 设置页读取的字段
    assert s["广告法违禁词"] == 1
    assert s["蓝V专属限制"] == 1
    # 「行业红线」= 行业包里的规则总数（临时 rules_dir 里没有行业包）
    assert s["行业红线"] == 0
    # 「自定义词条」= 用户自己加进 user_custom.json 的条数
    assert s["自定义词条"] == 0
    assert s["正则模式"] == 1
    assert s["总计"] == 3  # ad_law 1 + platform 1 + blue_v 1
    # 平台规则是 {中文名: 条数}
    assert s["平台规则"] == {"小红书": 1}


def test_summary_industry_redline_counts_packs(tmp_path):
    """「行业红线」必须数的是行业包，不是用户自建词条。

    历史 bug：这一栏取的是 ``len(user_custom)``，而 ``user_custom.json`` 默认是
    空数组 —— 于是桌面端「关于」卡片上写着「行业红线 0 条」，
    而磁盘上其实有 9 个行业包共 475 条规则。把 475 显示成 0，
    比不显示这一栏更糟：用户会以为行业词库是空的。
    """
    rules_dir = tmp_path / "rules"
    pack = rules_dir / "industry_packs" / "demo"
    pack.mkdir(parents=True)
    (pack / "rules.json").write_text(
        json.dumps([{"keyword": "保证下签", "category": "虚假承诺",
                     "severity": "high"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (pack / "pack.json").write_text(
        json.dumps({"id": "demo", "name": "演示合规包"}, ensure_ascii=False),
        encoding="utf-8",
    )
    for name in ("ad_law.json", "blue_v_only.json", "platform_rules.json"):
        (rules_dir / name).write_text("[]" if name != "platform_rules.json" else "{}",
                                      encoding="utf-8")

    s = ComplianceDetector(str(rules_dir)).get_rules_summary()
    assert s["行业红线"] == 1, "行业红线应统计行业包里的条数"
    # 显示名要取 pack.json 的 name，不能退回英文目录名
    assert s["行业词库包"] == {"演示合规包": 1}


def test_platform_names(detector):
    assert detector.PLATFORM_NAMES["xiaohongshu"] == "小红书"


# ---------------------------------------------------------------- 增删改


def test_add_rule_to_category_persists(detector, rules_dir):
    detector.add_rule_to_category("广告法", "第一", "极限词", "violation", "改为'领先'")
    raw = json.loads((rules_dir / "ad_law.json").read_text(encoding="utf-8"))
    assert any(r["keyword"] == "第一" for r in raw)
    assert detector.get_rules_summary()["广告法违禁词"] == 2


def test_add_blue_v_and_custom(detector, rules_dir):
    detector.add_rule_to_category("蓝V限制", "点赞抽", "蓝V", "violation", "")
    # 「行业红线」标签页写的是 user_custom.json（用户自建词条），
    # 对应摘要里的「自定义词条」栏 —— 与行业包的「行业红线」栏是两个东西。
    detector.add_rule_to_category("行业红线", "保过", "行业红线", "violation", "")
    assert detector.get_rules_summary()["蓝V专属限制"] == 2
    assert detector.get_rules_summary()["自定义词条"] == 1
    custom = json.loads((rules_dir / "user_custom.json").read_text(encoding="utf-8"))
    assert custom[0]["keyword"] == "保过"


def test_remove_custom_rule(detector):
    detector.add_rule_to_category("行业红线", "A", "行业红线", "violation", "")
    detector.add_rule_to_category("行业红线", "B", "行业红线", "violation", "")
    detector.remove_custom_rule(0)
    assert [r["keyword"] for r in detector.user_custom] == ["B"]


def test_save_rules_roundtrip(detector, rules_dir):
    detector.ad_law.append({"keyword": "国家级", "category": "极限词",
                            "severity": "violation", "suggestion": ""})
    detector._save_rules("广告法")
    reloaded = ComplianceDetector(str(rules_dir))
    assert any(r.get("keyword") == "国家级" for r in reloaded.ad_law)


# ---------------------------------------------------------------- 备份/还原


def test_backup_and_restore(detector, rules_dir):
    detector.add_rule_to_category("行业红线", "原始词", "行业红线", "violation", "")
    path = detector.backup_rules()
    assert path
    backups = detector.list_backups()
    assert len(backups) == 1
    assert backups[0]["file_count"] >= 1

    # 备份后改动，再还原 → 回到备份时状态
    detector.remove_custom_rule(0)
    assert detector.user_custom == []
    detector.restore_backup(backups[0]["name"])
    assert [r["keyword"] for r in detector.user_custom] == ["原始词"]


def test_restore_missing_backup_raises(detector):
    with pytest.raises(FileNotFoundError):
        detector.restore_backup("not-exist")


# ---------------------------------------------------------------- 检测契约


def test_detect_returns_legacy_shape(detector):
    r = detector.detect("这是最好的产品", "all", "non_blue_v")
    assert set(r.keys()) >= {"violations", "summary", "modified_text"}
    assert r["summary"]["violations"] >= 1
    assert r["violations"][0]["keyword"]  # 展示用关键词非空
    assert r["summary"]["risk_level"]


def test_regex_rule_loaded(detector):
    r = detector.detect("这款最优秀", "all", "non_blue_v")
    assert any(v["match_type"] == "regex" for v in r["violations"])
