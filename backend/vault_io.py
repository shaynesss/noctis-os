"""Direct filesystem read/write helpers for the vault (second-brain/).

No ORM, no migrations, no MCP/istefox dependency — the vault's markdown files
are the only persistence layer (see SPEC.md EDD: "Vault access: direct
filesystem read/write, no istefox/MCP dependency").
"""

import os
import re
import threading
from pathlib import Path
from typing import Any

import frontmatter

_SAFE_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def is_safe_slug(value: str) -> bool:
    """A slug used as a filesystem path segment (job slugs, inbox item
    slugs) or embedded in a runtime-log filename must be restricted to this
    charset. Added in the 2026-07-21 ship-gate security review after
    finding job.slug flowed unsanitized from request bodies into vault_io
    writes and hook-script log paths, allowing path traversal.
    """
    return bool(_SAFE_SLUG.match(value))

# A single lock around every write, not just log.md/index.md. The narrower
# version of this ("only log.md/index.md need it, everything else has one
# writer-type") was falsified by this project's own later additions --
# staleness.py's flag_stale_jobs() (run on every GET /mode/{name} poll)
# and PATCH /mode/dev/jobs/{slug} both read-modify-write the same
# modes/dev/state.md, discovered in the 2026-07-21 ship-gate security
# review. A single process-wide lock is disproportionate for nothing, but
# proportionate for a local single-user app's actual write volume, and
# closes the class of bug rather than special-casing one more file. Note:
# this still only protects the write itself, not the read-then-mutate step
# that happens in the caller between read_frontmatter and write_frontmatter
# -- full read-modify-write atomicity would need a transaction concept this
# module doesn't have; not attempted here as disproportionate to actual risk.
_write_lock = threading.Lock()


def get_vault_path() -> Path:
    vault_path = os.environ.get("VAULT_PATH")
    if not vault_path:
        raise RuntimeError("VAULT_PATH environment variable is not set")
    return Path(vault_path)


# Custos's spec-completeness audit (settings.md's Audit stage) can propose
# diffs against a project's own compiled SPEC.md/CLAUDE.md, not just vault
# mode files -- for this project that file is noctis-os/SPEC.md, which
# lives in a sibling git repo, outside second-brain/ entirely. Every prior
# accepted proposal only ever targeted modes/*/*.md (inside the vault), so
# this case was never exercised until a diff literally titled
# "--- noctis-os/SPEC.md" hit apply_proposal and failed with a bare
# FileNotFoundError -- vault_io had no path outside VAULT_PATH to resolve
# it against. Narrow, explicit allowlist rather than widening the vault
# root generally: only the literal `noctis-os/` prefix gets a second base
# directory, with the same containment check applied to it, so the write
# surface grows by exactly one named sibling project, not by all of
# ~/Developer/.
_PROJECT_ROOTS = {"noctis-os": Path(__file__).resolve().parent.parent}


def _resolve_within_vault(relative_path: str) -> Path:
    """Every public function in this module takes a caller-controlled
    `relative_path` -- some of those callers thread it from HTTP request
    bodies (job slugs) with no upstream character restriction. Resolve and
    verify containment here once, rather than trusting every call site to
    have sanitized its input (2026-07-21 ship-gate review found this
    missing entirely, allowing arbitrary-path writes via a crafted slug).
    """
    for prefix, root in _PROJECT_ROOTS.items():
        if relative_path == prefix or relative_path.startswith(prefix + "/"):
            root = root.resolve()
            resolved = (root / relative_path[len(prefix) + 1 :]).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError(f"Path escapes {prefix}: {relative_path!r}")
            return resolved

    vault_path = get_vault_path().resolve()
    resolved = (vault_path / relative_path).resolve()
    if resolved != vault_path and vault_path not in resolved.parents:
        raise ValueError(f"Path escapes the vault: {relative_path!r}")
    return resolved


def read_file(relative_path: str) -> str:
    path = _resolve_within_vault(relative_path)
    return path.read_text(encoding="utf-8")


def write_file(relative_path: str, content: str) -> None:
    path = _resolve_within_vault(relative_path)
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def read_frontmatter(relative_path: str) -> tuple[dict[str, Any], str]:
    """Parse a mode's state.md/lessons.md/job-context.md: YAML frontmatter
    (the state-schema contract every mode's files carry) plus freeform body.
    """
    path = _resolve_within_vault(relative_path)
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    return dict(post.metadata), post.content


def write_frontmatter(relative_path: str, metadata: dict[str, Any], content: str) -> None:
    path = _resolve_within_vault(relative_path)
    post = frontmatter.Post(content, **metadata)
    serialized = frontmatter.dumps(post)
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")


def file_exists(relative_path: str) -> bool:
    return _resolve_within_vault(relative_path).exists()


def move_file(src_relative: str, dst_relative: str) -> None:
    src = _resolve_within_vault(src_relative)
    dst = _resolve_within_vault(dst_relative)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def read_binary(relative_path: str) -> bytes:
    return _resolve_within_vault(relative_path).read_bytes()


def write_binary(relative_path: str, data: bytes) -> None:
    """Design Lodge preview images are the first binary vault content --
    everything else in the vault is markdown/frontmatter. Same containment
    check and write lock as write_file, just bytes instead of text.
    """
    path = _resolve_within_vault(relative_path)
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def list_dir(relative_path: str) -> list[str]:
    """Markdown filenames (no extension) in a vault subdirectory, sorted.

    Design Lodge's entries/ folder is the first vault content addressed by
    slug-per-file rather than one index file with an array field (unlike
    every mode's state.md/inbox pattern) -- entries can grow past what's
    comfortable to hold in one frontmatter array, so listing means reading
    the directory itself. Returns [] for a directory that doesn't exist yet
    rather than raising, matching read_frontmatter's job-file-not-found
    callers that already expect an empty/absent case.
    """
    dir_path = _resolve_within_vault(relative_path)
    if not dir_path.is_dir():
        return []
    return sorted(p.stem for p in dir_path.glob("*.md"))
