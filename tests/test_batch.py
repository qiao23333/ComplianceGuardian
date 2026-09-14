#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量检测模块单元测试。"""

import tempfile
from pathlib import Path

from guardian.batch_detect import BatchRunner
from guardian.schema import DetectionOptions


def _make(tmp, name, content):
    p = Path(tmp) / name
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_txt_and_md(tmp_path):
    _make(tmp_path, "a.txt", "这是最好的产品，全网最低价")
    _make(tmp_path, "b.md", "普通分享，无违规内容")
    runner = BatchRunner(options=DetectionOptions())
    results = runner.scan([tmp_path])
    by_name = {Path(r.path).name: r for r in results}
    assert "a.txt" in by_name and "b.md" in by_name
    # a.txt 含极限词(high) → 中风险；b.md 无 → 基本合规
    assert by_name["a.txt"].risk_level == "中风险"
    assert by_name["b.md"].risk_level == "基本合规"
    assert by_name["a.txt"].findings_count >= 2


def test_unsupported_type_skipped(tmp_path):
    _make(tmp_path, "note.pdf", "最好最低价")  # .pdf 不在支持列表
    runner = BatchRunner()
    results = runner.scan([tmp_path])
    assert results and results[0].skipped is True


def test_recursive_scan(tmp_path):
    sub = Path(tmp_path) / "sub"
    sub.mkdir()
    _make(sub, "deep.txt", "保证下签的移民项目")
    _make(tmp_path, "top.txt", "最好的服务")
    runner = BatchRunner()
    results = runner.scan([tmp_path], recursive=True)
    names = {Path(r.path).name for r in results}
    assert {"deep.txt", "top.txt"} <= names


def test_summarize(tmp_path):
    # 语料说明（2026-09-14 更新）：
    # 原先用"全网最低"作为 medium 档代表，现已在词库加固中提为 high ——
    # "全网最低价"属《广告法》第九条绝对化用语 + 《价格法》虚假价格宣称，
    # 与极限词同级，留在"低危建议"会让用户忽略真正的红线。
    # 这里换用"限时秒杀"（引诱消费 / medium）继续验证四级分档确实生效。
    _make(tmp_path, "a.txt", "这是最好的产品限时秒杀")
    _make(tmp_path, "b.txt", "普通内容无违规")
    runner = BatchRunner()
    results = runner.scan([tmp_path])
    s = runner.summarize(results)
    assert s.total_files == 2
    assert s.scanned == 2
    assert s.risky_files == 1
    # "最好"属极限词(high)、"秒杀"属引诱消费(medium)——四级体系真正分档
    assert s.severity_dist["high"] >= 1
    assert s.severity_dist["medium"] >= 1
    assert s.severity_dist["critical"] == 0
    assert s.top_keywords  # 有 Top 词统计


def test_export_csv(tmp_path):
    _make(tmp_path, "a.txt", "这是最好的产品")
    runner = BatchRunner()
    results = runner.scan([tmp_path])
    csv_path = runner.export_csv(results, tmp_path / "report.csv")
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8-sig")
    assert "risk_level" in content          # 表头（英文）
    assert "最好" in content                # top_findings 落地
