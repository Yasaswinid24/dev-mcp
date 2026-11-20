"""A JSON-lines log of every tool call, plus the decorator that writes it."""

from __future__ import annotations

import functools
import inspect
import json
import time
from typing import Callable

from .config import Config


def log_call(cfg: Config, tool: str, arguments: dict, result: str, seconds: float) -> None:
    """Append one line per call. A logging problem must never break a tool."""
    try:
        path = cfg.log_path
        if path.exists() and path.stat().st_size > cfg.log_max_bytes:
            path.replace(path.with_name(path.name + ".1"))
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": tool,
            "args": arguments,
            "ok": not result.startswith(("Error", "exit code", "Refusing", "Unknown")),
            "result": result[:300],
            "seconds": round(seconds, 2),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_recent(cfg: Config, count: int = 20) -> str:
    """Format the last `count` logged calls for humans."""
    count = max(1, min(count, 100))
    if not cfg.log_path.exists():
        return "No calls logged yet."
    lines = cfg.log_path.read_text(encoding="utf-8").splitlines()[-count:]
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        status = "ok" if rec.get("ok") else "FAILED"
        out.append(
            f"{rec['time']}  {rec['tool']}  {json.dumps(rec['args'], ensure_ascii=False)}"
            f"  -> {status} ({rec['seconds']}s)"
        )
    return "\n".join(out) or "No calls logged yet."


def make_safe(cfg: Config) -> Callable:
    """Build the decorator: readable errors for expected failures, and logging."""

    def safe(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            started = time.time()
            try:
                arguments = dict(sig.bind_partial(*args, **kwargs).arguments)
            except TypeError:
                arguments = dict(kwargs)
            try:
                result = fn(*args, **kwargs)
            except ValueError as e:
                result = f"Error: {e}"
            except Exception as e:  # log unexpected failures, then let them propagate
                log_call(cfg, fn.__name__, arguments,
                         f"Error: unexpected {type(e).__name__}: {e}", time.time() - started)
                raise
            if fn.__name__ != "show_log":
                log_call(cfg, fn.__name__, arguments, str(result), time.time() - started)
            return result

        return wrapper

    return safe
