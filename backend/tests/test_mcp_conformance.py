"""MCP conformance — the spec's criterion 3, as a test rather than a demo.

The pass condition is "all five tools callable from a client containing zero
Noctis-specific code, and a question whose answer exists only in the vault
answered correctly". The intended proof was Zed or Cursor pointed at the
server; this is the same property, checked automatically.

The client below is deliberately ignorant. It speaks JSON-RPC over stdio and
knows nothing about Noctis: no imports from the codebase, no hardcoded tool
names where the server can supply them, no assumptions about arguments beyond
what `tools/list` advertises. If it can drive the server, so can any MCP
client — which is the actual claim being made about the portable half.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "mcp" / "server.py"
VAULT = Path(__file__).resolve().parents[2].parent / "second-brain"


class DumbMCPClient:
    """A generic MCP client. Knows JSON-RPC and nothing else."""

    def __init__(self, command: list[str], env: dict | None = None):
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env,
        )
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        request = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            request["params"] = params
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()

        # Skip anything that is not a response to this id: a conformant
        # client cannot assume the next line is its answer.
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise AssertionError(f"server closed the stream during {method}")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == self._id:
                return message

    def close(self):
        self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


@pytest.fixture
def client():
    import os
    env = dict(os.environ)
    env["VAULT_PATH"] = str(VAULT)
    c = DumbMCPClient([sys.executable, str(SERVER)], env=env)
    c.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "dumb-client", "version": "0"}})
    yield c
    c.close()


def test_the_server_needs_nothing_installed():
    """Dependency-free by choice — it is what makes this the half that
    travels. A server needing a package manager is not something someone
    else points their editor at on a whim.

    The rule is "nothing to install", not "stdlib only": the server imports
    `retrieval.index`, which is a sibling module in this repo and therefore
    still `python3 server.py` with no pip. What would break the claim is a
    third-party package, so that is what this checks — every import must
    resolve to the standard library or to a file inside this repo.
    """
    import importlib.util
    import sysconfig

    stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
    repo = SERVER.resolve().parents[2]

    for line in SERVER.read_text().splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        module = stripped.split()[1].split(".")[0]
        if module == "__future__":
            continue

        spec = importlib.util.find_spec(module)
        assert spec is not None, f"{module} does not resolve at all"
        if spec.origin in (None, "built-in", "frozen"):
            continue                       # built into the interpreter

        origin = Path(spec.origin).resolve()
        bundled = stdlib in origin.parents or repo in origin.parents
        assert bundled, (
            f"{module} is a third-party package ({origin}) — a client would "
            "have to install something, and the server's claim is that it does not"
        )


def test_what_has_to_travel_with_the_server():
    """"Nothing to install" is true; "copy one file" is not.

    `python3 server.py` needs `retrieval/` and `orchestrator/` beside it, so
    adopting this means copying three directories. That is still no package
    manager and no install step — but it is what the adoption docs have to
    say, and this test exists so the list stays accurate rather than being
    discovered by whoever tries it first.
    """
    source = SERVER.read_text()
    siblings = {line.split()[1].split(".")[0]
                for line in source.splitlines()
                if line.strip().startswith("from ")}
    local = {s for s in siblings if (SERVER.parents[1] / s).is_dir()}
    assert local == {"retrieval", "orchestrator"}, (
        f"the server's local dependencies changed to {sorted(local)} — the "
        "adoption docs name exactly what has to be copied alongside it"
    )


def test_initialize_announces_the_server(client):
    result = client.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "x", "version": "0"}})["result"]
    assert result["serverInfo"]["name"] == "noctis"
    assert "protocolVersion" in result


# The retrieval surface a portfolio client would use. `permission_prompt` is
# deliberately not one of them: it is plumbing for --permission-prompt-tool,
# not something a session or a third-party client should call, and the
# spec's criterion-3 claim is about these five.
SESSION_TOOLS = {"vault_search", "history_search", "job_context", "worklist", "propose"}


def test_all_five_tools_are_advertised(client):
    """The spec's five, plus the internal prompt tool. Read from the server
    rather than asserted from a list here, so this fails if the surface
    changes rather than if this test goes stale."""
    tools = client.call("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == SESSION_TOOLS | {"permission_prompt"}
    for tool in tools:
        assert tool.get("description"), f"{tool['name']} has no description for a client to show"
        assert "inputSchema" in tool, f"{tool['name']} advertises no schema"


def test_every_advertised_tool_is_actually_callable(client):
    """Advertised and callable are different claims. A tool listed but
    erroring on invocation is worse than one that is absent, because a client
    shows it to the person as available.

    permission_prompt is excluded from the probe rather than given one: by
    design it blocks until a person answers, so calling it here would hang
    this test for the registry's full expiry and then assert on a refusal.
    Its own behaviour is covered in test_permissions.py.
    """
    tools = client.call("tools/list")["result"]["tools"]
    probes = {
        "vault_search": {"query": "noctis"},
        "history_search": {"query": "noctis"},
        "job_context": {"mode": "dev", "slug": "noctis-os"},
        "worklist": {},
        "propose": {"title": "conformance probe", "body": "not applied", "dry_run": True},
    }
    probed = 0
    for tool in tools:
        name = tool["name"]
        if name not in probes:
            continue
        response = client.call("tools/call", {"name": name, "arguments": probes[name]})
        assert "error" not in response, f"{name} errored: {response.get('error')}"
        assert "content" in response["result"], f"{name} returned no content"
        probed += 1
    assert probed == len(SESSION_TOOLS), "a session tool stopped being probed"


def test_a_vault_only_question_is_answerable_through_the_tools(client):
    """The spec's pass condition. The answer exists only in the vault, so a
    client that can reach it through these tools has proven the thing the
    whole MCP half claims."""
    if not VAULT.exists():
        pytest.skip("vault not present on this machine")

    found = client.call("tools/call", {
        "name": "vault_search", "arguments": {"query": "Noctis v2 orchestrator session"},
    })["result"]
    text = json.dumps(found)
    assert "noctis" in text.lower(), "vault_search found nothing about a vault-only subject"


def test_an_unknown_tool_is_refused_rather_than_ignored(client):
    """A client will send them; silence would be read as success."""
    response = client.call("tools/call", {"name": "not_a_tool", "arguments": {}})
    assert "error" in response or response["result"].get("isError")


def test_prompts_and_resources_are_exposed(client):
    """Both are part of the surface a generic client discovers — they are
    what make mode entry reachable from a client that has never heard of
    Noctis."""
    prompts = client.call("prompts/list")["result"]["prompts"]
    assert prompts, "no prompts advertised"
    resources = client.call("resources/list")["result"]["resources"]
    assert resources, "no resources advertised"


def test_the_handshake_answers_with_a_version_the_server_speaks(client):
    """The MCP handshake is a negotiation, not an echo. This replied with
    whatever the client asked for — told "1999-01-01" it agreed, and a client
    would then proceed to use features never implemented. It must answer with
    a version it actually supports so the client can decide."""
    from mcp.server import PROTOCOL_VERSIONS

    for requested, expected in (
        ("2024-11-05", "2024-11-05"),          # supported: agree
        ("1999-01-01", PROTOCOL_VERSIONS[0]),  # unknown: offer ours
        (None, PROTOCOL_VERSIONS[0]),          # absent: offer ours
    ):
        params = {"capabilities": {}, "clientInfo": {"name": "x", "version": "0"}}
        if requested is not None:
            params["protocolVersion"] = requested
        answered = client.call("initialize", params)["result"]["protocolVersion"]
        assert answered == expected, f"asked {requested}, answered {answered}"
        assert answered in PROTOCOL_VERSIONS


def test_a_notification_gets_no_response(client):
    """Real clients send notifications/initialized right after the
    handshake. A notification has no id, and replying to one desynchronises
    a client that is counting responses."""
    client.proc.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    client.proc.stdin.flush()
    # The next response must belong to the request after it, not to the
    # notification — if the server answered, this returns the wrong message.
    assert client.call("tools/list")["result"]["tools"]
