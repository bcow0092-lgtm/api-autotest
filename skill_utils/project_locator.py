# -*- coding: utf-8 -*-
"""从工作目录向上定位项目的 .api-autotest/config.json。

用户级 skill 不能靠自身安装位置推导项目根（skill 在 ~/.claude/skills/ 下，
往上三层毫无意义），改为让项目自己声明：项目根放一个 .api-autotest/ 目录。
"""

from __future__ import annotations

from pathlib import Path

CONFIG_DIR_NAME = ".api-autotest"
CONFIG_FILE_NAME = "config.json"

SKILL_ROOT = Path(__file__).resolve().parents[1]
_INIT_PROJECT_PATH = SKILL_ROOT / "tools" / "init_project.py"


def find_config(start_dir: str | Path) -> Path | None:
    """从 start_dir 起逐级向上查找配置文件，返回绝对路径；找不到返回 None。"""
    current = Path(start_dir).resolve()
    for candidate_dir in (current, *current.parents):
        candidate = candidate_dir / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_project_root(start_dir: str | Path) -> Path | None:
    """返回包含 .api-autotest/ 的目录；找不到返回 None。"""
    config_path = find_config(start_dir)
    return config_path.parent.parent if config_path else None


def missing_config_guidance(start_dir: str | Path) -> str:
    """找不到配置时给人看的指引（负向验收要求：给指引，不崩栈）。"""
    where = Path(start_dir).resolve()
    return (
        f"未在 {where} 及其任何上级目录找到 "
        f"{CONFIG_DIR_NAME}/{CONFIG_FILE_NAME}。\n"
        f"这说明当前项目还没有接入 api-autotest。请先运行接入引导：\n\n"
        f"    python \"{_INIT_PROJECT_PATH}\"\n\n"
        f"它会探测项目结构、询问被测服务地址，并生成 {CONFIG_DIR_NAME}/{CONFIG_FILE_NAME}。"
    )
