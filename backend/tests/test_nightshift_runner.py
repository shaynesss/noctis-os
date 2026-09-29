import json
import pathlib
import subprocess
import types

import pytest

import vault_io
from nightshift import runner
from nightshift.slack_surface import SlackItem


def _seed_job(vault, slug="noctis-build", flagged=False, last_touched=None):
    meta = {"name": "Noctis build", "stage": "Build", "status": "stalled", "flagged": flagged}
    if last_touched:
        meta["last_touched"] = last_touched
    vault_io.write_frontmatter(f"modes/dev/jobs/{slug}/context.md", meta, "")


def _probe(slug="b"):
    """A kind of slack with a template for a drafter, registered for one
    test. The machinery below is about staging, dedup and fault isolation,
    not about any particular kind -- and riding on whichever kind existed
    is why these tests broke when dev's flagged-job note was removed."""
    return SlackItem(mode="dev", kind="probe", slug_hint=slug, description="a probe", context="ctx")


PROBE_DRAFT = "## Rationale\nA probe.\n\n## Diff\n(none)\n\n## Evidence\n- none\n"


def _register_probe(monkeypatch):
    def draft(item, vault_path):
        return PROBE_DRAFT
    monkeypatch.setitem(runner.ADVANCE, "probe", draft)
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset({"probe"}))
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])


def test_extract_rationale_reads_the_rationale_section():
    text = "## Rationale\nBecause X happened.\nTwice.\n\n## Diff\nsomething\n"
    assert runner._extract_rationale(text) == "Because X happened.\nTwice."


def test_extract_rationale_missing_section_returns_none():
    assert runner._extract_rationale("## Diff\nonly a diff\n") is None


def test_extract_confidence_reads_high_or_low():
    assert runner._extract_confidence("## Confidence\nhigh -- three sources agree.\n") == "high"
    assert runner._extract_confidence("## Confidence\nlow -- single entry, weak signal.\n") == "low"


def test_extract_confidence_missing_or_malformed_returns_none():
    assert runner._extract_confidence("## Diff\nonly a diff\n") is None
    assert runner._extract_confidence("## Confidence\nmaybe?\n") is None


def test_confidence_is_high_for_a_mechanical_kind_and_parsed_otherwise(monkeypatch):
    """A drafter that makes no judgment is not asked for one. No mechanical
    kind is registered today (dev's flagged-job note went on 2026-09-17), so
    the contract is tested rather than whichever kind happens to exist."""
    item = SlackItem(mode="dev", kind="templated", slug_hint="x", description="d", context="c")
    assert runner._confidence_for(item, "no confidence section at all") is None
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset({"templated"}))
    assert runner._confidence_for(item, "no confidence section at all") == "high"


def test_confidence_for_distillation_reads_the_drafted_section():
    item = SlackItem(mode="settings", kind="undistilled-lessons", slug_hint="undistilled-learn", description="d", context="c")
    assert runner._confidence_for(item, "## Confidence\nlow -- one entry only.\n") == "low"
    assert runner._confidence_for(item, "no confidence section") is None


def test_run_stages_an_item_where_settings_reads(vault, monkeypatch):
    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])

    slugs, _failed, _dropped, _seen = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("probe-b-")

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1
    entry = state["inbox"][0]
    assert entry["origin_mode"] == "dev"
    assert entry["slug"] == slugs[0]
    assert entry["rationale"]
    assert entry["confidence"] == "high"

    # maintenance/inbox, which is where Settings reads; drafts went to
    # modes/nightshift/inbox until 2026-09-16 and were never shown.
    # Written by the runner, out of what the drafter returned -- the
    # drafter has no write tool (2026-09-18).
    proposal_path = vault / "maintenance" / "inbox" / f"{slugs[0]}.md"
    assert proposal_path.exists()
    assert proposal_path.read_text(encoding="utf-8") == PROBE_DRAFT


