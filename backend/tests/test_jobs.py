"""Job lookup, and the launch path actually using it.

The second half matters more than the first. `compose()` accepted a
`job_context` argument and spliced it in correctly for as long as it has
existed, and no caller ever passed one — so the feature was complete,
tested at the unit level, and dead. These tests pin the wiring, not just
the function.
"""
from pathlib import Path

import pytest

import jobs


@pytest.fixture
def home_is_tmp(tmp_path, monkeypatch):
    """The interactive-args route confines cwd to home. The project the tests
    write lives under tmp_path, so home has to be tmp_path for the duration."""
    import routers.sessions_v2 as sv2
    monkeypatch.setattr(sv2, "_HOME", tmp_path.resolve())
    monkeypatch.setenv("NOCTIS_API_TOKEN", "test-token")


def _write_job(vault_dir: Path, mode_dir: str, slug: str, project_path: Path, **meta):
    job = vault_dir / "modes" / mode_dir / "jobs" / slug
    job.mkdir(parents=True, exist_ok=True)
    # Popped before `fields` is built, not after: left in, the body text goes
    # into the frontmatter dict, and a multi-line value there is invalid YAML.
    body = meta.pop("_body", "First entry.\n\nSecond entry.")
    fields = {"name": slug, "stage": "Build", "status": "mid-flight",
              "project_path": str(project_path), **meta}
    front = "\n".join(f"{k}: {v}" for k, v in fields.items())
    (job / "context.md").write_text(f"---\n{front}\n---\n\n{body}\n", encoding="utf-8")
    return job


def test_maps_mode_name_to_vault_directory():
    assert jobs.jobs_dir("faber") == "modes/dev/jobs"
    assert jobs.jobs_dir("vesper") == "modes/research/jobs"


def test_general_has_no_jobs_directory():
    """Mapping `general` to something would invent a backlog it never has."""
    assert jobs.jobs_dir("general") is None
    assert jobs.job_brief("general", "/tmp") is None


def test_finds_the_job_whose_project_path_is_the_cwd(vault, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project)
    assert jobs.find_job_for_cwd("faber", project) == "proj"


def test_a_subdirectory_is_not_the_project(vault, tmp_path):
    """Prefix matching would make ~/Developer match every job at once.

    Wrong job context is worse than none: none is visibly absent, wrong is
    quietly believed.
    """
    project = tmp_path / "proj"
    (project / "backend").mkdir(parents=True)
    _write_job(tmp_path, "dev", "proj", project)
    assert jobs.find_job_for_cwd("faber", project / "backend") is None


def test_unrelated_directory_matches_nothing(vault, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    _write_job(tmp_path, "dev", "proj", project)
    assert jobs.find_job_for_cwd("faber", other) is None


def test_brief_leads_with_stage_and_status(vault, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, stage="Ship", status="awaiting gate")
    brief = jobs.job_brief("faber", project)
    assert "stage: Ship" in brief
    assert "status: awaiting gate" in brief
    assert "Second entry." in brief


def test_brief_carries_the_tail_not_the_head(vault, tmp_path, monkeypatch):
    """A job context grows without bound; the current end is what orients."""
    monkeypatch.setattr(jobs, "BRIEF_MAX_CHARS", 120)
    project = tmp_path / "proj"
    project.mkdir()
    body = "ancient history. " * 40 + "\n\nthe newest entry."
    _write_job(tmp_path, "dev", "proj", project, _body=body)
    brief = jobs.job_brief("faber", project)
    assert "the newest entry." in brief
    assert "ancient history" not in brief
    assert "call `job_context` for the full record" in brief


def test_flagged_job_says_so(vault, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, flagged="true")
    assert "flagged" in jobs.job_brief("faber", project)


def test_job_with_no_project_path_is_skipped(vault, tmp_path):
    """A Plan-stage job in a scratch directory has no project yet."""
    job = tmp_path / "modes" / "dev" / "jobs" / "unsited"
    job.mkdir(parents=True)
    (job / "context.md").write_text("---\nname: unsited\nstage: Plan\n---\n\nbody\n",
                                    encoding="utf-8")
    assert jobs.find_job_for_cwd("faber", tmp_path) is None


def _args_for(cwd, mode="faber"):
    """The argv a terminal would spawn with for this directory. This *is* the
    wire: there is no spec and no spawn between the route and the process."""
    from fastapi.testclient import TestClient

    from main import app
    r = TestClient(app).get(
        "/v2/sessions/interactive-args",
        headers={"Authorization": "Bearer test-token"},
        params={"mode": mode, "cwd": str(cwd)},
    )
    assert r.status_code == 200, r.text
    return r.json()["args"]


def _overlay(args):
    return args[args.index("--append-system-prompt") + 1] if "--append-system-prompt" in args else ""


def test_the_terminal_session_carries_its_job_context(vault, tmp_path, home_is_tmp):
    """The wiring test -- the one whose absence let the parameter die three
    times.

    First as a `compose()` argument no caller passed; then, after the
    cutover, as a correctly-resolved context written to a directory that no
    longer existed; then, in the first terminal version, as a `job_brief`
    the interactive argv simply never asked for. Each time the feature was
    complete, correct and unreachable. This watches the argv itself.
    """
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, status="a distinctive status line")

    assert "a distinctive status line" in _overlay(_args_for(project))


def test_a_directory_that_is_not_a_project_sends_no_job_context(vault, tmp_path, home_is_tmp):
    """No job is the honest result for a directory that is not one, and it
    has to be distinguishable from a job that failed to load: the overlay is
    still there, it just carries no job."""
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, status="a distinctive status line")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    overlay = _overlay(_args_for(elsewhere))
    assert "a distinctive status line" not in overlay
