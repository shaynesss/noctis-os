from session_prompt import extract_session_start_callout


def test_extracts_callout_blockquote():
    methodology = (
        "# Research — Vesper\n\n"
        "> canonical methodology intro\n\n"
        "## 1. Identity\n\n"
        "> **SESSION START — do this before anything else:** the first message\n"
        "> must be exactly this:\n"
        ">\n"
        '> "Adopt or inquiry track? Which is this?"\n\n'
        "Vesper (Latin: evening) — a moth.\n"
    )

    callout = extract_session_start_callout(methodology)

    assert callout is not None
    assert callout.startswith("**SESSION START")
    assert '"Adopt or inquiry track? Which is this?"' in callout
    # Stops at the callout's own end -- doesn't bleed into the next section.
    assert "Vesper (Latin: evening)" not in callout


def test_returns_none_when_no_callout_present():
    methodology = "# Settings — Custos\n\nNo session-start callout in this mode.\n"

    assert extract_session_start_callout(methodology) is None


def test_preserves_blank_lines_within_the_blockquote():
    methodology = (
        "> **SESSION START:** first line.\n"
        ">\n"
        "> Second paragraph after a blank quoted line.\n"
    )

    callout = extract_session_start_callout(methodology)

    assert callout == "**SESSION START:** first line.\n\nSecond paragraph after a blank quoted line."


def test_ignores_unrelated_blockquotes_before_the_callout():
    methodology = (
        "> just a regular blockquote, not a callout\n\n"
        "> **SESSION START:** the real one.\n"
    )

    callout = extract_session_start_callout(methodology)

    assert callout == "**SESSION START:** the real one."