def test_run_is_idempotent_against_already_pending_item(vault, monkeypatch):
    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])

    first, _, _, _ = runner.run()
    assert len(first) == 1

    second, _, _, _ = runner.run()
    assert second == []

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1


def test_identity_prefix_ignores_date_for_dedup():
    item = SlackItem(mode="dev", kind="undistilled-lessons", slug_hint="x", description="d", context="c")
    assert runner._identity_prefix(item) == "undistilled-lessons-x-"


def test_one_failing_item_does_not_drop_other_items(vault, monkeypatch):
    """A single failing/timing-out advance step (e.g. a claude subprocess
    call) must not abort the whole run and silently drop every other
    independent item -- 2026-07-21 ship-gate finding: this loop had no
    exception handling at all."""
    bad_item = SlackItem(mode="dev", kind="unregistered-kind", slug_hint="a", description="bad", context="c")

    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "learn", lambda: [bad_item])
    monkeypatch.setitem(runner.SLACK_CHECKS, "research", lambda: [_probe()])

    slugs, _failed, _dropped, _seen = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("probe-b-")


def test_run_flags_a_stale_job_and_stages_nothing_for_it(vault, monkeypatch, tmp_path):
    """The deterministic half runs first: a job whose session died three days
    ago is flagged in its own context. Nothing is staged about it -- the
    Inbox lists flags directly, and the note that used to be written here
    proposed nothing, sat beside the same job in that list, and came back
    the night after it was accepted (removed 2026-09-17)."""
    import staleness
    from datetime import datetime, timedelta, timezone
    runtime = tmp_path / "runtime"; runtime.mkdir()
    monkeypatch.setattr(staleness, "RUNTIME_DIR", runtime)
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    # The context was written before the session ran: nobody has looked
    # since it stopped, which is what makes it unattended.
    _seed_job(vault, slug="died-mid-build",
              last_touched=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat())
    (runtime / "dev__died-mid-build.log").write_text(f"{old} Edit x\n", encoding="utf-8")

    slugs, _failed, _dropped, _seen = runner.run()

    meta, _ = vault_io.read_frontmatter("modes/dev/jobs/died-mid-build/context.md")
    assert meta["flagged"] is True
    assert slugs == []


# --- drops: the outcome that was neither staged, nor failed, nor nothing ------
#
# Until 2026-09-17 each of these three gates was a bare `continue`. The item
# counted in `seen`, appeared in neither `staged` nor `failed`, and the night
# reported itself quiet: `data/nightshift.json` holds `seen: 3, staged: 0,
# failed: 0` for 2026-09-16 and `seen: 4, staged: 1, failed: 0` for 09-17,
# which is three paid-for distiller calls discarded each night, unlogged.

def _register_drafter(monkeypatch, draft_text: str | None):
    def draft(item, vault_path):
        return draft_text
    monkeypatch.setitem(runner.ADVANCE, "probe", draft)
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset())
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])


def test_a_drafter_that_writes_nothing_is_recorded_not_forgotten(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, None)

    staged, failed, dropped, seen = runner.run()

    assert (staged, failed, seen) == ([], [], 1)
    assert len(dropped) == 1
    assert dropped[0]["gate"] == "no-draft"
    assert dropped[0]["kept"] is None       # there was no draft to keep


def test_a_draft_missing_its_rationale_is_kept_for_reading(vault, monkeypatch, tmp_path):
    """The gate was silent *and* it unlinked the draft, so the morning had
    neither a reason nor an artefact. The draft moves to runtime now."""
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Diff\n(none)\n\n## Confidence\nhigh -- sure.\n")

    _staged, _failed, dropped, _seen = runner.run()

    assert dropped[0]["gate"] == "no-rationale"
    kept = pathlib.Path(dropped[0]["kept"])
    assert kept.exists() and "## Diff" in kept.read_text()


