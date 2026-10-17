# -*- coding: utf-8 -*-
"""把抓包 JSONL 与接口索引比对，生成 capture_selection.md 勾选草稿。

用法：
    python tools/match_captures.py                     # 用配置里的路径
    python tools/match_captures.py --jsonl <路径>

产物：config.paths.runtime_temp_dir/capture_selection.md
**草稿必须等用户勾选后才能写用例（草稿门禁）。**
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.api_index_db import list_records  # noqa: E402
from skill_utils.api_path_match import api_path_matches, to_pure_path  # noqa: E402
from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.console_io import configure_stdio  # noqa: E402
from skill_utils.text_io import read_text_utf8, write_text_utf8  # noqa: E402

DEFAULT_JSONL_NAME = "latest.jsonl"
DEFAULT_SELECTION_NAME = "capture_selection.md"


def load_jsonl(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.is_file():
        return []
    records = []
    for line in read_text_utf8(target).splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return records


def dedup_by_method_path(records: list[dict]) -> list[dict]:
    """同一 (method, pure_path) 只保留最后一条（含响应）。"""
    bucket: OrderedDict = OrderedDict()
    for record in records:
        bucket[(record.get("method", ""), record.get("pure_path", ""))] = record
    return list(bucket.values())


def bucket_records(records: list[dict], index_records: list[dict]) -> dict:
    """分四类：新接口 / 已实现 / 特殊响应 / 登录接口。"""
    buckets = {"new": [], "existing": [], "special": [], "login_ignored": []}
    for record in records:
        if record.get("is_login"):
            buckets["login_ignored"].append(record)
            continue
        if record.get("body_skipped"):
            buckets["special"].append(record)
            continue
        method = (record.get("method") or "").upper()
        pure_path = record.get("pure_path") or ""
        # 抓到的路径是**真实请求**、动态段是字面量（/wms/checkOrder/123），索引里的
        # pure_path 是归一化后的（/wms/checkOrder/{param}）。必须拿索引的 pure_path 当
        # pattern（api_path_matches 只替换 pattern 侧的 {...}），并把抓包路径也归一化，
        # 否则两侧字面量 ID 不同就永远配不上——会把已实现的接口重复报成"新接口"。
        matched = [
            item
            for item in index_records
            if (item.get("method") or "").upper() == method
            and api_path_matches(
                item.get("pure_path") or item.get("api_url") or "",
                to_pure_path(pure_path),
            )
        ]
        record["_impls"] = matched
        buckets["existing" if matched else "new"].append(record)
    return buckets


def render_selection(buckets: dict, meta: dict) -> str:
    lines = [
        "# capture_selection（抓包选择草稿）",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 抓包数据：`{meta.get('jsonl', '')}`",
        f"- 索引来源：`{meta.get('index', '')}`",
        f"- 抓包条目：{meta.get('count', 0)} 条（已按 method+path 去重）",
        "",
        "## 使用说明",
        "",
        "1. 这是**草稿**，请勾选你希望写进用例的接口，再让 AI 继续。",
        "2. `[x]` 默认勾选（通常是新接口），`[ ]` 默认不勾。",
        "3. 登录/登出接口与二进制响应接口已单独分区，默认不选。",
        "",
        "## 一、新接口（推荐勾选）",
        "",
    ]
    lines.extend(_render_bucket(buckets["new"], checked=True))
    lines.append("")
    lines.append("## 二、已实现接口（如需重跑请手动勾选）")
    lines.append("")
    lines.extend(_render_bucket(buckets["existing"], checked=False, show_impls=True))
    lines.append("")
    lines.append("## 三、特殊处理接口（二进制/文件响应，请手动处理）")
    lines.append("")
    if not buckets["special"]:
        lines.append("_无_")
    for index, record in enumerate(buckets["special"], 1):
        lines.append(
            f"- [ ] **{index}. {record.get('method', '?')} `{record.get('pure_path', '?')}`** ⚠️ {record.get('skip_reason', '')}"
        )
        lines.append(f"  - Content-Type：{record.get('resp_content_type', '')}")
    lines.append("")
    lines.append("## 已自动忽略的登录/登出接口")
    lines.append("")
    if not buckets["login_ignored"]:
        lines.append("_无_")
    for record in buckets["login_ignored"]:
        lines.append(f"- ~~{record.get('method', '?')} `{record.get('pure_path', '?')}`~~")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_勾选完成后，告诉 AI「已勾选」即可继续。_")
    return "\n".join(lines)


def _render_bucket(records: list[dict], checked: bool, show_impls: bool = False) -> list[str]:
    if not records:
        return ["_无_"]
    mark = "x" if checked else " "
    lines = []
    for index, record in enumerate(records, 1):
        lines.append(
            f"- [{mark}] **{index}. {record.get('method', '?')} `{record.get('pure_path', '?')}`**"
        )
        lines.append(f"  - 状态码：{record.get('status')}")
        lines.append(f"  - 完整 URL：`{record.get('url', '')}`")
        request_body = record.get("req_body")
        if request_body:
            excerpt = request_body if len(request_body) <= 200 else request_body[:200] + "..."
            lines.append(f"  - 请求体（节选）：`{excerpt}`")
        if show_impls:
            for impl in (record.get("_impls") or [])[:3]:
                lines.append(
                    f"  - 已实现：`{impl.get('file')}` → `{impl.get('api_name')}` (line {impl.get('line')})"
                )
    return lines


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="抓包结果与索引比对，生成勾选草稿")
    parser.add_argument("--config", default=None)
    parser.add_argument("--jsonl", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    jsonl_path = Path(args.jsonl) if args.jsonl else (config.runtime_temp_dir / DEFAULT_JSONL_NAME)
    out_path = Path(args.out) if args.out else (config.runtime_temp_dir / DEFAULT_SELECTION_NAME)

    records = dedup_by_method_path(load_jsonl(jsonl_path))
    if not records:
        print(f"WARN: 抓包数据为空 → {jsonl_path}", file=sys.stderr)

    index_records = list_records(config.api_index_db_path)
    if not index_records:
        print("WARN: 接口索引为空，本次将把所有抓到的接口都当作新接口。", file=sys.stderr)

    buckets = bucket_records(records, index_records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(
        out_path,
        render_selection(
            buckets,
            {
                "jsonl": str(jsonl_path),
                "index": str(config.api_index_db_path),
                "count": len(records),
            },
        )
        + "\n",
    )

    print(
        f"[match_captures] records={len(records)} new={len(buckets['new'])} "
        f"existing={len(buckets['existing'])} special={len(buckets['special'])} "
        f"login={len(buckets['login_ignored'])} → {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
