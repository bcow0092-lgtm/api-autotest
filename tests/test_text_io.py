from skill_utils.text_io import (
    has_bom,
    looks_mojibake,
    read_text_utf8,
    write_text_utf8,
)


def test_write_then_read_roundtrip_keeps_chinese(tmp_path):
    p = tmp_path / "a.py"
    write_text_utf8(p, "# 中文注释\nx = 1\n")
    assert read_text_utf8(p) == "# 中文注释\nx = 1\n"


def test_write_never_emits_bom(tmp_path):
    p = tmp_path / "a.py"
    write_text_utf8(p, "中文")
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")


def test_read_strips_existing_bom(tmp_path):
    p = tmp_path / "a.py"
    p.write_bytes("﻿中文".encode("utf-8"))
    assert read_text_utf8(p) == "中文"


def test_crlf_normalized_to_lf(tmp_path):
    p = tmp_path / "a.py"
    p.write_bytes(b"a\r\nb\rc")
    assert read_text_utf8(p) == "a\nb\nc"


def test_write_normalizes_crlf(tmp_path):
    p = tmp_path / "a.py"
    write_text_utf8(p, "a\r\nb")
    assert p.read_bytes() == b"a\nb"


def test_has_bom():
    assert has_bom("﻿x") is True
    assert has_bom("x") is False


def test_looks_mojibake():
    assert looks_mojibake("正常中文文本") is False
    assert looks_mojibake("?????") is True
    assert looks_mojibake("broken � text") is True


def test_text_io_source_uses_escapes_not_raw_invisible_chars():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "skill_utils" / "text_io.py").read_text(encoding="utf-8")
    assert "\ufeff" not in source
    assert "\ufffd" not in source
