# -*- coding: utf-8 -*-
"""预检：索引是不是够新。

主流程第 0 步用它。**只读不写**——过期只提示，不自动重扫（重扫是主流程的事，
预检必须够快）。判定依据是索引记录的 last_seen。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.api_index_db import list_records  # noqa: E402
from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.console_io import configure_stdio  # noqa: E402

MAX_AGE_DAYS = 7
# 提示语里要给出**可直接执行**的命令：skill 装在用户级目录，相对路径在用户的项目里
# 根本不存在，写 `<skill>` 这种占位符等于给了一条拷不动的命令（第一份计划的 Task 4 修过同类问题）
_SCAN_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "scan_api_methods.py"
SCAN_COMMAND = f'python "{_SCAN_SCRIPT}"'


def index_age_days(records: list[dict], today: date | None = None) -> int | None:
    """索引最近的 last_seen 距今天数；索引为空或日期都解析不了时返回 None。"""
    if not records:
        return None
    today = today or date.today()
    parsed = []
    for record in records:
        raw = (record.get("last_seen") or "").strip()
        if not raw:
            continue
        try:
            parsed.append(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            continue
    if not parsed:
        return None
    return (today - max(parsed)).days


def check_freshness(config, max_days: int = MAX_AGE_DAYS) -> dict:
    db_path = Path(config.api_index_db_path)
    if not db_path.is_file():
        # 索引库还不存在：直接判定为空。**不要**去调 list_records——它会顺带把目录和空库建出来，
        # 而本工具的契约是"只读不写"，且主流程第 0 步每次会话都会跑它。
        return {
            "status": "empty",
            "age_days": None,
            "message": f"接口索引还是空的，建议先跑一次 {SCAN_COMMAND} 建立索引。",
        }

    records = list_records(db_path)
    if not records:
        return {
            "status": "empty",
            "age_days": None,
            "message": f"接口索引还是空的，建议先跑一次 {SCAN_COMMAND} 建立索引。",
        }

    age = index_age_days(records)
    if age is None or age <= max_days:
        return {
            "status": "fresh",
            "age_days": age,
            "message": f"索引较新（最近更新 {age if age is not None else '未知'} 天前），可以直接开始工作。",
        }

    return {
        "status": "stale",
        "age_days": age,
        "message": (
            f"索引已经 {age} 天没更新了，建议先跑一次 {SCAN_COMMAND} 刷新，"
            f"否则查重可能漏掉最近新增的接口。"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="预检：索引时效")
    parser.add_argument("--config", default=None)
    parser.add_argument("--max-days", type=int, default=MAX_AGE_DAYS)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = check_freshness(config, max_days=args.max_days)
    print(f"[{result['status']}] {result['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
