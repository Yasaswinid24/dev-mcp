"""The actual work behind each tool. Every function takes a Config and returns text.

Expected problems raise ValueError; server.py turns those into readable messages.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import calllog, github, gitlab, paths
from .config import Config
from .runner import git_lines, run
from .safety import looks_secret


# ------------------------------------------------------------------ helpers
def _run(cfg: Config, args: list[str], cwd: Path, timeout: int = 120) -> str:
    return run(args, cwd, timeout=timeout, max_output=cfg.max_output)


def changed_files(project: Path) -> list[str]:
    """Paths of modified, new or deleted files according to git status."""
    return [
        line[3:].strip().strip('"')
        for line in git_lines(["status", "--porcelain", "-uall"], project)
    ]


def staged_files(project: Path) -> list[str]:
    return git_lines(["diff", "--cached", "--name-only"], project)


def python_for(project: Path) -> str:
    """Prefer the project's own virtual environment, else python on PATH."""
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python",
                "venv/Scripts/python.exe", "venv/bin/python"):
        candidate = project / rel
        if candidate.exists():
            return str(candidate)
    return "python"


# ---------------------------------------------------------------------- git
def list_projects(cfg: Config) -> list[str]:
    return paths.list_projects(cfg)


def git_status(cfg: Config, project: str) -> str:
    p = paths.resolve_project(cfg, project)
    return (
        _run(cfg, ["git", "status", "--short", "--branch"], p)
        + "\n\nRemotes:\n"
        + _run(cfg, ["git", "remote", "-v"], p)
    )


def git_commit(cfg: Config, project: str, message: str,
               files: list[str] | None = None, add_all: bool = False) -> str:
    p = paths.resolve_project(cfg, project)
    if not message.strip():
        return "Commit message must not be empty."

    if files:
        safe_files = [paths.inside_project(p, f) for f in files]
        bad = [f for f in safe_files if looks_secret(f)]
        if bad:
            return f"Refusing to stage likely secret files: {bad}"
        added = _run(cfg, ["git", "add", "--", *safe_files], p)
        if added.startswith("exit code"):
            return added
    elif add_all:
        bad = [f for f in changed_files(p) if looks_secret(f)]
        if bad:
            return (
                f"Refusing add_all: these look like secrets: {bad}. "
                "Add them to .gitignore, or commit chosen files with files=[...]."
            )
        added = _run(cfg, ["git", "add", "-A"], p)
        if added.startswith("exit code"):
            return added

    if not staged_files(p):
        changed = changed_files(p)
        return (
            "Nothing is staged, so nothing was committed. "
            f"Changed files: {changed or 'none'}. "
            "Call again with files=[...] or add_all=true."
        )
    return _run(cfg, ["git", "commit", "-m", message], p)


def git_diff(cfg: Config, project: str, staged: bool = False, path: str = "") -> str:
    p = paths.resolve_project(cfg, project)
    base = ["git", "diff"] + (["--cached"] if staged else [])
    tail = ["--", paths.inside_project(p, path)] if path else []
    stat = _run(cfg, base + ["--stat"] + tail, p)
    body = _run(cfg, base + tail, p)
    return f"{stat}\n\n{body}" if body != "ok" else "No changes."


def git_log(cfg: Config, project: str, count: int = 10) -> str:
    p = paths.resolve_project(cfg, project)
    count = max(1, min(count, 50))
    return _run(cfg, ["git", "log", f"-{count}", "--oneline", "--decorate"], p)


def push(cfg: Config, project: str, remotes: list[str], branch: str, confirm: bool) -> str:
    """Validate remotes, dry run unless confirmed, then push to each in order."""
    p = paths.resolve_project(cfg, project)
    known = _run(cfg, ["git", "remote"], p).split()
    unknown = [r for r in remotes if r not in known]
    if unknown:
        return f"Unknown remotes {unknown}. Configured remotes: {known}"
    if not confirm:
        return (
            f"DRY RUN: would push '{branch}' to {remotes}. "
            "Call again with confirm=true after the user agrees."
        )
    results = []
    for r in remotes:
        results.append(f"--- {r} ---\n" + _run(cfg, ["git", "push", "-u", r, branch], p, 180))
    return "\n".join(results)


def push_my_accounts(cfg: Config, project: str, branch: str, confirm: bool) -> str:
    if not cfg.my_remotes:
        raise ValueError('Set DEV_MCP_MY_REMOTES in the MCP config, for example "yassu,origin".')
    return push(cfg, project, list(cfg.my_remotes), branch, confirm)


REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")


