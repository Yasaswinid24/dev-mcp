"""GitHub repo creation, with the GitHub API replaced by a fake."""

import io
import json
import urllib.error

import pytest

from devhelper import calllog, github, ops
from devhelper.config import Config, GithubAccount, parse_github

from tests.conftest import git

TOKEN_A = "ghp_SECRETAAAA"
TOKEN_B = "ghp_SECRETBBBB"


class FakeGitHub:
    """Stands in for urllib.request.urlopen. State: which repos exist per user."""

    def __init__(self, tokens, existing=()):
        self.tokens = tokens            # token -> login
        self.repos = set(existing)      # {"user/name"}
        self.calls = []                 # (method, path, body)
        self.fail_create = None         # status code to return on POST

    def __call__(self, req, timeout=None):
        method, path = req.get_method(), req.full_url.replace(github.API, "")
        body = json.loads(req.data) if req.data else None
        self.calls.append((method, path, body))
        auth = req.headers.get("Authorization", "")
        login = self.tokens.get(auth.removeprefix("Bearer "))

        def http_error(code, msg="x"):
            return urllib.error.HTTPError(
                req.full_url, code, msg, {}, io.BytesIO(json.dumps({"message": msg}).encode()))

        def ok(code, obj):
            class R:
                status = code
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def read(s): return json.dumps(obj).encode()
            return R()

        if login is None:
            raise http_error(401, "Bad credentials")
        if path == "/user":
            return ok(200, {"login": login})
        if method == "GET" and path.startswith("/repos/"):
            if path.removeprefix("/repos/") in self.repos:
                return ok(200, {})
            raise http_error(404, "Not Found")
        if method == "POST" and path == "/user/repos":
            if self.fail_create:
                raise http_error(self.fail_create, "nope")
            self.repos.add(f"{login}/{body['name']}")
            return ok(201, {"html_url": "x"})
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def fake(monkeypatch):
    f = FakeGitHub({TOKEN_A: "UserA", TOKEN_B: "UserB"})
    monkeypatch.setattr("urllib.request.urlopen", f)
    return f


@pytest.fixture
def gcfg(cfg):
    return Config(
        roots=cfg.roots, log_path=cfg.log_path, my_remotes=("origin", "yassu"),
        github=(GithubAccount("origin", "UserA", TOKEN_A),
                GithubAccount("yassu", "UserB", TOKEN_B)),
    )


# ------------------------------------------------------------------ config
def test_parse_github_reads_accounts():
    accts = parse_github(f"origin=UserA:{TOKEN_A}, yassu=UserB:{TOKEN_B}")
    assert [(a.remote, a.user, a.token) for a in accts] == [
        ("origin", "UserA", TOKEN_A), ("yassu", "UserB", TOKEN_B)]


@pytest.mark.parametrize("raw", ["", "origin", "origin=UserA", "origin=UserA:", "=u:t", "origin=:t"])
def test_parse_github_skips_malformed(raw):
    assert parse_github(raw) == ()


def test_token_not_in_repr(gcfg):
    assert TOKEN_A not in repr(gcfg)
    assert TOKEN_B not in repr(gcfg)


def test_from_env_reads_github():
    c = Config.from_env({"DEV_MCP_ROOTS": "/tmp", "DEV_MCP_GITHUB": f"origin=UserA:{TOKEN_A}"})
    assert c.github[0].user == "UserA"


# -------------------------------------------------------------------- ops
def test_dry_run_creates_nothing(gcfg, repo, fake):
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=False)
    assert "DRY RUN" in out and "UserA" in out and "UserB" in out and "private" in out
    assert fake.calls == []
    assert git(repo, "remote") == ""


def test_dry_run_warns_when_public(gcfg, repo, fake):
    out = ops.create_github_repos(gcfg, "proj", "", False, "", confirm=False)
    assert "PUBLIC" in out


