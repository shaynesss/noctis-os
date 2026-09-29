"""The shared-tree guard.

Two halves, and the second matters more than the first. Blocking `git add -A`
is easy; not blocking `git add backend/jobs.py` is the whole reason the guard
is tolerable, because a guard that fires on ordinary work gets disabled.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hooks import guard_shared_tree as guard  # noqa: E402

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_shared_tree.py"


# --- what counts as a whole-tree command -------------------------------------

@pytest.mark.parametrize("command, effect", [
    ("git add -A", "stage every changed file"),
    ("git add --all", "stage every changed file"),
    ("git add .", "stage every changed file"),
    ("git add -u", "stage every changed file"),
    ("git add", "stage every changed file"),
    ("git -C /somewhere add -A", "stage every changed file"),
    ("npm test && git add -A", "stage every changed file"),
    ("git commit -a -m 'x'", "commit every changed file"),
    ("git commit -am 'x'", "commit every changed file"),
    ("git commit --all -m 'x'", "commit every changed file"),
    ("git stash", "stash the whole working tree"),
    ("git reset --hard", "discard every uncommitted change"),
    ("git reset --hard origin/main", "discard every uncommitted change"),
    ("git checkout -- .", "discard every uncommitted change"),
    ("git restore .", "discard every uncommitted change"),
    ("git clean -fd", "delete every untracked file"),
])
def test_whole_tree_commands_are_recognised(command, effect):
    found = guard.whole_tree_command(command)
    assert found is not None, command
    assert found[0] == effect


@pytest.mark.parametrize("command", [
    # The ones that must never fire. A path beginning with a dot is not `.`.
    "git add backend/jobs.py",
    "git add .claude/settings.local.json",
    "git add backend/jobs.py backend/tests/test_jobs.py",
    "git commit -m 'a message'",
    "git commit --amend -m 'x'",          # --amend is not -a
    "git commit -m 'adds a thing'",       # 'a' inside the message, not a flag
    "git stash push backend/jobs.py",
    "git stash pop",
    "git reset HEAD~1",                   # soft by default, keeps the tree
    "git checkout main",
    "git restore backend/jobs.py",
    "git status --short",
    "git log --oneline -5",
    "git diff",
    "ls -A",                              # -A, but not git
    "rg 'git add -A' docs/",              # the string, not the command
])
def test_scoped_and_unrelated_commands_are_left_alone(command):
    assert guard.whole_tree_command(command) is None


def test_unbalanced_quotes_are_not_judged():
    """Unparseable is not the same as dangerous, and guessing at a broken
    command is how a guard starts firing on things it does not understand."""
    assert guard.whole_tree_command("git commit -m 'unterminated") is None


# --- only with company --------------------------------------------------------

def _payload(command, **over):
    return {"tool_name": "Bash", "tool_input": {"command": command},
            "cwd": "/repo", "session_id": "mine", **over}


def test_alone_in_the_tree_everything_is_allowed(monkeypatch):
    monkeypatch.setattr(guard, "others_in_this_repo", lambda *a: [])
    assert guard.decide(_payload("git add -A")) is None


def test_with_company_a_whole_tree_command_is_refused(monkeypatch):
    monkeypatch.setattr(guard, "others_in_this_repo", lambda *a: ["term-2"])
    reason = guard.decide(_payload("git add -A"))
    assert reason is not None
    assert "term-2" in reason
    assert "git add <path>" in reason


def test_with_company_a_scoped_command_is_still_allowed(monkeypatch):
    """Splitting the work by file is the locked design; the guard must not
    make it impossible to commit your own half."""
    monkeypatch.setattr(guard, "others_in_this_repo", lambda *a: ["term-2"])
    assert guard.decide(_payload("git add backend/jobs.py")) is None


def test_a_non_bash_tool_is_not_examined(monkeypatch):
    monkeypatch.setattr(guard, "others_in_this_repo", lambda *a: ["term-2"])
    assert guard.decide({"tool_name": "Edit", "tool_input": {"command": "git add -A"}}) is None


# --- failing open -------------------------------------------------------------

def test_an_unreachable_backend_allows(monkeypatch):
    """The condition is usually false, so a check that cannot run must not
    block: a session broken by a down backend is a worse outcome than a
    collision that has to be undone."""
    monkeypatch.setattr(guard, "_live_sessions", lambda: [])
    monkeypatch.setattr(guard, "_repo_root", lambda p: "/repo")
    assert guard.others_in_this_repo("/repo", "mine") == []


def test_a_directory_outside_any_repo_allows(monkeypatch):
    monkeypatch.setattr(guard, "_repo_root", lambda p: None)
    assert guard.others_in_this_repo("/tmp", "mine") == []


def test_the_session_does_not_count_itself(monkeypatch):
    monkeypatch.setattr(guard, "_repo_root", lambda p: "/repo")
    monkeypatch.setattr(guard, "_live_sessions",
                        lambda: [{"session_id": "mine", "cwd": "/repo", "slot": "term-1"}])
    assert guard.others_in_this_repo("/repo", "mine") == []


def test_a_session_in_a_subdirectory_of_the_same_repo_counts(monkeypatch):
    """`backend/` and `frontend/` are one working tree, and `git add -A` from
    either reaches both, so the comparison is the repository, not the cwd."""
    monkeypatch.setattr(guard, "_repo_root", lambda p: "/repo")
    monkeypatch.setattr(guard, "_live_sessions",
                        lambda: [{"session_id": "other", "cwd": "/repo/backend", "slot": "term-2"}])
    assert guard.others_in_this_repo("/repo/frontend", "mine") == ["term-2"]


def test_a_session_in_a_different_repo_does_not_count(monkeypatch):
    monkeypatch.setattr(guard, "_repo_root", lambda p: {"/repo": "/repo"}.get(p, "/elsewhere"))
    monkeypatch.setattr(guard, "_live_sessions",
                        lambda: [{"session_id": "other", "cwd": "/other", "slot": "term-2"}])
    assert guard.others_in_this_repo("/repo", "mine") == []


# --- the contract with the CLI ------------------------------------------------

def _run(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30)


def test_the_process_exits_zero_and_silent_when_it_allows():
    """Run as the CLI runs it. `/tmp` is in no repository, so this allows
    without needing a backend."""
    out = _run(_payload("git add -A", cwd="/tmp"))
    assert out.returncode == 0
    assert out.stdout.strip() == ""


def test_an_unparseable_payload_allows():
    out = subprocess.run([sys.executable, str(HOOK)], input="not json",
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0


def test_the_deny_shape_is_what_the_cli_expects(monkeypatch):
    """Exit 2 is what blocks; the JSON only carries the reason. A deny printed
    with exit 0 is advisory and the command still runs."""
    monkeypatch.setattr(guard, "others_in_this_repo", lambda *a: ["term-2"])
    reason = guard.decide(_payload("git add -A"))
    body = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}
    assert json.loads(json.dumps(body))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_guard_is_registered_for_every_hosted_session():
    """The hook is only real if it reaches a session. It rides in the argv
    rather than a project's settings file, so that it holds in projects that
    have no Noctis files in them."""
    import interactive
    policy = interactive.statusline_settings("faber")
    entries = policy["hooks"]["PreToolUse"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert any("guard_shared_tree.py" in c for c in commands)
    assert all(e["matcher"] == "Bash" for e in entries)
    assert Path(commands[0].split()[-1]).exists(), "hook script must exist on disk"


# --- the bypasses found 2026-09-29 --------------------------------------------

HEREDOC_COMMIT = "git commit -am \"$(cat <<'EOF'\nA subject\n\nA body that says; things.\nEOF\n)\""


@pytest.mark.parametrize("command, effect", [
    (HEREDOC_COMMIT, "commit every changed file"),       # the most common commit of all
    ("bash -c 'git add -A'", "stage every changed file"),
    ("sh -c \"cd x && git add .\"", "stage every changed file"),
    ("(git add -A)", "stage every changed file"),
    ("echo $(git add -A)", "stage every changed file"),
    ("eval git add -A", "stage every changed file"),
    ("/usr/bin/git add -A", "stage every changed file"),
    ("git stash push", "stash the whole working tree"),
    ("git stash push -u", "stash the whole working tree"),
    ("git stash push -m 'wip'", "stash the whole working tree"),
    ("git stash save 'wip'", "stash the whole working tree"),
    ("git checkout -f", "discard every uncommitted change"),
    ("git switch -f main", "discard every uncommitted change"),
    ("git rm -r --cached .", "remove every file from the index"),
    ("git status\ngit add -A", "stage every changed file"),
])
def test_the_spellings_that_got_past_are_recognised(command, effect):
    found = guard.whole_tree_command(command)
    assert found is not None and found[0] == effect, command


@pytest.mark.parametrize("command", [
    # How a careful session commits: named paths, then a heredoc message
    # whose prose may mention the very commands the guard refuses.
    "git add backend/a.py && git commit -q -F - <<'EOF'\nGuard: refuses git add -A and git commit -am\n\nBody.\nEOF",
    "git commit -m \"$(cat <<'EOF'\nfixes git add -A; and git stash\nEOF\n)\"",
    "python3 - <<'EOF'\nprint('git add -A')\nEOF",
    "git stash push -- backend/jobs.py",
    "git stash push -m 'wip' backend/jobs.py",
    "git rm --cached backend/data/history.db",
    "git switch main",
])
def test_scoped_commands_with_that_prose_in_them_are_still_allowed(command):
    assert guard.whole_tree_command(command) is None, command


def test_the_repository_judged_is_the_one_the_command_reaches(monkeypatch):
    """`git -C` and `cd` move a command into another repository; it was
    judged against the session's own, so the vault could be swept from
    noctis-os while a session in the vault was unprotected."""
    assert guard.whole_tree_command("git -C ../second-brain add -A")[2] == "../second-brain"
    assert guard.whole_tree_command("cd ../second-brain && git add -A")[2] == "../second-brain"
    assert guard.whole_tree_command("git add -A")[2] is None

    asked = []
    monkeypatch.setattr(guard, "others_in_this_repo", lambda cwd, sid: asked.append(cwd) or [])
    guard.decide(_payload("cd ../vault && git add -A", cwd="/work/repo"))
    assert asked == ["/work/vault"]
