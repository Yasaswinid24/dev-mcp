import dataclasses
import json

import pytest

from devhelper import calllog, ops


def test_safe_turns_value_errors_into_messages_and_logs_them(cfg):
    safe = calllog.make_safe(cfg)

    @safe
    def failing_tool(project: str) -> str:
        raise ValueError("not allowed")

    assert failing_tool("x") == "Error: not allowed"
    rec = json.loads(cfg.log_path.read_text().splitlines()[-1])
    assert rec["tool"] == "failing_tool" and rec["ok"] is False
    assert rec["args"] == {"project": "x"}


def test_safe_logs_success_with_arguments(cfg):
    safe = calllog.make_safe(cfg)

    @safe
    def good_tool(project: str, count: int = 3) -> str:
        return "fine"

    good_tool("p", count=5)
    rec = json.loads(cfg.log_path.read_text().splitlines()[-1])
    assert rec["ok"] is True and rec["args"] == {"project": "p", "count": 5}


def test_unexpected_errors_are_logged_and_re_raised(cfg):
    safe = calllog.make_safe(cfg)

    @safe
    def broken_tool() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        broken_tool()
    assert "unexpected RuntimeError" in cfg.log_path.read_text()


def test_show_log_is_not_logged(cfg):
    safe = calllog.make_safe(cfg)

    @safe
    def show_log() -> str:
        return "x"

    show_log()
    assert not cfg.log_path.exists()


def test_read_recent_formats_calls_and_marks_failures(cfg):
    calllog.log_call(cfg, "git_status", {"project": "a"}, "## main", 0.1)
    calllog.log_call(cfg, "git_push", {"project": "a"}, "exit code 128\nfatal", 0.2)
    out = ops.show_log(cfg)
    assert "git_status" in out and "-> ok" in out
    assert "git_push" in out and "FAILED" in out


def test_read_recent_with_no_log_says_so(cfg):
    assert ops.show_log(cfg) == "No calls logged yet."


def test_read_recent_limits_count(cfg):
    for i in range(10):
        calllog.log_call(cfg, f"t{i}", {}, "ok", 0.0)
    assert len(ops.show_log(cfg, count=3).splitlines()) == 3


def test_log_rotates_when_too_big(cfg):
    small = dataclasses.replace(cfg, log_max_bytes=200)
    for i in range(10):
        calllog.log_call(small, "tool", {"i": i}, "ok" * 30, 0.0)
    assert small.log_path.with_name(small.log_path.name + ".1").exists()


def test_logging_problems_never_break_a_tool(cfg, tmp_path):
    broken = dataclasses.replace(cfg, log_path=tmp_path / "no" / "such" / "dir" / "x.log")
    calllog.log_call(broken, "tool", {}, "ok", 0.0)  # must not raise
