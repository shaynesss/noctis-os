#!/usr/bin/env python3
"""Claude Code PreToolUse hook -- refuse whole-tree git commands while another
live session shares this repository.

**The problem this exists for.** On 2026-09-17 two Faber sessions worked on
`noctis-os` at once, which the project's own rules allow ("two sessions on one
job split the work by file"). Twice, one of them ran `git add -A` and committed
the other's uncommitted edits under its own message. Nothing was lost, but the
Repo tab is the memory and two of that day's commit bodies describe work they
do not contain.

**Why a hook and not a rule.** The session that loses its work is not the
session running the command, so no amount of discipline in the victim's prompt
protects it. A rule binds whoever reads it; a hook binds whoever runs the
command. That asymmetry is the whole argument.

**Why not a worktree.** `jobs.find_job_for_cwd` matches `project_path` exactly,
so a second worktree gets no job context at all, and a worktree does not carry
the 250MB of gitignored `.venv` and `node_modules` this repo needs to run its
own tests. The isolation would cost more than the collision.

**What it blocks:** only commands that act on the whole working tree, and only
while another live session is in the same repository. Alone, everything is
allowed; with company, `git add <specific paths>` is still allowed, which is
what splitting the work by file means in practice.

**What it cannot do.** Match every spelling of a shell command. A guard is a
backstop, not the discipline, and it fails *open* everywhere: no backend, no
token, a slow reply, an unparseable payload, all allow. Blocking because the
check could not run would break sessions for a condition that is usually false.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from hooks import failure_log  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 2.0

# Shell separators. A command is split on these first so that `ls && git add -A`
# is examined as two segments and a `git` in one cannot borrow the arguments of
# the next.
SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")

# Git's own global options that take a value, skipped when locating the
# subcommand so `git -C /some/path add -A` is still seen as `add`.
GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

# Whole-tree pathspecs. A bare `.` or `:/` means everything; a path that merely
# starts with a dot (`.claude/settings.json`) does not and must not match.
EVERYTHING = {".", "./", ":/", "*", "-A", "--all", "-u", "--update"}


def _segments(command: str) -> list[list[str]]:
    out = []
    for piece in SEPARATORS.split(command):
        try:
            tokens = shlex.split(piece)
        except ValueError:
            continue  # unbalanced quotes: not parseable, so not judged
        if tokens:
            out.append(tokens)
    return out


def _subcommand(tokens: list[str]) -> tuple[str, list[str]] | None:
    """The git subcommand and its arguments, or None if this is not a git call."""
    try:
        i = tokens.index("git")
    except ValueError:
        return None
    i += 1
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in GLOBAL_WITH_VALUE:
            i += 2
        else:
            i += 1
    if i >= len(tokens):
        return None
    return tokens[i], tokens[i + 1:]


def _has_short_flag(args: list[str], letter: str) -> bool:
    """A single-dash cluster containing `letter`: `-a`, `-am`, `-va`. Excludes
    long options, so `--amend` is not read as `-a`."""
    return any(a.startswith("-") and not a.startswith("--") and letter in a[1:]
               for a in args)


def whole_tree_command(command: str) -> tuple[str, str] | None:
    """(what it would do, the command as written), or None if it is scoped.

    Scoped is the test, not safe: `git add backend/jobs.py` touches one file and
    is fine with company, while `git add -A` cannot know whose file it took.
    """
    for tokens in _segments(command):
        found = _subcommand(tokens)
        if not found:
            continue
        sub, args = found
        written = " ".join(tokens)
        positional = [a for a in args if not a.startswith("-")]

        if sub == "add" and (any(a in EVERYTHING for a in args) or not positional):
            return "stage every changed file", written
        if sub == "commit" and (_has_short_flag(args, "a") or "--all" in args):
            return "commit every changed file", written
        if sub == "stash" and not positional and "--" not in args:
            return "stash the whole working tree", written
        if sub == "reset" and "--hard" in args:
            return "discard every uncommitted change", written
        if sub in {"checkout", "restore"} and any(a in EVERYTHING for a in args):
            return "discard every uncommitted change", written
        if sub == "clean" and _has_short_flag(args, "f"):
            return "delete every untracked file", written
    return None


def _token() -> str:
    if token := os.environ.get("NOCTIS_API_TOKEN"):
        return token
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("NOCTIS_API_TOKEN"):
                return line.partition("=")[2].strip().strip('"')
    return ""


def _repo_root(path: str) -> str | None:
    """The repository a directory belongs to. Compared instead of the directory
    itself because two sessions in `backend/` and `frontend/` are in one working
    tree, and a whole-tree command from either reaches both."""
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _live_sessions() -> list[dict]:
    port = os.environ.get("PORT", "8000")
    # `GET /v2/sessions` is the whole listing: `{running, max_concurrent, live}`
    # where `live` is every terminal whose status line reported in the last
    # thirty seconds, each with its slot, session id and cwd. There is no
    # narrower endpoint, and asking for one would be a route that exists only
    # for this hook.
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v2/sessions",
        headers={"Authorization": f"Bearer {_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read()).get("live") or []
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []  # fail open: an unreachable backend must not block a session


def others_in_this_repo(cwd: str, session_id: str | None) -> list[str]:
    """Slots of live sessions sharing this repository, excluding this one."""
    mine = _repo_root(cwd)
    if not mine:
        return []
    others = []
    for session in _live_sessions():
        if session.get("session_id") and session.get("session_id") == session_id:
            continue
        their_cwd = session.get("cwd")
        if their_cwd and _repo_root(their_cwd) == mine:
            others.append(str(session.get("slot") or "another terminal"))
    return others


def decide(payload: dict) -> str | None:
    """The reason to refuse, or None to allow."""
    if payload.get("tool_name") != "Bash":
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command:
        return None
    verdict = whole_tree_command(command)
    if not verdict:
        return None
    effect, written = verdict

    cwd = str(payload.get("cwd") or os.getcwd())
    others = others_in_this_repo(cwd, payload.get("session_id"))
    if not others:
        return None  # alone in the tree: this is an ordinary command

    who = ", ".join(sorted(others))
    return (
        f"`{written}` would {effect} in this repository, and another live "
        f"session is working in it ({who}). Its uncommitted edits are not "
        f"yours to stage, commit or discard.\n\n"
        f"Name the paths you changed instead: `git add <path> [<path> ...]`, "
        f"then commit those. If you genuinely need the whole tree, ask the "
        f"person first, or wait until the other terminal has closed."
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return  # unreadable payload is not grounds to block

    if reason := decide(payload):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
        # Exit 2 is what actually blocks. The JSON above only carries the
        # reason: a `deny` on exit 0 is advisory and the command still runs.
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # Same contract as the other hooks: never break a session, never fail
        # silently. A guard that dies unnoticed is worse than no guard, because
        # it is trusted.
        failure_log.record("PreToolUse", exc)
