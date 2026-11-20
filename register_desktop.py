"""Add the dev-helper MCP server to Claude Desktop's config without touching anything else.

Usage (from the dev-mcp folder, with the venv active):
    python register_desktop.py
    python register_desktop.py --roots "C:\\Users\\Ravi\\Projects;C:\\Users\\Ravi\\my-repo"
    python register_desktop.py --config <path>     # only for testing

Quit Claude Desktop completely BEFORE running this, then reopen it afterwards.
The app rewrites this file while it runs and would overwrite the change.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


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
        "--roots",
        default=r"C:\Users\Ravi\Downloads\JobTrackerAPP;C:\Users\Ravi\ai-career-copilot;C:\Users\Ravi\ActionPlanApp",
        help='folders to watch, separated by ";" (each may hold projects or be a repo)')
    ap.add_argument("--my-remotes", default="yassu,origin",
                    help="remotes for push_my_accounts; the last one becomes upstream")
    ap.add_argument("--gitlab-url", default="https://gitlab.com")
    ap.add_argument("--gitlab-token", default="")
    ap.add_argument("--config", default="", help="config path (default: auto-detect)")
    args = ap.parse_args()

    cfg_path = Path(args.config) if args.config else find_config()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))  # stops here if invalid JSON

    if os.name == "nt":
        python = HERE / ".venv" / "Scripts" / "python.exe"
    else:
        python = HERE / ".venv" / "bin" / "python"

    entry = {
        "command": str(python),
        "args": [str(HERE / "server.py")],
        "env": {
            "DEV_MCP_ROOTS": args.roots,
            "DEV_MCP_MY_REMOTES": args.my_remotes,
            "GITLAB_URL": args.gitlab_url,
            "GITLAB_TOKEN": args.gitlab_token,
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
