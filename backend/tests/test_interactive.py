"""The argv for a session the shell hosts in a pseudo-terminal."""
import json

import pytest

import interactive
from engine import MODE_MODELS


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
