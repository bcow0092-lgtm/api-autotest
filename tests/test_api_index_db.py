import sqlite3

import pytest

from skill_utils.api_index_db import (
    find_by_path_method,
    list_records,
    replace_index,
    upsert_many,
)


def _record(url="/api/users/create", method="POST", name="create_user", file="api/user.py"):
    return {
        "api_url": url,
        "api_name": name,
        "http_method": method,
        "file": file,
        "line": 10,
    }


def test_replace_index_rebuilds_table(tmp_path):
    db = tmp_path / "index.sqlite3"
    assert replace_index(str(db), [_record()]) == 1

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT api_url, method, api_name FROM api_methods").fetchall()
    assert rows == [("/api/users/create", "POST", "create_user")]


def test_replace_index_clears_previous(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [_record()])
    replace_index(str(db), [_record(url="/api/orders/list", method="GET", name="list_orders")])

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT api_url FROM api_methods").fetchall()
    assert rows == [("/api/orders/list",)]


def test_pure_path_is_derived_and_unique_per_method(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [_record(url="/wms/warehouse/123/detail", method="GET")])

    found = find_by_path_method(str(db), "/wms/warehouse/{param}/detail", "GET")
    assert found is not None
    assert found["api_url"] == "/wms/warehouse/123/detail"
    assert find_by_path_method(str(db), "/wms/warehouse/{param}/detail", "DELETE") is None


def test_upsert_many_skips_existing_and_reports_inserted(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [_record()])

    inserted = upsert_many(str(db), [
        _record(),
        _record(url="/api/orders/list", method="GET", name="list_orders"),
    ])

    assert inserted == 1
    assert len(list_records(str(db))) == 2


def test_list_records_filters_by_source(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [
        {**_record(), "source": "scan"},
        {**_record(url="/api/x", method="GET"), "source": "capture"},
    ])

    assert len(list_records(str(db), source="scan")) == 1
    assert len(list_records(str(db), source="capture")) == 1
    assert len(list_records(str(db))) == 2


def test_corrupted_db_file_raises_clear_error(tmp_path):
    db = tmp_path / "index.sqlite3"
    db.write_text("这不是一个 SQLite 文件", encoding="utf-8")

    with pytest.raises(sqlite3.DatabaseError) as exc:
        replace_index(str(db), [_record()])

    assert "index.sqlite3" in str(exc.value)
