import json
from pathlib import Path

import pytest

from skill_utils.config_loader import ConfigError, load_config


def write_config(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_config_requires_project_root(tmp_path):
    config_path = write_config(tmp_path / "config.json", {"framework": "pytest_requests"})

    with pytest.raises(ConfigError) as exc:
        load_config(str(config_path))

    assert "project_root" in str(exc.value)


def test_load_config_resolves_project_relative_paths(tmp_path):
    project_root = tmp_path / "demo_project"
    api_dir = project_root / "tests" / "api"
    case_dir = project_root / "tests" / "cases"
    api_dir.mkdir(parents=True)
    case_dir.mkdir(parents=True)
    config_path = write_config(
        tmp_path / "config.json",
        {
            "framework": "pytest_requests",
            "project_root": str(project_root),
            "paths": {
                "api_method_dirs": ["tests/api"],
                "test_case_dirs": ["tests/cases"],
                "pytest_workdir": "tests",
                "runtime_temp_dir": "tmp/api_skill",
            },
            "api_index": {
                "db_path": "tools/page_api_index.sqlite3",
                "scan_dirs": ["tests/api"],
                "extract_rules_path": "tools/api_extract_rules.json",
            },
            "pytest": {"pythonpath": ".", "command_template": "pytest {target} -v --tb=short"},
        },
    )

    config = load_config(str(config_path))

    assert config.project_root == project_root.resolve()
    assert config.api_method_dirs == [api_dir.resolve()]
    assert config.test_case_dirs == [case_dir.resolve()]
    assert config.pytest_workdir == (project_root / "tests").resolve()
    assert config.runtime_temp_dir == (project_root / "tmp" / "api_skill").resolve()
    assert config.api_scan_dirs == [api_dir.resolve()]
    # Ruling 1：索引与规则文件相对 project_root，而非 skill 自身
    assert config.api_index_db_path == (project_root / "tools" / "page_api_index.sqlite3").resolve()
    assert config.extract_rules_path == (project_root / "tools" / "api_extract_rules.json").resolve()


def test_load_config_rejects_missing_scan_dir(tmp_path):
    project_root = tmp_path / "demo_project"
    project_root.mkdir()
    config_path = write_config(
        tmp_path / "config.json",
        {
            "project_root": str(project_root),
            "api_index": {"scan_dirs": ["missing/api"]},
        },
    )

    with pytest.raises(ConfigError) as exc:
        load_config(str(config_path))

    assert "api_index.scan_dirs" in str(exc.value)


def test_load_config_rejects_invalid_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(ConfigError) as exc:
        load_config(str(config_path))

    assert "config.json" in str(exc.value)


def test_load_config_rejects_missing_config_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(str(tmp_path / "nope.json"))


def test_load_config_rejects_nonexistent_project_root(tmp_path):
    config_path = write_config(
        tmp_path / "config.json",
        {"project_root": str(tmp_path / "ghost")},
    )

    with pytest.raises(ConfigError) as exc:
        load_config(str(config_path))

    assert "project_root" in str(exc.value)


def test_load_config_supports_chinese_and_space_in_project_root(tmp_path):
    project_root = tmp_path / "我的 项目"
    api_dir = project_root / "接口层"
    api_dir.mkdir(parents=True)
    config_path = write_config(
        tmp_path / "config.json",
        {
            "project_root": str(project_root),
            "paths": {"api_method_dirs": ["接口层"]},
            "api_index": {"scan_dirs": ["接口层"]},
        },
    )

    config = load_config(str(config_path))

    assert config.project_root == project_root.resolve()
    assert config.api_scan_dirs == [api_dir.resolve()]


def test_defaults_are_applied(tmp_path):
    project_root = tmp_path / "p"
    api_dir = project_root / "api"
    api_dir.mkdir(parents=True)
    config_path = write_config(
        tmp_path / "config.json",
        {"project_root": str(project_root), "api_index": {"scan_dirs": ["api"]}},
    )

    config = load_config(str(config_path))

    assert config.framework == "pytest_requests"
    assert config.pytest_workdir == project_root.resolve()
    assert config.pytest_pythonpath == "."
    assert config.pytest_command_template == "pytest {target} -v --tb=short"
    assert config.runtime_temp_dir == (project_root / ".api-autotest" / "tmp").resolve()
    assert config.api_index_db_path == (project_root / ".api-autotest" / "api_index.sqlite3").resolve()
    assert config.extract_rules_path == (project_root / ".api-autotest" / "extract_rules.json").resolve()
