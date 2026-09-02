"""``GET /api/runtime/assistant-companion`` — the companion link, reported honestly.

WHY THIS SUITE EXISTS
=====================
``apps/api/isaac_api/artifact_link.py`` shipped with **no consumer**: no route
registered it, no module imported it, and no screen referenced it. So the entry
point the companion needs — ISAAC offering a scientist the link — did not exist,
and every check that module makes was unreachable from anything a person meets.
This operation is that consumer. This file is what holds it to what it claims.

WHAT IS ASSERTED HERE, AND WHY IT IS ASSERTED OVER BEHAVIOUR
============================================================
``test_assistant_artifact_companion.py``'s own docstring records two guards in this
feature that **passed while being wrong**, because the central claim was pinned by
string presence rather than by what the code does: a visible lowercase "Status:
connected…" survived 25 tests, and a fabricating seam returning
``{ok: true, record: {...}}`` survived them too.

So every claim below is driven rather than read:

* the refusal categories are produced by CONFIGURING each bad value and reading
  the response, not by inspecting ``artifact_link``;
* "no rejected value is echoed" is checked by planting a distinctive marker in a
  different POSITION of each bad value (userinfo, host, port, path, query,
  fragment, after a control character) and searching the whole serialized
  response — with a negative control proving the search is not inert;
* "``embed_markup`` is not reachable through the route" is checked by REPLACING it
  with a recorder and asserting the recorder stayed empty in all three states —
  with a negative control proving the recorder fires when it is called;
* "it opens no outbound connection" is checked by ARMING the four plausible ways a
  future author would fetch a URL so that each raises — again with a negative
  control proving the trap is live.

NOTHING HERE PUBLISHES, SHARES, OR CONTACTS ANYTHING
====================================================
Every URL in this file is synthetic and unmistakably so. No artifact is created,
published or shared; no account identifier appears; nothing opens a socket. The
one permitted host is exercised only with obviously-fake paths, and a guard below
asserts this file commits no value that would read as a real companion link.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from isaac_api import artifact_link

COMPANION_PATH = "/api/runtime/assistant-companion"

#: A synthetic path segment, chosen so a reader can never mistake a value in this
#: file for a real artifact link.
SYNTHETIC_LINK = "https://claude.ai/public/artifacts/synthetic-not-a-real-artifact"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A clean environment. The companion variable is UNSET by default, because
    unset is the state this operation must get right first."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.delenv(artifact_link.ARTIFACT_URL_ENV, raising=False)
    return monkeypatch


@pytest.fixture()
def client(env):
    from isaac_api.app import create_app

    return TestClient(create_app())


def companion(client) -> dict:
    """The operation's body, with its status asserted on the way through.

    Every state this operation can report is a `200`. A helper that asserted only
    the body would let a refusal become a 500 without a single test noticing.
    """
    response = client.get(COMPANION_PATH)
    assert response.status_code == 200, response.text
    return response.json()


# --- 1. UNCONFIGURED: the default, and the case that matters most ---------------


def test_unconfigured_is_the_default_and_is_a_normal_answer(client):
    """No variable set, and the operation answers plainly rather than failing.

    Asserted as three separate facts because they fail independently: the status,
    the state, and the absence of a link.
    """
    response = client.get(COMPANION_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "unconfigured"
    assert body["url"] is None


def test_unconfigured_is_not_a_404_and_not_an_error(client):
    """The defect this catches: treating "no companion" as a missing resource.

    A `404` would make an absent companion look like a broken deployment, and a
    `5xx` would make it look like a fault. It is neither: it is the default state
    of every deployment of this application, and an operator has to be able to read
    that from a successful response.
    """
    response = client.get(COMPANION_PATH)
    assert response.status_code not in (404, 500, 501, 503)
    assert response.status_code == 200


def test_nothing_link_shaped_is_disclosed_when_nothing_is_configured(client):
    """Asserted over the WHOLE serialized body, not over the `url` key.

    A `url: null` beside a helpful example in some other field would satisfy a
    key-by-key check and would still be a committed link in the response.
    """
    dumped = json.dumps(companion(client)).lower()
    assert "http" not in dumped
    assert "claude.ai" not in dumped
    for host in artifact_link.PERMITTED_ARTIFACT_HOSTS:
        assert host.lower() not in dumped


def test_the_unconfigured_reason_is_the_modules_own_words(client):
    """Relayed, not re-worded, so the sentence a reader sees cannot drift from the
    module that decided it."""
    assert companion(client)["reason"] == artifact_link.UnconfiguredArtifactLink().reason


# --- 2. CONFIGURED: a well-formed operator value --------------------------------


def test_a_configured_link_is_reported_and_served(client, env):
    env.setenv(artifact_link.ARTIFACT_URL_ENV, SYNTHETIC_LINK)
    body = companion(client)
    assert body["state"] == "configured"
    assert body["url"] == SYNTHETIC_LINK


def test_the_served_link_is_the_validated_form_not_the_supplied_string(client, env):
    """THE DEFECT: a route that reads the environment itself and echoes what it
    finds, rather than serving what `artifact_link` validated and stored.

    Both halves are asserted, because either alone passes on the defect: the served
    value is the normalised one, AND the string as supplied appears nowhere in the
    response at all.
    """
    supplied = "https://CLAUDE.AI/public/artifacts/synthetic-mixed-case"
    env.setenv(artifact_link.ARTIFACT_URL_ENV, supplied)
    body = companion(client)
    assert body["url"] == "https://claude.ai/public/artifacts/synthetic-mixed-case"
    assert supplied not in json.dumps(body)
    assert "CLAUDE.AI" not in json.dumps(body)


def test_the_environment_is_read_per_request_and_never_cached(client, env):
    """THE DEFECT: resolving the link once at import, so an operator who changes
    the variable is reported from a value this process read before they did.

    Driven in both directions — off, on, off — because a cache that happened to be
    populated with the second value would pass a one-way check.
    """
    assert companion(client)["state"] == "unconfigured"
    env.setenv(artifact_link.ARTIFACT_URL_ENV, SYNTHETIC_LINK)
    assert companion(client)["state"] == "configured"
    env.delenv(artifact_link.ARTIFACT_URL_ENV)
    assert companion(client)["state"] == "unconfigured"


# --- 3. REFUSED: every category the module implements ---------------------------
#
# Every entry is a value on the SYNTHETIC path only, and each names the category
# `artifact_link` refuses it under. The table is deliberately exhaustive over that
# module's refusal branches: a category added there with no entry here is a
# category no route test covers.

REFUSALS: tuple[tuple[str, str, str], ...] = (
    (
        "scheme",
        "http://claude.ai/public/artifacts/synthetic-a",
        "the scheme is not https",
    ),
    (
        "credentials",
        "https://someone:pw@claude.ai/public/artifacts/synthetic-b",
        "it carries embedded credentials",
    ),
    (
        "explicit port",
        "https://claude.ai:8443/public/artifacts/synthetic-c",
        "it names an explicit port",
    ),
    (
        "unparseable port",
        "https://claude.ai:notaport/public/artifacts/synthetic-d",
        "its port is not a number",
    ),
    (
        "out-of-range port",
        "https://claude.ai:99999/public/artifacts/synthetic-e",
        "its port is not a number",
    ),
    (
        "host",
        "https://artifacts.example.invalid/public/artifacts/synthetic-f",
        "the host is not a permitted artifact host",
    ),
    ("no path", "https://claude.ai/", "it names no artifact path"),
    (
        "query string",
        "https://claude.ai/public/artifacts/synthetic-g?experiment=E1",
        "it carries a query string or fragment",
    ),
    (
        "fragment",
        "https://claude.ai/public/artifacts/synthetic-h#E1",
        "it carries a query string or fragment",
    ),
    (
        "control character",
        "https://claude.ai/public/artifacts/synthetic-i\r\nLocation: https://evil.invalid",
        "it contains a control character",
    ),
)


@pytest.mark.parametrize("category, value, because", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_a_refused_value_is_reported_as_a_state_not_as_a_failure(
    client, env, category, value, because
):
    """A present-but-wrong value is a configuration fact an operator must READ.

    Four independent assertions, because each fails on a different defect: the
    status is not an error, the state names the refusal, no link is served anyway,
    and the reason names the category that actually failed rather than a generic
    one.
    """
    env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    response = client.get(COMPANION_PATH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "refused", category
    assert body["url"] is None, category
    assert because in body["reason"], category


def test_a_refusal_never_becomes_a_server_error(client, env):
    """THE DEFECT: letting `ArtifactLinkRefusal` escape the handler.

    The malformed-port values are the ones that would do it most quietly — the
    module catches a `ValueError` from `urlsplit` there, and an earlier revision of
    that module did not — so a route that did not guard the refusal would surface
    them as a crash whose message QUOTES the value.
    """
    for _category, value, _because in REFUSALS:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
        assert client.get(COMPANION_PATH).status_code == 200, value


def test_a_blank_value_is_unconfigured_rather_than_refused(client, env):
    """Whitespace is somebody clearing the variable, not somebody getting it wrong.

    Reported as `unconfigured`, so a screen says "there is no companion" rather
    than "your operator misconfigured something".
    """
    env.setenv(artifact_link.ARTIFACT_URL_ENV, "   ")
    body = companion(client)
    assert body["state"] == "unconfigured"
    assert body["url"] is None


# --- 4. NO REJECTED VALUE IS EVER ECHOED ----------------------------------------
#
# The marker is planted in a DIFFERENT POSITION in each value — userinfo, host,
# port, path, query, fragment, and the text following a control character — because
# a leak is a property of a position, not of a category. A single marker in a path
# would leave six positions untested.

MARKER = "marker9f2b7c4e"

ECHO_CASES: tuple[tuple[str, str], ...] = (
    ("path, non-https", f"http://claude.ai/public/artifacts/{MARKER}"),
    ("userinfo", f"https://{MARKER}:pw@claude.ai/public/artifacts/synthetic-j"),
    ("port", f"https://claude.ai:{MARKER}/public/artifacts/synthetic-k"),
    ("host", f"https://{MARKER}.example.invalid/public/artifacts/synthetic-l"),
    ("query", f"https://claude.ai/public/artifacts/synthetic-m?ref={MARKER}"),
    ("fragment", f"https://claude.ai/public/artifacts/synthetic-n#{MARKER}"),
    ("after a control character", f"https://claude.ai/x\r\nX-Planted: {MARKER}"),
)


def echoes(marker: str, payload: object) -> bool:
    """Whether ``marker`` survives anywhere in a serialized payload."""
    return marker.lower() in json.dumps(payload).lower()


@pytest.mark.parametrize("where, value", ECHO_CASES, ids=[c[0] for c in ECHO_CASES])
def test_a_refusal_repeats_no_part_of_the_supplied_value(client, env, where, value):
    """An operator who pastes the wrong string into this variable must not have it
    copied back out into a response, a log line, or a screen.

    The whole serialized body is searched rather than the `reason` field, because a
    route that helpfully added `"supplied": value` beside an honest reason would
    pass a field-scoped check.
    """
    env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    body = companion(client)
    assert body["state"] == "refused", where
    assert not echoes(MARKER, body), where


def test_the_echo_search_would_actually_fire():
    """A negative control. Without it, a typo in `echoes` would leave every case
    above "clean" forever — which is exactly how this feature's two other guards
    passed while being wrong."""
    assert echoes(MARKER, {"reason": f"refused: {MARKER} is not permitted"})
    assert echoes(MARKER, {"nested": [{"supplied": MARKER.upper()}]})
    assert not echoes(MARKER, {"reason": "the host is not a permitted artifact host"})


#: Every `claude.ai` path this file is allowed to contain, other than one saying
#: `synthetic` outright: the empty path (the "names no artifact path" refusal), the
#: one-character stub the control-character values use, and the marker placeholder.
_NON_IDENTIFYING_PATHS = ("", "x", "public/artifacts/{MARKER}")


def test_no_value_in_this_file_would_read_as_a_real_companion_link():
    """A guard on the test file itself, mirroring the one over the companion's own
    committed files: a published artifact URL is access-bearing, and an example in
    a test is where one would most plausibly be pasted.

    The claim is narrow and checkable — no `claude.ai` URL here names a concrete
    artifact id. Every one either says `synthetic` in its path or is one of three
    enumerated non-identifying forms.
    """
    source = __import__("pathlib").Path(__file__).read_text()
    found = 0
    for match in re.finditer(
        r"(?i)https?://(?:www\.)?claude\.ai(?::[^/\s]*)?/([A-Za-z0-9._~\-/%{}]*)", source
    ):
        found += 1
        path = match.group(1)
        assert "synthetic" in path.lower() or path in _NON_IDENTIFYING_PATHS, match.group(0)
    # Not vacuous: this file really does carry URLs for the guard to inspect.
    assert found >= 10, found


# --- 5. EMBEDDING IS NOT REACHABLE THROUGH THIS ROUTE ---------------------------


class _Recorder:
    """Stands in for ``embed_markup`` and records rather than raising.

    Raising would be weaker: a handler that CALLED it inside a ``try`` would look
    identical to one that never called it at all.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs) -> str:
        self.calls.append((args, kwargs))
        return "<iframe src='about:blank'></iframe>"


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-o"],
    ids=["unconfigured", "configured", "refused"],
)
def test_the_route_never_reaches_the_embedding_function(client, env, monkeypatch, value):
    """`embed_markup` raises by design; a route that called it would be a 500 in one
    state and would be offering an embed in another. It is replaced with a recorder
    so BOTH failures are visible as an empty call list rather than as an exception.

    Driven in all three states, because a call site could sit in any one branch.
    """
    recorder = _Recorder()
    monkeypatch.setattr(artifact_link, "embed_markup", recorder)
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    companion(client)
    assert recorder.calls == []


