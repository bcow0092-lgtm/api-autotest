# -*- coding: utf-8 -*-
"""CLI 输出编码统一（多模块共用）。

Windows 下 Python 的 stdout/stderr 默认走 cp936。当输出**被父进程以 utf-8 捕获**
时（AI / 管道 / CI 都是这种情形），cp936 字节会被解成乱码，甚至触发
UnicodeDecodeError。所有 CLI 入口第一件事就是调用本函数。
"""

from __future__ import annotations

import sys

DEFAULT_ENCODING = "utf-8"


def configure_stdio(encoding: str = DEFAULT_ENCODING) -> None:
    """把 stdout/stderr 切到指定编码。不支持 reconfigure 的流静默跳过。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding=encoding)
        except (ValueError, OSError):
            # 流已被重定向到不支持换编码的对象（如 pytest 的捕获对象）
            pass
