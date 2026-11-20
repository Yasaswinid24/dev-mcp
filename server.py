"""Developer MCP server: local git, tests, Docker, GitLab CI and project scaffolding.

Runs over stdio. This file only declares the tools Claude sees; the logic lives in the
devhelper package. The docstrings below are what Claude reads to decide when to use
each tool, so keep them clear.

Environment variables:
  DEV_MCP_ROOTS       Folders to watch, separated by ";". Each may contain projects or be
                      a git project itself (default: your home folder).
                      DEV_MCP_ROOT (one folder) still works.
  DEV_MCP_MY_REMOTES  Remotes for push_my_accounts, e.g. "yassu,origin". The last one
                      becomes the tracking (upstream) branch.
  DEV_MCP_GITHUB      GitHub accounts for create_github_repos, as
                      "remote=username:token,remote2=username2:token2". Use a token that
                      may create repositories (classic token: "repo" scope). Keep it out
                      of git: it lives only in the Claude Desktop config.
  DEV_MCP_LOG         Log file path (default: dev-helper.log next to this file)
  GITLAB_URL          e.g. https://gitlab.com (default) or your university GitLab
  GITLAB_TOKEN        GitLab personal access token with read_api scope
"""

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from devhelper import ops
from devhelper.calllog import make_safe
from devhelper.config import Config

cfg = Config.from_env()
mcp = _Server("dev-helper")
_safe = make_safe(cfg)


# ------------------------------------------------------------------- git
@mcp.tool()
@_safe
def list_projects() -> list[str]:
    """List git projects found in the watched folders (the folders themselves included)."""
    return ops.list_projects(cfg)


@mcp.tool()
@_safe
def git_status(project: str) -> str:
    """Show branch, changed files and configured remotes for a project folder."""
    return ops.git_status(cfg, project)


@mcp.tool()
@_safe
def git_commit(
    project: str,
    message: str,
    files: list[str] | None = None,
    add_all: bool = False,
) -> str:
    """Create a commit. By default only commits what is already staged.

    Pass files=["a.py", "README.md"] to stage and commit just those files, or
    add_all=true to stage everything. Staging everything is refused if it would
    include likely secrets (.env, keys, tokens). Use git_diff first to review.
    """
    return ops.git_commit(cfg, project, message, files, add_all)


@mcp.tool()
@_safe
def git_diff(project: str, staged: bool = False, path: str = "") -> str:
    """Show what changed: a file summary plus the diff (truncated if very long).

    staged=true shows what is staged for the next commit. path limits it to one file.
    Use this to review changes before committing and to write a good commit message.
    """
    return ops.git_diff(cfg, project, staged, path)


@mcp.tool()
@_safe
def git_log(project: str, count: int = 10) -> str:
    """Show the last few commits, one per line."""
    return ops.git_log(cfg, project, count)


@mcp.tool()
@_safe
def git_push(
    project: str, remotes: list[str], branch: str = "main", confirm: bool = False
) -> str:
    """Push a branch to one or more named remotes (for example ["sai", "yassu"]).

    Pushing changes other people's repositories, so it only runs when confirm=True.
    Ask the user to confirm the remote names first.
    """
    return ops.push(cfg, project, remotes, branch, confirm)


@mcp.tool()
@_safe
def push_my_accounts(project: str, branch: str = "main", confirm: bool = False) -> str:
    """Push a branch to your own accounts' remotes, set in DEV_MCP_MY_REMOTES.

    One call replaces pushing to each account separately. Dry run unless confirm=true,
    so show the user the remotes and ask first. The last remote in the list becomes the
    branch's upstream (tracking) remote.
    """
    return ops.push_my_accounts(cfg, project, branch, confirm)


@mcp.tool()
@_safe
def create_github_repos(
    project: str,
    name: str = "",
    private: bool = True,
    description: str = "",
    confirm: bool = False,
) -> str:
    """Create a new, empty GitHub repository for a project on each of your accounts.

    Uses the accounts in DEV_MCP_GITHUB and points one git remote at each. Private by
    default; only pass private=false if the user explicitly wants it public. Dry run
    unless confirm=true, so show the user the plan first. name defaults to the project
    folder name. Does not push: call push_my_accounts afterwards. Skips repos that
    already exist.
    """
    return ops.create_github_repos(cfg, project, name, private, description, confirm)


# ------------------------------------------------------- tests and docker
@mcp.tool()
@_safe
def run_tests(project: str, extra_args: str = "") -> str:
    """Run pytest in a project folder and return the summary and failures."""
    return ops.run_tests(cfg, project, extra_args)


@mcp.tool()
@_safe
def docker_build(project: str, tag: str) -> str:
    """Build a Docker image from the Dockerfile in a project folder."""
    return ops.docker_build(cfg, project, tag)


# ---------------------------------------------------------------- GitLab
@mcp.tool()
@_safe
def gitlab_pipeline_status(project_path: str) -> str:
    """Show the latest pipeline and any failed jobs for a GitLab project.

    project_path is the full path, such as "group/subgroup/project".
    """
    return ops.gitlab_pipeline_status(cfg, project_path)


@mcp.tool()
@_safe
def gitlab_failed_job_log(project_path: str, job_id: int, last_lines: int = 60) -> str:
    """Return the last lines of a job log, to see why a CI job failed."""
    return ops.gitlab_failed_job_log(cfg, project_path, job_id, last_lines)


# -------------------------------------------------------------- scaffold
@mcp.tool()
@_safe
def scaffold_fastapi_project(name: str) -> str:
    """Create a new FastAPI project (app, test, Dockerfile, CI file, README) in the root."""
    return ops.scaffold_fastapi_project(cfg, name)


# ------------------------------------------------------------------- log
@mcp.tool()
@_safe
def show_log(count: int = 20) -> str:
    """Show the most recent tool calls this server ran (time, tool, arguments, outcome)."""
    return ops.show_log(cfg, count)


if __name__ == "__main__":
    mcp.run()
