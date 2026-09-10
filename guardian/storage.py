#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检测历史存储（SQLite）。

把每次检测的结果持久化到本地数据库，支撑桌面端的"历史记录"面板与
报告导出复用。设计要点：

* 仅依赖标准库（sqlite3 / json / datetime），不引入 tkinter / fastapi，
  可独立单元测试（测试时注入临时 db 路径）。
* 所有查询参数化，杜绝 SQL 注入。
* 默认落到 ``guardian.paths.AppPaths.db``；桌面端首次运行时由 paths.ensure()
  创建目录。用户可通过 GUARDIAN_DATA_DIR 把整个数据目录搬到 D 盘
  （满足"不碰 C 盘"的硬约束）。
* findings 以 JSON 原文存储，便于历史回填时直接重建命中列表与导出报告，
  不必重新跑引擎。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from guardian.paths import AppPaths


@dataclass
class HistoryRecord:
    """一条检测历史记录（入库前构造）。"""

    text: str
    risk_level: str
    score: int
    counts: dict
    findings: list = field(default_factory=list)
    safe_text: str = ""
    platform: str = "all"
    account_type: str = "non_blue_v"
    source: str = "single"          # single | batch
    created_at: str = ""

    def with_timestamp(self) -> "HistoryRecord":
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return self


class HistoryStore:
    """SQLite 历史库封装。线程安全由 sqlite3 连接独占保证（单连接复用）。"""

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path is None:
            db_path = AppPaths.current().db
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    # -------------------------------------------------- schema

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at   TEXT    NOT NULL,
                text         TEXT    NOT NULL,
                risk_level   TEXT    NOT NULL,
                score        INTEGER NOT NULL,
                counts       TEXT    NOT NULL,
                findings     TEXT    NOT NULL,
                safe_text    TEXT    NOT NULL DEFAULT '',
                platform     TEXT    NOT NULL DEFAULT 'all',
                account_type TEXT    NOT NULL DEFAULT 'non_blue_v',
                source       TEXT    NOT NULL DEFAULT 'single'
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_detections_created "
            "ON detections(created_at DESC)"
        )
        self._conn.commit()

    # -------------------------------------------------- 写入

    def add(self, rec: HistoryRecord) -> int:
        """插入一条记录，返回自增 id。"""
        rec.with_timestamp()
        cur = self._conn.execute(
            """
            INSERT INTO detections
                (created_at, text, risk_level, score, counts, findings,
                 safe_text, platform, account_type, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec.created_at,
                rec.text,
                rec.risk_level,
                rec.score,
                json.dumps(rec.counts, ensure_ascii=False),
                json.dumps(rec.findings, ensure_ascii=False),
                rec.safe_text,
                rec.platform,
                rec.account_type,
                rec.source,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # -------------------------------------------------- 读取

    def list(self, limit: int = 50, offset: int = 0,
             search: str = "") -> list[dict]:
        """分页列出历史（按时间倒序）。search 对原文/风险做模糊匹配。"""
        if search:
            like = f"%{search}%"
            rows = self._conn.execute(
                "SELECT * FROM detections "
                "WHERE text LIKE ? OR risk_level LIKE ? "
                "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (like, like, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM detections "
                "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get(self, record_id: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM detections WHERE id = ?", (record_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None

    def count(self, search: str = "") -> int:
        if search:
            like = f"%{search}%"
            return int(self._conn.execute(
                "SELECT COUNT(*) FROM detections "
                "WHERE text LIKE ? OR risk_level LIKE ?",
                (like, like),
            ).fetchone()[0])
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM detections").fetchone()[0])

    # -------------------------------------------------- 删除

    def delete(self, record_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM detections WHERE id = ?", (record_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> int:
        """清空全部历史，返回删除条数。"""
        n = self.count()
        self._conn.execute("DELETE FROM detections")
        self._conn.execute("DELETE FROM sqlite_sequence WHERE name='detections'")
        self._conn.commit()
        return n

    def close(self) -> None:
        self._conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["counts"] = json.loads(d["counts"]) if d.get("counts") else {}
    d["findings"] = json.loads(d["findings"]) if d.get("findings") else []
    return d
