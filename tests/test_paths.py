import dataclasses

import pytest

from devhelper import paths


def test_resolves_project_by_name(cfg, repo):
    assert paths.resolve_project(cfg, "proj") == repo


def test_relative_escape_is_refused(cfg, repo):
    with pytest.raises(ValueError, match="outside the allowed folders"):
        paths.resolve_project(cfg, "../../etc")


def test_absolute_path_outside_roots_is_refused(cfg, tmp_path):
    with pytest.raises(ValueError, match="outside the allowed folders"):
        paths.resolve_project(cfg, str(tmp_path))


def test_absolute_path_inside_roots_is_allowed(cfg, repo):
    assert paths.resolve_project(cfg, str(repo)) == repo


def test_unknown_project_is_not_a_folder(cfg):
    with pytest.raises(ValueError, match="not a folder"):
        paths.resolve_project(cfg, "does-not-exist")


def test_a_root_can_itself_be_the_project(cfg, tmp_path, make_repo):
    solo = make_repo(tmp_path / "elsewhere", "solo").resolve()
    cfg2 = dataclasses.replace(cfg, roots=cfg.roots + (solo,))
    assert paths.resolve_project(cfg2, "solo") == solo


def test_same_name_in_two_roots_is_ambiguous(cfg, repo, tmp_path, make_repo):
    other_root = (tmp_path / "root2")
    other_root.mkdir()
    make_repo(other_root, "proj")
    cfg2 = dataclasses.replace(cfg, roots=cfg.roots + (other_root.resolve(),))
    with pytest.raises(ValueError, match="ambiguous"):
        paths.resolve_project(cfg2, "proj")


def test_inside_project_accepts_normal_and_rejects_escape(repo):
    assert paths.inside_project(repo, "README.md") == "README.md"
    assert paths.inside_project(repo, ".") == "."
    with pytest.raises(ValueError, match="outside the project folder"):
        paths.inside_project(repo, "../other")


def test_list_projects_finds_repos_and_root_repos(cfg, repo, tmp_path, make_repo):
    (cfg.roots[0] / "not-a-repo").mkdir()
    solo = make_repo(tmp_path / "elsewhere", "solo").resolve()
    cfg2 = dataclasses.replace(cfg, roots=cfg.roots + (solo,))
    assert paths.list_projects(cfg2) == ["proj", "solo"]


def test_list_projects_ignores_missing_roots(cfg, repo, tmp_path):
    cfg2 = dataclasses.replace(cfg, roots=cfg.roots + ((tmp_path / "gone"),))
    assert paths.list_projects(cfg2) == ["proj"]
