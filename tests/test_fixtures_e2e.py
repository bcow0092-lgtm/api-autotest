import json
from pathlib import Path

from analyzers.node_web import NodeWebAnalyzer
from analyzers.python_web import PythonWebAnalyzer
from skill_utils.config_loader import load_config
from tools.analyze_source import analyze_source

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_fastapi_fixture_analyzed():
    analyzer = PythonWebAnalyzer()

    assert analyzer.detect(FIXTURES / "fastapi_app") is True
    endpoints = analyzer.analyze([FIXTURES / "fastapi_app"], {})
    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/api/orders/list"),
        ("POST", "/api/orders/create"),
        ("GET", "/api/orders/{order_id}"),
    ]


def test_express_fixture_analyzed():
    analyzer = NodeWebAnalyzer()

    assert analyzer.detect(FIXTURES / "express_app") is True
    endpoints = analyzer.analyze([FIXTURES / "express_app" / "routes"], {})
    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/items"),
        ("POST", "/items"),
        ("DELETE", "/items/{id}"),
    ]


def test_auto_language_picks_python_for_fastapi_fixture(tmp_path):
    # 注意：`auto` 模式是对 `project_root` 调各分析器的 detect() 来选语言的，
    # 所以这里必须让 project_root 就落在 fixture 上——若 project_root 是空目录，
    # 三个分析器都会 detect()=False，pick_analyzer 返回 None 并抛 ValueError。
    app_dir = FIXTURES / "fastapi_app"
    idx = tmp_path / "idx"
    idx.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(app_dir),
                "paths": {"api_method_dirs": ["."], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["."], "db_path": str(idx / "i.sqlite3")},
                "source_analysis": {"language": "auto", "roots": ["."]},
            }
        ),
        encoding="utf-8",
    )

    result = analyze_source(load_config(config_path), dry_run=True)

    assert result["analyzer"] == "python"
    assert result["endpoints"] == 3
