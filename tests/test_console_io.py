import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_configure_stdio_emits_utf8_bytes_in_subprocess():
    """本机 Windows 默认 stdout 是 cp936；configure_stdio 后必须是 UTF-8 字节。"""
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{ROOT}');"
        "from skill_utils.console_io import configure_stdio;"
        "configure_stdio();"
        "print('中文')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert result.returncode == 0, result.stderr
    # Windows 文本模式 stdout 会把 \n 翻成 os.linesep（\r\n），故期望值用平台换行。
    # 断言仍**严格比对 UTF-8 字节**：若编码没切走，cp936 字节会与之完全不同。
    assert result.stdout == ("中文" + os.linesep).encode("utf-8")


def test_configure_stdio_is_idempotent():
    from skill_utils.console_io import configure_stdio

    configure_stdio()
    configure_stdio()  # 重复调用不得抛异常


def test_cli_entry_points_configure_stdio():
    for name in ("init_project.py", "scan_api_methods.py", "append_extract_rule.py"):
        source = (ROOT / "tools" / name).read_text(encoding="utf-8")
        assert "configure_stdio" in source, f"{name} 未调用 configure_stdio()"
