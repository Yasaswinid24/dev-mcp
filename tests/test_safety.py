import pytest

from devhelper.safety import looks_secret


@pytest.mark.parametrize("name", [
    ".env", ".env.local", ".env.production", "app/.env", "id_rsa", "id_ed25519",
    "credentials.json", "secrets.json", "server.pem", "deploy.key", "cert.p12", "cert.pfx",
    "DEPLOY.PEM",
])
def test_secret_files_are_detected(name):
    assert looks_secret(name)


@pytest.mark.parametrize("name", [
    ".env.example", "README.md", "app/main.py", "keyboard.py", "monkey.txt", "environment.yml",
])
def test_normal_files_are_not_flagged(name):
    assert not looks_secret(name)
