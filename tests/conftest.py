"""Shared fixtures: temporary folders, throw-away git repos, and a ready-made Config."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devhelper.config import Config  # noqa: E402


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Let git commit inside tests without touching the user's real git config."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def make_repo():
    """Factory: make_repo(parent, name) creates a git repo with one commit."""

    def _make(parent: Path, name: str) -> Path:
        repo = parent / name
        repo.mkdir(parents=True)
        git(repo, "init", "-b", "main")
        (repo / "README.md").write_text("# hello\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "first")
        return repo

    return _make


@pytest.fixture
def root(tmp_path) -> Path:
    r = tmp_path / "root"
    r.mkdir()
    return r.resolve()


@pytest.fixture
def cfg(root, tmp_path) -> Config:
    return Config(
        roots=(root,),
        log_path=tmp_path / "calls.log",
        my_remotes=("one", "two"),
    )


@pytest.fixture
def repo(root, make_repo) -> Path:
    return make_repo(root, "proj").resolve()


@pytest.fixture
def bare_remote(tmp_path):
    """Factory: bare_remote("name") makes an empty bare repo to push into."""

    def _make(name: str) -> Path:
        path = tmp_path / "remotes" / f"{name}.git"
        path.parent.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "--bare", str(path)], capture_output=True, check=True)
        return path

    return _make
