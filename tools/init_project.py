# -*- coding: utf-8 -*-
"""接入引导：探测项目结构 → 询问关键信息 → 生成 .api-autotest/config.json 与最小骨架。

用 --answers <json> 可非交互运行（测试与自动化用）；无该参数时进入交互问答。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.project_locator import CONFIG_DIR_NAME, CONFIG_FILE_NAME, missing_config_guidance  # noqa: E402
from skill_utils.text_io import read_text_utf8, write_text_utf8  # noqa: E402

PROJECT_MARKERS = (".git", "pom.xml", "build.gradle", "package.json", "pyproject.toml", "requirements.txt")
API_DIR_CANDIDATES = ("tests/api", "test/api", "test/API_TEST/api", "api", "test_case/page_api", "src/clients")
CASE_DIR_CANDIDATES = ("tests/cases", "test/cases", "test/API_TEST/cases", "cases", "test_case")
CONFTEST_TEMPLATE = '''# -*- coding: utf-8 -*-
"""api-autotest 生成的骨架。

TODO: 补全登录 fixture。
      鉴权方式因项目而异（Sa-Token / JWT / Basic），
      由 AI 读后端登录接口后按项目实际实现填写，不要照抄示例。
"""

import pytest
import requests

BASE_URL = "{baseurl}"


@pytest.fixture(scope="session")
def api_session():
    """TODO: 完成登录并返回带鉴权信息的 requests.Session。"""
    session = requests.Session()
    yield session
    session.close()
'''

REQUIRED_ANSWERS = ("baseurl",)


def detect_project(project_root: str | Path) -> dict:
    """扫一遍项目结构，返回探测结果（不做任何写入）。"""
    root = Path(project_root).resolve()
    markers = [m for m in PROJECT_MARKERS if (root / m).exists()]
    source_roots = _find_source_roots(root)

    return {
        "project_root": str(root),
        "markers": markers,
        "backend_language": _guess_language(root, source_roots),
        "api_dir_candidates": [c for c in API_DIR_CANDIDATES if (root / c).is_dir()],
        "case_dir_candidates": [c for c in CASE_DIR_CANDIDATES if (root / c).is_dir()],
        "source_roots": source_roots,
    }


def build_config(project_root: str | Path, answers: dict) -> dict:
    """按探测结果与用户答案拼出 config.json 内容。"""
    missing = [k for k in REQUIRED_ANSWERS if not answers.get(k)]
    if missing:
        raise ValueError(f"接入引导缺少必填答案: {', '.join(missing)}")

    api_dirs = answers.get("api_method_dirs") or ["test/API_TEST/api"]
    case_dirs = answers.get("test_case_dirs") or ["test/API_TEST/cases"]
    workdir = answers.get("pytest_workdir") or "test/API_TEST"
    temp_dir = answers.get("runtime_temp_dir") or f"{workdir}/.tmp"
    index_dir = answers.get("index_dir") or f"{workdir}/.index"

    config = {
        "project_root": str(Path(project_root).resolve()),
        "framework": "pytest_requests",
        "paths": {
            "api_method_dirs": api_dirs,
            "test_case_dirs": case_dirs,
            "pytest_workdir": workdir,
            "runtime_temp_dir": temp_dir,
        },
        "api_index": {
            "db_path": f"{index_dir}/api_index.sqlite3",
            "scan_dirs": api_dirs,
            "extract_rules_path": f"{index_dir}/extract_rules.json",
        },
        "pytest": {
            "pythonpath": answers.get("pythonpath") or ".",
            "command_template": "pytest {target} -v --tb=short",
        },
        "capture": {
            "listen_port": int(answers.get("capture_port") or 12138),
            "baseurl": answers["baseurl"],
            "include_prefixes": answers.get("include_prefixes") or ["/api"],
            "exclude_prefixes": answers.get("exclude_prefixes") or ["/static", "/favicon.ico"],
            "login_path_hints": answers.get("login_path_hints") or ["/login", "/auth/login"],
            "session_cookie_names": answers.get("session_cookie_names") or [],
        },
    }

    language = answers.get("source_language")
    roots = answers.get("source_roots")
    if language and roots:
        config["source_analysis"] = {
            "language": language,
            "roots": roots,
            "url_prefix_map": answers.get("url_prefix_map") or {},
        }
    return config


def init_project(project_root: str | Path, answers: dict, *, dry_run: bool = False) -> dict:
    """生成配置与骨架，并跑一次 dry-run 扫描自检。"""
    root = Path(project_root).resolve()
    config = build_config(root, answers)
    config_path = root / CONFIG_DIR_NAME / CONFIG_FILE_NAME

    created_dirs: list[str] = []
    warnings: list[str] = []

    if dry_run:
        return {
            "config_path": None,
            "created_dirs": [],
            "scanned_records": 0,
            "warnings": ["dry-run：未写入任何文件"],
        }

    for relative in (
        list(config["paths"]["api_method_dirs"])
        + list(config["paths"]["test_case_dirs"])
        + [config["paths"]["runtime_temp_dir"], str(Path(config["api_index"]["db_path"]).parent)]
    ):
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(relative)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_utf8(config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")

    conftest = root / config["paths"]["pytest_workdir"] / "conftest.py"
    if not conftest.exists():
        conftest.parent.mkdir(parents=True, exist_ok=True)
        write_text_utf8(conftest, _render_conftest(config["capture"]["baseurl"]))

    from skill_utils.config_loader import load_config
    from tools.scan_api_methods import _compile_rule, _scan_all, DEFAULT_METHOD_RULES, DEFAULT_URL_RULES

    resolved = load_config(config_path)
    records, _ = _scan_all(
        str(resolved.project_root),
        [str(d) for d in resolved.api_scan_dirs],
        url_rules=[_compile_rule(r) for r in DEFAULT_URL_RULES],
        method_rules=[_compile_rule(r) for r in DEFAULT_METHOD_RULES],
    )
    if not records:
        warnings.append(
            "扫到 0 条接口。绿地项目属正常；若非绿地，请检查 config.json 的 "
            "api_index.scan_dirs 是否指向真正的接口方法层目录。"
        )

    return {
        "config_path": str(config_path),
        "created_dirs": created_dirs,
        "scanned_records": len(records),
        "warnings": warnings,
    }


def _render_conftest(baseurl: str) -> str:
    return CONFTEST_TEMPLATE.replace("{baseurl}", baseurl)


def _find_source_roots(root: Path) -> list[str]:
    roots = []
    for pattern in ("**/src/main/java", "**/app/routers", "**/routes", "**/routers"):
        for match in root.glob(pattern):
            if match.is_dir() and "node_modules" not in match.parts:
                roots.append(match.relative_to(root).as_posix())
    return sorted(set(roots))[:10]


def _guess_language(root: Path, source_roots: list[str]) -> str | None:
    joined = " ".join(source_roots)
    if "src/main/java" in joined or list(root.glob("**/*Controller.java")):
        return "java"
    if any((root / p).exists() for p in ("requirements.txt", "pyproject.toml")):
        return "python"
    if (root / "package.json").exists():
        return "node"
    return None


def _prompt(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="接入引导：生成 .api-autotest/config.json")
    parser.add_argument("--project-root", default=".", help="项目根目录（默认当前目录）")
    parser.add_argument("--answers", default=None, help="答案 JSON 文件（非交互运行）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    facts = detect_project(root)
    print(json.dumps(facts, ensure_ascii=False, indent=2))

    if args.answers:
        answers = json.loads(read_text_utf8(args.answers))
    elif sys.stdin.isatty():
        answers = _interactive_answers(facts)
    else:
        print(
            "ERROR: 非交互环境必须用 --answers <json> 提供答案。\n"
            + missing_config_guidance(root),
            file=sys.stderr,
        )
        return 2

    try:
        result = init_project(root, answers, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    for warning in result["warnings"]:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


def _interactive_answers(facts: dict) -> dict:
    api_default = (facts["api_dir_candidates"] or ["test/API_TEST/api"])[0]
    return {
        "baseurl": _prompt("被测服务 baseurl（如 http://localhost:8081）"),
        "api_method_dirs": [_prompt("接口方法层目录", api_default)],
        "test_case_dirs": [_prompt("用例目录", (facts["case_dir_candidates"] or ["test/API_TEST/cases"])[0])],
        "pytest_workdir": _prompt("pytest 工作目录", str(Path(api_default).parent)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
