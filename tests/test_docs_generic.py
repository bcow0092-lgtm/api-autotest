from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UPSTREAM_RESIDUE = (
    "E10自动化",
    "test-automation",
    "weapp.mulinquan.cn",
    "ETEAMSID",
    "api-test-E10",
    "git-diff-analyse",
)

DOC_FILES = [
    "SKILL.md",
    "doc/core_principles.md",
    "doc/coding_style_guide.md",
    "doc/preflight_gates_new.md",
    "doc/preflight_gates_maintenance.md",
    "doc/mode_reference_case.md",
    "doc/mode_curl_manual.md",
    "doc/troubleshooting.md",
    "doc/mode_capture_driven.md",
    "doc/mode_source_analysis.md",
    "doc/maintenance_context.md",
    "doc/mode_maintenance_pytest_driven.md",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_docs_exist():
    missing = [p for p in DOC_FILES if not (ROOT / p).is_file()]
    assert missing == []


def test_no_upstream_residue_in_docs():
    offenders = []
    for path in DOC_FILES:
        text = read(path)
        for marker in UPSTREAM_RESIDUE:
            if marker in text:
                offenders.append(f"{path}: {marker}")
    assert offenders == [], f"文档残留上游私货: {offenders}"


def test_skill_frontmatter_and_scope():
    text = read("SKILL.md")
    assert text.startswith("---")
    assert "name: api-autotest" in text
    assert "python + pytest + requests" in text


def test_skill_documents_main_flow_steps():
    text = read("SKILL.md")
    for step in ("预检", "判定任务类型", "门禁", "读规范", "pytest 闭环", "输出清单"):
        assert step in text, f"SKILL.md 缺少主流程环节: {step}"


def test_docs_are_config_driven_not_hardcoded():
    core = read("doc/core_principles.md")
    maintenance = read("doc/preflight_gates_maintenance.md")
    assert "config.json" in core
    assert "pytest.command_template" in maintenance or "pytest.workdir" in maintenance or "config.json" in maintenance


def test_skill_documents_explicit_shell_for_pytest_command():
    text = read("SKILL.md")
    assert "build_pytest_command" in text
    assert "shell" in text


def test_docs_no_longer_claim_capture_and_analysis_are_unimplemented():
    text = read("SKILL.md")
    # 第一份计划的 SKILL.md 用「规划中」标注抓包与源码分析尚未实现，本次已实现，该标记必须消失
    assert "规划中" not in text
