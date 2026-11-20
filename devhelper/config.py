"""Settings read from environment variables, kept in one immutable object."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

HERE = Path(__file__).resolve().parent.parent  # the dev-mcp folder


@dataclass(frozen=True)
class GithubAccount:
    remote: str                      # name of the git remote, e.g. "origin"
    user: str                        # GitHub username
    token: str = field(repr=False)   # never shown in logs or tracebacks


def parse_github(raw: str) -> tuple[GithubAccount, ...]:
    """Parse "origin=UserA:token,yassu=UserB:token". Malformed entries are skipped."""
    accounts = []
    for part in raw.split(","):
        remote, sep, rest = part.strip().partition("=")
        user, sep2, token = rest.partition(":")
        if sep and sep2 and remote.strip() and user.strip() and token.strip():
            accounts.append(GithubAccount(remote.strip(), user.strip(), token.strip()))
    return tuple(accounts)


@dataclass(frozen=True)
class Config:
    roots: tuple[Path, ...]
    log_path: Path
    my_remotes: tuple[str, ...] = ()
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = field(default="", repr=False)
    github: tuple[GithubAccount, ...] = ()
    max_output: int = 8000        # characters returned to the model
    log_max_bytes: int = 1_000_000

    @property
    def primary_root(self) -> Path:
        """Where new projects are created."""
        return self.roots[0]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        raw = env.get("DEV_MCP_ROOTS") or env.get("DEV_MCP_ROOT") or str(Path.home())
        roots: list[Path] = []
        for part in raw.split(";"):
            if part.strip():
                r = Path(part.strip()).expanduser().resolve()
                if r not in roots:
                    roots.append(r)
        remotes = tuple(
            r.strip() for r in env.get("DEV_MCP_MY_REMOTES", "").split(",") if r.strip()
        )
        return cls(
            roots=tuple(roots),
            log_path=Path(env.get("DEV_MCP_LOG") or HERE / "dev-helper.log"),
            my_remotes=remotes,
            gitlab_url=(env.get("GITLAB_URL") or "https://gitlab.com").rstrip("/"),
            gitlab_token=env.get("GITLAB_TOKEN", ""),
            github=parse_github(env.get("DEV_MCP_GITHUB", "")),
        )
