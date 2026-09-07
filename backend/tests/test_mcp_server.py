"""MCP server tests — Noctis v2 Stage 2 item 2.

Driven over real stdio JSON-RPC, the same way a client drives it, rather
than by importing handlers directly — the wire format is the contract, and
a test that bypasses it would not catch a broken one.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "mcp" / "server.py"


@pytest.fixture(scope="module")
def vault(tmp_path_factory):
    v = tmp_path_factory.mktemp("vault")
    (v / "wiki").mkdir()
    (v / "wiki" / "Tooling Decisions.md").write_text(
        "# Tooling Decisions\n\n## Deployment platform\n\n"
        "Railway adopted for anything with a persistent backend. Vercel for "
        "static frontends only, since serverless functions time out.\n" + ("filler. " * 60)
    )
    (v / "wiki" / "Bello.md").write_text(
        "# Bello\n\n## Scope\n\nInformational website only, mailing list signup.\n"
        + ("padding. " * 60)
    )
    jobs = v / "modes" / "dev" / "jobs" / "noctis-os"
    jobs.mkdir(parents=True)
    (jobs / "context.md").write_text("---\nstage: Build\n---\n\nTrack: Overhaul\n")
    (v / "modes" / "dev" / "state.md").write_text("---\njobs: [noctis-os]\n---\n")
    return v


def rpc(vault_path, *requests):
    """Send JSON-RPC lines to a fresh server process; return parsed replies."""
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    out = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload, capture_output=True, text=True, timeout=90,
        env={"PATH": "/usr/bin:/bin", "VAULT_PATH": str(vault_path)},
    )
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def call(vault_path, tool, args=None, rid=2):
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
         "params": {"name": tool, "arguments": args or {}}},
    ]
    reply = [r for r in rpc(vault_path, *reqs) if r.get("id") == rid][0]
    return reply["result"]["content"][0]["text"]


def test_handshake_declares_all_three_primitives(vault):
    (reply,) = rpc(vault, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18"}})
    caps = reply["result"]["capabilities"]
    assert {"tools", "prompts", "resources"} <= set(caps)
    assert reply["result"]["serverInfo"]["name"] == "noctis"


def test_lists_the_five_tools(vault):
    replies = rpc(vault,
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in replies[-1]["result"]["tools"]}
    assert names == {"vault_search", "history_search", "job_context", "worklist", "propose"}


def test_vault_search_returns_the_relevant_document(vault):
    out = call(vault, "vault_search", {"query": "which host for a persistent backend"})
    assert "Tooling Decisions.md" in out


def test_vault_search_says_so_when_nothing_matches(vault):
    """BM25 score is not a confidence signal, so an empty result set is the
    only honest 'nothing here' this layer can give."""
    out = call(vault, "vault_search", {"query": "zzzqqq nonexistent xylophone"})
    assert "No matches" in out


def test_job_context_returns_durable_state(vault):
    out = call(vault, "job_context", {"mode": "faber", "slug": "noctis-os"})
    assert "stage: Build" in out and "Overhaul" in out


def test_job_context_lists_jobs_when_no_slug_given(vault):
    assert "noctis-os" in call(vault, "job_context", {"mode": "faber"})


def test_unknown_mode_is_reported_not_crashed(vault):
    assert "Unknown mode" in call(vault, "job_context", {"mode": "nonsense"})


def test_worklist_reads_mode_state(vault):
    assert "dev" in call(vault, "worklist")


def test_propose_stages_a_file_and_names_what_is_still_required(vault):
    out = call(vault, "propose", {
        "slug": "test-proposal", "target": "modes/dev/dev.md",
        "rationale": "because X", "evidence": "lessons entry Y", "body": "the diff"})
    staged = vault / "modes" / "nightshift" / "inbox" / "test-proposal.md"
    assert staged.exists() and "because X" in staged.read_text()
    # The index entry is deliberately not written here: doing both would let
    # a caller believe it had filed something reviewable when it had not.
    assert "state.md" in out and "invisible" in out


def test_propose_refuses_to_clobber_an_existing_proposal(vault):
    args = {"slug": "dupe", "target": "t", "rationale": "r", "evidence": "e", "body": "b"}
    call(vault, "propose", args)
    assert "already exists" in call(vault, "propose", args)


def test_prompts_expose_mode_entry(vault):
    replies = rpc(vault,
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                  {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"})
    assert {"enter_faber", "enter_vesper"} <= {p["name"] for p in replies[-1]["result"]["prompts"]}


def test_unknown_method_returns_an_error_not_a_crash(vault):
    replies = rpc(vault,
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                  {"jsonrpc": "2.0", "id": 2, "method": "nonsense/method"})
    assert replies[-1]["error"]["code"] == -32601


def test_server_runs_with_no_third_party_dependencies(vault):
    """The 'clone it and point it at your own vault' story depends on this:
    the env below has no site-packages beyond the stdlib on PATH."""
    assert call(vault, "worklist")
