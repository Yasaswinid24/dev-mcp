# dev-helper MCP

A small MCP server that gives Claude tools for your local developer workflow.
It complements the official GitHub MCP: GitHub's server works on github.com, this one works on your computer.

## Tools

| Tool | What it does |
|---|---|
| `list_projects` | Git projects in all watched folders |
| `git_status` | Branch, changed files, remotes |
| `git_diff` | Show what changed (all, staged, or one file) to review before committing |
| `git_commit` | Commit what is staged, or stage chosen `files=[...]`, or `add_all=true`. Refuses likely secrets (.env, keys) |
| `git_log` | Last commits |
| `git_push` | Push to one or more named remotes. Dry run unless `confirm=true` |
| `push_my_accounts` | Push to the remotes in `DEV_MCP_MY_REMOTES` (for example `yassu,origin`). Dry run unless `confirm=true`. The last remote becomes the upstream |
| `show_log` | The most recent tool calls: time, tool, arguments, outcome |
| `run_tests` | Run pytest using the project's own `.venv`/`venv` Python (falls back to `python` on PATH) |
| `docker_build` | Build an image from the project's Dockerfile |
| `gitlab_pipeline_status` | Latest pipeline and failed jobs |
| `gitlab_failed_job_log` | Tail of a failed job's log |
| `scaffold_fastapi_project` | New FastAPI project with test, Dockerfile, CI file, README |

## Safety

- Every path is restricted to the folders in `DEV_MCP_ROOTS`. Anything outside them is refused, and a name that exists in two watched folders is refused as ambiguous.
- Every tool call is written to `dev-helper.log` (JSON lines, rotated at 1 MB). Review it with `show_log`.
- `git_push` only pushes after `confirm=true`. Claude should ask you first.
- No shell is used, so tool inputs cannot inject commands.
- Nothing deletes files, and there is no force push.
- The GitLab token only needs the `read_api` scope.

## Setup on Windows (PowerShell)

```powershell
cd C:\Users\Ravi\dev-mcp          # wherever you put this folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python test_client.py             # optional smoke test, needs git on PATH
```

### Claude Desktop

Open `%APPDATA%\Claude\claude_desktop_config.json` and add (use your real paths, double backslashes):

```json
{
  "mcpServers": {
    "dev-helper": {
      "command": "C:\\Users\\Ravi\\dev-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Ravi\\dev-mcp\\server.py"],
      "env": {
        "DEV_MCP_ROOTS": "C:\\Users\\Ravi\\Projects;C:\\Users\\Ravi\\my-repo",
        "DEV_MCP_MY_REMOTES": "yassu,origin",
        "GITLAB_URL": "https://gitlab.com",
        "GITLAB_TOKEN": "paste-read_api-token-here"
      }
    }
  }
}
```

Restart Claude Desktop completely (quit from the tray), then check that `dev-helper` shows up under connectors/tools.

### Claude Code

```powershell
claude mcp add dev-helper -- C:\Users\Ravi\dev-mcp\.venv\Scripts\python.exe C:\Users\Ravi\dev-mcp\server.py
```

## Pushing to both GitHub accounts

Add each account as a named remote once, then push to both in one call:

```powershell
git remote add sai   https://github.com/SaiVamshi45/<repo>.git
git remote add yassu https://github.com/Yassu-24/<repo>.git
```

Then ask Claude: "push demo-api to sai and yassu". Claude calls `git_push` with a dry run, asks you to confirm, then pushes.
Login still comes from Git Credential Manager, so sign in to each account the first time.

## Try these prompts

- "Which of my projects have uncommitted changes?"
- "Run the tests in job-email-classifier and tell me what failed."
- "Why did the last pipeline in group/project fail?"
- "Scaffold a FastAPI project called expense-api."

## Settings (environment variables)

| Name | Meaning |
|---|---|
| `DEV_MCP_ROOTS` | Folders to watch, separated by `;`. Each can hold projects or be a repo itself. `DEV_MCP_ROOT` (one folder) still works |
| `DEV_MCP_MY_REMOTES` | Remotes for `push_my_accounts`, comma separated |
| `DEV_MCP_LOG` | Log file path (default: `dev-helper.log` next to `server.py`) |
| `GITLAB_URL`, `GITLAB_TOKEN` | For the GitLab tools |

Easiest way to write these into Claude Desktop's config: `python register_desktop.py` (quit the app first).

## Project layout

```
server.py            the tools Claude sees (names, docstrings); thin wrappers
devhelper/
  config.py          settings from environment variables
  paths.py           project lookup and folder restrictions
  runner.py          run commands safely (no shell, timeout, trimmed output)
  safety.py          detects secret files (.env, keys)
  ops.py             the logic behind every tool
  gitlab.py          read-only GitLab API calls
  calllog.py         call log and the error-handling decorator
tests/               76 unit tests (pytest)
test_client.py       28 end-to-end checks against the real server over stdio
.gitlab-ci.yml       CI for GitLab
.github/workflows/   CI for GitHub Actions
register_desktop.py  writes dev-helper into Claude Desktop's config
```

## Development

```powershell
pip install -r requirements-dev.txt
pytest                  # 76 unit tests, a few seconds
python test_client.py   # 28 end-to-end checks
```

The unit tests use throw-away git repos in temporary folders and a mocked GitLab,
so they never touch your real projects or the network. CI runs both on every push
(GitLab: unit-tests and integration-test jobs; GitHub: Python 3.11 to 3.13).

Adding a tool: write the logic in `devhelper/ops.py` with a test in `tests/`,
then add a short wrapper with a clear docstring in `server.py`.
Restart Claude Desktop afterwards so it loads the new version.

## Changes in version 1.3

- Code split into the `devhelper` package, with 76 unit tests and CI files.
- `gitlab_pipeline_status` now shows job ids, so Claude can fetch a failed job's log.
- Network errors from GitLab give a readable message.
- Command output is decoded as UTF-8 with replacement, so odd characters on Windows no longer break a tool.

## Changes in version 1.2

- Several watched folders (`DEV_MCP_ROOTS`).
- Every tool call is logged; `show_log` shows recent calls.
- `push_my_accounts` pushes to your own accounts' remotes in one step.
- 28 end-to-end checks in `test_client.py`.

## Changes in version 1.1

- New `git_diff` tool.
- `git_commit` no longer stages everything by default. It commits what is staged, chosen files, or everything with `add_all=true`, and refuses likely secrets.
- `run_tests` uses the project's own virtual environment when it has one.
- The smoke test now prints 16 PASS/FAIL checks.

## Ideas for version 2

- Split `server.py` into modules and add unit tests plus a CI file.
- A `docker_run` tool for health checks.
- A Streamable HTTP version with OAuth to use it from any device.