def test_a_draft_with_no_usable_confidence_is_dropped_and_kept(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Rationale\nA probe.\n\n## Confidence\nmaybe?\n")

    _staged, _failed, dropped, _seen = runner.run()

    assert dropped[0]["gate"] == "no-confidence"
    assert pathlib.Path(dropped[0]["kept"]).exists()


def test_a_dropped_draft_does_not_stay_in_the_inbox(vault, monkeypatch, tmp_path):
    """A rejected draft must not be left where Settings lists proposals: it
    met none of the contract the listing assumes."""
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Diff\n(none)\n")

    _staged, _failed, dropped, _seen = runner.run()

    inbox = vault_io.get_vault_path() / runner.MAINTENANCE_INBOX
    assert not (inbox / f"{dropped[0]['slug']}.md").exists()
    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert state.get("inbox") in ([], None)


def test_the_cursor_marker_uses_the_real_lessons_path_for_maintenance(vault, monkeypatch):
    """`maintenance/lessons.md` is not `modes/maintenance/lessons.md`, and
    the drafter hardcoded the second shape. Any maintenance draft that got
    as far as the marker raised FileNotFoundError and took the whole item
    down as a failure (found 2026-09-17)."""
    vault_io.write_file("maintenance/lessons.md", "# Lessons\n\none\ntwo\n")
    # What the drafter reads before it calls anything.
    vault_io.write_file("maintenance/schedule.md", "# Schedule\n")
    vault_io.write_file("maintenance/agents/distiller.md", "# Distiller\n")
    vault_io.write_file(f"{runner.MAINTENANCE_INBOX}/README.md", "# Format\n")
    item = SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-maintenance", description="d", context="c")
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda *a, **k: _completed("## Rationale\nx\n"))

    draft = runner._draft_distillation(item, vault_io.get_vault_path())

    assert "<!-- cursor-advance: maintenance=4 -->" in draft


# --- the drafter returns its work, and the runner writes it ------------------
#
# Until 2026-09-18 the drafter was handed `Write(<one absolute path>)` and told
# to save the file itself. Every parenthesised specifier on `Write` in
# `--allowedTools` is refused, so every distillation draft the machine ever
# produced was denied at the last step and recorded as `no-draft` -- three
# nights, nine model calls, nine finished proposals thrown away. The reason was
# in the subprocess's own JSON the whole time, under `permission_denials`.

def _completed(result_text, denials=(), is_error=False, stdout=None, returncode=0):
    payload = {"result": result_text, "permission_denials": list(denials), "is_error": is_error}
    return types.SimpleNamespace(
        stdout=json.dumps(payload) if stdout is None else stdout, stderr="",
        returncode=returncode)


def _seed_distiller_reads():
    """What `_draft_distillation` reads before it calls anything."""
    vault_io.write_file("maintenance/schedule.md", "# Schedule\n")
    vault_io.write_file("maintenance/agents/distiller.md", "# Distiller\n")
    vault_io.write_file(f"{runner.MAINTENANCE_INBOX}/README.md", "# Format\n")
    vault_io.write_file("maintenance/lessons.md", "# Lessons\n\none\n")


def test_the_drafter_is_given_no_write_tool(vault, monkeypatch):
    """The regression that matters: a `Write` rule with a specifier is
    silently refused, and a bare `Write` on an unattended nightly job is the
    whole vault. The drafter gets neither."""
    _seed_distiller_reads()
    seen = {}

    def spy(cmd, **kw):
        seen["cmd"] = cmd
        return _completed("## Rationale\nx\n\n## Confidence\nhigh -- sure.\n")

    monkeypatch.setattr(runner.subprocess, "run", spy)
    item = SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-dev", description="d", context="c")
    monkeypatch.setattr(runner, "lessons_path", lambda mode: "maintenance/lessons.md")

    runner._draft_distillation(item, vault_io.get_vault_path())

    cmd = seen["cmd"]
    allowed = cmd[cmd.index("--allowedTools") + 1]
    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    assert allowed == "Read Grep"
    assert "Write" not in allowed
    assert "Write" in disallowed.split()


