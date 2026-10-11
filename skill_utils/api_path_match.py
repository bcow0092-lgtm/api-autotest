# -*- coding: utf-8 -*-
"""URL 归一化与 `{n}` 通配匹配（多模块共用）。

两组能力：
1. 归一化 —— normalize_path 去 scheme/host/query；to_pure_path 再把动态段换成 {param}，
   用作索引键。
2. 模式匹配 —— api_path_matches 把 pattern 里的 {n} 当作可跨路径段的通配符，全串匹配。
   `{1}` 能吃掉 `foo/` 甚至空串，因此段数不必相等（spec Ruling 10）。
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# 动态段判定：纯数字 / UUID / >=16 位十六进制 / {x} / <x> / :name
_DYNAMIC_SEGMENT = re.compile(
    r"^(?:"
    r"\d+"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{16,}"
    r"|\{[^/}]*\}"
    r"|<[^/]*>"
    r"|:[A-Za-z_]\w*"
    r")$"
)

# 模式中的通配占位符（形如 {1}、{id}、{0}）
_PATTERN_PLACEHOLDER = re.compile(r"\{[^/}]*\}")
_TOKEN = "__API_AUTOTEST_WILDCARD__"


def normalize_path(url_or_path: str) -> str:
    """去掉 scheme/host/query/fragment，返回以 / 开头且无尾斜杠的路径。"""
    raw = (url_or_path or "").strip()
    if "://" in raw:
        raw = urlsplit(raw).path
    else:
        raw = raw.split("?", 1)[0].split("#", 1)[0]
    if not raw.startswith("/"):
        raw = "/" + raw
    raw = re.sub(r"/{2,}", "/", raw)
    return raw.rstrip("/") or "/"


def to_pure_path(url_or_path: str) -> str:
    """归一化，并把动态段统一替换为 {param}。"""
    segments = [s for s in normalize_path(url_or_path).split("/") if s]
    out = ["{param}" if _is_dynamic(seg) else seg for seg in segments]
    return "/" + "/".join(out)


def api_path_matches(pattern: str, actual: str) -> bool:
    """`{n}` 可跨越多个路径段的通配匹配，要求全串一致。"""
    return re.fullmatch(_pattern_to_regex(pattern), normalize_path(actual)) is not None


def _is_dynamic(segment: str) -> bool:
    return _DYNAMIC_SEGMENT.match(segment) is not None


def _pattern_to_regex(pattern: str) -> str:
    tokenized = _PATTERN_PLACEHOLDER.sub(_TOKEN, normalize_path(pattern))
    escaped = re.escape(tokenized)
    return escaped.replace(re.escape(_TOKEN), ".*")
