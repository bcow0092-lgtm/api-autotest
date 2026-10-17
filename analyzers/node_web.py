# -*- coding: utf-8 -*-
"""Node Web 源码分析器：Express / NestJS。

已知限制（如实记录，不假装能做到）：Express 的挂载前缀写在别的文件里
（`app.use('/api', router)`），本版**不跨文件推断**，只取路由文件内写的路径。
NestJS 的 `@Controller('users')` 前缀在同一个文件里，可以拼。
"""

from __future__ import annotations

import re
from pathlib import Path

from analyzers.base import ApiEndpoint, apply_prefix_map, classify_endpoint, join_url_paths
from skill_utils.text_io import read_text_utf8

_EXPRESS_ROUTE = re.compile(
    r"\b(?P<obj>[A-Za-z_$]\w*)\.(?P<verb>get|post|put|delete|patch|head|options)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<path>[^'\"`]*)(?P=quote)"
)
_NEST_CONTROLLER = re.compile(
    r"@Controller\s*\(\s*(?P<quote>['\"`])(?P<prefix>[^'\"`]*)(?P=quote)\s*\)"
)
_NEST_ROUTE = re.compile(
    r"@(?P<verb>Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*(?:(?P<quote>['\"`])(?P<path>[^'\"`]*)(?P=quote))?\s*\)"
)
_NEST_HANDLER = re.compile(r"^\s*(?:async\s+)?(?P<name>[A-Za-z_$]\w*)\s*\(", re.M)

_EXPRESS_HINT = re.compile(r"require\s*\(\s*['\"]express['\"]\s*\)|from\s+['\"]express['\"]")

_PATH_PARAM = re.compile(r":([A-Za-z_]\w*)")


def parse_node_source(
    source: str, file_path: str, url_prefix_map: dict | None = None
) -> list[ApiEndpoint]:
    endpoints = _parse_nest(source, file_path)
    if not endpoints:
        endpoints = _parse_express(source, file_path)
    mapped = url_prefix_map or {}
    if mapped:
        for endpoint in endpoints:
            endpoint.path = apply_prefix_map(endpoint.path, mapped)
    return endpoints


def _parse_express(source: str, file_path: str) -> list[ApiEndpoint]:
    # 门禁：`X.get("字面量")` 在普通 JS 里遍地都是（Map.get / cache.get / config.get），
    # 不先确认这是 Express 文件就会产出成片的假接口。与 Django 那处是同一类问题。
    if not _EXPRESS_HINT.search(source):
        return []
    endpoints = []
    for match in _EXPRESS_ROUTE.finditer(source):
        method = match.group("verb").upper()
        path = "/" + _PATH_PARAM.sub(lambda m: "{%s}" % m.group(1), match.group("path").lstrip("/"))
        endpoints.append(
            ApiEndpoint(
                method=method,
                path=path,
                handler="",
                file_path=file_path,
                line_no=source.count("\n", 0, match.start()) + 1,
                doc="",
                params=[],
                category=classify_endpoint(method, "", path, []),
            )
        )
    return endpoints


def _parse_nest(source: str, file_path: str) -> list[ApiEndpoint]:
    controller = _NEST_CONTROLLER.search(source)
    if not controller:
        return []
    prefix = controller.group("prefix")

    endpoints = []
    for match in _NEST_ROUTE.finditer(source):
        method = match.group("verb").upper()
        sub_path = match.group("path") or ""
        path = join_url_paths("/" + prefix, sub_path)
        endpoint_path = _PATH_PARAM.sub(lambda m: "{%s}" % m.group(1), path)
        endpoints.append(
            ApiEndpoint(
                method=method,
                path=endpoint_path,
                handler=_nest_handler_after(source, match.end()),
                file_path=file_path,
                line_no=source.count("\n", 0, match.start()) + 1,
                doc="",
                params=[],
                category=classify_endpoint(method, "", endpoint_path, []),
            )
        )
    return endpoints


def _nest_handler_after(source: str, position: int) -> str:
    match = _NEST_HANDLER.search(source, position)
    return match.group("name") if match else ""


class NodeWebAnalyzer:
    language = "node"

    def detect(self, project_root: Path) -> bool:
        for node_file in Path(project_root).rglob("*.ts"):
            if "node_modules" in node_file.parts:
                continue
            if _NEST_CONTROLLER.search(read_text_utf8(node_file)):
                return True
        for node_file in Path(project_root).rglob("*.js"):
            if "node_modules" in node_file.parts:
                continue
            source = read_text_utf8(node_file)
            if _EXPRESS_HINT.search(source) and _EXPRESS_ROUTE.search(source):
                return True
        return False

    def analyze(self, roots: list[Path], url_prefix_map: dict[str, str]) -> list[ApiEndpoint]:
        endpoints: list[ApiEndpoint] = []
        for root in roots:
            for pattern in ("*.ts", "*.js"):
                for node_file in sorted(Path(root).rglob(pattern)):
                    if "node_modules" in node_file.parts:
                        continue
                    endpoints.extend(
                        parse_node_source(
                            read_text_utf8(node_file), node_file.name, url_prefix_map or {}
                        )
                    )
        return endpoints
