# -*- coding: utf-8 -*-
"""Java / Spring 源码分析器。

识别 @RestController 类，拼出「类级 @RequestMapping + 方法级 @XxxMapping」的完整路径。
纯正则 + 括号配平，不依赖 javalang 之类的解析库（保持零三方依赖）。
"""

from __future__ import annotations

import re
from pathlib import Path

from analyzers.base import (
    ApiEndpoint,
    HTTP_METHOD_BY_ANNOTATION,
    annotation_args,
    apply_prefix_map,
    classify_endpoint,
    first_string_arg,
    join_url_paths,
)
from skill_utils.text_io import read_text_utf8

_MAPPING_ANNOTATION = re.compile(
    r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\b"
)
_SIGNATURE_LINE = re.compile(r"\bpublic\b")
_SIGNATURE_HEAD = re.compile(r"\bpublic\s+(?P<ret>.+?)\s+(?P<name>\w+)\s*\(")
_JAVADOC = re.compile(r"/\*\*(.*?)\*/", re.S)
_REQUEST_METHOD_ATTR = re.compile(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH)")
_METHOD_ATTR_STRING = re.compile(r'method\s*=\s*"?(GET|POST|PUT|DELETE|PATCH)"?', re.I)
_PARAM_KIND = (
    ("@RequestBody", "RequestBody"),
    ("@RequestParam", "RequestParam"),
    ("HttpServletRequest", "HttpServletRequest"),
)


def parse_controller_file(path: Path, url_prefix_map: dict | None = None) -> list[ApiEndpoint]:
    return _parse(read_text_utf8(path), path.as_posix(), url_prefix_map or {})


def parse_java_source(
    source: str, file_path: str, url_prefix_map: dict | None = None
) -> list[ApiEndpoint]:
    """解析一段 Java 源码。file_path 只用来填 ApiEndpoint.file_path，不读文件。"""
    return _parse(source, file_path, url_prefix_map or {})


def _parse(source: str, file_path: str, url_prefix_map: dict) -> list[ApiEndpoint]:
    lines = source.splitlines()
    class_mapping = _extract_class_mapping(source)
    endpoints: list[ApiEndpoint] = []

    index = 0
    while index < len(lines):
        line = lines[index]
        match = _MAPPING_ANNOTATION.search(line)
        if not match:
            index += 1
            continue

        annotation = match.group(1)
        method = HTTP_METHOD_BY_ANNOTATION.get(annotation) or _request_mapping_method(line)
        if not method:
            index += 1
            continue

        found = _find_signature(lines, index)
        if found is None:
            index += 1
            continue
        signature_index, return_type, handler, raw_params = found

        block_end = _find_block_end(lines, signature_index)
        method_path = first_string_arg(annotation_args(line))
        endpoint_path = apply_prefix_map(join_url_paths(class_mapping, method_path), url_prefix_map)

        params = [_parse_param(item) for item in _split_params(raw_params)]
        endpoints.append(
            ApiEndpoint(
                method=method,
                path=endpoint_path,
                handler=handler,
                file_path=file_path,
                line_no=signature_index + 1,
                doc=_javadoc_of(lines, index),
                params=params,
                category=classify_endpoint(method, handler, endpoint_path, params),
                extra={
                    "class_mapping": class_mapping,
                    "method_mapping": method_path,
                    "return_type": return_type,
                },
            )
        )
        index = block_end + 1

    return endpoints


def _extract_class_mapping(source: str) -> str:
    """取 class 声明之前最后一个 @RequestMapping 的路径。"""
    before_class = source.split(" class ", 1)[0]
    matches = list(re.finditer(r"@RequestMapping\s*\((.*?)\)", before_class, re.S))
    if not matches:
        return ""
    return first_string_arg(matches[-1].group(1))


def _request_mapping_method(line: str) -> str:
    args = annotation_args(line)
    found = _REQUEST_METHOD_ATTR.search(args)
    if found:
        return found.group(1)
    found = _METHOD_ATTR_STRING.search(args)
    return found.group(1).upper() if found else ""


def _parens_balanced(text: str) -> bool:
    return text.count("(") > 0 and text.count("(") == text.count(")")


def _gather_signature(lines: list[str], start: int, max_lines: int = 8) -> str:
    """从 start 行起逐行拼接，直到参数括号配平——方法签名常常跨行。"""
    collected = ""
    for index in range(start, min(start + max_lines, len(lines))):
        collected = f"{collected} {lines[index].strip()}".strip()
        if _parens_balanced(collected):
            break
    return collected


def _split_signature(text: str) -> tuple[str, str, str] | None:
    """把签名拆成 (返回类型, 方法名, 参数字符串)。

    参数按**括号深度配平**截取，这样参数上的注解（如
    `@NotNull(message = "...")`）不会把参数表提前截断。
    """
    match = _SIGNATURE_HEAD.search(text)
    if not match:
        return None
    depth = 1
    index = match.end()
    start = index
    while index < len(text) and depth:
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    if depth != 0:
        return None
    return match.group("ret").strip(), match.group("name"), text[start:index - 1]


