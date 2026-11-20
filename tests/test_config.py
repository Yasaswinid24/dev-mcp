from pathlib import Path

from devhelper.config import Config


def test_roots_split_on_semicolon_and_deduplicate(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    cfg = Config.from_env({"DEV_MCP_ROOTS": f"{a};{b};{a}"})
    assert cfg.roots == (a.resolve(), b.resolve())
    assert cfg.primary_root == a.resolve()


def test_legacy_single_root_still_works(tmp_path):
    cfg = Config.from_env({"DEV_MCP_ROOT": str(tmp_path)})
    assert cfg.roots == (tmp_path.resolve(),)


def test_roots_take_priority_over_legacy(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    cfg = Config.from_env({"DEV_MCP_ROOTS": str(tmp_path), "DEV_MCP_ROOT": str(other)})
    assert cfg.roots == (tmp_path.resolve(),)


def test_defaults_to_home_when_nothing_is_set():
    cfg = Config.from_env({})
    assert cfg.roots == (Path.home().resolve(),)
    assert cfg.my_remotes == ()
    assert cfg.gitlab_url == "https://gitlab.com"


def test_my_remotes_are_trimmed_and_empty_entries_dropped():
    cfg = Config.from_env({"DEV_MCP_MY_REMOTES": " yassu , origin,, "})
    assert cfg.my_remotes == ("yassu", "origin")


def test_gitlab_url_loses_trailing_slash():
    cfg = Config.from_env({"GITLAB_URL": "https://git.example.org/"})
    assert cfg.gitlab_url == "https://git.example.org"
