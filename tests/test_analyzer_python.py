from pathlib import Path

from analyzers.python_web import PythonWebAnalyzer, parse_python_source

FASTAPI = '''
from fastapi import APIRouter

router = APIRouter(prefix="/items")


@router.get("/list")
def list_items():
    """查询条目列表"""
    return []


@router.post("/create")
def create_item(payload: dict):
    """创建条目"""
    return payload


@router.delete("/{item_id}")
def delete_item(item_id: int):
    """删除条目"""
    return {"ok": True}
'''

FLASK = '''
from flask import Flask

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return "ok"


@app.route("/orders", methods=["GET", "POST"])
def orders():
    return "ok"
'''

DJANGO = '''
from django.urls import path

urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
]
'''


def test_fastapi_paths_and_methods():
    endpoints = parse_python_source(FASTAPI, "app/main.py")

    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/items/list"),
        ("POST", "/items/create"),
        ("DELETE", "/items/{item_id}"),
    ]


def test_fastapi_docstring_becomes_doc():
    endpoints = parse_python_source(FASTAPI, "app/main.py")

    assert endpoints[0].doc == "查询条目列表"
    assert endpoints[0].handler == "list_items"


def test_flask_single_and_multi_methods():
    endpoints = parse_python_source(FLASK, "app.py")

    assert ("GET", "/health") in [(e.method, e.path) for e in endpoints]
    assert ("GET", "/orders") in [(e.method, e.path) for e in endpoints]
    assert ("POST", "/orders") in [(e.method, e.path) for e in endpoints]


def test_django_paths_have_no_http_method():
    endpoints = parse_python_source(DJANGO, "urls.py")

    assert [(e.method, e.path) for e in endpoints] == [
        ("ANY", "/users"),
        ("ANY", "/users/{pk}"),
    ]


def test_detect_and_analyze(tmp_path):
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text(FASTAPI, encoding="utf-8")

    analyzer = PythonWebAnalyzer()

    assert analyzer.detect(root) is True
    assert len(analyzer.analyze([root], {})) == 3


def test_detect_returns_false_for_non_python_web(tmp_path):
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "util.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    assert PythonWebAnalyzer().detect(root) is False


def test_url_prefix_map_applied():
    # 用一个**真的能命中**的映射：/items → /api/items，否则这条断言恒真、测不到任何东西
    endpoints = parse_python_source(FASTAPI, "app/main.py", {"/items": "/api/items"})

    assert [(e.method, e.path) for e in endpoints] == [
        ("GET", "/api/items/list"),
        ("POST", "/api/items/create"),
        ("DELETE", "/api/items/{item_id}"),
    ]


def test_django_gate_ignores_files_without_urlpatterns():
    source = '''
def path(a, b):
    return os.path.join(a, b)


CONFIG = path("config", "base")
'''

    assert parse_python_source(source, "util.py") == []


def test_django_ignores_include_mounts():
    source = '''
from django.urls import path, include

urlpatterns = [
    path("api/", include("app.urls")),
    path("users/", views.user_list, name="user_list"),
]
'''
    endpoints = parse_python_source(source, "urls.py")

    assert [(e.method, e.path) for e in endpoints] == [("ANY", "/users")]


def test_flask_tuple_methods_are_supported():
    source = '''
from flask import Flask

app = Flask(__name__)


@app.route("/orders", methods=("GET", "POST"))
def orders():
    return "ok"
'''
    endpoints = parse_python_source(source, "app.py")

    assert sorted(e.method for e in endpoints) == ["GET", "POST"]


def test_detect_returns_false_for_non_django_path_calls(tmp_path):
    root = tmp_path / "proj"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "util.py").write_text(
        'def path(a, b):\n    return a + b\n\n\nCONFIG = path("config", "base")\n',
        encoding="utf-8",
    )

    assert PythonWebAnalyzer().detect(root) is False
