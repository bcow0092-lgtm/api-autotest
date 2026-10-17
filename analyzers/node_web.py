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
from skill_utils.api_path_match import normalize_path
from skill_utils.text_io import read_text_utf8

# 路由注册必然是"路径 + 处理函数"两个参数，路径字面量后必跟逗号；而 req.get('Authorization')
# / config.get('db.host') 这类**通用单参调用**不跟逗号。这条收窄是挡假接口的第一层判据。
_EXPRESS_ROUTE = re.compile(
    r"\b(?P<obj>[A-Za-z_$]\w*)\.(?P<verb>get|post|put|delete|patch|head|options)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<path>[^'\"`]*)(?P=quote)\s*,"
)
_ROUTER_BINDING = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$]\w*)\s*=\s*(?:express\s*\(\s*\)|express\.Router\s*\([^)]*\))"
)
_DEFAULT_ROUTER_NAMES = {"router", "app"}
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


def _router_names(source: str) -> set[str]:
    """本文件里"路由器对象"的候选名：惯用名 + 显式绑定自 express()/express.Router() 的标识符。"""
    names = set(_DEFAULT_ROUTER_NAMES)
    names.update(match.group("name") for match in _ROUTER_BINDING.finditer(source))
    return names


def _parse_express(source: str, file_path: str) -> list[ApiEndpoint]:
    # 门禁：`X.get("字面量")` 在普通 JS 里遍地都是（Map.get / cache.get / config.get），
    # 不先确认这是 Express 文件就会产出成片的假接口。.get( 是和普通代码同处一文件的通用
    # 调用，文件级门禁挡不住文件内部的误报，故再加两层判据：接收者须是路由器对象、
    # 且路径字面量后必须跟逗号（见 _EXPRESS_ROUTE 与 _router_names）。
    if not _EXPRESS_HINT.search(source):
        return []
    names = _router_names(source)
    endpoints = []
    for match in _EXPRESS_ROUTE.finditer(source):
        if match.group("obj") not in names:
            continue
        method = match.group("verb").upper()
        raw_path = "/" + _PATH_PARAM.sub(
            lambda m: "{%s}" % m.group(1), match.group("path").lstrip("/")
        )
        path = normalize_path(raw_path)
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
    """解析 NestJS 控制器。

    限制：一个文件里出现**多个** `@Controller` 时整份跳过（返回 []）——无法把路由
    准确归属到各自前缀，宁可漏报也不产出错路径。Nest 惯例是一文件一控制器。
    """
    controllers = list(_NEST_CONTROLLER.finditer(source))
    if not controllers:
        return []
    if len(controllers) > 1:
        return []
    prefix = controllers[0].group("prefix")

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
        # .ts 与 .js 都要同时找 Nest 与 Express 线索：analyze() 对两种扩展名都送进
        # 两个解析器，若 detect() 只看 .js 的 Express，纯 TS 的 Express 工程会
        # detect()=False 但 analyze() 有产出，auto 模式调度器据此漏判整个工程。
        for pattern in ("*.ts", "*.js"):
            for node_file in Path(project_root).rglob(pattern):
                if "node_modules" in node_file.parts:
                    continue
                source = read_text_utf8(node_file)
                if _NEST_CONTROLLER.search(source):
                    return True
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
