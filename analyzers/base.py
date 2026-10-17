# -*- coding: utf-8 -*-
"""源码分析器的统一接口与跨语言共享工具。

ApiEndpoint 的 5 个必需字段来自 spec §4.6；doc / params / category / extra 是
本计划追加的可选字段（带默认值，属兼容性扩展）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from skill_utils.api_path_match import normalize_path

HTTP_METHOD_BY_ANNOTATION = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

_QUERY_WORDS = re.compile(r"\b(get|list|page|query|check|info|detail|select|search)\w*", re.I)
_WRITE_WORDS = re.compile(
    r"\b(save|update|delete|create|add|edit|remove|enable|disable|publish|change|set|upload|import|export)\w*",
    re.I,
)


@dataclass
class ApiEndpoint:
    method: str
    path: str
    handler: str
    file_path: str
    line_no: int
    doc: str = ""
    params: list = field(default_factory=list)
    category: str = ""
    extra: dict = field(default_factory=dict)


class BaseAnalyzer(Protocol):
    language: str

    def detect(self, project_root: Path) -> bool: ...

    def analyze(self, roots: list[Path], url_prefix_map: dict[str, str]) -> list[ApiEndpoint]: ...


def join_url_paths(base: str, sub: str) -> str:
    """拼接类级前缀与方法级路径，并归一化。"""
    if not base:
        return normalize_path(sub)
    if not sub:
        return normalize_path(base)
    return normalize_path(f"{base.rstrip('/')}/{sub.lstrip('/')}")


def apply_prefix_map(path: str, url_prefix_map: dict[str, str]) -> str:
    """把前端代理前缀映射回后端真实前缀。

    例如 {"/dev-api": ""} 会把 /dev-api/wms/list 变成 /wms/list。
    未命中任何前缀时原样返回。

    前缀按**路径段边界**判定：`/dev-api` 能命中 `/dev-api/wms/list` 与 `/dev-api`，
    但**不能**命中 `/dev-api-v2/list`（否则会被误剥成 `/-v2/list`）。
    """
    normalized = normalize_path(path)
    for front_prefix, back_prefix in (url_prefix_map or {}).items():
        front = normalize_path(front_prefix)
        if front == "/" or not (normalized == front or normalized.startswith(front + "/")):
            continue
        rest = normalized[len(front):]
        back = (back_prefix or "").rstrip("/")
        return normalize_path(f"{back}/{rest.lstrip('/')}")
    return normalized


def annotation_args(line: str) -> str:
    """取注解括号里的内容；没有成对括号则返回空串。"""
    start = line.find("(")
    end = line.rfind(")")
    if start == -1 or end == -1 or end <= start:
        return ""
    return line[start + 1:end]


def first_string_arg(args: str) -> str:
    """取第一个字符串字面量，能穿透 { "a", "b" } 这种数组写法。"""
    match = re.search(r'"([^"]*)"', args or "")
    return match.group(1) if match else ""


def classify_endpoint(method: str, handler: str, path: str, params: list) -> str:
    """按方法名/路径/参数来源给接口分类，用于草稿里的场景分组。"""
    if any((p or {}).get("kind") == "HttpServletRequest" for p in params or []):
        return "特殊参数接口"
    lowered = f"{handler} {path}".lower()
    if "upload" in lowered or "import" in lowered:
        return "特殊参数接口"
    if method.upper() == "GET" or _QUERY_WORDS.search(handler or ""):
        return "查询/初始化接口"
    if _WRITE_WORDS.search(handler or ""):
        return "写入/状态变更接口"
    return "独立业务接口"
