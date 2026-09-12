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
def no_real_spawn(tmp_path, monkeypatch):
    """Isolate the two tests below that post a *valid* launch request.

    Every other test that posts to `/v2/sessions` is refused before the spawn
    -- unknown mode, cwd outside home, empty prompt -- so the suite had never
    reached `SessionManager.start`, and nothing was in place to stop it when
    it finally did. These two were the first to get there: each run launched a
    real Claude Code session into a pytest tmp_path and, because
    `sessions_v2._store` is module-level and unparameterised, wrote its
    transcript into the real history database. Found 2026-09-11 by one of the
    spawned sessions, which read its own working directory and recognised the
    `vault` fixture's scaffolding.

    Only the runner is replaced, so the manager's concurrency bookkeeping is
    still the real thing. A test that genuinely wants to exercise a launch
    should inject its own runner rather than drop this fixture.
    """
    import routers.sessions_v2 as sv2
    from orchestrator.manager import SessionManager
    from orchestrator.store import ConversationStore

    async def never_spawns(spec, timeout=None):
        return
        yield  # pragma: no cover -- makes this an async generator

    monkeypatch.setattr(sv2, "_manager", SessionManager(runner=never_spawns))
    monkeypatch.setattr(sv2, "_store", ConversationStore(tmp_path / "history.db"))


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


def _spy_spec(monkeypatch, tmp_path):
    """Capture the SessionSpec the route actually spawns.

    Asserted at the spec rather than at `render()`, which is what the
    previous version of this test did — and it passed for hours after the
    cutover while the job context was being composed into a config directory
    nothing read. A wiring test has to watch the wire, not a function that
    used to be on it.
    """
    import routers.sessions_v2 as sv2
    from orchestrator.manager import SessionManager

    seen: dict = {}

    async def capture(spec, timeout=None):
        seen["spec"] = spec
        return
        yield  # pragma: no cover -- makes this an async generator

    monkeypatch.setattr(sv2, "_manager", SessionManager(runner=capture))
    monkeypatch.setattr(sv2, "_HOME", tmp_path.resolve())
    monkeypatch.setenv("NOCTIS_API_TOKEN", "test-token")
    return seen


def _launch(cwd, mode="faber"):
    from fastapi.testclient import TestClient

    from main import app
    return TestClient(app).post(
        "/v2/sessions",
        headers={"Authorization": "Bearer test-token"},
        json={"mode": mode, "prompt": "go", "cwd": str(cwd)},
    )


def test_the_spawned_session_carries_its_job_context(vault, tmp_path, monkeypatch,
                                                     no_real_spawn):
    """The wiring test — the one whose absence let the parameter die twice.

    First as a `compose()` argument no caller passed; then, after the
    cutover, as a correctly-resolved context written to a directory that no
    longer existed. Both times the feature was complete, correct and
    unreachable.
    """
    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, status="a distinctive status line")

    seen = _spy_spec(monkeypatch, tmp_path)
    _launch(project)

    spec = seen.get("spec")
    assert spec is not None, "the route never reached the spawn"
    assert spec.job_context, "the spec was built without the job context"
    assert "a distinctive status line" in spec.job_context


def test_the_job_context_reaches_the_argv(vault, tmp_path, monkeypatch, no_real_spawn):
    """And survives composition — the spec carrying it is necessary but not
    sufficient, since the prompt is assembled a layer further down."""
    from orchestrator.driver import build_command

    project = tmp_path / "proj"
    project.mkdir()
    _write_job(tmp_path, "dev", "proj", project, status="a distinctive status line")

    seen = _spy_spec(monkeypatch, tmp_path)
    _launch(project)

    cmd = build_command(seen["spec"])
    prompt = cmd[cmd.index("--append-system-prompt") + 1]
    assert "a distinctive status line" in prompt


def test_launch_outside_any_project_sends_no_job_context(vault, tmp_path, monkeypatch,
                                                         no_real_spawn):
    """No job is the honest result for a directory that is not one, and it
    has to be distinguishable from a job that failed to load."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    seen = _spy_spec(monkeypatch, tmp_path)
    _launch(elsewhere)

    assert seen["spec"].job_context is None
