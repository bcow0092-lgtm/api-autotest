# -*- coding: utf-8 -*-
"""Python Web 源码分析器：FastAPI / Flask / Django。

三种框架的写法差异很大，这里各用一组正则处理：
- FastAPI：@router.get("/x") / @app.post("/x")，路由器可能有 prefix=
- Flask  ：@app.route("/x", methods=["GET","POST"])
- Django ：urlpatterns = [path("users/", view)]，路由本身不含 HTTP 方法，一律记为 ANY
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from analyzers.base import ApiEndpoint, apply_prefix_map, classify_endpoint, join_url_paths
from skill_utils.api_path_match import normalize_path
from skill_utils.text_io import read_text_utf8

_FASTAPI_ROUTE = re.compile(
    r"@\s*(?P<obj>[A-Za-z_]\w*)\.(?P<verb>get|post|put|delete|patch|head|options)\s*\(\s*"
    r"(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)"
)
_ROUTER_PREFIX = re.compile(
    r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?:APIRouter|Blueprint)\s*\([^)]*prefix\s*=\s*"
    r"(?P<quote>['\"])(?P<prefix>[^'\"]*)(?P=quote)",
    re.S,
)
_FLASK_ROUTE = re.compile(
    r"@\s*(?P<obj>[A-Za-z_]\w*)\.route\s*\(\s*(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)"
    r"(?P<rest>(?:\([^)]*\)|[^)])*)\)",
    re.S,
)
_FLASK_METHODS = re.compile(r"methods\s*=\s*[\[(]([^\])]*)[\])]")
_DJANGO_PATH = re.compile(
    r"\b(?:re_)?path\s*\(\s*(?P<quote>['\"])(?P<path>[^'\"]*)(?P=quote)\s*,\s*(?P<view>[^,)]+)"
)
_DJANGO_URLPATTERNS = re.compile(r"\burlpatterns\s*=")
_DJANGO_INCLUDE = re.compile(r"^\s*include\s*\(")
_DEF_NAME = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.M)

_DJANGO_CONVERTER = re.compile(r"<(?:(?P<conv>[a-zA-Z]+):)?(?P<name>[a-zA-Z_]\w*)>")


def parse_python_source(
    source: str, file_path: str, url_prefix_map: dict | None = None
) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    docs = _docstrings_by_function(source)
    endpoints.extend(_parse_fastapi(source, file_path, docs))
    endpoints.extend(_parse_flask(source, file_path, docs))
    endpoints.extend(_parse_django(source, file_path))
    mapped = url_prefix_map or {}
    if mapped:
        for endpoint in endpoints:
            endpoint.path = apply_prefix_map(endpoint.path, mapped)
    return endpoints


def _parse_fastapi(source: str, file_path: str, docs: dict[str, str]) -> list[ApiEndpoint]:
    prefixes = {m.group("name"): m.group("prefix") for m in _ROUTER_PREFIX.finditer(source)}
    endpoints = []
    for match in _FASTAPI_ROUTE.finditer(source):
        prefix = prefixes.get(match.group("obj"), "")
        path = join_url_paths(prefix, match.group("path"))
        handler = _handler_after(source, match.end())
        method = match.group("verb").upper()
        endpoint = ApiEndpoint(
            method=method,
            path=path,
            handler=handler,
            file_path=file_path,
            line_no=source.count("\n", 0, match.start()) + 1,
            doc=docs.get(handler, ""),
            params=[],
            category=classify_endpoint(method, handler, path, []),
        )
        endpoints.append(endpoint)
    return endpoints


def _parse_flask(source: str, file_path: str, docs: dict[str, str]) -> list[ApiEndpoint]:
    endpoints = []
    for match in _FLASK_ROUTE.finditer(source):
        methods_match = _FLASK_METHODS.search(match.group("rest") or "")
        if methods_match:
            methods = [
                token.strip().strip("'\"").upper()
                for token in methods_match.group(1).split(",")
                if token.strip()
            ]
        else:
            methods = ["GET"]

        path = normalize_path(match.group("path"))
        handler = _handler_after(source, match.end())
        line_no = source.count("\n", 0, match.start()) + 1
        doc = docs.get(handler, "")
        for method in methods:
            endpoints.append(
                ApiEndpoint(
                    method=method,
                    path=path,
                    handler=handler,
                    file_path=file_path,
                    line_no=line_no,
                    doc=doc,
                    params=[],
                    category=classify_endpoint(method, handler, path, []),
                )
            )
    return endpoints


def _parse_django(source: str, file_path: str) -> list[ApiEndpoint]:
    if not _DJANGO_URLPATTERNS.search(source):
        return []
    endpoints = []
    for match in _DJANGO_PATH.finditer(source):
        view = match.group("view").strip()
        if _DJANGO_INCLUDE.match(view):
            continue  # include(...) 是路由挂载，不是接口
        raw_path = match.group("path")
        path = normalize_path(_DJANGO_CONVERTER.sub(lambda m: "{%s}" % (m.group("name") or "param"), raw_path))
        handler = view.rsplit(".", 1)[-1].strip("'\"")
        endpoints.append(
            ApiEndpoint(
                method="ANY",
                path=path,
                handler=handler,
                file_path=file_path,
                line_no=source.count("\n", 0, match.start()) + 1,
                doc="",
                params=[],
                category=classify_endpoint("ANY", handler, path, []),
            )
        )
    return endpoints


def _handler_after(source: str, position: int) -> str:
    match = _DEF_NAME.search(source, position)
    return match.group(1) if match else ""


def _docstrings_by_function(source: str) -> dict[str, str]:
    """一次解析整份源码，返回 {函数名: docstring 首行}。

    解析失败（例如源码里有语法错误）时返回**空字典**——拿不到 docstring 不能让整个
    分析挂掉。同名函数（不同类里）只取第一个。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node)
        if doc and doc.strip():
            result.setdefault(node.name, doc.strip().splitlines()[0].strip())
    return result


class PythonWebAnalyzer:
    language = "python"

    def detect(self, project_root: Path) -> bool:
        for python_file in Path(project_root).rglob("*.py"):
            if any(part in {".venv", "venv", "node_modules", "site-packages"} for part in python_file.parts):
                continue
            source = read_text_utf8(python_file)
            if (
                _FASTAPI_ROUTE.search(source)
                or _FLASK_ROUTE.search(source)
                or (_DJANGO_URLPATTERNS.search(source) and _DJANGO_PATH.search(source))
            ):
                return True
        return False

    def analyze(self, roots: list[Path], url_prefix_map: dict[str, str]) -> list[ApiEndpoint]:
        endpoints: list[ApiEndpoint] = []
        for root in roots:
            for python_file in sorted(Path(root).rglob("*.py")):
                if any(
                    part in {".venv", "venv", "node_modules", "site-packages"}
                    for part in python_file.parts
                ):
                    continue
                source = read_text_utf8(python_file)
                endpoints.extend(
                    parse_python_source(source, python_file.name, url_prefix_map or {})
                )
        return endpoints
