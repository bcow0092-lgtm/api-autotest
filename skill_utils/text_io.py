# -*- coding: utf-8 -*-
"""UTF-8 无 BOM 读写与乱码检测（多模块共用）。

Windows + 中文路径下，编辑器与 patch 工具常引入 BOM 或 `???` 乱码。
所有写入统一走 write_text_utf8，所有读取统一走 read_text_utf8。
"""

from __future__ import annotations

from pathlib import Path

BOM_UTF8 = "﻿"
_REPLACEMENT_CHAR = "�"
_MOJIBAKE_MARKERS = (_REPLACEMENT_CHAR, "ï¿½", "锟斤拷")


def read_text_utf8(path: str | Path) -> str:
    """以 UTF-8 读取，吞掉可能存在的 BOM，换行统一为 \\n。"""
    text = Path(path).read_text(encoding="utf-8-sig")
    return _normalize_newlines(text)


def write_text_utf8(path: str | Path, content: str) -> None:
    """以 UTF-8 无 BOM 写入，换行统一为 \\n。"""
    Path(path).write_text(_normalize_newlines(content), encoding="utf-8", newline="")


def has_bom(text: str) -> bool:
    """文本是否以 UTF-8 BOM 开头。"""
    return text.startswith(BOM_UTF8)


def looks_mojibake(text: str, *, threshold: int = 3) -> bool:
    """粗判是否出现成片乱码。

    命中条件（任一）：出现替换字符 / 典型乱码标记，或存在连续 threshold 个问号。
    """
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        return True
    return ("?" * threshold) in text


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
