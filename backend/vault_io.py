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


def _resolve_within_vault(relative_path: str) -> Path:
    """Every public function in this module takes a caller-controlled
    `relative_path` -- some of those callers thread it from HTTP request
    bodies (job slugs) with no upstream character restriction. Resolve and
    verify containment here once, rather than trusting every call site to
    have sanitized its input (2026-07-21 ship-gate review found this
    missing entirely, allowing arbitrary-path writes via a crafted slug).
    """
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
