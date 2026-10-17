"""用假 mitmdump + 临时项目配置，真实执行三个批处理，验证端口链路闭合。

START 走 `python launch.py start`，launch.py 从 `config.capture.listen_port`
读端口后去调 PATH 上的 mitmdump；我们在假项目里写 config、在 PATH 最前放一个
只会 echo 的假 mitmdump，就能断言它收到的确实是配置端口。
STOP 走 `python launch.py stop`，端口空闲时找不到监听进程，天然安全。
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "capture"

pytestmark = pytest.mark.skipif(os.name != "nt", reason="仅 Windows 批处理")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _fake_mitmdump_dir(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    (fake_bin / "mitmdump.bat").write_text(
        "@echo off\r\necho FAKE-MITMDUMP %*\r\n", encoding="ascii"
    )
    return fake_bin


def _write_project(tmp_path: Path, listen_port=None) -> Path:
    """建一个带 .api-autotest/config.json 的临时项目（cwd 会指过去）。"""
    project = tmp_path / "proj"
    (project / "api").mkdir(parents=True)
    (project / ".api-autotest").mkdir()
    capture = {} if listen_port is None else {"listen_port": listen_port}
    config = {
        "project_root": str(project),
        "paths": {"api_method_dirs": ["api"], "pytest_workdir": "."},
        "api_index": {"scan_dirs": ["api"]},
        "capture": capture,
    }
    (project / ".api-autotest" / "config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    return project


def _env_with(fake_bin: Path | None = None, extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env.pop("CAPTURE_PORT", None)
    parts = []
    if fake_bin is not None:
        parts.append(str(fake_bin))
    parts.append(str(Path(sys.executable).parent))  # 保证批处理里的 python 能解析
    parts.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(parts)
    env.update(extra or {})
    return env


def _run_bat(
    name: str, cwd: Path, env: dict
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd", "/c", str(CAPTURE / name)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_start_bat_uses_configured_port(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    project = _write_project(tmp_path, listen_port=9999)

    result = _run_bat("start.bat", project, _env_with(fake_bin))

    assert "FAKE-MITMDUMP" in result.stdout, result.stderr
    assert "--listen-port 9999" in result.stdout, result.stderr
    assert "capture_addon.py" in result.stdout, result.stderr


def test_start_bat_env_override_beats_config(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    project = _write_project(tmp_path, listen_port=9999)

    result = _run_bat("start.bat", project, _env_with(fake_bin, {"CAPTURE_PORT": "8888"}))

    assert "--listen-port 8888" in result.stdout, result.stderr


def test_start_bat_falls_back_to_default_port_when_config_missing(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    project = tmp_path / "no_config_project"  # 无 .api-autotest/config.json
    project.mkdir()

    result = _run_bat("start.bat", project, _env_with(fake_bin))

    assert "--listen-port 12138" in result.stdout, result.stderr
    assert "12138" in result.stderr, "配置缺失应告警并说明回落端口"


def test_stop_bat_on_free_port_is_a_noop(tmp_path):
    project = _write_project(tmp_path, listen_port=_free_port())

    result = _run_bat("stop.bat", project, _env_with())

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "taskkill" not in (result.stdout + result.stderr).lower()
    assert "没有监听进程" in result.stdout, result.stdout


def test_restart_bat_reaches_start(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    project = _write_project(tmp_path, listen_port=_free_port())

    result = _run_bat("restart.bat", project, _env_with(fake_bin))

    assert "FAKE-MITMDUMP" in result.stdout, result.stderr
