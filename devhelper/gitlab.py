"""Read-only GitLab API calls for pipeline status and failed-job logs."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .config import Config


def api_get(cfg: Config, path: str) -> str:
    if not cfg.gitlab_token:
        raise ValueError("Set GITLAB_TOKEN (read_api scope) in the MCP config.")
    req = urllib.request.Request(
        f"{cfg.gitlab_url}/api/v4{path}", headers={"PRIVATE-TOKEN": cfg.gitlab_token}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"GitLab returned {e.code} for {path}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach GitLab at {cfg.gitlab_url}: {e.reason}") from e


def pipeline_status(cfg: Config, project_path: str) -> str:
    pid = urllib.parse.quote(project_path, safe="")
    pipelines = json.loads(api_get(cfg, f"/projects/{pid}/pipelines?per_page=1"))
    if not pipelines:
        return "No pipelines found."
    pl = pipelines[0]
    lines = [
        f"Pipeline #{pl['id']} on '{pl['ref']}': {pl['status']}",
        f"Link: {pl['web_url']}",
    ]
    jobs = json.loads(api_get(cfg, f"/projects/{pid}/pipelines/{pl['id']}/jobs?per_page=50"))
    failed = [j for j in jobs if j["status"] == "failed"]
    for j in failed:
        lines.append(f"FAILED job '{j['name']}' (stage {j['stage']}) (job id {j['id']}) - {j['web_url']}")
    if not failed:
        lines.append("No failed jobs.")
    return "\n".join(lines)


def failed_job_log(cfg: Config, project_path: str, job_id: int, last_lines: int = 60) -> str:
    pid = urllib.parse.quote(project_path, safe="")
    log = api_get(cfg, f"/projects/{pid}/jobs/{job_id}/trace")
    tail = "\n".join(log.splitlines()[-max(1, min(last_lines, 300)):])
    return tail[-cfg.max_output:]
