"""Create GitHub repositories through the REST API, one token per account.

Only two calls are made: look up who a token belongs to, and create a repo. Tokens are
sent in a header and are never put in remote URLs, results, or the call log.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import GithubAccount

API = "https://api.github.com"


def _call(acct: GithubAccount, method: str, path: str, body: dict | None = None):
    """Return (status, parsed JSON or None). Network failures raise ValueError."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {acct.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "dev-helper-mcp",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            parsed = None
        return e.code, parsed
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach GitHub: {e.reason}") from e


def _message(parsed) -> str:
    if isinstance(parsed, dict):
        msg = str(parsed.get("message", ""))
        errs = parsed.get("errors")
        if errs:
            msg += f" {errs}"
        return msg.strip()
    return ""


def whoami(acct: GithubAccount) -> str:
    status, parsed = _call(acct, "GET", "/user")
    if status == 401:
        raise ValueError(f"GitHub rejected the token for '{acct.user}' (expired or wrong).")
    if status != 200 or not isinstance(parsed, dict):
        raise ValueError(f"GitHub returned {status} when checking the token: {_message(parsed)}")
    return str(parsed.get("login", ""))


def ensure_repo(acct: GithubAccount, name: str, private: bool, description: str = "") -> str:
    """Create user/name if it does not exist. Returns 'created' or 'already exists'."""
    login = whoami(acct)
    if login.lower() != acct.user.lower():
        raise ValueError(
            f"The token for '{acct.user}' belongs to '{login}'. "
            "Nothing was created; check the tokens in DEV_MCP_GITHUB."
        )
    status, parsed = _call(acct, "GET", f"/repos/{acct.user}/{name}")
    if status == 200:
        return "already exists"
    if status != 404:
        raise ValueError(f"GitHub returned {status} when checking the repo: {_message(parsed)}")
    body = {"name": name, "private": private, "auto_init": False}
    if description:
        body["description"] = description
    status, parsed = _call(acct, "POST", "/user/repos", body)
    if status == 201:
        return "created"
    if status in (401, 403, 404):
        raise ValueError(
            f"GitHub refused to create the repo ({status}). The token needs permission "
            f"to create repositories (classic token: 'repo' scope). {_message(parsed)}"
        )
    raise ValueError(f"GitHub returned {status} when creating the repo: {_message(parsed)}")
