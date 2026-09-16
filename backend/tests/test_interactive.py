"""The argv for a session the shell hosts in a pseudo-terminal."""
import json

import pytest

import interactive
from engine import MODE_MODELS


@pytest.fixture(autouse=True)
def _vault_for_every_argv(vault):
    """Every test here builds an argv, and an argv names the vault.

    Without this the file passes only when something else has imported
    `main` first, which loads `../.env` and sets VAULT_PATH process-wide:
    the suite was green and the file alone was nine failures.
    """


def test_it_is_not_a_print_spawn():
    """The whole point of the difference.

    An interactive session renders itself, prompts for its own permissions and
    reads what you type. Carrying `-p`, `--output-format stream-json` or a
    permission-prompt tool would produce a session that does none of those and
    prints JSON at a terminal instead.
    """
    args = interactive.spawn_args("faber", "/tmp")["args"]
    for flag in ("-p", "--print", "--output-format", "--verbose",
                 "--permission-prompt-tool", "--permission-prompts"):
        assert flag not in args, f"{flag} belongs to a -p spawn, not an interactive one"


def test_the_mode_still_travels_in_the_argv():
    """The part that must not drift from `build_command`: a mode is its
    methodology and its model, and a terminal session is no less a mode."""
    for mode, model in MODE_MODELS.items():
        args = interactive.spawn_args(mode, "/tmp")["args"]
        assert args[args.index("--model") + 1] == model, mode


def test_the_vault_is_reachable():
    """A session sandboxed to its working directory cannot read its own
    methodology, job context or lessons -- all of which live outside it."""
    args = interactive.spawn_args("noctua", "/tmp")["args"]
    assert "--add-dir" in args


def test_the_status_line_reports_back():
    """How an interactive session hands over what the stream used to: the 5h
    and 7d windows, context occupancy, effort and the model. Without this the
    status bar has no source at all once `stream-json` is gone."""
    args = interactive.spawn_args("vesper", "/tmp")["args"]
    settings = json.loads(args[args.index("--settings") + 1])
    assert settings["statusLine"]["type"] == "command"
    assert "statusline.sh" in settings["statusLine"]["command"]
    assert interactive.STATUSLINE.exists(), "the status line script must be there"


def test_it_carries_the_same_tracked_policy():
    """One permission file, both spawn paths. A terminal session that quietly
    had different permissions would be the 09-11 defect wearing a new shape."""
    from engine import SHARED_SETTINGS
    tracked = json.loads(SHARED_SETTINGS.read_text())
    settings = json.loads(
        interactive.spawn_args("faber", "/tmp")["args"][
            interactive.spawn_args("faber", "/tmp")["args"].index("--settings") + 1])
    assert settings["permissions"] == tracked["permissions"]
    assert settings["crossSessionInbound"] == tracked["crossSessionInbound"]


def test_resume_is_passed_through():
    args = interactive.spawn_args("faber", "/tmp", resume_id="abc-123")["args"]
    assert args[args.index("--resume") + 1] == "abc-123"


def test_an_unknown_mode_is_refused_here_not_at_spawn():
    with pytest.raises(ValueError):
        interactive.spawn_args("nonsense", "/tmp")


def test_the_environment_names_the_mode_for_the_hooks():
    """The telemetry hooks attribute an action by reading NOCTIS_MODE. A PTY
    child inherits the shell process's environment, and the end-to-end sweep
    found a vesper session logging under faber -- whatever the shell had.
    The environment travels beside the argv, from the same place."""
    for mode in MODE_MODELS:
        env = interactive.spawn_args(mode, "/tmp")["env"]
        assert env["NOCTIS_MODE"] == mode
        assert "NOCTIS_JOB_ID" not in env      # /tmp is nobody's project


def test_a_prompt_that_starts_with_a_dash_is_still_a_prompt():
    """A handoff summary that opens with a bullet is an argument that opens
    with a dash, and the CLI parsed one as an unknown option and exited
    before the terminal painted. The terminator makes it text."""
    args = interactive.spawn_args("general", "/tmp", prompt="- first point\n- second")["args"]
    assert args[-2:] == ["--", "- first point\n- second"]


def test_a_fresh_session_opens_by_saying_what_it_is_and_a_resume_does_not():
    """A terminal at a bare prompt looks like nothing loaded, and the first
    thing anyone types into it is "what are you". A fresh session gets that
    question as its opening prompt; a resumed one has a conversation to come
    back to and must not be interrupted with an introduction."""
    fresh = interactive.spawn_args("general", "/tmp")["args"]
    assert fresh[-2:] == ["--", interactive.OPENING_PROMPT]
    resumed = interactive.spawn_args("general", "/tmp", resume_id="abc")["args"]
    assert "--" not in resumed and interactive.OPENING_PROMPT not in resumed
    given = interactive.spawn_args("general", "/tmp", prompt="hello")["args"]
    assert given[-2:] == ["--", "hello"]


def test_effort_is_passed_when_chosen_and_omitted_when_not(vault, tmp_path):
    """The launcher's chooser, as a flag. Omitted when nothing was chosen,
    because a default sent as an override would outrank the machine's own
    `~/.claude/settings.json` for every session the app starts."""
    plain = interactive.spawn_args("faber", str(tmp_path))
    assert "--effort" not in plain["args"]

    chosen = interactive.spawn_args("faber", str(tmp_path), effort="xhigh")
    args = chosen["args"]
    assert args[args.index("--effort") + 1] == "xhigh"


def test_an_unknown_effort_is_refused_before_the_terminal_opens(vault, tmp_path):
    """The CLI rejects a bad level after the pane has opened, so the error
    lands where a session should be. Caught here instead, as a 400."""
    with pytest.raises(ValueError, match="unknown effort"):
        interactive.spawn_args("faber", str(tmp_path), effort="maximum")
