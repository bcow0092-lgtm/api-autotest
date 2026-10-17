import json
from pathlib import Path

from analyzers.base import ApiEndpoint
from skill_utils.config_loader import load_config
from tools.analyze_source import analyze_source, cross_check, pick_analyzer, render_draft


def _endpoint(method, path, handler="h"):
    return ApiEndpoint(method=method, path=path, handler=handler, file_path="A.java", line_no=1)


def _record(url, method, name="m", file="api/x.py"):
    return {"api_url": url, "pure_path": url, "method": method, "api_name": name, "file": file, "line": 3}


def test_cross_check_marks_covered_and_uncovered():
    endpoints = [_endpoint("GET", "/wms/list"), _endpoint("POST", "/wms/add")]
    records = [_record("/wms/list", "GET")]

    result = cross_check(endpoints, records)

    assert result[0]["impls"], "已实现的接口应当命中索引"
    assert result[1]["impls"] == [], "未实现的接口不应命中"


def test_cross_check_on_empty_index_treats_all_as_new():
    endpoints = [_endpoint("GET", "/a"), _endpoint("POST", "/b")]

    result = cross_check(endpoints, [])

    assert all(item["impls"] == [] for item in result)


def test_cross_check_matches_literal_index_against_placeholder_source():
    """索引里存的 api_url 是字面量、pure_path 是归一化路径；源码分析产出的是占位符路径。
    匹配方向搞反（拿 api_url 当 pattern）就永远配不上，会把“已实现”标成“未覆盖”。"""
    endpoints = [_endpoint("GET", "/wms/checkOrder/{id}")]
    records = [
        {
            "api_url": "/wms/checkOrder/123",
            "pure_path": "/wms/checkOrder/{param}",
            "method": "GET",
            "api_name": "getInfo",
            "file": "api/check.py",
            "line": 3,
        }
    ]

    result = cross_check(endpoints, records)

    assert result[0]["impls"], "字面量索引应当能匹配占位符源码路径"


def test_render_draft_lists_uncovered_first():
    endpoints = cross_check([_endpoint("GET", "/wms/list")], [])
    text = render_draft(endpoints, {"source": "java", "roots": ["src"], "index_path": "db"})

    assert "未覆盖接口候选" in text
    assert "- [x] **1. GET `/wms/list`**" in text


def test_pick_analyzer_explicit_language():
    analyzer = pick_analyzer("java", Path("."))

    assert analyzer is not None
    assert analyzer.language == "java"


def test_pick_analyzer_unknown_language_returns_none():
    assert pick_analyzer("cobol", Path(".")) is None


def test_analyze_source_writes_draft(tmp_path):
    project = tmp_path / "proj"
    java_dir = project / "src" / "main" / "java"
    java_dir.mkdir(parents=True)
    (java_dir / "DemoController.java").write_text(
        '''
@RestController
@RequestMapping("/demo")
public class DemoController {
    @GetMapping("/list")
    public Object list() { return null; }
}
'''.strip(),
        encoding="utf-8",
    )
    db_dir = project / "idx"
    db_dir.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["src"], "pytest_workdir": "."},
                "api_index": {
                    "scan_dirs": ["src"],
                    "db_path": str(db_dir / "index.sqlite3"),
                },
                "source_analysis": {
                    "language": "java",
                    "roots": ["src/main/java"],
                    "url_prefix_map": {},
                },
            }
        ),
        encoding="utf-8",
    )

    result = analyze_source(load_config(config_path))

    assert result["analyzer"] == "java"
    assert result["endpoints"] == 1
    assert Path(result["draft_path"]).is_file()
    assert "GET `/demo/list`" in Path(result["draft_path"]).read_text(encoding="utf-8")


def test_analyze_source_rejects_missing_root(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    idx = tmp_path / "idx"
    idx.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["."], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["."], "db_path": str(idx / "i.sqlite3")},
                "source_analysis": {"language": "java", "roots": ["nope/does/not/exist"]},
            }
        ),
        encoding="utf-8",
    )

    try:
        analyze_source(load_config(config_path), dry_run=True)
    except ValueError as exc:
        assert "roots" in str(exc)
    else:
        raise AssertionError("roots 指向不存在的目录时应当抛 ValueError，而不是静默产出空结果")
