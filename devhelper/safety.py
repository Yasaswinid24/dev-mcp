"""Checks that stop Claude from committing credentials."""

from __future__ import annotations

from pathlib import Path

SECRET_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def looks_secret(rel_path: str) -> bool:
    """True for files that usually hold credentials and should never be committed."""
    name = Path(rel_path).name.lower()
    if name in SECRET_NAMES or name.startswith(".env."):
        return name != ".env.example"
    return name.endswith(SECRET_SUFFIXES)
