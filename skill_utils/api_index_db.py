# -*- coding: utf-8 -*-
"""接口索引（SQLite）读写（多模块共用）。

表结构见 spec 第 4.1 节。字段命名沿用上游契约（Ruling 9）：
api_url / method / api_name / file / line 保持原名，能力字段做加法。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .api_path_match import normalize_path, to_pure_path

SCHEMA_VERSION = 1
TABLE = "api_methods"

_COLUMNS = (
    "api_url", "pure_path", "method", "api_name",
    "file", "line", "source", "first_seen", "last_seen",
)

_CREATE_SQL = f"""
CREATE TABLE {TABLE} (
  id          INTEGER PRIMARY KEY,
  api_url     TEXT NOT NULL,
  pure_path   TEXT NOT NULL,
  method      TEXT NOT NULL,
  api_name    TEXT,
  file        TEXT NOT NULL,
  line        INTEGER,
  source      TEXT NOT NULL,
  first_seen  TEXT,
  last_seen   TEXT,
  UNIQUE(pure_path, method)
)
"""


def replace_index(db_path: str | Path, records: list[dict]) -> int:
    """清空索引并全量写入，返回写入条数。"""
    conn = _connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(_CREATE_SQL)
        rows = [_to_row(r) for r in records]
        conn.executemany(
            f"INSERT OR REPLACE INTO {TABLE} ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(_COLUMNS))})",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def upsert_many(db_path: str | Path, records: list[dict]) -> int:
    """增量写入；已存在的 (pure_path, method) 只更新 last_seen，返回新增条数。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        inserted = 0
        for record in records:
            row = _to_row(record)
            pure_path, method = row[1], row[2]
            existing = conn.execute(
                f"SELECT id FROM {TABLE} WHERE pure_path = ? AND method = ?",
                (pure_path, method),
            ).fetchone()
            if existing:
                conn.execute(
                    f"UPDATE {TABLE} SET last_seen = ? WHERE id = ?",
                    (date.today().isoformat(), existing[0]),
                )
                continue
            conn.execute(
                f"INSERT INTO {TABLE} ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(_COLUMNS))})",
                row,
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def find_by_path_method(db_path: str | Path, pure_path: str, method: str) -> dict | None:
    """按 (pure_path, method) 查一条记录。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        row = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE pure_path = ? AND method = ?",
            (to_pure_path(pure_path), method.upper()),
        ).fetchone()
    finally:
        conn.close()
    return dict(zip(_COLUMNS, row)) if row else None


def list_records(db_path: str | Path, source: str | None = None) -> list[dict]:
    """列出索引记录，可按来源过滤。"""
    conn = _connect(db_path)
    try:
        _ensure_table(conn)
        if source:
            rows = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE source = ? ORDER BY id",
                (source,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} ORDER BY id"
            ).fetchall()
    finally:
        conn.close()
    return [dict(zip(_COLUMNS, row)) for row in rows]


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.DatabaseError as exc:
        raise sqlite3.DatabaseError(
            f"索引库不是合法的 SQLite 文件: {path} — 请删除后重新扫描。原始错误: {exc}"
        ) from exc
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_SQL.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
    conn.commit()


def _to_row(record: dict) -> tuple:
    api_url = normalize_path(record.get("api_url") or record.get("url") or "/")
    method = (record.get("method") or record.get("http_method") or "GET").upper()
    today = date.today().isoformat()
    return (
        api_url,
        record.get("pure_path") or to_pure_path(api_url),
        method,
        record.get("api_name"),
        record.get("file") or "",
        record.get("line"),
        record.get("source") or "scan",
        record.get("first_seen") or today,
        record.get("last_seen") or today,
    )
