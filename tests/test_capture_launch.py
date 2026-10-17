# -*- coding: utf-8 -*-
"""capture/launch.py 的端口解析优先级与配置缺失回落（三层 + 容错）。"""

import types

from capture import launch
from skill_utils.config_loader import ConfigError
from skill_utils.port_process import parse_pid_from_netstat


def _config(listen_port):
    return types.SimpleNamespace(capture={"listen_port": listen_port})


def test_resolve_port_env_override_wins():
    # CAPTURE_PORT > config.capture.listen_port
    assert launch.resolve_port(_config(9999), {"CAPTURE_PORT": "8888"}) == 8888


def test_resolve_port_uses_config_when_env_absent():
    assert launch.resolve_port(_config(9999), {}) == 9999


def test_resolve_port_defaults_to_12138():
    # 既无环境变量、也无配置时用默认端口
    assert launch.resolve_port(None, {}) == launch.DEFAULT_PORT == 12138
    assert launch.resolve_port(_config(None), {}) == 12138


def test_resolve_port_ignores_blank_env():
    assert launch.resolve_port(_config(9999), {"CAPTURE_PORT": "  "}) == 9999


def test_resolve_port_from_environment_warns_and_defaults_on_config_error(
    monkeypatch, capsys
):
    def boom(*args, **kwargs):
        raise ConfigError("没有配置文件")

    monkeypatch.setattr(launch, "load_config", boom)

    assert launch.resolve_port_from_environment({}) == 12138

    err = capsys.readouterr().err
    assert "12138" in err
    assert "没有配置文件" in err


def test_resolve_port_from_environment_uses_config(monkeypatch):
    monkeypatch.setattr(launch, "load_config", lambda: _config(7777))
    assert launch.resolve_port_from_environment({}) == 7777


_NETSTAT_SAMPLE = """\
  TCP    0.0.0.0:12138          0.0.0.0:0              LISTENING       4321
  TCP    127.0.0.1:9999         0.0.0.0:0              LISTENING       555
  TCP    127.0.0.1:99990        0.0.0.0:0              LISTENING       999
  TCP    127.0.0.1:9999         127.0.0.1:52341        ESTABLISHED     555
"""


def test_parse_pid_from_netstat_matches_exact_port():
    assert parse_pid_from_netstat(12138, _NETSTAT_SAMPLE) == "4321"
    assert parse_pid_from_netstat(9999, _NETSTAT_SAMPLE) == "555"


def test_parse_pid_from_netstat_does_not_match_superstring_port():
    # :9999 不能命中 :99990
    assert parse_pid_from_netstat(999, _NETSTAT_SAMPLE) is None