def test_the_embedding_recorder_would_actually_fire(monkeypatch):
    """A negative control. A recorder patched onto the wrong name records nothing
    and the test above passes vacuously."""
    recorder = _Recorder()
    monkeypatch.setattr(artifact_link, "embed_markup", recorder)
    artifact_link.embed_markup("anything")
    assert len(recorder.calls) == 1


def test_the_real_embedding_function_still_refuses():
    """The route not calling it is only half the claim. The other half is that it
    remains a refusal rather than becoming implementable by accident."""
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.embed_markup()
    assert "organization-private" in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-p"],
    ids=["unconfigured", "configured", "refused"],
)
def test_the_response_offers_no_embed_in_any_state(client, env, value):
    """Asserted over the payload rather than over the handler: no markup, no inline
    frame, and no list of domains permitted to host the companion."""
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    body = companion(client)
    dumped = json.dumps(body).lower()
    for forbidden in ("<iframe", "iframe", "<script", "allowed_domains", "allowed domains"):
        assert forbidden not in dumped, forbidden
    assert body["link_kind"] == "deep_link"


# --- 6. IT OPENS NOTHING AND CLAIMS NOTHING ABOUT REACHABILITY ------------------


@pytest.fixture()
def no_outbound(monkeypatch):
    """Arm the four plausible ways a future author would fetch the configured link.

    ``TestClient`` speaks to the application in-process, so none of these is on the
    path of an ordinary request — which is what makes them a usable trap.
    """
    import http.client
    import socket
    import urllib.request

    fired: list[str] = []

    def trap(name):
        def _trap(*_args, **_kwargs):
            fired.append(name)
            raise AssertionError(f"the companion report opened an outbound connection via {name}")

        return _trap

    monkeypatch.setattr(socket, "create_connection", trap("socket.create_connection"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", trap("HTTPConnection"))
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", trap("HTTPSConnection"))
    monkeypatch.setattr(urllib.request, "urlopen", trap("urlopen"))
    return fired


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-q"],
    ids=["unconfigured", "configured", "refused"],
)
def test_the_report_opens_no_outbound_connection(client, env, no_outbound, value):
    """THE DEFECT: a future "helpful" improvement that resolves the link so the
    screen can say whether it works — turning a configuration read into an outbound
    request, from a route that documents itself as opening none."""
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    companion(client)
    assert no_outbound == []


def test_the_outbound_trap_would_actually_fire(no_outbound):
    """A negative control: a trap patched onto the wrong name never fires, and the
    test above then passes without establishing anything."""
    import socket

    with pytest.raises(AssertionError):
        socket.create_connection(("example.invalid", 443))
    assert no_outbound == ["socket.create_connection"]


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-r"],
    ids=["unconfigured", "configured", "refused"],
)
def test_reachability_is_never_claimed_in_any_state(client, env, value):
    """`configured` must not be readable as `working`. The claim is published as a
    field so a screen cannot quietly assume the stronger one."""
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    assert companion(client)["checked_reachable"] is False


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-s"],
    ids=["unconfigured", "configured", "refused"],
)
def test_no_state_claims_the_companion_is_connected(client, env, value):
    """`docs/ai-integration-decision-packet.md` §6 forbids a fake connected state.

    Case-insensitive and negation-aware, matching the guard over the companion page
    itself — where a *visible* lowercase claim once passed 25 tests because the
    check was case-sensitive.
    """
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    dumped = json.dumps(companion(client))
    for match in re.finditer(r"(?i)\bconnected\b", dumped):
        preceding = dumped[: match.start()]
        assert re.search(r"(?i)\b(not|never|isn'?t|no)\s+$", preceding), dumped


