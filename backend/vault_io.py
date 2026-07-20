"""Direct filesystem read/write helpers for the vault (second-brain/).

No ORM, no migrations, no MCP/istefox dependency — the vault's markdown files
are the only persistence layer (see SPEC.md EDD: "Vault access: direct
filesystem read/write, no istefox/MCP dependency").
"""

import os
from pathlib import Path


def get_vault_path() -> Path:
    vault_path = os.environ.get("VAULT_PATH")
    if not vault_path:
        raise RuntimeError("VAULT_PATH environment variable is not set")
    return Path(vault_path)


def read_file(relative_path: str) -> str:
    path = get_vault_path() / relative_path
    return path.read_text(encoding="utf-8")


def write_file(relative_path: str, content: str) -> None:
    # TODO: shared vault files (log.md, index.md) must go through a single
    # serialized writer once multiple sessions can call this concurrently
    # (see SPEC.md EDD: "Serialized write path for shared vault files").
    path = get_vault_path() / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
