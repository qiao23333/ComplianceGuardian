#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出模块（HTML/PNG/PDF）单元测试。"""

from pathlib import Path

from guardian.export_report import (
    build_html, build_payload, export_all, export_image, export_pdf,
)
from guardian.engine import DetectionEngine
from guardian.schema import DetectionOptions


def _payload():
    return {
        "text": "加我微信，全网最低价最好用的移民项目保证下签！",
        "risk_level": "高风险",
        "score": 80,
        "counts": {"critical": 2, "high": 0, "medium": 0, "low": 0},
        "findings": [
            {"keyword": "全网最低", "matched_text": "全网最低", "severity": "critical",
             "category": "广告法", "source": "ad_law", "match_type": "keyword",
             "suggestion": "改为'价格实惠'"},
            {"keyword": "最好", "matched_text": "最好", "severity": "critical",
             "category": "广告法", "source": "ad_law", "match_type": "keyword",
             "suggestion": "改为'良好'"},
        ],
        "safe_text": "加我微信，价格实惠价良好用的移民项目保证下签！",
        "platform": "all",
        "created_at": "2026-09-10T14:00:00+00:00",
    }


def test_build_html_contains_key_info():
    h = build_html(_payload())
    assert "<!DOCTYPE html>" in h
    assert "合规检测报告" in h
    assert "高风险" in h
    assert "全网最低" in h
    assert "全网最低价最好用" in h  # 原文完整
    assert "价格实惠价良好用" in h  # 改写文案


def test_export_image_valid_png(tmp_path):
    p = export_image(_payload(), tmp_path / "r.png")
    assert p.exists() and p.stat().st_size > 1000
    from PIL import Image
    img = Image.open(p)
    assert img.format == "PNG"
    assert img.width > 300 and img.height > 300


def test_export_pdf_valid(tmp_path):
    p = export_pdf(_payload(), tmp_path / "r.pdf")
    assert p.exists() and p.stat().st_size > 500
    head = p.read_bytes()[:5]
    assert head == b"%PDF-"


def test_export_all_three_files(tmp_path):
    out = export_all(_payload(), tmp_path / "out")
    assert out["html"].exists() and out["html"].suffix == ".html"
    assert out["png"].exists()
    assert out["pdf"].exists()


def test_build_payload_from_engine_result():
    eng = DetectionEngine()
    r = eng.detect_text("这是最好的服务", DetectionOptions())
    payload = build_payload(r, platform="xiaohongshu")
    assert payload["text"] == "这是最好的服务"
    assert payload["risk_level"] == "高风险"
    assert any(f["keyword"] == "最好" for f in payload["findings"])
    assert payload["platform"] == "xiaohongshu"
