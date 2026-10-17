# -*- coding: utf-8 -*-
"""检查抓包服务（mitmdump）是否在配置的端口上监听。

退出码：0 RUNNING / 1 NOT_RUNNING / 2 PORT_OCCUPIED
端口取自 config.capture.listen_port，不再写死。
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_utils.config_loader import ConfigError, load_config  # noqa: E402
from skill_utils.console_io import configure_stdio  # noqa: E402
from skill_utils.port_process import exe_of_pid, pid_listening_on_port  # noqa: E402

DEFAULT_PORT = 12138
HOST = "127.0.0.1"

# 监听进程的可执行名里出现这些子串，就判定为「是我们自己的抓包服务」。
CAPTURE_EXE_HINTS = ("mitm", "python")


def check_port(host: str, port: int, timeout: float = 0.5) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def capture_port_from_config(config) -> int:
    return int((config.capture or {}).get("listen_port") or DEFAULT_PORT)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="检查抓包服务状态")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    port = DEFAULT_PORT
    if args.config:
        try:
            port = capture_port_from_config(load_config(args.config))
        except ConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        # 没有 --config 也要能工作：能读到就用配置端口，读不到就用默认端口。
        try:
            port = capture_port_from_config(load_config())
        except ConfigError:
            port = DEFAULT_PORT

    if not check_port(HOST, port):
        print("NOT_RUNNING")
        return 1

    pid = pid_listening_on_port(port)
    if pid is None:
        print("RUNNING")
        return 0

    exe = exe_of_pid(pid)
    if any(hint in exe.lower() for hint in CAPTURE_EXE_HINTS):
        print(f"RUNNING pid={pid} exe={exe}")
        return 0

    print(f"PORT_OCCUPIED pid={pid} exe={exe}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
