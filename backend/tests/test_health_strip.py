from datetime import datetime, timedelta, timezone

import health_strip
import vault_io


def test_lint_status_unknown_when_file_missing(vault):
    result = health_strip.compute_lint_status()
    assert result == {"status": "unknown", "last_run": None, "label": None}


def test_lint_status_ok_for_recent_run(vault):
    today = datetime.now(timezone.utc).date().isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {today} — run 5\n\nNo findings.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["status"] == "ok"
    assert result["last_run"] == today
    assert "run 5" in result["label"]


def test_lint_status_stale_after_seven_days(vault):
    old = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {old} — run 1\n\nBaseline.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["status"] == "stale"
    assert result["last_run"] == old


def test_lint_status_uses_last_of_multiple_headings(vault):
    older = (datetime.now(timezone.utc).date() - timedelta(days=20)).isoformat()
    newer = datetime.now(timezone.utc).date().isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {older} — run 1\n\nFirst.\n\n## {newer} — run 2\n\nSecond.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["last_run"] == newer
    assert "run 2" in result["label"]
