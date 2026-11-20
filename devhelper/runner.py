"""Run external commands safely: no shell, a timeout, and trimmed output."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path, timeout: int = 120, max_output: int = 8000) -> str:
    """Run a command and return trimmed combined output.

    Returns "ok" for a silent success, "exit code N\\n<output>" for a failure.
    """
    try:
        r = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except FileNotFoundError:
        return f"Command not found: {args[0]}. Is it installed and on PATH?"
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s: {' '.join(args)}"
    out = (r.stdout + r.stderr).strip()
    if len(out) > max_output:
        out = "...(truncated)...\n" + out[-max_output:]
    return f"exit code {r.returncode}\n{out}" if r.returncode else (out or "ok")


def git_lines(args: list[str], cwd: Path) -> list[str]:
    """Run a git command and return its non-empty output lines (empty on failure)."""
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    return [line for line in r.stdout.splitlines() if line]
