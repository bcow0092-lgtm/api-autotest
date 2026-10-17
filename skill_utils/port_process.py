# -*- coding: utf-8 -*-
"""Windows 下按端口定位并终止进程（check_capture_server.py 与 capture/launch.py 共用）。

「查监听端口的 PID」「查 PID 的可执行名」「按 PID 强杀」这三件事原本在抓包状态检查和
启停脚本里各写一遍，抽到这里只留一份，避免两边逻辑漂移。

只依赖标准库；非 Windows 平台调用时 netstat/tasklist 不存在，函数会各自返回
None / 空串 / False，调用方按「查不到」处理即可。
"""

from __future__ import annotations

import subprocess

# 中文 Windows 的 netstat / tasklist 输出是 GBK，按 UTF-8 解会乱码。
_CMD_ENCODING = "gbk"


def parse_pid_from_netstat(port: int, output: str) -> str | None:
    """从 netstat -ano 输出里找出监听 `port` 的 PID。

    只看 LISTENING 行，且本地地址必须**恰好**以 `:<port>` 结尾——这样 `:9999`
    不会误配到 `:99990`。
    """
    suffix = f":{port}"
    for line in output.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        if parts[1].endswith(suffix):
            return parts[-1]
    return None


def pid_listening_on_port(port: int) -> str | None:
    """返回监听 `port` 的进程 PID；查不到返回 None。"""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano"], stderr=subprocess.DEVNULL
        ).decode(_CMD_ENCODING, errors="ignore")
    except Exception:
        return None
    return parse_pid_from_netstat(port, output)


def exe_of_pid(pid: str) -> str:
    """返回 PID 对应的可执行名（如 mitmdump.exe / python.exe）；查不到返回空串。"""
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
        ).decode(_CMD_ENCODING, errors="ignore")
    except Exception:
        return ""
    first = output.strip().splitlines()[0] if output.strip() else ""
    if not first:
        return ""
    return first.split(",")[0].strip().strip('"')


def kill_pid(pid: str) -> bool:
    """强杀进程；成功返回 True。"""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return result.returncode == 0