def test_a_denied_tool_is_a_failure_with_its_reason_not_a_silent_no_draft():
    """`permission_denials` was in this payload every night for three nights
    and nothing read it."""
    denial = {"tool_name": "Write", "tool_input": {"file_path": "/x.md"}}
    with pytest.raises(RuntimeError, match="denied Write"):
        runner._result_text(_completed("", denials=[denial]))


def test_an_errored_drafter_raises_rather_than_returning_an_empty_draft():
    with pytest.raises(RuntimeError, match="drafter errored"):
        runner._result_text(_completed("ran out of turns", is_error=True))


def test_output_that_is_not_json_raises_with_what_arrived():
    with pytest.raises(RuntimeError, match="not JSON"):
        runner._result_text(_completed("", stdout="claude: command not found"))


# --- a failed call reports its reason, not its command line ------------------
#
# 2026-09-19, 05:40: the machine's network was not up, `claude -p` exited 1, and
# the envelope on stdout carried the sentence that said so. `check=True` raised
# `CalledProcessError` before anything read it, and that exception's string is
# the entire argv -- whose second element is a ten-kilobyte prompt. What the
# morning's card showed was the opening lines of the Maintenance methodology.

API_ERROR = "API Error: Can't reach the API server -- check your internet or DNS (ENOTFOUND)"


def test_an_api_error_on_a_non_zero_exit_reports_the_error_not_the_argv():
    with pytest.raises(RuntimeError) as exc:
        runner._result_text(_completed(API_ERROR, is_error=True, returncode=1))
    assert "ENOTFOUND" in str(exc.value)
    assert "--allowedTools" not in str(exc.value)


def test_a_non_zero_exit_the_envelope_does_not_explain_still_raises_with_the_code():
    """Otherwise it returns "" and the `no-draft` gate records the drafter
    as having had nothing to say, which is the silent-failure shape again."""
    with pytest.raises(RuntimeError, match="exited 1 with no proposal"):
        runner._result_text(_completed("", returncode=1))


def test_a_non_zero_exit_that_wrote_no_envelope_raises_with_the_code():
    with pytest.raises(RuntimeError, match="exited 127 and its output was not JSON"):
        runner._result_text(_completed("", stdout="claude: not found", returncode=127))


def test_a_failing_call_reaches_the_run_record_as_a_readable_reason(vault, monkeypatch):
    """End to end through the drafter: no `CalledProcessError` escapes, and
    what a failure carries is short enough to survive `str(exc)[:200]`."""
    _seed_distiller_reads()
    monkeypatch.setattr(runner, "lessons_path", lambda mode: "maintenance/lessons.md")
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda *a, **k: _completed(API_ERROR, is_error=True, returncode=1))
    item = SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-dev", description="d", context="c")

    with pytest.raises(RuntimeError) as exc:
        runner._draft_distillation(item, vault_io.get_vault_path())

    assert "ENOTFOUND" in str(exc.value)[:200]


def test_a_timed_out_call_reports_the_timeout_not_the_argv(vault, monkeypatch):
    """`TimeoutExpired` carries the command line exactly as
    `CalledProcessError` did, so dropping `check=True` alone left the same
    wall of prompt on the other path out. Found by running the fix against a
    real unreachable API, which retried rather than exiting."""
    _seed_distiller_reads()
    monkeypatch.setattr(runner, "lessons_path", lambda mode: "maintenance/lessons.md")

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd=["claude", "-p", "x" * 5000],
                                        timeout=runner.DRAFT_TIMEOUT)

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    item = SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-dev", description="d", context="c")

    with pytest.raises(RuntimeError) as exc:
        runner._draft_distillation(item, vault_io.get_vault_path())

    assert str(exc.value) == f"drafter timed out after {runner.DRAFT_TIMEOUT}s"


def test_a_drafter_that_answers_with_nothing_returns_nothing():
    """No denial, no error, no text: the `no-draft` gate's remaining job."""
    assert runner._result_text(_completed("   ")) == ""


