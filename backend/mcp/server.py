#!/usr/bin/env python3
"""Noctis MCP server — Stage 2 item 2.

Exposes the vault's *brain* over MCP: ranked retrieval, mode/job state, and
the proposal pipeline. A client spawns this as a stdio subprocess and talks
JSON-RPC over pipes; nothing listens on a port.

**This is the half of Noctis that travels.** It contains no Anthropic auth
and no Claude-specific code — it reads markdown and returns JSON — so any
MCP-speaking client driving any model can use it, including open-weight
ones. The orchestrator, mode entry and config dirs do not travel; they are
Claude-Code-shaped by design.

Dependency-free on purpose. The protocol is small enough that hand-rolling
it costs less than a dependency would, and it keeps the "clone it and point
it at your own vault" story to `python3 server.py` with nothing to install.

    python3 backend/mcp/server.py            # stdio, VAULT_PATH from env
    VAULT_PATH=/path/to/vault python3 ...
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import MODE_VAULT_DIR, methodology_path  # noqa: E402
from retrieval.index import TOP_K, VaultIndex  # noqa: E402

# Versions this server actually implements, newest first. The spec's
# handshake is a negotiation: the client names what it wants, and the server
# answers with a version *it* supports so the client can decide whether to
# proceed. Echoing the request back instead — which this did — means
# claiming to speak anything a client names, including versions that do not
# exist. Asked for "1999-01-01" it agreed, and a client would then have gone
# on to use features that were never implemented.
PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")
PROTOCOL_FALLBACK = PROTOCOL_VERSIONS[0]


def negotiate(requested: str | None) -> str:
    """The version to answer with: theirs if we speak it, else our newest."""
    return requested if requested in PROTOCOL_VERSIONS else PROTOCOL_FALLBACK
VAULT = Path(os.environ.get("VAULT_PATH", Path(__file__).resolve().parents[3] / "second-brain"))
HISTORY_DB = os.environ.get("NOCTIS_HISTORY_DB")

# Where to reach the backend for a permission decision. Only the permission
# tool uses these: everything else here reads the vault directly, which is
# what keeps "clone it and point it at your own vault" true.
BACKEND = os.environ.get("NOCTIS_BACKEND", "http://127.0.0.1:8000")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:5180")

MODES = ("faber", "noctua", "vesper", "maintenance")


# ---------------------------------------------------------------- wire
def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def ok(rid, result) -> None:
    send({"jsonrpc": "2.0", "id": rid, "result": result})


def err(rid, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


# ---------------------------------------------------------------- tools
TOOLS = [
    {
        "name": "vault_search",
        "description": (
            "Ranked BM25 search across the vault: decisions, methodology, project "
            "notes, the daily log. Use this before answering from memory about "
            "anything previously decided — it returns up to 20 results because the "
            "reading is yours to do, so prefer scanning several over trusting the first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "natural language is fine"},
                "limit": {"type": "integer", "default": TOP_K},
            },
            "required": ["query"],
        },
    },
    {
        "name": "history_search",
        "description": (
            "Search past conversation transcripts. Separate from vault_search "
            "because conversations are application data, not vault knowledge — "
            "use this for 'what did we discuss', vault_search for 'what did I decide'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
            "required": ["query"],
        },
    },
    {
        "name": "job_context",
        "description": (
            "Read a job's durable state: stage, status, track, and its freeform prose. "
            "This is what makes a resumed session know where it stands without being told."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(MODES)},
                "slug": {"type": "string", "description": "omit to list this mode's jobs"},
            },
            "required": ["mode"],
        },
    },
    {
        "name": "worklist",
        "description": "What is in flight across every mode, from each mode's state.md.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose",
        "description": (
            "File a staged change into the maintenance inbox. This is the ONLY way a "
            "methodology change may be made: proposals are reviewed and applied by a "
            "person, never written directly. Requires the evidence that motivated it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "kebab-case identifier"},
                "target": {"type": "string", "description": "vault path the change applies to"},
                "rationale": {"type": "string", "description": "one or two plain sentences: what changes and why"},
                "evidence": {"type": "string", "description": "the lessons entries or audit findings behind it"},
                "body": {"type": "string", "description": "the proposed change itself"},
            },
            "required": ["slug", "target", "rationale", "evidence", "body"],
        },
    },
]


# ---------------------------------------------------------------- impl
_index: VaultIndex | None = None


def index() -> VaultIndex:
    global _index
    if _index is None:
        _index = VaultIndex(VAULT)
        _index.rebuild()
    return _index


def t_vault_search(args: dict) -> dict:
    hits = index().search(args.get("query", ""), k=int(args.get("limit", TOP_K)))
    if not hits:
        # Saying so matters as much as finding things: BM25 score is not a
        # confidence signal (measured), so an empty result is the only
        # honest "nothing here" this layer can give.
        return text("No matches in the vault for that query.")
    lines = [f"{len(hits)} result(s), best first:\n"]
    for h in hits:
        head = f" › {h.heading}" if h.heading else ""
        lines.append(f"— {h.path}{head}\n  {h.excerpt}\n")
    return text("\n".join(lines))


def t_history_search(args: dict) -> dict:
    if not HISTORY_DB or not Path(HISTORY_DB).exists():
        return text("No conversation history available (NOCTIS_HISTORY_DB unset).")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from orchestrator.store import ConversationStore

    store = ConversationStore(HISTORY_DB)
    try:
        rows = store.search(args.get("query", ""), limit=int(args.get("limit", 20)))
        if not rows:
            return text("Nothing in past conversations matches that.")
        return text("\n".join(
            f"— [{r['mode']} · {r['created_at'][:10]}] {r['role']}: {r['content'][:220]}"
            for r in rows))
    finally:
        store.close()


def t_job_context(args: dict) -> dict:
    mode = args.get("mode", "")
    if mode not in MODES:
        return text(f"Unknown mode '{mode}'. Known: {', '.join(MODES)}.")
    # Mapping owned by `jobs.py`, which the launch path also reads. It was
    # inline here until a second caller needed it; two copies drift by
    # returning "no jobs" rather than raising, which reads as an empty
    # backlog instead of a bug.
    jobs_dir = VAULT / "modes" / MODE_VAULT_DIR[mode] / "jobs"
    slug = args.get("slug")
    if not slug:
        if not jobs_dir.is_dir():
            return text(f"No jobs directory for {mode}.")
        names = sorted(p.name for p in jobs_dir.iterdir() if p.is_dir())
        return text(f"{mode} jobs: {', '.join(names) or '(none)'}")
    ctx = jobs_dir / slug / "context.md"
    if not ctx.exists():
        return text(f"No job '{slug}' in {mode}.")
    return text(ctx.read_text()[:8000])


def t_worklist(_args: dict) -> dict:
    out = []
    for d in sorted((VAULT / "modes").iterdir()) if (VAULT / "modes").is_dir() else []:
        state = d / "state.md"
        if state.exists():
            out.append(f"## {d.name}\n{state.read_text()[:1200]}")
    return text("\n\n".join(out) or "No mode state found.")


def t_propose(args: dict) -> dict:
    """Writes to the inbox and nowhere else.

    The mandatory index entry that `audit.md` warns about is deliberately
    NOT written here: a proposal file with no index entry is invisible, and
    making one tool do both would let a caller believe it had filed
    something reviewable when it had not. The tool reports what still needs
    doing rather than silently half-completing.
    """
    inbox = VAULT / "modes" / "nightshift" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    slug = "".join(c for c in args.get("slug", "") if c.isalnum() or c in "-_") or "untitled"
    target_file = inbox / f"{slug}.md"
    if target_file.exists():
        return text(f"A proposal named '{slug}' already exists. Choose another slug.")
    target_file.write_text(
        f"# {slug}\n\n**Target:** `{args.get('target','')}`\n\n"
        f"**Rationale:** {args.get('rationale','')}\n\n"
        f"**Evidence:** {args.get('evidence','')}\n\n---\n\n{args.get('body','')}\n"
    )
    return text(
        f"Staged: maintenance/inbox/{slug}.md\n\n"
        "Still required before this is reviewable: add the matching index entry to "
        "maintenance/state.md's `inbox` array. Without it the proposal is "
        "invisible to the inbox view and the stat block."
    )


HANDLERS = {
    "vault_search": t_vault_search,
    "history_search": t_history_search,
    "job_context": t_job_context,
    "worklist": t_worklist,
    "propose": t_propose,
}

PROMPTS = [
    {"name": f"enter_{m}", "description": f"Open {m} with its methodology and job context loaded."}
    for m in MODES
]


def prompt_text(name: str) -> str:
    mode = name.removeprefix("enter_")
    # Was a fourth hardcoded copy of this map, and one that happened to be
    # right while another was wrong. jobs.py owns it now.
    method = methodology_path(mode)
    body = (VAULT / method).read_text()[:6000] if method and (VAULT / method).exists() else ""
    return (f"You are operating in Noctis's {mode} mode. Its methodology follows. "
            f"Call worklist to see what is in flight, and job_context for any active job.\n\n{body}")


# ---------------------------------------------------------------- loop
def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        if rid is None:
            continue                      # notification

        try:
            if method == "initialize":
                ok(rid, {
                    "protocolVersion": negotiate(req.get("params", {}).get("protocolVersion")),
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": {"name": "noctis", "version": "2.0.0"},
                })
            elif method == "tools/list":
                ok(rid, {"tools": TOOLS})
            elif method == "tools/call":
                p = req.get("params", {})
                handler = HANDLERS.get(p.get("name", ""))
                if handler is None:
                    err(rid, -32602, f"no such tool: {p.get('name')}")
                else:
                    ok(rid, handler(p.get("arguments") or {}))
            elif method == "prompts/list":
                ok(rid, {"prompts": PROMPTS})
            elif method == "prompts/get":
                name = req.get("params", {}).get("name", "")
                ok(rid, {"description": name, "messages": [
                    {"role": "user", "content": {"type": "text", "text": prompt_text(name)}}]})
            elif method == "resources/list":
                ok(rid, {"resources": [
                    {"uri": "noctis://worklist", "name": "worklist", "mimeType": "text/markdown"}]})
            elif method == "resources/read":
                ok(rid, {"contents": [{
                    "uri": "noctis://worklist", "mimeType": "text/markdown",
                    "text": t_worklist({})["content"][0]["text"]}]})
            else:
                err(rid, -32601, f"no method {method}")
        except Exception as e:                      # never take the server down
            err(rid, -32603, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