def _find_signature(lines: list[str], annotation_index: int):
    """从注解行往下最多找 12 行，定位方法签名。

    返回 (签名起始行号, 返回类型, 方法名, 参数字符串)；找不到返回 None。
    """
    limit = min(annotation_index + 12, len(lines))
    for probe in range(annotation_index + 1, limit):
        if not _SIGNATURE_LINE.search(lines[probe]):
            continue
        split = _split_signature(_gather_signature(lines, probe))
        if split:
            return (probe, *split)
    return None


def _find_block_end(lines: list[str], signature_index: int) -> int:
    """按花括号配平找方法体结束行；没有花括号（如抽象方法）则返回签名行。"""
    depth = 0
    started = False
    for index in range(signature_index, len(lines)):
        line = lines[index]
        depth += line.count("{")
        if "{" in line:
            started = True
        depth -= line.count("}")
        if started and depth <= 0:
            return index
    return signature_index


def _javadoc_of(lines: list[str], annotation_index: int) -> str:
    """向上回溯找**紧贴**注解的 Javadoc，取第一行非空、非 @ 标记的内容。

    先跳过紧邻的其他注解行（@Xxx），此时上一行必须是 Javadoc 的结束行 */；
    否则说明这个方法没有 Javadoc——不能继续往上找，那会把上一条方法的注释吃进来。
    """
    index = annotation_index - 1
    while index >= 0 and lines[index].strip().startswith("@"):
        index -= 1
    if index < 0 or not lines[index].strip().endswith("*/"):
        return ""

    end = index
    while index >= 0 and not lines[index].strip().startswith("/*"):
        index -= 1
    if index < 0:
        return ""

    match = _JAVADOC.search("\n".join(lines[index:end + 1]))
    if not match:
        return ""
    for raw_line in match.group(1).splitlines():
        candidate = raw_line.strip().lstrip("*").strip()
        if candidate and not candidate.startswith("@"):
            return candidate
    return ""


def _split_params(params: str) -> list[str]:
    """按顶层逗号切分参数，忽略泛型尖括号与注解括号里的逗号。"""
    result: list[str] = []
    buffer: list[str] = []
    angle = paren = 0
    for char in params:
        if char == "<":
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        if char == "," and angle == 0 and paren == 0:
            item = "".join(buffer).strip()
            if item:
                result.append(item)
            buffer = []
            continue
        buffer.append(char)
    tail = "".join(buffer).strip()
    if tail:
        result.append(tail)
    return result


def _parse_param(param: str) -> dict:
    clean = " ".join(param.split())
    kind = "普通参数"
    for marker, label in _PARAM_KIND:
        if marker in clean:
            kind = label
            break

    without_annotations = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", clean).strip()
    pieces = without_annotations.split()
    java_name = pieces[-1] if pieces else ""
    java_type = " ".join(pieces[:-1]) if len(pieces) >= 2 else without_annotations

    explicit_name = ""
    name_match = re.search(r"@RequestParam\s*\((.*?)\)", clean)
    if name_match:
        named = re.search(r'(?:value|name)\s*=\s*"([^"]+)"', name_match.group(1))
        explicit_name = named.group(1) if named else first_string_arg(name_match.group(1))

    required = None
    if re.search(r"required\s*=\s*false", clean):
        required = False
    elif "@RequestParam" in clean:
        required = True

    default_match = re.search(r'defaultValue\s*=\s*"([^"]*)"', clean)

    return {
        "kind": kind,
        "name": explicit_name or java_name,
        "type": java_type,
        "required": required,
        "default": default_match.group(1) if default_match else "",
    }


class JavaSpringAnalyzer:
    language = "java"

    def detect(self, project_root: Path) -> bool:
        root = Path(project_root)
        for candidate in root.glob("**/*Controller.java"):
            if "node_modules" not in candidate.parts:
                return True
        for candidate in root.glob("**/*.java"):
            if "node_modules" in candidate.parts or "target" in candidate.parts:
                continue
            if "@RestController" in read_text_utf8(candidate):
                return True
        return False

    def analyze(self, roots: list[Path], url_prefix_map: dict[str, str]) -> list[ApiEndpoint]:
        endpoints: list[ApiEndpoint] = []
        for root in roots:
            for java_file in sorted(Path(root).rglob("*.java")):
                if "target" in java_file.parts or "node_modules" in java_file.parts:
                    continue
                source = read_text_utf8(java_file)
                if "@RestController" not in source and "@Controller" not in source:
                    continue
                endpoints.extend(_parse(source, java_file.name, url_prefix_map or {}))
        return endpoints
