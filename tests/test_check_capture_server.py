import json
import socket

from skill_utils.config_loader import load_config
from tools.check_capture_server import check_port, capture_port_from_config, main


def test_check_port_false_for_closed_port():
    assert check_port("127.0.0.1", 1, timeout=0.2) is False


def test_check_port_true_for_listening_socket():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert check_port("127.0.0.1", port, timeout=0.5) is True
    finally:
        server.close()


def test_capture_port_from_config(tmp_path):
    project = tmp_path / "p"
    api_dir = project / "api"
    api_dir.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["api"], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["api"]},
                "capture": {"listen_port": 9999},
            }
        ),
        encoding="utf-8",
    )

    assert capture_port_from_config(load_config(config_path)) == 9999


def test_main_reports_not_running(tmp_path, capsys, monkeypatch):
    project = tmp_path / "p"
    api_dir = project / "api"
    api_dir.mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(project),
                "paths": {"api_method_dirs": ["api"], "pytest_workdir": "."},
                "api_index": {"scan_dirs": ["api"]},
                "capture": {"listen_port": 1},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["--config", str(config_path)])

    assert exit_code == 1
    assert "NOT_RUNNING" in capsys.readouterr().out
