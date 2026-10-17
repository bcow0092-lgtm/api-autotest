# -*- coding: utf-8 -*-
"""抓包服务启停入口：端口统一从配置读，批处理脚本都委派到这里。

优先级：`CAPTURE_PORT` 环境变量 > `config.capture.listen_port` > 12138。
配置读不到（ConfigError）时**回落默认端口并告警**，不崩——检查/启停服务不该被
配置缺失挡住。本文件只负责拉起 mitmdump 进程，不 import mitmproxy。

用法：**在项目根目录执行**（配置沿 cwd 向上查找）；脚本在 skill 目录，要用**绝对路径**调用，
别 cd 到 skill 目录（切走就读不到项目配置）：
    python "<skill>/capture/launch.py" start     # 前台运行 mitmdump，监听配置端口
    python "<skill>/capture/launch.py" stop      # 杀掉监听该端口的进程
    python "<skill>/capture/launch.py" restart   # 先 stop 再 start
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CAPTURE_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CAPTURE_DIR.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.console_io import configure_stdio  # noqa: E402
from skill_utils.port_process import (  # noqa: E402
    exe_of_pid,
    kill_pid,
    pid_listening_on_port,
)

DEFAULT_PORT = 12138
ENV_PORT_KEY = "CAPTURE_PORT"
ADDON_PATH = CAPTURE_DIR / "capture_addon.py"


def _warn(message: str) -> None:
    print(f"[api-autotest] {message}", file=sys.stderr)


def resolve_port(config, env) -> int:
    """端口优先级：CAPTURE_PORT 环境变量 > config.capture.listen_port > 12138。"""
    override = str((env or {}).get(ENV_PORT_KEY) or "").strip()
    if override:
        try:
            return int(override)
        except ValueError:
            _warn(f"{ENV_PORT_KEY}={override!r} 不是合法端口，已忽略")

    configured = (getattr(config, "capture", None) or {}).get("listen_port")
    if configured:
        try:
            return int(configured)
        except (TypeError, ValueError):
            _warn(f"config.capture.listen_port={configured!r} 不是合法端口，已忽略")

    return DEFAULT_PORT


def resolve_port_from_environment(env=None) -> int:
    """读环境变量 + 当前项目配置，给出最终端口；配置读不到时告警并回落默认值。"""
    env = os.environ if env is None else env
    try:
        config = load_config()
    except ConfigError as exc:
        _warn(f"读取配置失败，回落默认端口 {DEFAULT_PORT}：{exc}")
        config = None
    return resolve_port(config, env)


def start(port: int) -> int:
    mitmdump = shutil.which("mitmdump")
    if mitmdump is None:
        print("ERROR: 未找到 mitmdump，请先 pip install mitmproxy", file=sys.stderr)
        return 1
    print(f"启动 mitmdump：监听端口 {port}，addon={ADDON_PATH}")
    return subprocess.call([mitmdump, "-s", str(ADDON_PATH), "--listen-port", str(port)])


def stop(port: int) -> int:
    pid = pid_listening_on_port(port)
    if pid is None:
        print(f"端口 {port} 上没有监听进程，无需停止")
        return 0
    exe = exe_of_pid(pid)
    print(f"停止端口 {port} 上的进程 PID={pid} ({exe or '未知'})")
    if kill_pid(pid):
        print("已停止")
        return 0
    print(f"停止失败：PID={pid}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="启停抓包服务（端口取自配置）")
    parser.add_argument("action", choices=("start", "stop", "restart"))
    args = parser.parse_args(argv)

    port = resolve_port_from_environment()

    if args.action == "stop":
        return stop(port)
    if args.action == "restart":
        stop(port)
        return start(port)
    return start(port)


if __name__ == "__main__":
    raise SystemExit(main())
