import dataclasses
import io
import json
import urllib.error

import pytest

from devhelper import gitlab, ops


class FakeResponse:
    def __init__(self, payload):
        self._data = payload if isinstance(payload, str) else json.dumps(payload)

    def read(self):
        return self._data.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def gl_cfg(cfg):
    return dataclasses.replace(cfg, gitlab_token="tok", gitlab_url="https://gl.example")


def fake_urlopen(routes):
    def _open(req, timeout=0):
        for needle, payload in routes.items():
            if needle in req.full_url:
                assert req.headers["Private-token"] == "tok"
                return FakeResponse(payload)
        raise AssertionError(f"unexpected URL {req.full_url}")
    return _open


# ------------------------------------------------------------------- GitLab
def test_missing_token_gives_clear_error(cfg):
    with pytest.raises(ValueError, match="GITLAB_TOKEN"):
        gitlab.pipeline_status(cfg, "g/p")


def test_pipeline_status_lists_failed_jobs_with_ids(gl_cfg, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen({
        "/pipelines?per_page=1": [{"id": 7, "ref": "main", "status": "failed", "web_url": "u"}],
        "/pipelines/7/jobs": [
            {"id": 11, "name": "lint", "stage": "test", "status": "success", "web_url": "a"},
            {"id": 12, "name": "unit", "stage": "test", "status": "failed", "web_url": "b"},
        ],
    }))
    out = gitlab.pipeline_status(gl_cfg, "group/sub/proj")
    assert "Pipeline #7 on 'main': failed" in out
    assert "FAILED job 'unit'" in out and "job id 12" in out
    assert "lint" not in out


def test_pipeline_status_all_green(gl_cfg, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen({
        "/pipelines?per_page=1": [{"id": 1, "ref": "main", "status": "success", "web_url": "u"}],
        "/pipelines/1/jobs": [{"id": 2, "name": "t", "stage": "s", "status": "success", "web_url": "x"}],
    }))
    assert "No failed jobs." in gitlab.pipeline_status(gl_cfg, "g/p")


def test_no_pipelines(gl_cfg, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen({"/pipelines?per_page=1": []}))
    assert gitlab.pipeline_status(gl_cfg, "g/p") == "No pipelines found."


def test_project_path_is_url_encoded(gl_cfg, monkeypatch):
    seen = []

    def _open(req, timeout=0):
        seen.append(req.full_url)
        return FakeResponse([])

    monkeypatch.setattr("urllib.request.urlopen", _open)
    gitlab.pipeline_status(gl_cfg, "group/sub/proj")
    assert "group%2Fsub%2Fproj" in seen[0]


def test_failed_job_log_returns_only_the_tail(gl_cfg, monkeypatch):
    log = "\n".join(f"line {i}" for i in range(500))
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen({"/trace": log}))
    out = gitlab.failed_job_log(gl_cfg, "g/p", 9, last_lines=3)
    assert out.splitlines() == ["line 497", "line 498", "line 499"]


def test_http_errors_become_readable_messages(gl_cfg, monkeypatch):
    def _open(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", _open)
    with pytest.raises(ValueError, match="404"):
        gitlab.pipeline_status(gl_cfg, "g/p")


def test_unreachable_server_becomes_a_readable_message(gl_cfg, monkeypatch):
    def _open(req, timeout=0):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", _open)
    with pytest.raises(ValueError, match="Could not reach GitLab"):
        gitlab.pipeline_status(gl_cfg, "g/p")


# ----------------------------------------------------------------- scaffold
def test_scaffold_creates_a_runnable_project(cfg):
    out = ops.scaffold_fastapi_project(cfg, "demo-api")
    p = cfg.primary_root / "demo-api"
    assert "Created" in out and (p / ".git").exists()
    for name in ("app/main.py", "tests/test_health.py", "Dockerfile", ".gitlab-ci.yml",
                 "requirements.txt", "README.md", ".gitignore"):
        assert (p / name).exists(), name
    assert ".env" in (p / ".gitignore").read_text()


def test_scaffold_refuses_existing_and_bad_names(cfg):
    ops.scaffold_fastapi_project(cfg, "demo")
    assert "already exists" in ops.scaffold_fastapi_project(cfg, "demo")
    assert "letters, numbers" in ops.scaffold_fastapi_project(cfg, "bad/name")
    assert "letters, numbers" in ops.scaffold_fastapi_project(cfg, "../evil")
    assert not (cfg.primary_root.parent / "evil").exists()