def test_confirm_creates_repos_and_remotes(gcfg, repo, fake):
    out = ops.create_github_repos(gcfg, "proj", "", True, "my tool", confirm=True)
    assert fake.repos == {"UserA/proj", "UserB/proj"}
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert all(b["private"] is True and b["description"] == "my tool" for _, _, b in posts)
    assert git(repo, "remote", "get-url", "origin") == "https://UserA@github.com/UserA/proj.git"
    assert git(repo, "remote", "get-url", "yassu") == "https://UserB@github.com/UserB/proj.git"
    assert "created" in out


def test_custom_name_and_public(gcfg, repo, fake):
    ops.create_github_repos(gcfg, "proj", "cool-name", False, "", confirm=True)
    posts = [b for m, _, b in fake.calls if m == "POST"]
    assert all(b["name"] == "cool-name" and b["private"] is False for b in posts)


def test_existing_remote_is_updated_and_existing_repo_skipped(gcfg, repo, fake):
    git(repo, "remote", "add", "origin", "https://github.com/old/place.git")
    fake.repos.add("UserA/proj")
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    assert git(repo, "remote", "get-url", "origin") == "https://UserA@github.com/UserA/proj.git"
    assert "already exists" in out
    assert [c for c in fake.calls if c[0] == "POST" and c[2]["name"] == "proj"].__len__() == 1


def test_rerun_is_safe(gcfg, repo, fake):
    ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    posts_before = len([c for c in fake.calls if c[0] == "POST"])
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    assert len([c for c in fake.calls if c[0] == "POST"]) == posts_before
    assert out.count("already exists") == 2


def test_token_never_in_output_or_remote(gcfg, repo, fake):
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    assert TOKEN_A not in out and TOKEN_B not in out
    assert TOKEN_A not in git(repo, "remote", "-v") and TOKEN_B not in git(repo, "remote", "-v")


def test_swapped_tokens_are_caught(cfg, repo, fake):
    swapped = Config(roots=cfg.roots, log_path=cfg.log_path,
                     github=(GithubAccount("origin", "UserA", TOKEN_B),))
    out = ops.create_github_repos(swapped, "proj", "", True, "", confirm=True)
    assert "belongs to 'UserB'" in out
    assert fake.repos == set()
    assert git(repo, "remote") == ""


def test_one_account_failing_does_not_block_the_other(gcfg, repo, fake):
    bad = Config(roots=gcfg.roots, log_path=gcfg.log_path, github=(
        GithubAccount("origin", "UserA", "wrong-token"), gcfg.github[1]))
    out = ops.create_github_repos(bad, "proj", "", True, "", confirm=True)
    assert "UserA: FAILED" in out and "rejected the token" in out
    assert "UserB/proj" in fake.repos
    assert git(repo, "remote") == "yassu"


def test_create_forbidden_gives_helpful_message(gcfg, repo, fake):
    fake.fail_create = 403
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    assert "'repo' scope" in out


def test_no_accounts_configured(cfg, repo):
    with pytest.raises(ValueError, match="DEV_MCP_GITHUB"):
        ops.create_github_repos(cfg, "proj", "", True, "", confirm=True)


@pytest.mark.parametrize("bad", ["has space", "a/b", "..", "x.git", "name;rm", "ä"])
def test_invalid_repo_names_refused(gcfg, repo, fake, bad):
    with pytest.raises(ValueError, match="not a valid"):
        ops.create_github_repos(gcfg, "proj", bad, True, "", confirm=True)
    assert fake.calls == []


def test_project_outside_roots_refused(gcfg, fake, tmp_path):
    with pytest.raises(ValueError):
        ops.create_github_repos(gcfg, str(tmp_path), "", True, "", confirm=True)
    assert fake.calls == []


def test_network_error_is_readable(gcfg, repo, monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    out = ops.create_github_repos(gcfg, "proj", "", True, "", confirm=True)
    assert "Could not reach GitHub" in out


def test_call_log_has_no_tokens(gcfg, repo, fake):
    @calllog.make_safe(gcfg)
    def create_github_repos(project: str, confirm: bool = False) -> str:
        return ops.create_github_repos(gcfg, project, "", True, "", confirm)

    create_github_repos("proj", confirm=True)
    text = gcfg.log_path.read_text()
    assert "create_github_repos" in text
    assert TOKEN_A not in text and TOKEN_B not in text
