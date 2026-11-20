"""Smoke test: start the server over stdio and call each tool like Claude would.

Prints PASS/FAIL checks at the end. Run with: python test_client.py
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

results = []


def check(label, condition):
    results.append((label, bool(condition)))
    print(("PASS " if condition else "FAIL ") + label)


async def main():
    root = Path(tempfile.mkdtemp())
    solo = Path(tempfile.mkdtemp()) / "solo-repo"   # a second watched folder that IS a repo
    solo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=solo, capture_output=True)
    other = Path(tempfile.mkdtemp())                 # a third folder, not watched
    log_file = Path(tempfile.mkdtemp()) / "calls.log"
    env = {
        **os.environ,
        "DEV_MCP_ROOTS": f"{root};{solo}",
        "DEV_MCP_MY_REMOTES": "fake2,fake",
        "DEV_MCP_LOG": str(log_file),
    }
    env.pop("DEV_MCP_ROOT", None)
    params = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "server.py")], env=env
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            check("git_diff tool is listed", "git_diff" in names)

            async def call(tool, **kw):
                res = await s.call_tool(tool, kw)
                return "".join(c.text for c in res.content if hasattr(c, "text"))

            await call("scaffold_fastapi_project", name="demo-api")
            proj = root / "demo-api"
            for k, v in (("user.email", "t@t.t"), ("user.name", "T")):
                subprocess.run(["git", "config", k, v], cwd=proj)

            # nothing staged, add_all not requested -> refuses and explains
            out = await call("git_commit", project="demo-api", message="x")
            check("commit with nothing staged is refused", "Nothing is staged" in out)

            # secrets are blocked for add_all and for chosen files
            (proj / "deploy.pem").write_text("KEY\n")
            out = await call("git_commit", project="demo-api", message="x", add_all=True)
            check("add_all refuses deploy.pem", "Refusing add_all" in out and "deploy.pem" in out)
            out = await call("git_commit", project="demo-api", message="x", files=["deploy.pem"])
            check("files=[deploy.pem] refused", "Refusing to stage" in out)
            (proj / "deploy.pem").unlink()

            # chosen files only
            out = await call(
                "git_commit", project="demo-api", message="init", files=["README.md", "app"]
            )
            check("commit of chosen files works", "init" in out and "exit code" not in out)
            log = await call("git_log", project="demo-api")
            check("commit appears in log", "init" in log)

            # a file name ending in 'k' must not break the staged check
            (proj / "book").write_text("a\n")
            subprocess.run(["git", "add", "book"], cwd=proj)
            out = await call("git_commit", project="demo-api", message="add book")
            check("staged file named 'book' commits", "add book" in out)

            # diff
            (proj / "README.md").write_text("# changed\n")
            out = await call("git_diff", project="demo-api")
            check("git_diff shows the change", "README.md" in out and "+# changed" in out)
            out = await call("git_diff", project="demo-api", path="README.md")
            check("git_diff with path works", "README.md" in out)
            out = await call("git_diff", project="demo-api", path="../outside")
            check("git_diff blocks path escape", "outside the project" in out)
            out = await call("git_diff", project="demo-api", staged=True)
            check("staged diff empty -> No changes", out.strip() == "No changes.")

            # add_all works when no secrets
            out = await call("git_commit", project="demo-api", message="edit", add_all=True)
            check("add_all commits when safe", "edit" in out and "exit code" not in out)

            # venv detection
            out = await call("run_tests", project="demo-api")
            check("run_tests reports interpreter (PATH fallback)", "Using Python: python" in out)
            vdir = proj / ".venv" / ("Scripts" if os.name == "nt" else "bin")
            vdir.mkdir(parents=True)
            exe = vdir / ("python.exe" if os.name == "nt" else "python")
            if os.name == "nt":
                import shutil
                shutil.copy(sys.executable, exe)
            else:
                exe.symlink_to(sys.executable)
            out = await call("run_tests", project="demo-api")
            check("run_tests picks project .venv", ".venv" in out.splitlines()[0])

            # ---- multiple folders
            out = await call("list_projects")
            check("list_projects sees both folders", "demo-api" in out and "solo-repo" in out)
            out = await call("git_status", project="solo-repo")
            check("a watched folder that is itself a repo works", "## " in out and "Error" not in out)
            out = await call("git_status", project=str(solo))
            check("absolute path inside a watched folder works", "Error" not in out)
            out = await call("git_status", project=str(other))
            check("absolute path in an unwatched folder refused", "outside the allowed folders" in out)
            (root / "dup").mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=root / "dup", capture_output=True)
            (solo / "dup").mkdir()
            out = await call("git_status", project="dup")
            check("same name in two folders is ambiguous", "ambiguous" in out)

            # ---- push_my_accounts
            for name in ("fake2", "fake"):
                b = Path(tempfile.mkdtemp()) / f"{name}.git"
                subprocess.run(["git", "init", "--bare", str(b)], capture_output=True)
                subprocess.run(["git", "remote", "add", name, str(b)], cwd=proj)
            out = await call("push_my_accounts", project="demo-api")
            check("push_my_accounts dry run by default", "DRY RUN" in out and "fake2" in out)
            out = await call("push_my_accounts", project="demo-api", confirm=True)
            check("push_my_accounts pushes to both remotes", "--- fake2 ---" in out and "--- fake ---" in out)
            up = subprocess.run(["git", "rev-parse", "--abbrev-ref", "@{u}"], cwd=proj,
                                capture_output=True, text=True).stdout.strip()
            check("last remote becomes upstream", up == "fake/main")

            # ---- logging
            out = await call("show_log", count=50)
            check("show_log lists earlier calls", "git_status" in out and "demo-api" in out)
            check("failed calls are marked FAILED", "FAILED" in out)
            before = log_file.read_text().count("\n")
            await call("show_log")
            check("show_log does not log itself", log_file.read_text().count("\n") == before)
            check("log file is valid JSON lines", all(
                json.loads(l)["tool"] for l in log_file.read_text().splitlines()))

            # earlier safety checks still hold
            out = await call("git_status", project="../../etc")
            check("path outside root refused", "outside the allowed folder" in out)
            out = await call("git_push", project="demo-api", remotes=["nope"], confirm=True)
            check("unknown remote refused", "Unknown remotes" in out)

    failed = [l for l, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


asyncio.run(main())
