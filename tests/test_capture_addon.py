import json
import sys
import types
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _install_fake_mitmproxy(monkeypatch):
    """把假 mitmproxy 注入 sys.modules，让 addon 可以在没装 mitmproxy 的机器上被 import。"""
    log = types.SimpleNamespace(warn=lambda _m: None, info=lambda _m: None)
    fake_pkg = types.ModuleType("mitmproxy")
    fake_ctx = types.ModuleType("mitmproxy.ctx")
    fake_http = types.ModuleType("mitmproxy.http")
    fake_ctx.log = log
    fake_http.HTTPFlow = object
    fake_pkg.ctx = fake_ctx
    fake_pkg.http = fake_http
    monkeypatch.setitem(sys.modules, "mitmproxy", fake_pkg)
    monkeypatch.setitem(sys.modules, "mitmproxy.ctx", fake_ctx)
    monkeypatch.setitem(sys.modules, "mitmproxy.http", fake_http)
    sys.modules.pop("capture.capture_addon", None)


def _write_config(tmp_path, capture=None):
    project = tmp_path / "project"
    api_dir = project / "api"
    api_dir.mkdir(parents=True)
    payload = {
        "project_root": str(project),
        "paths": {
            "api_method_dirs": ["api"],
            "pytest_workdir": ".",
            "runtime_temp_dir": "runtime",
        },
        "api_index": {"scan_dirs": ["api"]},
        "capture": capture
        or {
            "listen_port": 12138,
            "baseurl": "http://localhost:8081",
            "include_prefixes": ["/wms"],
            "exclude_prefixes": ["/static"],
            "login_path_hints": ["/login"],
            "session_cookie_names": [],
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path, project


def test_capture_config_comes_from_config_json(tmp_path, monkeypatch):
    _install_fake_mitmproxy(monkeypatch)
    config_path, project = _write_config(tmp_path)
    monkeypatch.setattr("skill_utils.config_loader.DEFAULT_CONFIG_PATH", config_path)

    addon_module = __import__("capture.capture_addon", fromlist=["load_capture_config"])

    cfg = addon_module.load_capture_config()

    assert cfg["baseurl"] == "http://localhost:8081"
    assert cfg["listen_port"] == 12138
    assert cfg["jsonl_path"] == str((project / "runtime" / "latest.jsonl"))


def test_should_capture_filters_static_and_host():
    from capture.capture_addon import should_capture

    cfg = {"baseurl": "http://localhost:8081", "include_prefixes": ["/wms"], "exclude_prefixes": []}

    assert should_capture({"host": "localhost:8081", "pure_path": "/wms/list"}, cfg) is True
    assert should_capture({"host": "localhost:8081", "pure_path": "/static/app.js"}, cfg) is False
    assert should_capture({"host": "other:8081", "pure_path": "/wms/list"}, cfg) is False
    assert should_capture({"host": "localhost:8081", "pure_path": "/login"}, cfg) is False


def test_exclude_prefixes_takes_effect():
    from capture.capture_addon import should_capture

    cfg = {
        "baseurl": "http://localhost:8081",
        "include_prefixes": ["/"],
        "exclude_prefixes": ["/actuator"],
    }

    assert should_capture({"host": "localhost:8081", "pure_path": "/actuator/health"}, cfg) is False
    assert should_capture({"host": "localhost:8081", "pure_path": "/wms/list"}, cfg) is True


def test_digest_truncates_and_reports_length():
    from capture.capture_addon import _digest

    assert _digest("") == ""
    assert _digest("abc") == "abc|len=3"
    long_value = "x" * 50
    assert _digest(long_value).startswith("x" * 20)
    assert _digest(long_value).endswith("|len=50")


def test_binary_and_encoded_detection():
    from capture.capture_addon import _is_binary_content_type, _looks_encoded_blob

    assert _is_binary_content_type("image/png") is True
    assert _is_binary_content_type("application/json") is False
    assert _looks_encoded_blob(b"a" * 3000) is False
    assert _looks_encoded_blob(("QUJD" * 800).encode("ascii")) is True
    assert _looks_encoded_blob(b"short") is False


def test_is_login_path_uses_configured_hints():
    from capture.capture_addon import _is_login_path

    assert _is_login_path("/wms/login", ["/login"]) is True
    assert _is_login_path("/wms/list", ["/login"]) is False
    assert _is_login_path("/anything/logout", []) is True  # 兜底规则始终生效


# ---- build_record：假的 flow 对象，覆盖"非文本响应"这条 Review Focus ----

class _Headers(dict):
    def get(self, key, default=None):
        for candidate, value in self.items():
            if candidate.lower() == key.lower():
                return value
        return default


class _FakeFlow:
    def __init__(
        self,
        *,
        method="GET",
        path="/wms/list",
        host="localhost",
        port=8081,
        request_body=None,
        response_body=b'{"ok": true}',
        content_type="application/json",
        status=200,
        cookie="abc123",
    ):
        self.request = types.SimpleNamespace(
            method=method,
            path=path,
            host=host,
            port=port,
            scheme="http",
            url=f"http://{host}:{port}{path}",
            content=request_body,
            headers=_Headers({"Cookie": cookie, "Accept": "application/json"}),
            get_text=lambda strict=False: (
                request_body.decode("utf-8") if isinstance(request_body, bytes) else request_body
            ),
        )
        self.response = types.SimpleNamespace(
            status_code=status,
            headers=_Headers({"content-type": content_type}),
            raw_content=response_body,
            get_text=lambda strict=False: response_body.decode("utf-8", errors="replace"),
        )


def test_build_record_redacts_sensitive_headers(monkeypatch):
    _install_fake_mitmproxy(monkeypatch)
    from capture.capture_addon import build_record

    long_cookie = "x" * 50
    record = build_record(_FakeFlow(cookie=long_cookie), {"login_path_hints": ["/login"]})

    assert record["method"] == "GET"
    assert record["pure_path"] == "/wms/list"
    assert record["host"] == "localhost:8081"
    assert record["is_login"] is False
    assert record["body_skipped"] is False
    assert long_cookie not in record["req_headers"]["Cookie"]
    assert record["req_headers"]["Cookie"].endswith("|len=50")


def test_build_record_skips_binary_body(monkeypatch):
    _install_fake_mitmproxy(monkeypatch)
    from capture.capture_addon import build_record

    flow = _FakeFlow(content_type="image/png", response_body=b"\x89PNG" + b"\x00" * 4096)

    record = build_record(flow, {})

    assert record["body_skipped"] is True
    assert record["skip_reason"].startswith("binary-content-type:")
    assert record["resp_body"].startswith("<BINARY_SKIPPED")
    assert "PNG" not in record["resp_body"]


def test_build_record_truncates_oversized_text_body(monkeypatch):
    _install_fake_mitmproxy(monkeypatch)
    from capture.capture_addon import build_record

    # 注意载荷必须含非 base64/十六进制字符，否则会先被 _looks_encoded_blob 判成编码大块
    payload = b'{"data": "' + b"B" * (2 * 1024 * 1024) + b'"}'
    flow = _FakeFlow(response_body=payload, content_type="application/json")

    record = build_record(flow, {})

    assert record["body_truncated"] is True
    assert record["body_skipped"] is False
    assert len(record["resp_body"]) <= 1024 * 1024


def test_build_record_skips_encoded_blob(monkeypatch):
    _install_fake_mitmproxy(monkeypatch)
    from capture.capture_addon import build_record

    flow = _FakeFlow(response_body=("QUJD" * 800).encode("ascii"), content_type="text/plain")

    record = build_record(flow, {})

    assert record["body_skipped"] is True
    assert record["skip_reason"] == "encoded-blob"
