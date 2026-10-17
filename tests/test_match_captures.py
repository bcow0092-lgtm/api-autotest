import json
from pathlib import Path

from tools.match_captures import (
    bucket_records,
    dedup_by_method_path,
    load_jsonl,
    render_selection,
)


def _capture(method, path, is_login=False, body_skipped=False, status=200):
    return {
        "method": method,
        "pure_path": path,
        "path": path,
        "url": f"http://localhost:8081{path}",
        "status": status,
        "is_login": is_login,
        "body_skipped": body_skipped,
        "skip_reason": "binary-content-type:image/png" if body_skipped else "",
        "req_body": None,
        "resp_content_type": "image/png" if body_skipped else "application/json",
    }


def _record(url, method, name="m", file="api/x.py"):
    return {"api_url": url, "pure_path": url, "method": method, "api_name": name, "file": file, "line": 1}


def test_load_jsonl_skips_blank_and_broken_lines(tmp_path):
    path = tmp_path / "latest.jsonl"
    path.write_text(
        json.dumps({"method": "GET", "pure_path": "/a"}, ensure_ascii=False) + "\n"
        + "\n"
        + "{ 不是 JSON\n"
        + json.dumps({"method": "POST", "pure_path": "/b"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    records = load_jsonl(path)

    assert len(records) == 2


def test_load_jsonl_missing_file_returns_empty(tmp_path):
    assert load_jsonl(tmp_path / "nope.jsonl") == []


def test_load_jsonl_skips_valid_json_that_is_not_an_object(tmp_path):
    """合法 JSON 但非对象（null / [..] / "str"）必须跳过——下游会 .get() 取字段。"""
    path = tmp_path / "latest.jsonl"
    path.write_text(
        json.dumps({"method": "GET", "pure_path": "/a"}, ensure_ascii=False) + "\n"
        + "null\n"
        + "[1, 2]\n"
        + '"str"\n'
        + "123\n"
        + json.dumps({"method": "POST", "pure_path": "/b"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    records = load_jsonl(path)

    assert [r["pure_path"] for r in records] == ["/a", "/b"]


def test_dedup_does_not_crash_on_load_jsonl_output(tmp_path):
    path = tmp_path / "latest.jsonl"
    path.write_text(
        json.dumps({"method": "GET", "pure_path": "/a"}, ensure_ascii=False) + "\n"
        + "null\n"
        + "[1, 2]\n"
        + '"str"\n',
        encoding="utf-8",
    )

    deduped = dedup_by_method_path(load_jsonl(path))

    assert [r["pure_path"] for r in deduped] == ["/a"]


def test_dedup_keeps_last_occurrence():
    records = [
        {"method": "GET", "pure_path": "/a", "status": 500},
        {"method": "GET", "pure_path": "/a", "status": 200},
        {"method": "POST", "pure_path": "/a", "status": 201},
    ]

    deduped = dedup_by_method_path(records)

    assert len(deduped) == 2
    assert [r["status"] for r in deduped if r["method"] == "GET"] == [200]


def test_bucket_records_splits_all_four_categories():
    records = [
        _capture("GET", "/wms/list"),
        _capture("POST", "/wms/add"),
        _capture("GET", "/wms/export", body_skipped=True),
        _capture("POST", "/login", is_login=True),
    ]
    index = [_record("/wms/list", "GET")]

    buckets = bucket_records(records, index)

    assert [r["pure_path"] for r in buckets["new"]] == ["/wms/add"]
    assert [r["pure_path"] for r in buckets["existing"]] == ["/wms/list"]
    assert [r["pure_path"] for r in buckets["special"]] == ["/wms/export"]
    assert [r["pure_path"] for r in buckets["login_ignored"]] == ["/login"]


def test_bucket_records_with_empty_index_puts_all_in_new():
    records = [_capture("GET", "/a"), _capture("POST", "/b")]

    buckets = bucket_records(records, [])

    assert len(buckets["new"]) == 2
    assert buckets["existing"] == []


def test_render_selection_marks_new_checked_and_existing_unchecked():
    buckets = bucket_records([_capture("GET", "/wms/list"), _capture("POST", "/wms/add")], [])
    text = render_selection(buckets, {"jsonl": "latest.jsonl", "index": "idx", "count": 2})

    assert "- [x] **1. GET `/wms/add`**" in text or "- [x] **1. GET `/wms/list`**" in text
    assert "## 已自动忽略的登录/登出接口" in text


def test_render_selection_includes_implementation_reference():
    buckets = bucket_records([_capture("GET", "/wms/list")], [_record("/wms/list", "GET", name="list_receipt")])
    text = render_selection(buckets, {"jsonl": "latest.jsonl", "index": "idx", "count": 1})

    assert "list_receipt" in text


def test_bucket_records_matches_literal_capture_against_placeholder_index():
    """抓到的路径带**真实 ID**（字面量），索引里的 pure_path 带占位符。
    匹配方向搞反（拿索引 api_url 当 pattern）就永远配不上，会把已实现的接口
    重复报成"新接口"并默认勾选。"""
    records = [_capture("GET", "/wms/checkOrder/123")]
    index = [
        {
            "api_url": "/wms/checkOrder/123",
            "pure_path": "/wms/checkOrder/{param}",
            "method": "GET",
            "api_name": "getInfo",
            "file": "api/check.py",
            "line": 3,
        }
    ]

    buckets = bucket_records(records, index)

    assert buckets["existing"], "字面量抓包路径应当能匹配占位符索引"
    assert buckets["new"] == []