def test_the_connected_search_would_actually_fire():
    """A negative control for the check above."""
    pattern = re.compile(r"(?i)\bconnected\b")
    assert pattern.search('{"state": "connected"}')
    assert not pattern.search('{"state": "configured"}')


# --- 7. THE PUBLISHED SHAPE IS A CONTRACT ---------------------------------------


EXPECTED_KEYS = {
    "state",
    "url",
    "reason",
    "configured_by",
    "link_kind",
    "checked_reachable",
    "prerequisite",
    "reference",
}


@pytest.mark.parametrize(
    "value",
    [None, SYNTHETIC_LINK, "http://claude.ai/public/artifacts/synthetic-t"],
    ids=["unconfigured", "configured", "refused"],
)
def test_every_state_publishes_exactly_the_same_key_set(client, env, value):
    """A key that appears only in one state is a key a client will forget to handle
    — and, in the refused state, a key that could carry what was supplied."""
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    assert set(companion(client)) == EXPECTED_KEYS


@pytest.mark.parametrize(
    "value, expected_state",
    [
        (None, "unconfigured"),
        (SYNTHETIC_LINK, "configured"),
        ("http://claude.ai/public/artifacts/synthetic-u", "refused"),
    ],
    ids=["unconfigured", "configured", "refused"],
)
def test_a_link_is_served_exactly_when_the_state_says_configured(
    client, env, value, expected_state
):
    """Stated as the property rather than as three cases, because the failure this
    prevents is a link served beside a state that says there is none."""
    if value is not None:
        env.setenv(artifact_link.ARTIFACT_URL_ENV, value)
    body = companion(client)
    assert body["state"] == expected_state
    assert (body["url"] is not None) is (body["state"] == "configured")