def create_github_repos(cfg: Config, project: str, name: str, private: bool,
                        description: str, confirm: bool) -> str:
    """Create the repo on every configured GitHub account and point a remote at each.

    Does not push. Dry run unless confirm is true.
    """
    p = paths.resolve_project(cfg, project)
    if not cfg.github:
        raise ValueError(
            "No GitHub accounts configured. Set DEV_MCP_GITHUB in the MCP config, "
            'for example "origin=UserA:token,yassu=UserB:token".'
        )
    repo_name = name.strip() or p.name
    if (not REPO_NAME.fullmatch(repo_name) or repo_name in (".", "..")
            or repo_name.endswith(".git")):
        raise ValueError(f"'{repo_name}' is not a valid GitHub repository name.")

    visibility = "private" if private else "PUBLIC"
    known = _run(cfg, ["git", "remote"], p).split()

    if not confirm:
        lines = [f"DRY RUN: would create a {visibility} repository '{repo_name}' on:"]
        for a in cfg.github:
            action = "update" if a.remote in known else "add"
            lines.append(f"  - {a.user}  ({action} remote '{a.remote}')")
        lines.append("Nothing is pushed. Call again with confirm=true after the user agrees"
                     + (" (they asked for PUBLIC, so say so)." if not private else "."))
        return "\n".join(lines)

    lines = []
    for a in cfg.github:
        url = f"https://{a.user}@github.com/{a.user}/{repo_name}.git"
        try:
            outcome = github.ensure_repo(a, repo_name, private, description)
        except ValueError as e:
            lines.append(f"{a.user}: FAILED - {e}")
            continue
        verb = "set-url" if a.remote in known else "add"
        res = _run(cfg, ["git", "remote", verb, a.remote, url], p)
        if res.startswith("exit code"):
            lines.append(f"{a.user}: repo {outcome}, but setting the remote failed: {res}")
        else:
            lines.append(f"{a.user}: repo {outcome} ({visibility}); remote '{a.remote}' -> {url}")
    lines.append("Next: push with push_my_accounts (or git_push) after the user confirms.")
    return "\n".join(lines)


# ------------------------------------------------------------ tests, docker
def run_tests(cfg: Config, project: str, extra_args: str = "") -> str:
    p = paths.resolve_project(cfg, project)
    py = python_for(p)
    args = [py, "-m", "pytest", "-q", "--tb=short"]
    if extra_args.strip():
        args += extra_args.split()
    return f"Using Python: {py}\n" + _run(cfg, args, p, timeout=300)


def docker_build(cfg: Config, project: str, tag: str) -> str:
    p = paths.resolve_project(cfg, project)
    if not (p / "Dockerfile").exists():
        return "No Dockerfile found in this project."
    if not tag or any(c.isspace() for c in tag):
        return "Provide a tag without spaces, like myapp:dev."
    return _run(cfg, ["docker", "build", "-t", tag, "."], p, timeout=600)


# ------------------------------------------------------------------- GitLab
def gitlab_pipeline_status(cfg: Config, project_path: str) -> str:
    return gitlab.pipeline_status(cfg, project_path)


def gitlab_failed_job_log(cfg: Config, project_path: str, job_id: int, last_lines: int = 60) -> str:
    return gitlab.failed_job_log(cfg, project_path, job_id, last_lines)


# ----------------------------------------------------------------- scaffold
def scaffold_fastapi_project(cfg: Config, name: str) -> str:
    if not name.replace("-", "").replace("_", "").isalnum():
        return "Use letters, numbers, - or _ only for the project name."
    p = cfg.primary_root / name
    if p.exists():
        return f"{p} already exists. Choose another name."
    (p / "app").mkdir(parents=True)
    (p / "tests").mkdir()
    files = {
        "app/__init__.py": "",
        "app/main.py": (
            "from fastapi import FastAPI\n\napp = FastAPI(title=\"" + name + "\")\n\n\n"
            "@app.get(\"/health\")\ndef health():\n    return {\"status\": \"ok\"}\n"
        ),
        "tests/test_health.py": (
            "from fastapi.testclient import TestClient\n\nfrom app.main import app\n\n\n"
            "def test_health():\n    r = TestClient(app).get(\"/health\")\n"
            "    assert r.status_code == 200\n    assert r.json() == {\"status\": \"ok\"}\n"
        ),
        "requirements.txt": "fastapi\nuvicorn\nhttpx\npytest\n",
        "Dockerfile": (
            "FROM python:3.12-slim\nWORKDIR /code\n"
            "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n"
            "COPY app app\n"
            "CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n"
        ),
        ".gitlab-ci.yml": (
            "test:\n  image: python:3.12-slim\n  script:\n"
            "    - pip install -r requirements.txt\n    - pytest -q\n"
        ),
        ".gitignore": "__pycache__/\n.venv/\n.env\n",
        "README.md": f"# {name}\n\nRun: `uvicorn app.main:app --reload`\n\nTest: `pytest`\n",
    }
    for rel, content in files.items():
        (p / rel).write_text(content, encoding="utf-8")
    _run(cfg, ["git", "init", "-b", "main"], p)
    return f"Created {p} with {len(files)} files and initialised git."


# ---------------------------------------------------------------------- log
def show_log(cfg: Config, count: int = 20) -> str:
    return calllog.read_recent(cfg, count)
