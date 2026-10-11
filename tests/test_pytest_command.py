import json

from skill_utils.pytest_command import build_pytest_command


def _write_config(tmp_path):
    project = tmp_path / "project"
    workdir = project / "tests"
    api_dir = project / "api"
    workdir.mkdir(parents=True)
    api_dir.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["api"], "pytest_workdir": "tests"},
                "api_index": {"scan_dirs": ["api"]},
                "pytest": {
                    "pythonpath": ".;../common",
                    "command_template": "pytest {target} -q --tb=short",
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path, workdir


def test_build_pytest_command_from_config(tmp_path):
    config_path, workdir = _write_config(tmp_path)

    command = build_pytest_command(
        target="cases/test_user.py::TestUser::test_create",
        config_path=str(config_path),
        shell="bash",
    )

    assert str(workdir.resolve()) in command
    assert 'PYTHONPATH=".;../common"' in command
    assert "pytest cases/test_user.py::TestUser::test_create -q --tb=short" in command


def test_build_pytest_command_for_powershell(tmp_path):
    config_path, workdir = _write_config(tmp_path)

    command = build_pytest_command(
        target="cases/test_user.py::TestUser::test_create",
        config_path=str(config_path),
        shell="powershell",
    )

    assert f'Set-Location -LiteralPath "{workdir.resolve()}"' in command
    assert '$env:PYTHONPATH=".;../common"' in command
    assert "pytest cases/test_user.py::TestUser::test_create -q --tb=short" in command


def test_unknown_shell_raises(tmp_path):
    config_path, _ = _write_config(tmp_path)
    try:
        build_pytest_command(target="x", config_path=str(config_path), shell="fish")
    except ValueError as exc:
        assert "fish" in str(exc)
    else:
        raise AssertionError("未知 shell 应当抛 ValueError")
