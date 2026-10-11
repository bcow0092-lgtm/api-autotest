# -*- coding: utf-8 -*-
"""按配置生成 pytest 执行命令，适配 bash / PowerShell（多模块共用）。"""

from __future__ import annotations

import os
from pathlib import Path

from .config_loader import ApiTestConfig, load_config

SUPPORTED_SHELLS = ("bash", "powershell")


def build_pytest_command(
    target: str,
    *,
    config: ApiTestConfig | None = None,
    config_path: str | Path | None = None,
    shell: str | None = None,
) -> str:
    """生成一条可直接执行、已切好工作目录并设好 PYTHONPATH 的 pytest 命令。"""
    resolved = config or load_config(config_path)
    shell = (shell or detect_shell()).lower()
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(f"不支持的 shell: {shell}（可用: {', '.join(SUPPORTED_SHELLS)}）")

    command = resolved.pytest_command_template.format(target=target)
    workdir = str(resolved.pytest_workdir)
    pythonpath = resolved.pytest_pythonpath

    if shell == "powershell":
        return (
            f'Set-Location -LiteralPath "{workdir}"; '
            f'$env:PYTHONPATH="{pythonpath}"; {command}'
        )
    return f'cd "{workdir}" && PYTHONPATH="{pythonpath}" {command}'


def detect_shell() -> str:
    """猜测当前 shell：Windows 且存在 PSModulePath 视为 PowerShell，否则 bash。"""
    if os.name == "nt" and os.environ.get("PSModulePath"):
        return "powershell"
    return "bash"
