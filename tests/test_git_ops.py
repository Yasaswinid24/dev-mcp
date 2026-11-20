import pytest

from devhelper import ops
from tests.conftest import git


# ------------------------------------------------------------------- commit
def test_commit_with_nothing_staged_explains_and_commits_nothing(cfg, repo):
    (repo / "new.txt").write_text("x\n")
    out = ops.git_commit(cfg, "proj", "msg")
    assert "Nothing is staged" in out and "new.txt" in out
    assert git(repo, "rev-list", "--count", "HEAD") == "1"


def test_commit_chosen_files_only(cfg, repo):
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    out = ops.git_commit(cfg, "proj", "add a", files=["a.txt"])
    assert "exit code" not in out
    assert "a.txt" in git(repo, "show", "--name-only", "--format=", "HEAD")
    assert "b.txt" not in git(repo, "show", "--name-only", "--format=", "HEAD")


def test_commit_add_all_stages_everything(cfg, repo):
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    ops.git_commit(cfg, "proj", "all", add_all=True)
    assert git(repo, "status", "--porcelain") == ""


def test_add_all_refuses_secrets_and_stages_nothing(cfg, repo):
    (repo / "deploy.pem").write_text("KEY\n")
    (repo / "ok.txt").write_text("ok\n")
    out = ops.git_commit(cfg, "proj", "x", add_all=True)
    assert out.startswith("Refusing add_all") and "deploy.pem" in out
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_chosen_secret_file_is_refused(cfg, repo):
    (repo / ".env").write_text("T=1\n")
    assert ops.git_commit(cfg, "proj", "x", files=[".env"]).startswith("Refusing to stage")


def test_files_outside_the_project_are_refused(cfg, repo):
    with pytest.raises(ValueError, match="outside the project folder"):
        ops.git_commit(cfg, "proj", "x", files=["../elsewhere.txt"])


def test_empty_message_is_refused(cfg, repo):
    assert ops.git_commit(cfg, "proj", "   ") == "Commit message must not be empty."


def test_staged_file_name_ending_in_k_or_o_still_commits(cfg, repo):
    (repo / "book").write_text("a\n")
    git(repo, "add", "book")
    assert "exit code" not in ops.git_commit(cfg, "proj", "add book")


# --------------------------------------------------------------------- diff
def test_diff_shows_changes_and_reports_none_when_clean(cfg, repo):
    assert ops.git_diff(cfg, "proj") == "No changes."
    (repo / "README.md").write_text("# changed\n")
    out = ops.git_diff(cfg, "proj")
    assert "README.md" in out and "+# changed" in out


def test_diff_staged_and_single_path(cfg, repo):
    (repo / "README.md").write_text("# changed\n")
    git(repo, "add", "README.md")
    assert "+# changed" in ops.git_diff(cfg, "proj", staged=True)
    assert "README.md" in ops.git_diff(cfg, "proj", staged=True, path="README.md")


def test_diff_path_cannot_escape(cfg, repo):
    with pytest.raises(ValueError):
        ops.git_diff(cfg, "proj", path="../outside")


# ---------------------------------------------------------------- status/log
def test_status_lists_branch_and_remotes(cfg, repo, bare_remote):
    git(repo, "remote", "add", "one", str(bare_remote("one")))
    out = ops.git_status(cfg, "proj")
    assert "## main" in out and "one" in out


def test_log_shows_commits_and_clamps_count(cfg, repo):
    assert "first" in ops.git_log(cfg, "proj", count=999)
    assert "first" in ops.git_log(cfg, "proj", count=0)


# --------------------------------------------------------------------- push
@pytest.fixture
def with_remotes(repo, bare_remote):
    for name in ("one", "two"):
        git(repo, "remote", "add", name, str(bare_remote(name)))
    return repo


def test_push_is_a_dry_run_without_confirm(cfg, with_remotes, bare_remote):
    out = ops.push(cfg, "proj", ["one"], "main", confirm=False)
    assert out.startswith("DRY RUN")
    # nothing reached the remote
    assert git(with_remotes, "ls-remote", "one") == ""


def test_push_unknown_remote_is_refused(cfg, with_remotes):
    out = ops.push(cfg, "proj", ["nope"], "main", confirm=True)
    assert out.startswith("Unknown remotes")


def test_push_with_confirm_reaches_the_remote(cfg, with_remotes):
    out = ops.push(cfg, "proj", ["one", "two"], "main", confirm=True)
    assert "--- one ---" in out and "--- two ---" in out
    assert "refs/heads/main" in git(with_remotes, "ls-remote", "one")
    assert "refs/heads/main" in git(with_remotes, "ls-remote", "two")


def test_push_my_accounts_pushes_and_tracks_the_last_remote(cfg, with_remotes):
    ops.push_my_accounts(cfg, "proj", "main", confirm=True)
    assert git(with_remotes, "rev-parse", "--abbrev-ref", "@{u}") == "two/main"


def test_push_my_accounts_is_a_dry_run_by_default(cfg, with_remotes):
    out = ops.push_my_accounts(cfg, "proj", "main", confirm=False)
    assert out.startswith("DRY RUN") and "'one', 'two'" in out


def test_push_my_accounts_needs_configured_remotes(cfg, repo):
    import dataclasses
    with pytest.raises(ValueError, match="DEV_MCP_MY_REMOTES"):
        ops.push_my_accounts(dataclasses.replace(cfg, my_remotes=()), "proj", "main", False)


# ------------------------------------------------------------ tests, docker
def test_python_for_prefers_project_venv(repo):
    assert ops.python_for(repo) == "python"
    venv_python = repo / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    assert ops.python_for(repo) == str(venv_python)


def test_run_tests_reports_which_python_it_used(cfg, repo):
    (repo / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    out = ops.run_tests(cfg, "proj")
    assert out.startswith("Using Python:") and "1 passed" in out


def test_docker_build_needs_dockerfile_and_clean_tag(cfg, repo):
    assert ops.docker_build(cfg, "proj", "x:1") == "No Dockerfile found in this project."
    (repo / "Dockerfile").write_text("FROM scratch\n")
    assert "without spaces" in ops.docker_build(cfg, "proj", "bad tag")
