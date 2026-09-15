#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端产物 ↔ Python 内核 的一致性门禁。

为什么单独开一个文件
--------------------
Web 体验页最核心的宣称是「它和桌面端是同一个工具，同一套词库」。
这句话只有在**前端产物始终跟着源词库走**时才成立。

2026-09-15 真实翻过一次车：``harden_rulebank.py`` 已经把源词库改了
（新增 12 条、把「全网最低」提级为中危），但没人重新跑导出，于是
Web 体验页连续几天跑的是 9 月 10 日的旧词库 —— 而页面上**完全看不出来**，
它照样能检测、照样给分数，只是给的不是同一个工具的分数。

更讽刺的是：项目里早就有 ``scripts/verify_web_parity.py`` 能发现这件事，
但它一直是"需要人记得手动跑"的脚本。没有被自动化拦住的知识等于不存在。

所以这里放三道门：

1. 编译产物与源词库一致（快，纯 CPU）
2. 两端跑同一批语料，结论一致（需要 node）
3. **``--check`` 自己必须能报错** —— 一个不会失败的守卫等于没有守卫
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_EXPORT = _ROOT / "scripts" / "export_web_rules.py"
_PARITY = _ROOT / "scripts" / "verify_web_parity.py"
_WEB_RULES = _ROOT / "web" / "data" / "rules.json"


def _run(args: list[str], cwd: Path = _ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ============================================================ 1. 产物一致性


def test_web_rules_artifact_is_in_sync():
    """前端词库必须与源词库一致。

    失败时的修复动作只有一条：``python scripts/export_web_rules.py``。
    报错信息里把差异条目打出来，避免"知道不一致但不知道差在哪"。
    """
    proc = _run([str(_EXPORT), "--check"])
    assert proc.returncode == 0, (
        "前端词库已与 Python 端漂移，Web 体验页会给出与桌面端不同的结论。\n"
        f"修复：python scripts/export_web_rules.py\n\n{proc.stdout}"
    )


def test_web_rules_artifact_exists_and_has_rules():
    """产物存在且条数合理（防止有人误删或导出成空文件）。"""
    assert _WEB_RULES.exists(), f"缺少前端词库产物：{_WEB_RULES}"
    data = json.loads(_WEB_RULES.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    assert len(rules) > 900, f"前端词库只有 {len(rules)} 条，疑似导出不完整"
    assert data["meta"]["rule_count"] == len(rules), "meta.rule_count 与实际条数不符"

    # 行业包必须真的在（这是这个作品的主要差异点，不能悄悄丢）
    industries = {r.get("i") for r in rules if r.get("i")}
    assert industries == {"immigration", "study_abroad"}, f"行业包异常：{industries}"


def test_artifact_rules_js_is_generated_next_to_json():
    """rules.js 必须与 rules.json 同时生成 —— 页面靠的是 .js（file:// 也能跑）。"""
    js = _WEB_RULES.with_suffix(".js")
    assert js.exists(), "缺少 rules.js，页面双击打开会加载不到词库"
    head = js.read_text(encoding="utf-8")[:120]
    assert "window.GUARDIAN_RULES" in head, "rules.js 内容不像自动生成的产物"


# ============================================================ 2. 行为对拍


@pytest.mark.skipif(shutil.which("node") is None, reason="本机未安装 node，跳过双端对拍")
def test_python_and_js_engines_agree():
    """同一批语料，两端给出的命中与风险等级必须一致。

    唯一允许的差异是拼音通道（前端不含拼音库，这是设计取舍，
    脚本会把它单列为"预期差异"，不计入失败）。
    """
    proc = _run([str(_PARITY)])
    assert proc.returncode == 0, (
        "前端引擎与 Python 内核结论不一致 —— 页面展示的将不是同一个工具的行为。\n"
        f"{proc.stdout[-2000:]}"
    )
    assert "不一致  ：0" in proc.stdout or "不一致 ：0" in proc.stdout, (
        f"对拍脚本未报告 0 不一致，输出：\n{proc.stdout[-1500:]}"
    )


# ============================================================ 3. 守卫自测


def test_check_mode_actually_detects_drift(tmp_path: Path):
    """``--check`` 必须能真的报错。

    一个永远返回 0 的守卫比没有守卫更糟——它会给人"已经守住了"的错觉。
    这里复制一份产物、人为改坏一条，断言检查退出码为 1 且指出了差异。
    """
    tampered = tmp_path / "rules.json"
    data = json.loads(_WEB_RULES.read_text(encoding="utf-8"))

    # 制造两种典型漂移：漏掉一条 + 严重度过时
    victim = None
    for r in data["rules"]:
        if r.get("s") == "high":
            victim = r
            break
    assert victim is not None, "语料假设失效：词库里没有 high 级规则"

    victim["s"] = "medium"                       # 严重度过时
    data["rules"] = [r for r in data["rules"]      # 整条漏掉
                     if r.get("k") != "现成雇主"]

    tampered.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    proc = _run([str(_EXPORT), "--check", "--out", str(tampered)])
    assert proc.returncode == 1, "改坏的产物竟然通过了检查，守卫失效"
    assert "漂移" in proc.stdout, f"未报出漂移：{proc.stdout}"
    assert "现成雇主" in proc.stdout, "未定位到被删掉的规则"
    assert victim["k"] in proc.stdout, "未定位到严重度不一致的规则"
