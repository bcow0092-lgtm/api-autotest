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

    stdlib_ok = {
        "argparse", "ast", "dataclasses", "datetime", "json", "os", "pathlib",
        "re", "sqlite3", "sys", "typing", "urllib", "collections", "shutil",
        "subprocess", "tempfile", "textwrap", "unicodedata",
    }
    offenders = []
    for py in (ROOT / "skill_utils").glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib_ok and top != "skill_utils":
                        offenders.append(f"{py.name}: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib_ok and top != "skill_utils":
                    offenders.append(f"{py.name}: {node.module}")
    assert offenders == [], f"发现第三方依赖: {offenders}"