def test_the_variable_name_is_published_and_the_value_is_not(client, env):
    """An operator needs to know WHICH variable to set. That is a name, and a name
    is not a value."""
    env.setenv(artifact_link.ARTIFACT_URL_ENV, SYNTHETIC_LINK)
    body = companion(client)
    assert body["configured_by"] == artifact_link.ARTIFACT_URL_ENV
    assert artifact_link.ARTIFACT_URL_ENV in json.dumps(body)


def test_the_prerequisite_this_application_cannot_observe_is_stated(client):
    """The feasibility record requires the connector prerequisite to travel beside
    the link, because a scientist who has not enabled it lands on a companion that
    can do nothing."""
    body = companion(client)
    assert "connector" in body["prerequisite"].lower()
    assert body["reference"].endswith(".md")


# --- 8. READ-ONLY, AND DOCUMENTED --------------------------------------------


def test_it_is_get_only(client):
    for method in (client.post, client.put, client.patch, client.delete):
        assert method(COMPANION_PATH).status_code == 405


def test_it_mutates_nothing(client, tmp_path, env):
    ws_dir = tmp_path / "ws"

    def listing():
        return sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []

    before = listing()
    companion(client)
    env.setenv(artifact_link.ARTIFACT_URL_ENV, SYNTHETIC_LINK)
    companion(client)
    env.setenv(artifact_link.ARTIFACT_URL_ENV, "http://claude.ai/public/artifacts/synthetic-v")
    companion(client)
    assert listing() == before


def test_the_operation_is_published_in_the_generated_contract(client):
    """A route a client cannot discover is not an entry point. Checked against the
    served document rather than the route table, because that is what a client
    reads."""
    schema = client.get("/api/openapi").json()
    operation = schema["paths"][COMPANION_PATH]["get"]
    assert operation["summary"] and operation["summary"] != "Get Assistant Artifact Companion"
    assert len(operation["description"]) > 400
    assert sorted(operation["responses"]) == ["200", "401"]


def test_the_published_documentation_offers_no_embed(client):
    """The description must not hand a reader an embedding affordance either — the
    refusal is a decision, and documentation that hedged it would be the first step
    to reversing it."""
    schema = client.get("/api/openapi").json()
    description = schema["paths"][COMPANION_PATH]["get"]["description"].lower()
    assert "iframe" not in description
    assert "deep_link" in description
    assert "never returns markup" in description
