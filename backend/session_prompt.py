"""Extracts a mode's "SESSION START" callout out of its methodology
markdown, so it can be delivered as a genuine system-level instruction
(`claude --append-system-prompt`) instead of sitting buried at the top of
the huge first user-turn message (methodology + lessons + job context,
often 9-17K characters).

Found live 2026-07-22: Vesper's track question landed reliably, Noctua's
only about half the time, even after two wording-only fixes to Noctua's
callout closed the gap in reinforcement between the two files. Confirmed
by direct inspection that the callout text was arriving fully intact at
the top of the delivered prompt in a failing case -- so this isn't a
delivery/escaping bug, it's that an ordinary user message, however
explicit, doesn't reliably carry the same instruction-following weight as
a system prompt once it's followed by thousands more characters of
reference material with no structural marker separating "do this" from
"here's context." The fix is architectural, not another wording pass:
give the callout its own channel.
"""

import re

_CALLOUT_START_RE = re.compile(r"SESSION START")


def extract_session_start_callout(methodology: str) -> str | None:
    """Pulls the '> **SESSION START...' blockquote out of a mode's
    methodology text. Returns None if the file has no such callout (e.g.
    settings.md/nightshift.md have none at all; dev.md's is conditional on
    a resumed-shipped-build marker and is handled separately in
    session.py, not through this generic extraction).
    """
    lines = methodology.splitlines()

    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(">") and _CALLOUT_START_RE.search(stripped):
            start = i
            break
    if start is None:
        return None

    end = start
    while end < len(lines) and lines[end].strip().startswith(">"):
        end += 1

    callout_lines = []
    for line in lines[start:end]:
        stripped = line.strip()
        # A bare ">" is a blank line inside the blockquote (markdown's way
        # of separating paragraphs within one quote block) -- preserve it
        # as an actual blank line rather than a literal ">".
        callout_lines.append(stripped[1:].strip() if stripped != ">" else "")

    return "\n".join(callout_lines).strip()
