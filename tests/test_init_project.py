import json
from pathlib import Path

from tools.init_project import build_config, detect_project, init_project


def _java_project(tmp_path):
    root = tmp_path / "ruoyi"
    (root / "ruoyi-admin" / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
    (root / "ruoyi-admin" / "src" / "main" / "java" / "com" / "demo" / "UserController.java").write_text(
        "@RestController\npublic class UserController {}\n", encoding="utf-8"
    )
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    return root


def test_detect_java_project(tmp_path):
    root = _java_project(tmp_path)

    facts = detect_project(root)

    assert facts["backend_language"] == "java"
    assert "pom.xml" in facts["markers"]
    assert any("main/java" in r for r in facts["source_roots"])


def test_detect_greenfield_project_reports_no_api_dirs(tmp_path):
    root = tmp_path / "empty_project"
    root.mkdir()

    facts = detect_project(root)

    assert facts["api_dir_candidates"] == []
    assert facts["backend_language"] is None


def test_build_config_shape():
    answers = {
        "baseurl": "http://localhost:8081",
        "api_method_dirs": ["test/API_TEST/api"],
        "test_case_dirs": ["test/API_TEST/cases"],
        "pytest_workdir": "test/API_TEST",
        "runtime_temp_dir": "test/API_TEST/.tmp",
    }

    config = build_config(Path("E:/demo"), answers)

    assert config["project_root"]
    assert config["framework"] == "pytest_requests"
    assert config["paths"]["api_method_dirs"] == ["test/API_TEST/api"]
    assert config["api_index"]["scan_dirs"] == ["test/API_TEST/api"]
    assert config["api_index"]["db_path"] == "test/API_TEST/.index/api_index.sqlite3"
    assert config["pytest"]["command_template"] == "pytest {target} -v --tb=short"
    assert config["capture"]["baseurl"] == "http://localhost:8081"


def test_init_project_writes_config_and_scaffold(tmp_path):
    root = _java_project(tmp_path)
    answers = {
        "baseurl": "http://localhost:8081",
        "api_method_dirs": ["test/API_TEST/api"],
        "test_case_dirs": ["test/API_TEST/cases"],
        "pytest_workdir": "test/API_TEST",
        "runtime_temp_dir": "test/API_TEST/.tmp",
    }

    result = init_project(root, answers)

    config_path = root / ".api-autotest" / "config.json"
    assert config_path.is_file()
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["project_root"] == str(root.resolve())
    assert (root / "test" / "API_TEST" / "api").is_dir()
    assert (root / "test" / "API_TEST" / "conftest.py").is_file()
    assert "TODO" in (root / "test" / "API_TEST" / "conftest.py").read_text(encoding="utf-8")
    assert result["config_path"] == str(config_path)
    assert result["scanned_records"] == 0
    assert any("扫到 0 条" in w for w in result["warnings"])


def test_init_project_dry_run_writes_nothing(tmp_path):
    root = _java_project(tmp_path)
    answers = {
        "baseurl": "http://localhost:8081",
        "api_method_dirs": ["test/API_TEST/api"],
        "test_case_dirs": ["test/API_TEST/cases"],
        "pytest_workdir": "test/API_TEST",
        "runtime_temp_dir": "test/API_TEST/.tmp",
    }

    result = init_project(root, answers, dry_run=True)

    assert not (root / ".api-autotest").exists()
    assert not (root / "test").exists()
    assert result["config_path"] is None


def test_init_project_rejects_missing_baseurl(tmp_path):
    root = _java_project(tmp_path)

    try:
        init_project(root, {"api_method_dirs": ["api"]})
    except ValueError as exc:
        assert "baseurl" in str(exc)
    else:
        raise AssertionError("缺少 baseurl 应当抛 ValueError")


def _answers(baseurl: str) -> dict:
    return {
        "baseurl": baseurl,
        "api_method_dirs": ["test/API_TEST/api"],
        "test_case_dirs": ["test/API_TEST/cases"],
        "pytest_workdir": "test/API_TEST",
        "runtime_temp_dir": "test/API_TEST/.tmp",
    }


def test_init_project_rerun_preserves_hand_edited_config(tmp_path):
    """重跑接入引导不得静默覆盖用户手改过的 config.json。"""
    root = _java_project(tmp_path)
    answers = _answers("http://localhost:8081")
    init_project(root, answers)

    config_path = root / ".api-autotest" / "config.json"
    edited = json.loads(config_path.read_text(encoding="utf-8"))
    edited["capture"]["baseurl"] = "http://edited.example:9999"
    edited["capture"]["include_prefixes"] = ["/custom"]
    config_path.write_text(json.dumps(edited, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = init_project(root, answers)

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after["capture"]["baseurl"] == "http://edited.example:9999"
    assert after["capture"]["include_prefixes"] == ["/custom"]
    assert any("已存在" in w for w in result["warnings"])
    assert result["created_dirs"] == []


def test_init_project_rerun_with_force_overwrites_config(tmp_path):
    """force=True 时按本次答案强制覆盖已存在的 config.json。"""
    root = _java_project(tmp_path)
    answers = _answers("http://localhost:8081")
    init_project(root, answers)

    config_path = root / ".api-autotest" / "config.json"
    edited = json.loads(config_path.read_text(encoding="utf-8"))
    edited["capture"]["baseurl"] = "http://edited.example:9999"
    config_path.write_text(json.dumps(edited, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    init_project(root, answers, force=True)

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after["capture"]["baseurl"] == "http://localhost:8081"
