import json
import sqlite3
from pathlib import Path

from skill_utils.config_loader import load_config
from skill_utils.pytest_command import build_pytest_command
from tools.init_project import init_project
from tools.scan_api_methods import main as scan_main


def _make_java_project(tmp_path: Path) -> Path:
    root = tmp_path / "ruoyi-like"
    (root / "ruoyi-admin" / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
    (root / "ruoyi-admin" / "src" / "main" / "java" / "com" / "demo" / "UserController.java").write_text(
        "@RestController\npublic class UserController {}\n", encoding="utf-8"
    )
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    return root


def test_init_then_scan_then_build_command(tmp_path):
    root = _make_java_project(tmp_path)

    result = init_project(
        root,
        {
            "baseurl": "http://localhost:8081",
            "api_method_dirs": ["test/API_TEST/api"],
            "test_case_dirs": ["test/API_TEST/cases"],
            "pytest_workdir": "test/API_TEST",
            "runtime_temp_dir": "test/API_TEST/.tmp",
        },
    )
    config_path = Path(result["config_path"])
    assert config_path.is_file()

    # 绿地项目：先扫一次应当 0 条
    assert scan_main(["--config", str(config_path)]) == 0

    # 放进一个接口方法后，再扫应当 1 条
    (root / "test" / "API_TEST" / "api" / "user_api.py").write_text(
        '''
import requests


class UserApi:
    def create_user(self):
        """创建用户"""
        url = "https://example.com/api/users/create"
        return requests.post(url, json={})
'''.strip(),
        encoding="utf-8",
    )
    assert scan_main(["--config", str(config_path)]) == 0

    config = load_config(config_path)
    with sqlite3.connect(config.api_index_db_path) as conn:
        rows = conn.execute("SELECT api_url, method FROM api_methods").fetchall()
    assert rows == [("/api/users/create", "POST")]

    command = build_pytest_command(
        target="cases/test_user.py::TestUser::test_create", config=config, shell="bash"
    )
    assert "pytest cases/test_user.py::TestUser::test_create" in command
    assert str(config.pytest_workdir) in command


def test_scan_full_rebuild_is_idempotent(tmp_path):
    root = _make_java_project(tmp_path)
    result = init_project(
        root,
        {
            "baseurl": "http://localhost:8081",
            "api_method_dirs": ["test/API_TEST/api"],
            "test_case_dirs": ["test/API_TEST/cases"],
            "pytest_workdir": "test/API_TEST",
            "runtime_temp_dir": "test/API_TEST/.tmp",
        },
    )
    config_path = Path(result["config_path"])
    (root / "test" / "API_TEST" / "api" / "user_api.py").write_text(
        '''
import requests


class UserApi:
    def create_user(self):
        """创建用户"""
        url = "https://example.com/api/users/create"
        return requests.post(url, json={})
'''.strip(),
        encoding="utf-8",
    )

    assert scan_main(["--config", str(config_path), "--full"]) == 0
    assert scan_main(["--config", str(config_path), "--full"]) == 0

    config = load_config(config_path)
    with sqlite3.connect(config.api_index_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM api_methods").fetchone()[0]
    assert count == 1


def test_config_example_matches_schema():
    example = json.loads((Path(__file__).resolve().parents[1] / "config.example.json").read_text(encoding="utf-8"))
    assert "project_root" in example
    assert set(example["paths"]) >= {"api_method_dirs", "test_case_dirs", "pytest_workdir", "runtime_temp_dir"}
    assert set(example["api_index"]) >= {"db_path", "scan_dirs", "extract_rules_path"}
    assert set(example["pytest"]) >= {"pythonpath", "command_template"}
    assert set(example["capture"]) >= {"listen_port", "baseurl", "include_prefixes", "exclude_prefixes", "login_path_hints", "session_cookie_names"}
