#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HistoryStore (SQLite) 单元测试。"""

import tempfile
from pathlib import Path

from guardian.storage import HistoryRecord, HistoryStore


def _store():
    d = Path(tempfile.mkdtemp())
    return HistoryStore(d / "history.sqlite3")


def _rec(text="测试文案", risk="中风险", score=80,
         counts=None, findings=None, safe="改写后"):
    return HistoryRecord(
        text=text, risk_level=risk, score=score,
        counts=counts or {"critical": 0, "high": 1, "medium": 0, "low": 0},
        findings=findings or [{"keyword": "最低价", "severity": "high"}],
        safe_text=safe,
    )


def test_add_returns_id_and_roundtrip():
    s = _store()
    rid = s.add(_rec())
    assert rid == 1
    got = s.get(rid)
    assert got["text"] == "测试文案"
    assert got["risk_level"] == "中风险"
    assert got["score"] == 80
    assert got["counts"]["high"] == 1
    assert got["findings"][0]["keyword"] == "最低价"
    assert got["safe_text"] == "改写后"
    assert got["created_at"]  # 时间戳已填充


def test_list_pagination_and_order():
    s = _store()
    for i in range(5):
        s.add(_rec(text=f"文案{i}"))
    rows = s.list(limit=2, offset=0)
    assert len(rows) == 2
    # 倒序：最新插入的在前
    assert rows[0]["text"] == "文案4"
    assert rows[1]["text"] == "文案3"
    assert s.count() == 5


def test_list_search():
    s = _store()
    s.add(_rec(text="双十一大促最低价"))
    s.add(_rec(text="普通分享无违规"))
    hits = s.list(search="最低价")
    assert len(hits) == 1
    assert "最低价" in hits[0]["text"]
    # 按风险模糊
    s.add(_rec(risk="极高风险"))
    risk_hits = s.list(search="极高")
    assert len(risk_hits) == 1


def test_delete_and_clear():
    s = _store()
    r1 = s.add(_rec(text="a"))
    r2 = s.add(_rec(text="b"))
    assert s.delete(r1) is True
    assert s.get(r1) is None
    assert s.get(r2) is not None
    n = s.clear()
    assert n == 1
    assert s.count() == 0
    assert s.list() == []


def test_timestamp_auto_filled():
    s = _store()
    rec = HistoryRecord(text="x", risk_level="低风险", score=100,
                       counts={}, findings=[])
    assert rec.created_at == ""
    rid = s.add(rec)
    assert s.get(rid)["created_at"]  # 入库时自动补时间戳
