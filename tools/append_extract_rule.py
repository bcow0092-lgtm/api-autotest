# -*- coding: utf-8 -*-
"""追加接口提取规则，并按新规则重新扫描（preview / apply 两段语义）。

遇到扫描器认不出的 URL 写法时，用它教一次，以后永久认得。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.api_index_db import upsert_many  # noqa: E402
from skill_utils.text_io import read_text_utf8, write_text_utf8  # noqa: E402
from tools.scan_api_methods import _compile_rule, _scan_all  # noqa: E402

RULE_KEYS = ("url_extract_rules", "method_extract_rules")


def append_extract_rule(
    *,
    repo_root: str,
    scan_dirs: list[str],
    db_path: str,
    rules_path: str,
    rule_update: dict,
    apply: bool = False,
) -> dict:
    """合并新规则并按新规则扫描。

    apply=False 时只预览（不写规则文件、不写库）；apply=True 时落盘并增量入库。
    """
    if apply:
        _ensure_rules_file(rules_path)

    existing = read_text_utf8(rules_path) if Path(rules_path).is_file() else "{}"
    merged = _merge_rule_files(existing, rule_update)

    if apply:
        write_text_utf8(rules_path, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")

    url_rules, method_rules = _rules_from_data(merged)
    records, _ = _scan_all(repo_root, scan_dirs, url_rules=url_rules, method_rules=method_rules)

    if not apply:
        return {"applied": False, "new_records": len(records), "records": records}

    inserted = upsert_many(db_path, records)
    return {
        "applied": True,
        "inserted": inserted,
        "new_records": len(records),
        "records": records,
    }


def _ensure_rules_file(rules_path: str) -> str:
    path = Path(rules_path)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(path, json.dumps({k: [] for k in RULE_KEYS}, ensure_ascii=False) + "\n")
    return rules_path


def _merge_rule_files(existing_text: str, rule_update: dict) -> dict:
    data = json.loads(existing_text or "{}") or {}
    for key in RULE_KEYS:
        current = list(data.get(key) or [])
        seen = {r.get("pattern") for r in current}
        for rule in rule_update.get(key) or []:
            if rule.get("pattern") in seen:
                continue
            seen.add(rule.get("pattern"))
            current.append(dict(rule))
        data[key] = current
    return data


def _rules_from_data(data: dict) -> tuple[list, list]:
    return (
        [_compile_rule(r) for r in data.get("url_extract_rules") or []],
        [_compile_rule(r) for r in data.get("method_extract_rules") or []],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="追加接口提取规则并按新规则重扫")
    parser.add_argument("--config", required=True)
    parser.add_argument("--rule", required=True, help="规则 JSON 文件（含 url_extract_rules / method_extract_rules）")
    parser.add_argument("--apply", action="store_true", help="确认写入；缺省为仅预览")
    args = parser.parse_args(argv)

    from skill_utils.config_loader import ConfigError, load_config

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    rule_update = json.loads(read_text_utf8(args.rule))
    result = append_extract_rule(
        repo_root=str(config.project_root),
        scan_dirs=[str(d) for d in config.api_scan_dirs],
        db_path=str(config.api_index_db_path),
        rules_path=str(config.extract_rules_path),
        rule_update=rule_update,
        apply=args.apply,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, ensure_ascii=False))
    for record in result["records"]:
        print(f"  - {record['http_method']:6} {record['api_url']}  ({record['file']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
