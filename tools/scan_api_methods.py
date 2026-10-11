# -*- coding: utf-8 -*-
"""扫描接口方法层源码，提取已覆盖接口，写入 SQLite 索引。

用法：
    python tools/scan_api_methods.py                 # 按配置增量更新
    python tools/scan_api_methods.py --full          # 全量重建（清空后重写）
    python tools/scan_api_methods.py --dry-run       # 只报条数，不写库
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.api_index_db import replace_index, upsert_many  # noqa: E402
from skill_utils.api_path_match import normalize_path, to_pure_path  # noqa: E402
from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.text_io import read_text_utf8  # noqa: E402

# ---- 内置提取规则 ----------------------------------------------------------

DEFAULT_URL_RULES: list[dict] = [
    {
        # (?m) 必需：规则作用在"函数块"文本上，赋值语句很少出现在块首
        "name": "url_assignment",
        "pattern": r"(?m)^[ \t]*(?:url|url_path|api_url|path)\s*=\s*f?['\"]([^'\"]+)['\"]",
        "group": 1,
    },
    {
        "name": "requests_inline_url",
        "pattern": r"requests\.(?:get|post|put|delete|patch|head|options)\s*\(\s*f?['\"]([^'\"]+)['\"]",
        "group": 1,
    },
]

DEFAULT_METHOD_RULES: list[dict] = [
    {"name": "requests_verb", "pattern": r"requests\.(get|post|put|delete|patch|head|options)\s*\(", "group": 1},
    {"name": "requests_request", "pattern": r"requests\.request\s*\(\s*['\"]([A-Za-z]+)['\"]", "group": 1},
    {"name": "client_request", "pattern": r"\.client\.request\s*\(\s*['\"]([A-Za-z]+)['\"]", "group": 1},
    # 会话式调用：接口层常把登录好的 requests.Session 作为参数传入并调用 session.post(...)，
    # 这是文档推荐的写法，必须能被识别，否则新接口会被静默漏扫（不报错，只在一条都扫不到时才 WARN）。
    # 放在 client_request 之后、self_verb 之前：self.get(...) 仍由 self_verb 命中；
    # 而 self.session.post(...) 里 self. 后面跟的是 session（非动词），self_verb 本就匹配不到。
    {"name": "session_verb", "pattern": r"(?:self\.)?(?:session|client|http|api)\.(get|post|put|delete|patch|head|options)\s*\(", "group": 1},
    {"name": "self_verb", "pattern": r"self\.(get|post|put|delete|patch|head|options)\s*\(", "group": 1},
]

_DEF_RE = re.compile(r"^(?P<indent>[ \t]*)(?:async\s+)?def\s+(?P<name>\w+)\s*\(", re.MULTILINE)
_DOCSTRING_RE = re.compile(r'(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.DOTALL)
_AUTHOR_RE = re.compile(r"#\s*Author:\s*(.+)")
_CREATE_DATE_RE = re.compile(r"#\s*Create\s*Date:\s*(.+)")


def _load_extract_rules(rules_path: str) -> tuple[list, list]:
    """读取提取规则，并与内置规则合并（同 pattern 去重）。"""
    url_rules = [dict(r) for r in DEFAULT_URL_RULES]
    method_rules = [dict(r) for r in DEFAULT_METHOD_RULES]

    path = Path(rules_path)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8-sig")) or {}
        url_rules = _merge_rules(url_rules, data.get("url_extract_rules") or [])
        method_rules = _merge_rules(method_rules, data.get("method_extract_rules") or [])

    return [_compile_rule(r) for r in url_rules], [_compile_rule(r) for r in method_rules]


def _merge_rules(base: list[dict], extra: list[dict]) -> list[dict]:
    seen = {r.get("pattern") for r in base}
    merged = list(base)
    for rule in extra:
        if rule.get("pattern") in seen:
            continue
        seen.add(rule.get("pattern"))
        merged.append(dict(rule))
    return merged


def _compile_rule(rule: dict) -> dict:
    compiled = dict(rule)
    pattern = compiled["pattern"]
    compiled["pattern"] = re.compile(pattern) if isinstance(pattern, str) else pattern
    compiled.setdefault("group", 1)
    return compiled


def _as_rule(rule) -> tuple[re.Pattern, int]:
    """规则既可能是 dict（含 pattern/group），也可能是裸正则。"""
    if isinstance(rule, dict):
        return rule["pattern"], rule.get("group", 1)
    return rule, 1


def _extract_urls_from_source(source: str, url_rules: list) -> list[str]:
    """按规则提取 URL，保持出现顺序并去重（多条规则可能命中同一个 URL）。"""
    urls: list[str] = []
    for rule in url_rules:
        pattern, group = _as_rule(rule)
        for match in pattern.finditer(source):
            try:
                value = match.group(group)
            except IndexError:
                continue
            if value:
                urls.append(value)
    return list(dict.fromkeys(urls))


def _extract_http_method(source: str, method_rules: list) -> str | None:
    for rule in method_rules:
        pattern, group = _as_rule(rule)
        match = pattern.search(source)
        if match:
            try:
                return match.group(group).upper()
            except IndexError:
                continue
    return None


def _parse_file(
    path: str,
    url_rules: list | None = None,
    method_rules: list | None = None,
    repo_root: str | None = None,
) -> list[dict]:
    """解析单个 Python 文件，返回接口记录列表。

    未显式传入规则时使用内置规则（不读配置文件）。
    """
    if url_rules is None:
        url_rules = [_compile_rule(r) for r in DEFAULT_URL_RULES]
    if method_rules is None:
        method_rules = [_compile_rule(r) for r in DEFAULT_METHOD_RULES]

    source = read_text_utf8(path)
    records: list[dict] = []

    for func_name, block, def_line in _iter_blocks(source):
        urls = _extract_urls_from_source(block, url_rules)
        if not urls:
            continue
        method = _extract_http_method(block, method_rules)
        if not method:
            continue
        api_url = normalize_path(urls[0])
        records.append(
            {
                "api_url": api_url,
                "pure_path": to_pure_path(api_url),
                "api_name": func_name,
                "api_desc": _extract_desc(block),
                "author": _first_group(_AUTHOR_RE, block),
                "create_date": _first_group(_CREATE_DATE_RE, block),
                "http_method": method,
                "file": _relative_file(path, repo_root),
                "line": def_line,
            }
        )
    return records


def _iter_blocks(source: str) -> list[tuple[str | None, str, int]]:
    """按 def 缩进切分函数块，返回 [(函数名, 块文本, 起始行号), ...]。"""
    matches = list(_DEF_RE.finditer(source))
    if not matches:
        return [(None, source, 1)]

    blocks: list[tuple[str | None, str, int]] = []
    for index, match in enumerate(matches):
        indent = len(match.group("indent").expandtabs(4))
        end = len(source)
        for later in matches[index + 1:]:
            if len(later.group("indent").expandtabs(4)) <= indent:
                end = later.start()
                break
        line_no = source.count("\n", 0, match.start()) + 1
        blocks.append((match.group("name"), source[match.start():end], line_no))
    return blocks


def _extract_desc(block: str) -> str | None:
    match = _DOCSTRING_RE.search(block)
    if not match:
        return None
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("desc:"):
            return line.split(":", 1)[1].strip()
        if line.startswith(":"):
            continue
        return line
    return None


def _first_group(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _relative_file(path: str, repo_root: str | None) -> str:
    file_path = Path(path)
    if repo_root:
        try:
            return file_path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
        except ValueError:
            pass
    return file_path.as_posix()


def _scan_all(
    repo_root: str,
    scan_dirs: list[str],
    url_rules: list | None = None,
    method_rules: list | None = None,
    on_warn=None,
) -> tuple[list[dict], int]:
    """扫描多个目录下的全部 *.py，返回 (记录列表, 扫描文件数)。

    单个文件读取失败（非 UTF-8 编码 / IO 错误）时**跳过该文件并继续**，不让一个坏文件
    中断整轮扫描。on_warn 为 None 时静默跳过（维持原二元组返回契约）。
    """
    records: list[dict] = []
    scanned = 0
    for scan_dir in scan_dirs:
        for py_file in sorted(Path(scan_dir).rglob("*.py")):
            scanned += 1
            try:
                parsed = _parse_file(
                    str(py_file),
                    url_rules=url_rules,
                    method_rules=method_rules,
                    repo_root=repo_root,
                )
            except (UnicodeDecodeError, OSError) as exc:
                if on_warn is not None:
                    on_warn(f"跳过无法读取的文件 {py_file}: {exc}")
                continue
            records.extend(parsed)
    return records, scanned


def _resolve_scan_roots(config=None) -> tuple[str, list[str]]:
    """从配置解析 (项目根, 扫描目录列表)，均为字符串。"""
    resolved = config or load_config()
    return str(resolved.project_root), [str(d) for d in resolved.api_scan_dirs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描接口方法层并更新索引")
    parser.add_argument("--config", default=None, help="配置文件路径（默认按 CWD 向上探测）")
    parser.add_argument("--full", action="store_true", help="全量重建索引")
    parser.add_argument("--dry-run", action="store_true", help="只报条数，不写库")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    url_rules, method_rules = _load_extract_rules(config.extract_rules_path)
    records, scanned_files = _scan_all(
        str(config.project_root),
        [str(d) for d in config.api_scan_dirs],
        url_rules=url_rules,
        method_rules=method_rules,
        on_warn=lambda msg: print(msg, file=sys.stderr),
    )

    # 优先级#4 的低成本缓解：把“静默的错误索引”变成“响亮的警告”。
    # URL 由无 scheme 的变量拼成时（如 f"{BASE_URL}/api/users/create"），字面量里没有 ://，
    # 整串会被当成路径，pure_path 首段落成 /{param}，永远匹配不到真实端点，且原先静默。
    dynamic_lead = [r for r in records if str(r.get("pure_path") or "").startswith("/{param}")]
    if dynamic_lead:
        print(
            f"WARN: 有 {len(dynamic_lead)} 条记录的路径首段是动态变量（形如 /{{param}}/...），"
            f"可能因为 URL 由变量拼接而未被正确解析；请人工确认这些接口的 URL 写法。",
            file=sys.stderr,
        )

    if args.dry_run:
        print(f"[scan_api_methods] dry-run scanned={scanned_files} records={len(records)}")
        if not records:
            print("WARN: 未扫到任何接口，请检查 api_index.scan_dirs 是否正确。", file=sys.stderr)
        return 0

    if args.full:
        written = replace_index(config.api_index_db_path, records)
        print(f"[scan_api_methods] mode=full scanned={scanned_files} written={written}")
    else:
        inserted = upsert_many(config.api_index_db_path, records)
        print(f"[scan_api_methods] mode=incremental scanned={scanned_files} inserted={inserted}")

    if not records:
        print("WARN: 未扫到任何接口，请检查 api_index.scan_dirs 是否正确。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
