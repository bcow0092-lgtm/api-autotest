# -*- coding: utf-8 -*-
"""mitmdump addon：把真实 HTTP 请求录成 JSONL，供 match_captures.py 比对索引。

与上游的关键差别：**没有任何硬编码**。端口、baseurl、过滤前缀、登录路径特征全部
来自项目自己的 `<project>/.api-autotest/config.json` 的 `capture` 节。

启动：
    mitmdump -s capture_addon.py --listen-port <config.capture.listen_port>
或双击 start.bat
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

CAPTURE_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CAPTURE_DIR.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from mitmproxy import ctx  # noqa: E402

from skill_utils.config_loader import ConfigError, load_config  # noqa: E402

STATIC_SUFFIX = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".ico", ".map",
)

BINARY_CONTENT_TYPE_PREFIXES = (
    "application/octet-stream", "application/pdf", "application/zip",
    "application/x-zip", "application/x-rar", "application/x-7z",
    "application/x-tar", "application/x-gzip", "application/vnd.ms-",
    "application/vnd.openxmlformats-", "image/", "video/", "audio/",
)

FALLBACK_LOGIN_HINTS = ("/login", "/logout", "/auth/token")

MAX_BODY_BYTES = 1024 * 1024
DEFAULT_JSONL_NAME = "latest.jsonl"

JSONL_PATH: str = ""


def _warn(message: str) -> None:
    ctx.log.warn(f"[api-autotest] {message}")


def _info(message: str) -> None:
    ctx.log.info(f"[api-autotest] {message}")


def load_capture_config() -> dict:
    """读取项目配置并解析出抓包需要的全部参数。"""
    try:
        config = load_config()
    except ConfigError as exc:
        _warn(f"读取配置失败：{exc}")
        return {}
    capture = dict(config.capture or {})
    capture["jsonl_path"] = str(Path(config.runtime_temp_dir) / DEFAULT_JSONL_NAME)
    capture.setdefault("listen_port", 12138)
    capture.setdefault("baseurl", "")
    capture.setdefault("include_prefixes", ["/"])
    capture.setdefault("exclude_prefixes", [])
    capture.setdefault("login_path_hints", [])
    capture.setdefault("session_cookie_names", [])
    return capture


def should_capture(record_ctx: dict, capture_cfg: dict) -> bool:
    """按静态后缀 / host / 前缀 / 排除前缀 / 登录路径判断该不该记录。"""
    pure_path = (record_ctx.get("pure_path") or "/").lower()

    if pure_path.endswith(STATIC_SUFFIX):
        return False
    for excluded in capture_cfg.get("exclude_prefixes") or []:
        if excluded and pure_path.startswith(excluded.lower()):
            return False
    if not _match_baseurl(record_ctx.get("host") or "", capture_cfg.get("baseurl") or ""):
        return False
    includes = capture_cfg.get("include_prefixes") or ["/"]
    if not any(pure_path.startswith(prefix.lower()) for prefix in includes):
        return False
    if _is_login_path(pure_path, capture_cfg.get("login_path_hints") or []):
        return False
    return True


def build_record(flow, capture_cfg: dict) -> dict:
    """把一条 mitmproxy flow 变成 JSONL 记录，敏感头做摘要、二进制响应跳过 body。"""
    request = flow.request
    response = flow.response

    headers = {}
    for key, value in request.headers.items():
        if key.lower() in ("cookie", "authorization"):
            headers[key] = _digest(value)
        else:
            headers[key] = value

    req_body = None
    try:
        if request.content is not None:
            req_body = request.get_text(strict=False)
    except Exception:
        req_body = None

    content_type = (response.headers.get("content-type") or "") if response else ""
    resp_body = None
    body_skipped = False
    body_truncated = False
    skip_reason = ""

    if response is not None:
        raw = response.raw_content or b""
        if _is_binary_content_type(content_type):
            body_skipped = True
            skip_reason = f"binary-content-type:{content_type}"
            resp_body = f"<BINARY_SKIPPED: content-type={content_type}, size={len(raw)}>"
        elif _looks_encoded_blob(raw):
            body_skipped = True
            skip_reason = "encoded-blob"
            resp_body = f"<ENCODED_SKIPPED: size={len(raw)}>"
        elif len(raw) > MAX_BODY_BYTES:
            body_truncated = True
            resp_body = raw[:MAX_BODY_BYTES].decode("utf-8", errors="replace")
        else:
            try:
                resp_body = response.get_text(strict=False)
            except Exception:
                resp_body = None

    pure_path = (request.path or "/").split("?", 1)[0]
    host = request.host
    if request.port and request.port not in (80, 443):
        host = f"{request.host}:{request.port}"

    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "epoch": time.time(),
        "method": request.method,
        "scheme": request.scheme,
        "host": host,
        "path": request.path,
        "pure_path": pure_path,
        "url": request.url,
        "req_headers": headers,
        "req_body": req_body,
        "status": response.status_code if response else None,
        "resp_content_type": content_type,
        "resp_body": resp_body,
        "body_skipped": body_skipped,
        "body_truncated": body_truncated,
        "skip_reason": skip_reason,
        "is_login": _is_login_path(pure_path.lower(), capture_cfg.get("login_path_hints") or []),
    }


def _match_baseurl(host_port: str, baseurl: str) -> bool:
    if not baseurl:
        return True
    target = baseurl.split("//")[-1].split("/")[0].strip().lower()
    if not target:
        return True
    lowered = (host_port or "").lower()
    return lowered == target or lowered.startswith(target + ":")


def _is_login_path(path: str, hints: list) -> bool:
    lowered = (path or "").lower()
    if any(hint.lower() in lowered for hint in (hints or [])):
        return True
    return re.search(r"/(login|logout)(?:\?|$)", lowered) is not None


def _is_binary_content_type(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return any(lowered.startswith(prefix) for prefix in BINARY_CONTENT_TYPE_PREFIXES)


def _looks_encoded_blob(body: bytes) -> bool:
    """超过 2KB、只由 base64 / 十六进制 / 数字构成，且字符足够多样，才是大块编码数据。

    单一字符的长串（例如整段重复的分隔线、填充字符）不是编码数据：base64 / 十六进制
    的真实数据必然含多种字符，若不排除这种退化串，会把正常文本误吞成 blob。
    """
    if len(body) <= 2048:
        return False
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError:
        return False
    if len(set(text)) < 2:
        return False
    return bool(
        re.fullmatch(r"[A-Za-z0-9+/=\s]+", text)
        or re.fullmatch(r"[0-9a-fA-F\s]+", text)
        or re.fullmatch(r"[0-9\s]+", text)
    )


def _digest(value: str, keep: int = 20) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return f"{value}|len={len(value)}"
    return f"{value[:keep]}...|len={len(value)}"


class ApiCaptureAddon:
    def __init__(self):
        global JSONL_PATH
        self.config = load_capture_config()
        self.jsonl_path = self.config.get("jsonl_path") or ""
        JSONL_PATH = self.jsonl_path
        if self.jsonl_path:
            Path(self.jsonl_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.jsonl_path).touch(exist_ok=True)
        _info(f"baseurl={self.config.get('baseurl') or '<未配置，不过滤 host>'}")
        _info(f"include_prefixes={self.config.get('include_prefixes')}")
        _info(f"jsonl_path={self.jsonl_path or '<未配置，落盘已禁用>'}")

    def response(self, flow) -> None:
        try:
            if not self.jsonl_path:
                return
            request = flow.request
            pure_path = (request.path or "/").split("?", 1)[0]
            host = request.host
            if request.port and request.port not in (80, 443):
                host = f"{request.host}:{request.port}"
            if not should_capture({"host": host, "pure_path": pure_path}, self.config):
                return
            record = build_record(flow, self.config)
            with open(self.jsonl_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:  # 抓包不能因为单条记录失败而中断
            _warn(f"落盘异常：{exc}")


addons = [ApiCaptureAddon()]
