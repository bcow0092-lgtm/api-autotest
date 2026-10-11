from skill_utils.project_locator import (
    find_config,
    find_project_root,
    missing_config_guidance,
)


def _make_project(tmp_path):
    cfg_dir = tmp_path / ".api-autotest"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    return cfg


def test_find_config_walks_up(tmp_path):
    cfg = _make_project(tmp_path)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_config(deep) == cfg.resolve()


def test_find_config_returns_none_when_absent(tmp_path):
    assert find_config(tmp_path) is None


def test_find_project_root(tmp_path):
    _make_project(tmp_path)
    assert find_project_root(tmp_path / ".") == tmp_path.resolve()


def test_guidance_names_init_project(tmp_path):
    text = missing_config_guidance(tmp_path)
    assert ".api-autotest" in text
    assert "config.json" in text
    assert "init_project.py" in text


def test_guidance_gives_runnable_path(tmp_path):
    from skill_utils.project_locator import SKILL_ROOT, missing_config_guidance

    text = missing_config_guidance(tmp_path)

    assert "<skill_root>" not in text
    assert str(SKILL_ROOT / "tools" / "init_project.py") in text
