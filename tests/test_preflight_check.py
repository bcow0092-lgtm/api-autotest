import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from skill_utils.api_index_db import replace_index
from skill_utils.config_loader import load_config
from tools.preflight_check import check_freshness, index_age_days, main


def _config(tmp_path, db_path):
    project = tmp_path / "p"
    api_dir = project / "api"
    api_dir.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["api"], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["api"], "db_path": str(db_path)},
            }
        ),
        encoding="utf-8",
    )
    return load_config(config_path)


def test_index_age_days_empty_index_is_none():
    assert index_age_days([]) is None


def test_index_age_days_uses_latest_last_seen():
    today = date(2026, 10, 11)
    records = [
        {"last_seen": "2026-10-01"},
        {"last_seen": "2026-10-09"},
    ]

    assert index_age_days(records, today=today) == 2


def test_index_age_days_skips_unparsable_last_seen():
    """一条坏日期不能毁掉整个判断：坏记录跳过，全坏则返回 None。"""
    today = date(2026, 10, 11)
    mixed = [
        {"last_seen": "not-a-date"},
        {"last_seen": "2026-10-08"},
        {"last_seen": ""},
        {"last_seen": None},
    ]

    assert index_age_days(mixed, today=today) == 3
    assert index_age_days([{"last_seen": "??"}, {"last_seen": None}], today=today) is None


def test_check_freshness_fresh_index(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [{"api_url": "/a", "http_method": "GET", "file": "api/a.py", "line": 1}])
    config = _config(tmp_path, db)

    result = check_freshness(config)

    assert result["status"] == "fresh"
    assert result["age_days"] == 0


def test_check_freshness_stale_index(tmp_path):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [{"api_url": "/a", "http_method": "GET", "file": "api/a.py", "line": 1}])
    old = (date.today() - timedelta(days=30)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE api_methods SET first_seen = ?, last_seen = ?", (old, old))
    config = _config(tmp_path, db)

    result = check_freshness(config)

    assert result["status"] == "stale"
    assert result["age_days"] >= 30
    assert "scan_api_methods" in result["message"]


def test_check_freshness_empty_index(tmp_path):
    db = tmp_path / "index.sqlite3"
    config = _config(tmp_path, db)

    result = check_freshness(config)

    assert result["status"] == "empty"
    assert "scan_api_methods" in result["message"]


def test_main_prints_message_and_returns_zero(tmp_path, capsys):
    db = tmp_path / "index.sqlite3"
    replace_index(str(db), [{"api_url": "/a", "http_method": "GET", "file": "api/a.py", "line": 1}])
    config = _config(tmp_path, db)

    exit_code = main(["--config", str(config.config_path)])

    assert exit_code == 0
    assert "索引" in capsys.readouterr().out


def test_stale_message_gives_a_runnable_command():
    """提示语必须给**可直接执行**的路径，不能是 `<skill>` 这类占位符。"""
    from tools.preflight_check import SCAN_COMMAND

    assert "<skill>" not in SCAN_COMMAND
    assert SCAN_COMMAND.startswith("python ")
    assert "scan_api_methods.py" in SCAN_COMMAND
