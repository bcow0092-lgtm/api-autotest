"""用假 mitmdump + 空闲端口真实执行三个批处理，验证它们的行为。

不依赖已安装的 mitmproxy：START 会去调 PATH 上的 mitmdump，我们放一个只会 echo 的
假脚本顶在最前面；STOP 走 netstat/findstr，端口空闲时循环体不执行，天然安全。
"""

import os
import socket
import subprocess
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


def _run_bat(name: str, port: int, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CAPTURE_PORT"] = str(port)
    env.update(extra_env or {})
    return subprocess.run(
        ["cmd", "/c", str(CAPTURE / name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_start_bat_invokes_mitmdump_with_configured_port(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    port = _free_port()

    result = _run_bat("start.bat", port, {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"})

    assert "FAKE-MITMDUMP" in result.stdout, result.stderr
    assert f"--listen-port {port}" in result.stdout
    assert "capture_addon.py" in result.stdout


def test_start_bat_falls_back_to_default_port_when_env_missing(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    env = os.environ.copy()
    env.pop("CAPTURE_PORT", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ['PATH']}"

    result = subprocess.run(
        ["cmd", "/c", str(CAPTURE / "start.bat")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    assert "--listen-port 12138" in result.stdout, result.stderr


def test_stop_bat_on_free_port_is_a_noop():
    port = _free_port()

    result = _run_bat("stop.bat", port)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "Stopping PID" not in result.stdout
    assert "taskkill" not in (result.stdout + result.stderr).lower()


def test_restart_bat_reaches_start(tmp_path):
    fake_bin = _fake_mitmdump_dir(tmp_path)
    port = _free_port()

    result = _run_bat(
        "restart.bat", port, {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
    )

    assert "FAKE-MITMDUMP" in result.stdout, result.stderr
