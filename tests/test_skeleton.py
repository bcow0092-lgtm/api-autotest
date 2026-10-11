from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_license_keeps_upstream_attribution():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "dengwanpeng" in text
    assert "buer2233/ai-api-test-skill" in text


def test_skill_utils_is_importable():
    import skill_utils  # noqa: F401


def test_no_third_party_imports_in_skill_utils():
    import ast
    import sys

    allowed = set(sys.stdlib_module_names) | {"__future__", "skill_utils"}
    offenders = []
    for py in (ROOT / "skill_utils").glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in allowed:
                        offenders.append(f"{py.name}: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 相对导入（from .x import y），不是第三方依赖
                    continue
                top = (node.module or "").split(".")[0]
                if top and top not in allowed:
                    offenders.append(f"{py.name}: {node.module}")
    assert offenders == [], f"发现第三方依赖: {offenders}"