def test_a_fenced_answer_is_unwrapped():
    body = runner._proposal_body("```markdown\n## Rationale\nx\n```")
    assert body == "## Rationale\nx\n"


def test_a_preamble_before_the_proposal_is_cut():
    """A model told to answer with a file still says "Here is the proposal:"
    sometimes, and that line would be the vault file's first line for good."""
    body = runner._proposal_body("Here is the proposal:\n\n## Rationale\nx\n\n## Diff\n(none)\n")
    assert body.startswith("## Rationale")
    assert "Here is" not in body


def test_a_draft_with_no_rationale_comes_back_whole_for_the_gate_to_reject():
    """Nothing is repaired on the way through: the gate rejects it and the
    drops folder keeps it, which is how the morning sees what went wrong."""
    assert runner._proposal_body("I could not find a pattern.") == "I could not find a pattern.\n"


def test_the_runner_writes_what_the_drafter_returned_and_nothing_else(vault, monkeypatch, tmp_path):
    """The whole point of the change: one writer, and it is this one."""
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Rationale\nA real one.\n\n## Confidence\nlow -- one entry.\n")

    staged, failed, dropped, seen = runner.run()

    assert (failed, dropped, seen) == ([], [], 1)
    inbox = vault_io.get_vault_path() / runner.MAINTENANCE_INBOX
    written = (inbox / f"{staged[0]}.md").read_text(encoding="utf-8")
    assert written == "## Rationale\nA real one.\n\n## Confidence\nlow -- one entry.\n"
    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert state["inbox"][0]["confidence"] == "low"


# --- a laptop that sleeps mid-draft (2026-09-21, 09-26, 09-29) ----------------

def _sleepy(monkeypatch, outcomes):
    """Drafter calls that each take `outcomes[i]`: ("slept"|"awake", result).
    A slept call moves the wall clock an hour while the timer does not."""
    import time as _time
    wall = {"t": 1_000_000.0}
    monkeypatch.setattr(_time, "time", lambda: wall["t"])
    calls = []

    def fake(cmd, **kw):
        kind, result = outcomes[len(calls)]
        calls.append(kind)
        if kind == "slept":
            wall["t"] += 3600
        if result is None:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        return result

    monkeypatch.setattr(runner.subprocess, "run", fake)
    return calls


def _dev_item(monkeypatch):
    _seed_distiller_reads()
    monkeypatch.setattr(runner, "lessons_path", lambda mode: "maintenance/lessons.md")
    return SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-dev", description="d", context="c")


def test_a_draft_the_machine_slept_through_is_retried_on_waking(vault, monkeypatch):
    item = _dev_item(monkeypatch)
    calls = _sleepy(monkeypatch, [("slept", None), ("awake", _completed("## Rationale\nx\n"))])
    draft = runner._draft_distillation(item, vault_io.get_vault_path())
    assert calls == ["slept", "awake"] and draft.startswith("## Rationale")


def test_an_awake_timeout_is_not_retried(vault, monkeypatch):
    item = _dev_item(monkeypatch)
    calls = _sleepy(monkeypatch, [("awake", None)])
    with pytest.raises(RuntimeError) as e:
        runner._draft_distillation(item, vault_io.get_vault_path())
    assert calls == ["awake"] and str(e.value) == f"drafter timed out after {runner.DRAFT_TIMEOUT}s"


def test_two_slept_timeouts_say_the_machine_slept(vault, monkeypatch):
    item = _dev_item(monkeypatch)
    _sleepy(monkeypatch, [("slept", None), ("slept", None)])
    with pytest.raises(RuntimeError, match="the machine slept"):
        runner._draft_distillation(item, vault_io.get_vault_path())


def test_the_drafter_is_told_the_house_style(vault, monkeypatch):
    item = _dev_item(monkeypatch)
    seen = {}
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda cmd, **kw: seen.setdefault("prompt", cmd[2]) and _completed("## Rationale\nx\n"))
    runner._draft_distillation(item, vault_io.get_vault_path())
    assert "no em dashes" in seen["prompt"]
