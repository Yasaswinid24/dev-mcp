"""Add the dev-helper MCP server to Claude Desktop's config without touching anything else.

Usage (from the dev-mcp folder, with the venv active):
    python register_desktop.py
    python register_desktop.py --roots "C:\\Users\\Ravi\\Projects;C:\\Users\\Ravi\\my-repo"
    python register_desktop.py --config <path>     # only for testing

Quit Claude Desktop completely BEFORE running this, then reopen it afterwards.
The app rewrites this file while it runs and would overwrite the change.
"""
import argparse
import getpass
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOTS = (r"C:\Users\Ravi\Downloads\JobTrackerAPP;C:\Users\Ravi\ai-career-copilot;"
                 r"C:\Users\Ravi\ActionPlanApp")


def find_config() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Claude-Data"
    found = sorted(base.glob("*/claude_desktop_config.json"))
    if not found:
        sys.exit(f"No claude_desktop_config.json found under {base}")
    if len(found) > 1:
        print("Several configs found, using the most recently changed one:")
        found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--roots", default=None,
        help='folders to watch, separated by ";" (each may hold projects or be a repo). '
             "If omitted, the folders already in your config are kept")
    ap.add_argument("--my-remotes", default=None,
                    help="remotes for push_my_accounts; the last one becomes upstream "
                         "(default: keep what is in the config)")
    ap.add_argument("--gitlab-url", default=None)
    ap.add_argument("--gitlab-token", default="")
    ap.add_argument("--github-accounts", default=None,
                    help='"remote=username,..." used by create_github_repos '
                         "(default: keep the accounts already in the config, "
                         "else origin=Yasaswinid24,yassu=Yassu-24)")
    ap.add_argument("--ask-github-tokens", action="store_true",
                    help="prompt (hidden) for each account's token; nothing is echoed or "
                         "saved in your shell history")
    ap.add_argument("--config", default="", help="config path (default: auto-detect)")
    args = ap.parse_args()

    cfg_path = Path(args.config) if args.config else find_config()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))  # stops here if invalid JSON

    if os.name == "nt":
        python = HERE / ".venv" / "Scripts" / "python.exe"
    else:
        python = HERE / ".venv" / "bin" / "python"

    servers_old = data.get("mcpServers", {}).get("dev-helper", {}).get("env", {})
    old_tokens = {}
    for part in servers_old.get("DEV_MCP_GITHUB", "").split(","):
        remote, _, rest = part.strip().partition("=")
        user, _, token = rest.partition(":")
        if remote and token:
            old_tokens[(remote, user)] = token

    if not args.github_accounts:
        args.github_accounts = ",".join(f"{r}={u}" for r, u in old_tokens) \
            or "origin=Yasaswinid24,yassu=Yassu-24"
    github_parts = []
    for part in args.github_accounts.split(","):
        remote, _, user = part.strip().partition("=")
        if not (remote and user):
            continue
        token = old_tokens.get((remote, user), "")
        if args.ask_github_tokens:
            typed = getpass.getpass(f"GitHub token for {user} (Enter keeps current): ").strip()
            token = typed or token
        if token:
            github_parts.append(f"{remote}={user}:{token}")
        else:
            print(f"Note: no token for {user}; create_github_repos will skip setup until "
                  "you run again with --ask-github-tokens.")

    args.roots = args.roots or servers_old.get("DEV_MCP_ROOTS") or DEFAULT_ROOTS
    args.my_remotes = args.my_remotes or servers_old.get("DEV_MCP_MY_REMOTES") or "yassu,origin"
    args.gitlab_url = args.gitlab_url or servers_old.get("GITLAB_URL") or "https://gitlab.com"

    entry = {
        "command": str(python),
        "args": [str(HERE / "server.py")],
        "env": {
            "DEV_MCP_ROOTS": args.roots,
            "DEV_MCP_MY_REMOTES": args.my_remotes,
            "GITLAB_URL": args.gitlab_url,
            "GITLAB_TOKEN": args.gitlab_token,
            "DEV_MCP_GITHUB": ",".join(github_parts),
        },
    }

    servers = data.setdefault("mcpServers", {})
    existed = "dev-helper" in servers
    old_env = servers.get("dev-helper", {}).get("env", {})
    if not args.gitlab_token and old_env.get("GITLAB_TOKEN"):
        entry["env"]["GITLAB_TOKEN"] = old_env["GITLAB_TOKEN"]  # keep a token you added
    servers["dev-helper"] = entry

    backup = cfg_path.with_name(cfg_path.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(cfg_path, backup)

    tmp = cfg_path.with_name(cfg_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))  # re-check what we wrote
    tmp.replace(cfg_path)

    print(f"{'Updated' if existed else 'Added'} dev-helper in: {cfg_path}")
    print(f"Backup saved as: {backup}")
    print(f"Other servers kept: {[k for k in servers if k != 'dev-helper'] or 'none'}")
    if not python.exists():
        print(f"WARNING: {python} does not exist. Create the .venv first.")
    print("Now reopen Claude Desktop and start a NEW chat.")


if __name__ == "__main__":
    main()
