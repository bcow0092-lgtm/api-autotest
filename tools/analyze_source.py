# -*- coding: utf-8 -*-
"""调度源码分析器，产出待测接口清单草稿（草稿门禁的输入）。

用法：
    python tools/analyze_source.py                      # 按 config.source_analysis 跑
    python tools/analyze_source.py --language java      # 覆盖语言
    python tools/analyze_source.py --dry-run            # 只报数，不写草稿

草稿写到 config.paths.runtime_temp_dir/source_analysis_result.md。
**草稿只是候选清单，必须等用户勾选后才能写用例。**
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from analyzers.java_spring import JavaSpringAnalyzer  # noqa: E402
from analyzers.node_web import NodeWebAnalyzer  # noqa: E402
from analyzers.python_web import PythonWebAnalyzer  # noqa: E402
from skill_utils.api_index_db import list_records  # noqa: E402
from skill_utils.api_path_match import api_path_matches  # noqa: E402
from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.console_io import configure_stdio  # noqa: E402
from skill_utils.text_io import write_text_utf8  # noqa: E402

DRAFT_NAME = "source_analysis_result.md"
AUTO = "auto"


def get_analyzers() -> list:
    return [JavaSpringAnalyzer(), PythonWebAnalyzer(), NodeWebAnalyzer()]


def pick_analyzer(language: str, project_root: Path):
    analyzers = get_analyzers()
    if language and language != AUTO:
        for analyzer in analyzers:
            if analyzer.language == language:
                return analyzer
        return None
    for analyzer in analyzers:
        if analyzer.detect(Path(project_root)):
            return analyzer
    return None


def cross_check(endpoints: list, index_records: list[dict]) -> list[dict]:
    """把分析出的接口与索引比对，标注哪些已实现、哪些有相似参考。"""
    result = []
    for endpoint in endpoints:
        impls = [
            record
            for record in index_records
            if (record.get("method") or "").upper() == endpoint.method.upper()
            and api_path_matches(record.get("api_url") or "", endpoint.path)
        ]
        tail = endpoint.path.rstrip("/").rsplit("/", 1)[-1].lower()
        similar = [
            record
            for record in index_records
            if tail
            and tail in " ".join(
                str(record.get(key) or "") for key in ("api_url", "api_name", "file")
            ).lower()
        ][:3]
        result.append({"endpoint": endpoint, "impls": impls, "similar": similar})
    return result


def render_draft(cross_checked: list[dict], meta: dict) -> str:
    uncovered = [item for item in cross_checked if not item["impls"]]
    covered = [item for item in cross_checked if item["impls"]]

    lines = [
        "# source_analysis_result（源码分析草稿）",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 分析语言：{meta.get('source', '')}",
        f"- 扫描根：{', '.join(meta.get('roots') or []) or '（未配置）'}",
        f"- 索引来源：`{meta.get('index_path', '')}`",
        f"- 提取接口：{len(cross_checked)} 个；未覆盖候选：{len(uncovered)} 个；已覆盖：{len(covered)} 个",
        "",
        "## 使用说明",
        "",
        "1. 这是**候选清单**，不是待办列表。请勾选你真正想写成用例的接口，再让 AI 继续。",
        "2. `[x]` 只是默认建议；`[ ]` 表示默认不选。改完保存并告诉 AI「已勾选」。",
        "3. 是否已覆盖以索引的 `(pure_path, method)` 为准；索引为空时全部算新。",
        "",
        "## 一、未覆盖接口候选（默认勾选）",
        "",
    ]
    if not uncovered:
        lines.append("_无_")
    for index, item in enumerate(uncovered, 1):
        lines.extend(_render_item(item, index, checked=True))
    lines.append("")

    lines.append("## 二、已覆盖接口（默认不勾选）")
    lines.append("")
    if not covered:
        lines.append("_无_")
    for index, item in enumerate(covered, 1):
        lines.extend(_render_item(item, index, checked=False))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_勾选完成后，告诉 AI「已勾选」即可继续编写用例。_")
    return "\n".join(lines)


def _render_item(item: dict, index: int, checked: bool) -> list[str]:
    endpoint = item["endpoint"]
    mark = "x" if checked else " "
    title = endpoint.doc or endpoint.handler or "（无描述）"
    lines = [
        f"- [{mark}] **{index}. {endpoint.method} `{endpoint.path}`** {title}",
        f"  - 位置：`{endpoint.file_path}` L{endpoint.line_no}",
        f"  - 分类：{endpoint.category or '未分类'}",
    ]
    if endpoint.params:
        rendered = "；".join(
            f"{p.get('kind', '')} {p.get('name', '')}:{p.get('type', '')}"
            for p in endpoint.params
        )
        lines.append(f"  - 参数：{rendered}")
    if item["impls"]:
        for impl in item["impls"][:3]:
            lines.append(f"  - 已实现：`{impl.get('file')}` → `{impl.get('api_name')}` (line {impl.get('line')})")
    elif item["similar"]:
        lines.append("  - 相似参考候选：")
        for similar in item["similar"]:
            lines.append(f"    - `{similar.get('file')}` → `{similar.get('api_name')}`")
    return lines


def analyze_source(config, *, language: str | None = None, out_path=None, dry_run: bool = False) -> dict:
    settings = config.source_analysis or {}
    chosen_language = language or settings.get("language") or AUTO
    analyzer = pick_analyzer(chosen_language, config.project_root)
    if analyzer is None:
        raise ValueError(
            f"没有可用的分析器（language={chosen_language!r}）；"
            f"可选：java / python / node / auto，或检查 source_analysis.roots"
        )

    raw_roots = settings.get("roots") or ["."]
    roots = [
        (config.project_root / root).resolve()
        if not Path(root).is_absolute()
        else Path(root)
        for root in raw_roots
    ]
    endpoints = analyzer.analyze(roots, settings.get("url_prefix_map") or {})

    index_records = list_records(config.api_index_db_path)
    cross_checked = cross_check(endpoints, index_records)

    draft_path = None
    if not dry_run:
        draft_path = Path(out_path) if out_path else (config.runtime_temp_dir / DRAFT_NAME)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(
            draft_path,
            render_draft(
                cross_checked,
                {
                    "source": analyzer.language,
                    "roots": [str(root) for root in roots],
                    "index_path": str(config.api_index_db_path),
                },
            )
            + "\n",
        )

    return {
        "analyzer": analyzer.language,
        "endpoints": len(endpoints),
        "uncovered": sum(1 for item in cross_checked if not item["impls"]),
        "draft_path": str(draft_path) if draft_path else None,
    }


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="调度源码分析器并产出待测接口清单草稿")
    parser.add_argument("--config", default=None)
    parser.add_argument("--language", default=None, help="java / python / node / auto")
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true", help="只报数，不写草稿")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        result = analyze_source(
            config, language=args.language, out_path=args.out, dry_run=args.dry_run
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"[analyze_source] analyzer={result['analyzer']} endpoints={result['endpoints']} "
        f"uncovered={result['uncovered']} draft={result['draft_path'] or '(dry-run)'}"
    )
    if result["endpoints"] == 0:
        print(
            "WARN: 未提取到任何接口。请检查 source_analysis.roots 是否指向真正的后端源码目录。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
