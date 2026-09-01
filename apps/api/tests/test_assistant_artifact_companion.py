"""The artifact companion declares no more than the MCP server permits.

WHY THIS SUITE EXISTS AT ALL
============================
The companion's tool list lives in a JSON file that no running code reads. That is
a genuine hazard: a declaration nothing consumes drifts silently, and the first
reader to notice is an operator holding a companion that asks for a capability the
server refuses — or, worse, one that stopped asking for a capability it needs and
quietly does less.

So the enforcement is here. Every assertion below compares the committed
declaration against ``policy.py``, which is the thing that actually decides. None
of it needs a live MCP endpoint, a network, a credential, or a scientific record.

WHAT THIS SUITE DELIBERATELY DOES NOT CLAIM
===========================================
It does not prove the companion works. It cannot: no vendor-documented client API
for AI-powered or MCP-calling artifacts was available on 2026-08-31, so the
companion's call surface is an unimplemented seam and is tested only for being
honest about that. Proving the companion works needs an externally-verifiable fact
this repository does not hold.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from isaac_api import artifact_link
from isaac_api.mcp import policy, tools

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPANION_DIR = REPO_ROOT / "artifacts" / "isaac-assistant"
MANIFEST_PATH = COMPANION_DIR / "tool-permission-manifest.json"
HTML_PATH = COMPANION_DIR / "index.html"
PROMPT_PATH = COMPANION_DIR / "artifact-prompt.md"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


# --- the declaration matches the server ------------------------------------


def test_manifest_declares_exactly_the_permitted_tools(manifest):
    """Not a subset. Exact.

    A subset check would pass a manifest that had quietly dropped a tool, which is
    the drift direction a reviewer is least likely to notice.
    """
    declared = {entry["tool"] for entry in manifest["tools"]}
    assert declared == set(policy.PERMITTED_TOOL_NAMES)


def test_every_declared_tool_carries_the_scope_the_server_gives_it(manifest):
    """A manifest may not inflate a read into a write, or deflate a write into a read."""
    for entry in manifest["tools"]:
        actual = tools.TOOLS[entry["tool"]].scope.value
        assert entry["scope"] == actual, entry["tool"]


def test_every_declared_mutation_flag_matches_the_tools_own_annotation(manifest):
    for entry in manifest["tools"]:
        annotations = tools.TOOLS[entry["tool"]].annotations()
        assert entry["mutates"] is (not annotations["readOnlyHint"]), entry["tool"]


def test_the_manifest_requests_no_scope_the_server_cannot_express(manifest):
    """``Scope`` has two members on purpose. A third here would be a fiction."""
    assert set(manifest["scopes_requested"]) == {scope.value for scope in policy.Scope}


def test_no_declared_tool_name_carries_a_forbidden_capability_token(manifest):
    """The server refuses these at import. The companion must not ask for one either."""
    for entry in manifest["tools"]:
        assert policy.forbidden_tool_reason(entry["tool"]) is None, entry["tool"]


def test_the_manifests_forbidden_token_list_is_the_servers_own(manifest):
    """Kept in sync so a token added to the server is a failing test here.

    Without this, adding a forbidden verb server-side would leave the companion's
    published "never" list quietly understating the refusal.
    """
    assert set(manifest["never"]["forbidden_name_tokens"]) == set(
        policy.FORBIDDEN_TOOL_TOKENS
    )


def test_the_companion_declares_no_finalisation_capability(manifest):
    """Submit, export, delete, governance, migration — named, not implied."""
    never = manifest["never"]
    for capability in ("submit", "export", "delete", "governance", "migration"):
        assert capability in never
        assert isinstance(never[capability], str) and never[capability].strip()


# --- the operator-supplied link is disabled by default ----------------------


def test_the_artifact_link_is_unconfigured_by_default():
    resolved = artifact_link.resolve_artifact_link({})
    assert resolved.is_configured is False
    assert resolved.url is None


def test_a_blank_value_is_still_unconfigured_rather_than_a_refusal():
    resolved = artifact_link.resolve_artifact_link(
        {artifact_link.ARTIFACT_URL_ENV: "   "}
    )
    assert resolved.is_configured is False


def test_a_well_formed_operator_value_is_accepted():
    resolved = artifact_link.resolve_artifact_link(
        {artifact_link.ARTIFACT_URL_ENV: "https://claude.ai/public/artifacts/synthetic-id"}
    )
    assert resolved.is_configured is True
    assert resolved.url == "https://claude.ai/public/artifacts/synthetic-id"


@pytest.mark.parametrize(
    "value, because",
    [
        ("http://claude.ai/public/artifacts/x", "the scheme is not https"),
        ("https://user:pw@claude.ai/public/artifacts/x", "it carries embedded credentials"),
        ("https://claude.ai:8443/public/artifacts/x", "it names an explicit port"),
        ("https://artifacts.example.invalid/x", "the host is not a permitted artifact host"),
        ("https://claude.ai/", "it names no artifact path"),
        ("https://claude.ai/public/artifacts/x?experiment=E1", "query string or fragment"),
        ("https://claude.ai/public/artifacts/x#E1", "query string or fragment"),
    ],
)
def test_a_bad_operator_value_is_refused_with_a_reason(value, because):
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.resolve_artifact_link({artifact_link.ARTIFACT_URL_ENV: value})
    assert because in str(caught.value)


def test_a_refusal_never_repeats_the_offending_value():
    """An operator who pastes a secret into the wrong variable must not see it logged.

    The distinctive substring is checked rather than the whole URL, because a
    message that echoed only the host would still be an echo.
    """
    secret_ish = "https://artifacts.example.invalid/tok-abcdef123456"
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.resolve_artifact_link(
            {artifact_link.ARTIFACT_URL_ENV: secret_ish}
        )
    message = str(caught.value)
    assert "tok-abcdef123456" not in message
    assert "artifacts.example.invalid" not in message


def test_embedding_is_refused_rather_than_unimplemented():
    """The raise is the decision. See docs/isaac-assistant-artifact-feasibility.md §4."""
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.embed_markup()
    assert "organization-private" in str(caught.value)


# --- nothing account-bearing is committed ----------------------------------


COMPANION_FILES = (HTML_PATH, PROMPT_PATH, MANIFEST_PATH, COMPANION_DIR / "README.md")


def test_no_committed_companion_file_carries_an_artifact_url():
    """The URL is operator-supplied. A literal here would be an access-bearing commit.

    ``claude.ai`` is permitted to appear as prose; a ``https://claude.ai/...`` URL
    is not, which is the distinction that matters.
    """
    pattern = re.compile(r"https?://(?:www\.)?claude\.ai/\S+")
    for path in COMPANION_FILES:
        assert not pattern.search(path.read_text()), path


def test_the_page_source_embeds_no_endpoint_token_or_account_identifier():
    text = HTML_PATH.read_text()
    for forbidden in ("Bearer ", "api_key", "apiKey", "client_secret", "@slac.stanford.edu"):
        assert forbidden not in text, forbidden


def test_the_page_source_makes_no_connected_claim():
    """docs/ai-integration-decision-packet.md §6.1 — no fake ``Connected`` state.

    The page may say it is NOT connected; it may not say it is.
    """
    text = HTML_PATH.read_text()
    assert "Not connected" in text
    assert not re.search(r"(?<!Not )\bConnected\b", text)


def test_the_page_source_states_that_finalising_is_not_its_act():
    text = HTML_PATH.read_text()
    assert "Finalising a record" in text
    assert "No\n          tool here can do it" in text or "No tool here can do it" in text


def test_the_seam_fails_closed_and_says_so():
    """The seam must not look like a working call that happened to return nothing."""
    text = HTML_PATH.read_text()
    assert "companion_seam_unset" in text
    assert "Nothing was sent" in text


def test_the_prompt_carries_the_refusal_paths_it_must(manifest):
    """The behaviour contract is reviewable source, so its load-bearing clauses are pinned."""
    text = PROMPT_PATH.read_text()
    assert "You cannot submit a record" in text
    assert "412 stale_write" in text
    assert "each user connects independently" in text.lower() or (
        "connect independently" in text.lower()
    )
    assert "never guessed" in text.lower()
