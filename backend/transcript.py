"""Stored messages -> the blocks the shell renders a history transcript from.

This lived in `orchestrator/wire.py` beside the SSE contract, so that a
restored conversation and a live one were described by the same shapes. The
live half is gone -- a session is a real terminal now -- but history is still
read from the store, and this is the one shape the shell's Transcript
component reads it in.

Tool calls and their results are stored as two rows and rendered as one
block, paired by the id in their meta. Pairing on adjacency would break on
interleaving.
"""
from __future__ import annotations

import json
from typing import Any, Iterable


def blocks_from_messages(rows: Iterable[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    by_tool_id: dict[str, dict[str, Any]] = {}

    for row in rows:
        role, content = row["role"], row["content"] or ""
        meta = json.loads(row["meta"]) if row["meta"] else {}

        if role == "user":
            blocks.append({"kind": "user", "text": content,
                           "at": str(row["created_at"])[11:16]})
        elif role == "assistant":
            # Deltas were stored as separate rows; rejoin them, or a reloaded
            # reply arrives shattered into one paragraph per fragment.
            if blocks and blocks[-1]["kind"] == "text":
                blocks[-1]["text"] += content
            else:
                blocks.append({"kind": "text", "text": content})
        elif role == "thinking":
            blocks.append({"kind": "thinking", "tokens": meta.get("tokens", 0), "ms": 0})
        elif role == "tool":
            block = {"kind": "tool", "id": meta.get("id", ""), "name": meta.get("tool", "tool"),
                     "target": content.split(" ", 1)[-1] if " " in content else "",
                     "meta": "done", "body": ""}
            blocks.append(block)
            if block["id"]:
                by_tool_id[block["id"]] = block
        elif role == "tool_result":
            target = by_tool_id.get(meta.get("id", ""))
            if target is not None:
                target["body"] = content
                target["meta"] = "error" if meta.get("is_error") else "done"
                target["open"] = bool(meta.get("is_error"))
    return blocks
