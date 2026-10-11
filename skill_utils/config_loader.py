# -*- coding: utf-8 -*-
"""配置加载与路径解析（多模块共用）。

schema 见 spec 第 3.1 节。要点：
- project_root 必填；
- 配置里的相对路径一律相对 project_root 解析（Ruling 1）；
- api_index.scan_dirs 中的目录必须存在，否则报错（防止路径配错后静默扫 0 条）。

DEFAULT_CONFIG_PATH 是模块级可变全局，供 load_config() 无参调用时使用。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .project_locator import CONFIG_DIR_NAME, find_config, missing_config_guidance

DEFAULT_FRAMEWORK = "pytest_requests"
DEFAULT_PYTHONPATH = "."
DEFAULT_COMMAND_TEMPLATE = "pytest {target} -v --tb=short"
DEFAULT_DB_NAME = "api_index.sqlite3"
DEFAULT_RULES_NAME = "extract_rules.json"

# 无参 load_config() 时使用的配置文件；测试会 monkeypatch 它
DEFAULT_CONFIG_PATH: Path | None = None


class ConfigError(Exception):
    """配置缺失或不合法。"""


@dataclass(frozen=True)
class ApiTestConfig:
    project_root: Path
    config_path: Path
    framework: str
    api_method_dirs: list[Path] = field(default_factory=list)
    test_case_dirs: list[Path] = field(default_factory=list)
    pytest_workdir: Path | None = None
    runtime_temp_dir: Path | None = None
    api_scan_dirs: list[Path] = field(default_factory=list)
    api_index_db_path: Path | None = None
    extract_rules_path: Path | None = None
    pytest_pythonpath: str = DEFAULT_PYTHONPATH
    pytest_command_template: str = DEFAULT_COMMAND_TEMPLATE
    capture: dict = field(default_factory=dict)
    source_analysis: dict = field(default_factory=dict)


def load_config(config_path: str | Path | None = None) -> ApiTestConfig:
    """读取并校验配置，返回解析后的 ApiTestConfig。"""
    path = Path(config_path) if config_path is not None else _resolve_default_config_path()
    raw = _read_json(path)

    project_root = _resolve_project_root(raw, path)
    paths = raw.get("paths") or {}
    api_index = raw.get("api_index") or {}
    pytest_cfg = raw.get("pytest") or {}

    api_method_dirs = _to_abs_list(paths.get("api_method_dirs") or [], project_root)
    api_scan_dirs = _to_abs_list(
        api_index.get("scan_dirs") or paths.get("api_method_dirs") or [], project_root
    )
    _require_existing_dirs(api_scan_dirs, "api_index.scan_dirs")

    temp_dir_name = paths.get("runtime_temp_dir") or f"{CONFIG_DIR_NAME}/tmp"

    return ApiTestConfig(
        project_root=project_root,
        config_path=path.resolve(),
        framework=raw.get("framework") or DEFAULT_FRAMEWORK,
        api_method_dirs=api_method_dirs,
        test_case_dirs=_to_abs_list(paths.get("test_case_dirs") or [], project_root),
        pytest_workdir=_to_abs(paths.get("pytest_workdir") or ".", project_root),
        runtime_temp_dir=_to_abs(temp_dir_name, project_root),
        api_scan_dirs=api_scan_dirs,
        api_index_db_path=_to_abs(
            api_index.get("db_path") or f"{CONFIG_DIR_NAME}/{DEFAULT_DB_NAME}", project_root
        ),
        extract_rules_path=_to_abs(
            api_index.get("extract_rules_path") or f"{CONFIG_DIR_NAME}/{DEFAULT_RULES_NAME}",
            project_root,
        ),
        pytest_pythonpath=pytest_cfg.get("pythonpath") or DEFAULT_PYTHONPATH,
        pytest_command_template=pytest_cfg.get("command_template") or DEFAULT_COMMAND_TEMPLATE,
        capture=dict(raw.get("capture") or {}),
        source_analysis=dict(raw.get("source_analysis") or {}),
    )


def _resolve_default_config_path() -> Path:
    if DEFAULT_CONFIG_PATH is not None:
        return Path(DEFAULT_CONFIG_PATH)
    found = find_config(Path.cwd())
    if found is None:
        raise ConfigError(
            f"当前目录及其上级都不存在 {CONFIG_DIR_NAME}/config.json。\n"
            + missing_config_guidance(Path.cwd())
        )
    return found


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"配置文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是对象: {path}")
    return data


def _resolve_project_root(raw: dict, config_path: Path) -> Path:
    value = raw.get("project_root")
    if not value:
        raise ConfigError(f"缺少必填字段 project_root: {config_path}")
    root = _to_abs(value, config_path.parent)
    if not root.is_dir():
        raise ConfigError(f"project_root 指向的目录不存在: {root}")
    return root


def _to_abs(value: str, base: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def _to_abs_list(values: list, base: Path) -> list[Path]:
    return [_to_abs(v, base) for v in values]


def _require_existing_dirs(dirs: list[Path], field_name: str) -> None:
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing:
        raise ConfigError(f"{field_name} 中的目录不存在: {', '.join(missing)}")
