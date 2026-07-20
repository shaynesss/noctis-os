"""Direct filesystem read/write helpers for the vault (second-brain/).

No ORM, no migrations, no MCP/istefox dependency — the vault's markdown files
are the only persistence layer (see SPEC.md EDD: "Vault access: direct
filesystem read/write, no istefox/MCP dependency").
"""

import os
import threading
from pathlib import Path
from typing import Any

import frontmatter

# Files every mode session can append to concurrently — CLAUDE.md's hard
# constraint: "log.md/index.md go through a single serialized writer."
# Per-mode lessons.md/state.md/job contexts have exactly one writer-type
# each and don't need this lock.
_SERIALIZED_FILES = {"log.md", "index.md"}
_write_lock = threading.Lock()


def get_vault_path() -> Path:
    vault_path = os.environ.get("VAULT_PATH")
    if not vault_path:
        raise RuntimeError("VAULT_PATH environment variable is not set")
    return Path(vault_path)


def read_file(relative_path: str) -> str:
    path = get_vault_path() / relative_path
    return path.read_text(encoding="utf-8")


def write_file(relative_path: str, content: str) -> None:
    path = get_vault_path() / relative_path
    if relative_path in _SERIALIZED_FILES:
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_frontmatter(relative_path: str) -> tuple[dict[str, Any], str]:
    """Parse a mode's state.md/lessons.md/job-context.md: YAML frontmatter
    (the state-schema contract every mode's files carry) plus freeform body.
    """
    path = get_vault_path() / relative_path
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    return dict(post.metadata), post.content


def write_frontmatter(relative_path: str, metadata: dict[str, Any], content: str) -> None:
    path = get_vault_path() / relative_path
    post = frontmatter.Post(content, **metadata)
    serialized = frontmatter.dumps(post)
    if relative_path in _SERIALIZED_FILES:
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(serialized, encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def file_exists(relative_path: str) -> bool:
    return (get_vault_path() / relative_path).exists()


def move_file(src_relative: str, dst_relative: str) -> None:
    vault_path = get_vault_path()
    dst = vault_path / dst_relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    (vault_path / src_relative).rename(dst)
