"""Turn project names into folders, and refuse anything outside the watched roots."""

from __future__ import annotations

from pathlib import Path

from .config import Config


def inside_roots(cfg: Config, p: Path) -> bool:
    return any(p == r or r in p.parents for r in cfg.roots)


def resolve_project(cfg: Config, path: str) -> Path:
    """Resolve a project by name or absolute path. Raises ValueError if not allowed."""
    given = Path(path).expanduser()
    if given.is_absolute():
        candidates = [given.resolve()]
    else:
        candidates: list[Path] = []
        for r in cfg.roots:
            options = []
            if r.name == path and r.is_dir():
                options.append(r)  # the root is itself the project
            child = (r / given).resolve()
            if child.is_dir():
                options.append(child)
            for o in options:
                if o not in candidates:
                    candidates.append(o)
        if len(candidates) > 1:
            raise ValueError(
                f"'{path}' is ambiguous, it matches: {[str(c) for c in candidates]}. "
                "Use the full path."
            )
        if not candidates:
            candidates = [(cfg.roots[0] / given).resolve()]
    p = candidates[0]
    if not inside_roots(cfg, p):
        raise ValueError(
            f"{p} is outside the allowed folders {[str(r) for r in cfg.roots]}"
        )
    if not p.is_dir():
        raise ValueError(f"{p} is not a folder")
    return p


def inside_project(project: Path, rel: str) -> str:
    """Return rel relative to the project folder, refusing anything that escapes it."""
    full = (project / rel).resolve()
    if full != project and project not in full.parents:
        raise ValueError(f"{rel} is outside the project folder")
    return str(full.relative_to(project)) if full != project else "."


def list_projects(cfg: Config) -> list[str]:
    """Names of git projects in the watched folders (the folders themselves included)."""
    found: set[str] = set()
    for r in cfg.roots:
        if not r.is_dir():
            continue
        if (r / ".git").exists():
            found.add(r.name)
        try:
            for d in r.iterdir():
                if d.is_dir() and (d / ".git").exists():
                    found.add(d.name)
        except OSError:
            continue
    return sorted(found)
