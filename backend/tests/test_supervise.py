"""The supervisor keeps trying, and does not kill a server for being slow.

On 2026-09-16 a two-second probe timed out against a backend that was
answering every request, the supervisor reaped it, four restarts in 48s did
not come up, and it gave up -- Settings read "not responding" for an hour.
These pin the two behaviours that turn that into a blip: a failed probe is
confirmed before it counts, and the restart ladder ends in a steady retry
rather than an exit.
"""
from __future__ import annotations

import supervise


def test_a_slow_answer_is_not_a_death(monkeypatch):
    """The routine probe times out; the confirming probe, with more patience,
    gets an answer. That is a busy server, and it is left alone."""
    seen = []

    def healthy(timeout=2.0):
        seen.append(timeout)
        return timeout >= supervise.CONFIRM_S

    monkeypatch.setattr(supervise, "healthy", healthy)
    assert supervise.answering() is True
    assert seen == [supervise.PROBE_S, supervise.CONFIRM_S], "one quick look, then one patient one"


def test_a_dead_server_fails_both_probes(monkeypatch):
    monkeypatch.setattr(supervise, "healthy", lambda timeout=2.0: False)
    assert supervise.answering() is False


def test_the_ladder_ends_in_a_steady_interval_not_an_exit():
    ladder = [supervise.next_delay(i) for i in range(len(supervise.BACKOFF_S))]
    assert ladder == list(supervise.BACKOFF_S)
    for beyond in (len(supervise.BACKOFF_S), len(supervise.BACKOFF_S) + 1, 100):
        assert supervise.next_delay(beyond) == supervise.STEADY_S


def test_the_loop_keeps_restarting_past_the_ladder_and_resets_when_the_backend_returns(monkeypatch):
    """Eight probes with the backend down: five ladder restarts, then steady
    ones every minute, and no return. Then it answers once, the count
    resets, and the next fault starts the ladder from the top."""
    spawns, logs, sleeps = [], [], []
    # Probe outcomes in order: down for eight polls, up for one, down for one.
    # `answering` asks `healthy` twice per failed poll (probe, then confirm),
    # so the script is keyed on polls, not on calls.
    outcomes = [False] * 8 + [True] + [False]
    poll = {"i": -1}
    original_answering = supervise.answering

    def answering():
        poll["i"] += 1
        return outcomes[poll["i"]]

    monkeypatch.setattr(supervise, "answering", answering)
    monkeypatch.setattr(supervise, "spawn", lambda: spawns.append(1) or None)
    monkeypatch.setattr(supervise, "reap", lambda: None)
    monkeypatch.setattr(supervise, "_log", lambda m: logs.append(m))
    monkeypatch.setattr(supervise.time, "sleep", lambda s: sleeps.append(s))

    supervise.supervise(iterations=len(outcomes))

    assert len(spawns) == 9, "every failed poll ends in a restart -- none in an exit"
    delays = [s for s in sleeps if s != supervise.POLL_S]
    assert delays == list(supervise.BACKOFF_S) + [supervise.STEADY_S] * 3 + [supervise.BACKOFF_S[0]], delays
    assert any("still not answering after 5 restarts" in m for m in logs), logs
    assert any("back after 8 restarts" in m for m in logs), logs
    assert not any("giving up" in m for m in logs)
    assert original_answering is not answering  # the real one is what main() runs
