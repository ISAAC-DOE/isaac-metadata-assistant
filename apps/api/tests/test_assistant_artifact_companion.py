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

TWO GUARDS WERE PINNED BY STRING PRESENCE AND ARE NOW PINNED BY BEHAVIOUR
========================================================================
An independent review on 2026-08-31 ran two mutations that this suite passed:

1. It added a **visible** ``<p>Status: connected to your ISAAC workspace and
   ready.</p>`` to the page. All 25 tests passed, because the guard searched for
   ``(?<!Not )\\bConnected\\b`` — **case-sensitively**. The exact defect
   ``docs/ai-integration-decision-packet.md`` §6.1 forbids was caught only if the
   author happened to capitalise the C.
2. It replaced ``runCompanionTurn``'s body with a fabricated success —
   ``{ ok: true, record: { status: "complete", pending: 0, qc: "valid" } }``. All
   25 tests passed, because the seam guard only checked that
   ``companion_seam_unset`` and ``Nothing was sent`` appeared **somewhere** in the
   file, and the surviving constant and the empty-ID branch kept both strings
   alive.

Both are now asserted over what the page **does**: the Connected guard is
case-insensitive, requires a negation before every occurrence, and additionally
requires the disclosure to be rendered inside the live region a reader sees; and
the seam is **executed** in a Node harness that invokes a turn and reads the
result, with an unconditional structural backstop for an environment with no Node.
"""

from __future__ import annotations

import html as html_module
import json
import re
import shutil
import subprocess
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


# --- small deterministic readers over the page source -----------------------
#
# These exist so the assertions below can be about what a READER sees rather than
# about what the bytes contain. A claim inside an HTML comment, a ``<style>`` block
# or an attribute is not a claim the page makes to a person, and a claim the page
# makes to a person must not be provable only by ``in text``.

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def rendered_text(source: str) -> str:
    """Roughly what a reader sees: comments, scripts, styles and tags removed."""
    stripped = _SCRIPT_OR_STYLE.sub(" ", _COMMENT.sub(" ", source))
    return " ".join(html_module.unescape(_TAG.sub(" ", stripped)).split())


def element_source(source: str, element_id: str) -> str:
    """The full source of the element carrying ``id="<element_id>"``.

    Deliberately a small hand-rolled scanner rather than a dependency: it has to
    work on a file that is committed page source, and it only has to handle the
    one well-formed shape this repository writes.
    """
    marker = source.index(f'id="{element_id}"')
    start = source.rindex("<", 0, marker)
    name = re.match(r"<([A-Za-z][\w-]*)", source[start:]).group(1)
    opener = re.compile(rf"<{name}\b", re.IGNORECASE)
    closer = re.compile(rf"</{name}\s*>", re.IGNORECASE)
    depth = 0
    cursor = start
    while cursor < len(source):
        nxt_open = opener.search(source, cursor)
        nxt_close = closer.search(source, cursor)
        assert nxt_close is not None, element_id
        if nxt_open is not None and nxt_open.start() < nxt_close.start():
            depth += 1
            cursor = nxt_open.end()
            continue
        depth -= 1
        cursor = nxt_close.end()
        if depth == 0:
            return source[start:cursor]
    raise AssertionError(element_id)


_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_JS_LINE_COMMENT = re.compile(r"//[^\n]*")


def strip_js_comments(script: str) -> str:
    """Comments are not behaviour.

    Needed because this file's own comments quote the fabricating mutation they
    warn about, and a check for a truthy ``ok`` literal must not fire on the
    warning.
    """
    return _JS_LINE_COMMENT.sub("", _JS_BLOCK_COMMENT.sub("", script))


def companion_script(source: str) -> str:
    """The page's one ``<script>`` body."""
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", source, re.DOTALL | re.IGNORECASE)
    assert len(blocks) == 1, len(blocks)
    return blocks[0]


def function_body(script: str, name: str) -> str:
    """The braced body of ``name``, by brace matching. Used to count returns."""
    signature = re.search(rf"function\s+{re.escape(name)}\s*\(", script)
    assert signature is not None, name
    opening = script.index("{", signature.end())
    depth = 0
    for index in range(opening, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[opening + 1 : index]
    raise AssertionError(name)


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


@pytest.mark.parametrize(
    "value",
    [
        "https://claude.ai:abc/public/artifacts/x",
        "https://claude.ai:99999/public/artifacts/x",
    ],
)
def test_a_malformed_port_is_refused_rather_than_crashing(value):
    """``urlsplit`` defers port validation to attribute access, and it RAISES.

    ``parts.port`` was read outside the guard, so ``:abc`` and ``:99999`` left this
    function with a bare ``ValueError`` — breaking the contract that a
    present-but-wrong value raises :class:`ArtifactLinkRefusal`, which a caller
    catching that exception would experience as a crash.
    """
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.resolve_artifact_link({artifact_link.ARTIFACT_URL_ENV: value})
    assert "port is not a number" in str(caught.value)


@pytest.mark.parametrize(
    "value, fragment_of_the_value",
    [
        ("https://claude.ai:abc/public/artifacts/x", "abc"),
        ("https://claude.ai:99999/public/artifacts/x", "99999"),
    ],
)
def test_a_malformed_port_refusal_does_not_echo_the_value(value, fragment_of_the_value):
    """The uncaught ``ValueError`` quoted the port back.

    ``Port could not be cast to integer value as 'abc'`` — the one thing every
    refusal in this module is written not to do. The regression is worth its own
    test because it is invisible to the test above, which would pass on a message
    that echoed everything.
    """
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.resolve_artifact_link({artifact_link.ARTIFACT_URL_ENV: value})
    assert fragment_of_the_value not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [
        "https://claude.ai/public/artifacts/x\r\nLocation: https://evil.example",
        "https://cla\tude.ai/public/artifacts/x",
    ],
)
def test_a_value_carrying_a_control_character_is_refused(value):
    """Validated the parsed form, stored the raw form — a URL-validation bypass.

    ``urlsplit`` silently strips ASCII TAB, CR and LF, so both of these values
    validated as host ``claude.ai`` and were then stored **with the control
    characters intact**. A consumer that does not re-parse — an ``href``, a
    ``Location:`` header, a ``fetch`` — could resolve the stored string differently
    from the string that was checked.
    """
    with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
        artifact_link.resolve_artifact_link({artifact_link.ARTIFACT_URL_ENV: value})
    assert "control character" in str(caught.value)


def test_an_accepted_value_is_stored_in_the_form_that_was_validated():
    """The host check lowercased; the store did not. Now both do.

    Stated as the general property rather than as a case: what is stored is
    re-serialised from the parts that passed, so it cannot differ from what was
    checked.
    """
    resolved = artifact_link.resolve_artifact_link(
        {artifact_link.ARTIFACT_URL_ENV: "https://CLAUDE.AI/public/artifacts/x"}
    )
    assert resolved.url == "https://claude.ai/public/artifacts/x"
    assert "CLAUDE.AI" not in resolved.url


def test_query_and_fragment_smuggling_is_still_refused_after_normalisation():
    """A negative control for the change above.

    Re-serialising drops a query and a fragment. If the refusal were ever removed,
    normalisation would silently make a smuggled Experiment ID *disappear* rather
    than be rejected — quieter, and worse.
    """
    for value in (
        "https://claude.ai/public/artifacts/x?experiment=E1",
        "https://claude.ai/public/artifacts/x#E1",
    ):
        with pytest.raises(artifact_link.ArtifactLinkRefusal) as caught:
            artifact_link.resolve_artifact_link(
                {artifact_link.ARTIFACT_URL_ENV: value}
            )
        assert "query string or fragment" in str(caught.value)


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


COMPANION_FILES = (
    HTML_PATH,
    PROMPT_PATH,
    MANIFEST_PATH,
    COMPANION_DIR / "README.md",
    # Added 2026-08-31. The four files above are the ones an artifact is BUILT
    # from; the two below are the ones a URL would most plausibly be pasted into
    # by someone following the very documents that tell them not to. The operator
    # checklist is where step 7 hands the value to an environment variable, which
    # is exactly where a helpful example would appear.
    REPO_ROOT / "docs" / "isaac-assistant-artifact-operator-checklist.md",
    REPO_ROOT / "docs" / "isaac-assistant-artifact-feasibility.md",
    # NOT ``artifact_link.py``, and the omission is reasoned rather than an
    # oversight: its docstring deliberately quotes MALFORMED example values on the
    # permitted host to document two defects, so this pattern would match prose
    # that is the opposite of a committed artifact URL. What that module actually
    # needs guarding is that it holds no DEFAULT, and
    # ``test_the_artifact_link_is_unconfigured_by_default`` asserts exactly that,
    # by resolving against an empty environment rather than by grepping.
)


def test_no_committed_companion_file_carries_an_artifact_url():
    """The URL is operator-supplied. A literal here would be an access-bearing commit.

    ``claude.ai`` is permitted to appear as prose; a ``https://claude.ai/...`` URL
    is not, which is the distinction that matters.
    """
    pattern = re.compile(r"https?://(?:www\.)?claude\.ai/\S+")
    for path in COMPANION_FILES:
        assert not pattern.search(path.read_text()), path


def test_that_url_guard_would_actually_fire():
    """A negative control. The pattern above must not be inert.

    Without this, a typo in the regex would leave every file "clean" forever.
    """
    pattern = re.compile(r"https?://(?:www\.)?claude\.ai/\S+")
    assert pattern.search("see https://claude.ai/public/artifacts/some-id for it")


def test_the_page_source_embeds_no_endpoint_token_or_account_identifier():
    text = HTML_PATH.read_text()
    for forbidden in ("Bearer ", "api_key", "apiKey", "client_secret", "@slac.stanford.edu"):
        assert forbidden not in text, forbidden


NOT_CONNECTED_DISCLOSURE = "Not connected to a model or an MCP server."


def unnegated_connected(text: str) -> list[str]:
    """Every occurrence of the word "connected" that is not preceded by a negation.

    Case-insensitive on purpose: ``docs/ai-integration-decision-packet.md`` §6.1
    forbids the CLAIM, and a claim does not become permissible in lower case.
    """
    found = []
    for match in re.finditer(r"(?i)\bconnected\b", text):
        if not re.search(r"(?i)\b(not|never|isn'?t|no)\s+$", text[: match.start()]):
            found.append(text[max(0, match.start() - 60) : match.end() + 20])
    return found


def test_the_page_makes_no_connected_claim_in_any_casing():
    """docs/ai-integration-decision-packet.md §6.1 — no fake ``Connected`` state.

    **This guard used to be case-sensitive**, and a review added a visible
    ``<p>Status: connected to your ISAAC workspace and ready.</p>`` that the whole
    suite passed. The forbidden claim does not depend on an author capitalising a
    letter, so neither does the check: every occurrence of the word, in any casing,
    must be immediately preceded by a negation.
    """
    assert unnegated_connected(HTML_PATH.read_text()) == []


def test_the_connected_guard_would_actually_fire():
    """A negative control, and it is the review's exact mutation.

    Without it, a typo in the pattern would leave the page "clean" forever — which
    is precisely how the case-sensitive version passed.
    """
    assert unnegated_connected("<p>Status: connected to your ISAAC workspace.</p>")
    assert unnegated_connected("<strong>Connected.</strong>")
    assert unnegated_connected("") == []
    assert unnegated_connected("Not connected to a model or an MCP server.") == []


def test_the_not_connected_disclosure_is_rendered_where_a_reader_meets_it():
    """The positive half, asserted over the RENDERED page rather than over bytes.

    ``"Not connected" in text`` would be satisfied by the phrase sitting in an HTML
    comment, a ``<style>`` block or an attribute — none of which a reader sees. So
    this asserts three things a reader can actually experience: the sentence
    survives comment/script/style removal; it is the FIRST thing inside the live
    region; and that region is not hidden.
    """
    source = HTML_PATH.read_text()
    assert NOT_CONNECTED_DISCLOSURE in rendered_text(source)

    region = element_source(source, "seam-status")
    assert rendered_text(region).startswith(NOT_CONNECTED_DISCLOSURE)
    assert not re.search(r"(?i)\bhidden\b", region.split(">", 1)[0])
    assert not re.search(r"(?i)display\s*:\s*none|visibility\s*:\s*hidden", source)


def test_the_disclosure_is_reached_before_any_capability_copy():
    """Reading order is part of the claim.

    The status card used to sit BELOW the Experiment ID field and the "Check this
    record" button, so the first thing a reader met was a capability and the last
    was the fact that no call surface exists. Capability-first ordering implies a
    connection without ever claiming one.
    """
    source = HTML_PATH.read_text()
    body = source[source.index("<main>") : source.index("</main>")]
    visible = rendered_text(body)
    assert visible.index(NOT_CONNECTED_DISCLOSURE) < visible.index("Check this record")


def test_the_page_states_that_finalising_is_not_its_act():
    """Asserted over normalised rendered text, not over the file's line wrapping.

    The previous version matched ``"No\\n          tool here can do it"`` — ten
    spaces of indentation load-bearing in an assertion about a claim.
    """
    visible = rendered_text(HTML_PATH.read_text())
    assert "Finalising a record" in visible
    assert "No tool here can do it" in visible


# --- the seam is executed, not grepped --------------------------------------
#
# WHY THIS IS NOT A STRING CHECK ANY MORE. A review replaced ``runCompanionTurn``'s
# body with ``{ ok: true, record: { status: "complete", pending: 0, qc: "valid" },
# message: "Record looks complete. 0 blocking questions remain." }`` and the suite
# stayed green: the old guard asserted only that ``companion_seam_unset`` and
# ``Nothing was sent`` appeared SOMEWHERE in the file, and the surviving constant
# and the empty-ID branch kept both alive. That is the central honesty claim of the
# whole companion pinned by string presence — the "test asserting more than it
# established" shape ``CLAUDE.md`` §11 records repeatedly.

_HARNESS_PRELUDE = """
'use strict';
const __handlers = {};
const __elements = {};
function __el(id) {
  if (!__elements[id]) {
    __elements[id] = {
      id: id,
      value: "",
      innerHTML: "",
      addEventListener: function (type, fn) {
        if (!__handlers[id]) { __handlers[id] = {}; }
        __handlers[id][type] = fn;
      },
    };
  }
  return __elements[id];
}
globalThis.document = { getElementById: __el };
"""

_HARNESS_EPILOGUE = """
(async () => {
  const direct = await globalThis.runCompanionTurn({ experimentId: "E-SYNTHETIC-0001" });

  __el("experiment-id").value = "";
  __el("seam-status").innerHTML = "";
  await __handlers["start"]["click"]();
  const renderedWithoutId = __el("seam-status").innerHTML;

  __el("experiment-id").value = "E-SYNTHETIC-0001";
  __el("seam-status").innerHTML = "";
  await __handlers["start"]["click"]();
  const renderedTurn = __el("seam-status").innerHTML;

  console.log(JSON.stringify({
    direct: direct,
    directKeys: Object.keys(direct),
    renderedWithoutId: renderedWithoutId,
    renderedTurn: renderedTurn,
  }));
})();
"""


def _run_the_seam(tmp_path, source: str) -> dict:
    """Evaluate the page's script in Node with a minimal DOM and take one turn."""
    node = shutil.which("node")
    if node is None:  # pragma: no cover - Node is present locally and on CI runners
        pytest.skip(
            "node is not on PATH, so the seam could not be EXECUTED. The structural "
            "backstop test_the_seam_has_exactly_one_return_and_it_is_the_frozen_"
            "unset_result still runs unconditionally and still fails a fabricating "
            "seam; only the strongest assertion is lost, not the guarantee."
        )
    harness = tmp_path / "companion_seam_harness.js"
    harness.write_text(
        _HARNESS_PRELUDE + companion_script(source) + _HARNESS_EPILOGUE
    )
    completed = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, timeout=60, check=False
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_a_turn_returns_the_fail_closed_result(tmp_path):
    """Executed, not asserted about. This is the seam's actual return value."""
    outcome = _run_the_seam(tmp_path, HTML_PATH.read_text())["direct"]
    assert outcome["ok"] is False
    assert outcome["reason"] == "companion_seam_unset"
    assert "Nothing was sent" in outcome["message"]


def test_a_turn_cannot_return_a_fabricated_record(tmp_path):
    """The mutation that passed 25 tests. It fails here on three independent counts.

    ``ok`` is not true, the result carries no record-shaped key, and the result's
    key set is exactly the three the seam declares — so a fabricated ``record``,
    ``status``, ``pending`` or ``qc`` cannot ride along beside an honest ``ok``.
    """
    executed = _run_the_seam(tmp_path, HTML_PATH.read_text())
    outcome, keys = executed["direct"], executed["directKeys"]
    assert outcome["ok"] is not True
    assert sorted(keys) == ["message", "ok", "reason"]
    for fabricated in ("record", "status", "pending", "qc", "experiment", "questions"):
        assert fabricated not in outcome


def test_what_a_turn_renders_says_nothing_was_sent(tmp_path):
    """A refusal a reader never sees is not a refusal.

    Both branches are driven: a click with no Experiment ID, and a click with one.
    """
    executed = _run_the_seam(tmp_path, HTML_PATH.read_text())
    assert "Nothing was sent" in executed["renderedWithoutId"]

    rendered_turn = executed["renderedTurn"]
    assert "Could not check this record" in rendered_turn
    assert "Nothing was sent" in rendered_turn
    assert unnegated_connected(rendered_turn) == []


def test_the_seam_has_exactly_one_return_and_it_is_the_frozen_unset_result():
    """The unconditional backstop, so a Node-less environment loses no guarantee.

    Structural rather than behavioural, and deliberately narrow: one ``return``,
    returning the one frozen constant, in a script that contains no truthy ``ok``
    literal anywhere. The fabricating mutation fails all three.
    """
    script = strip_js_comments(companion_script(HTML_PATH.read_text()))
    body = function_body(script, "runCompanionTurn")
    returns = re.findall(r"\breturn\b[^;]*;", body)
    assert returns == ["return SEAM_UNSET_RESULT;"], returns

    declaration = re.search(
        r"const\s+SEAM_UNSET_RESULT\s*=\s*Object\.freeze\(\{(.*?)\}\);",
        script,
        re.DOTALL,
    )
    assert declaration is not None
    assert "ok: false" in declaration.group(1)
    assert not re.search(r"(?i)\bok\b\s*:\s*true", script)


def test_the_prompt_carries_the_refusal_paths_it_must(manifest):
    """The behaviour contract is reviewable source, so its load-bearing clauses are pinned."""
    text = PROMPT_PATH.read_text()
    assert "You cannot submit a record" in text
    assert "412 stale_write" in text
    assert "each user connects independently" in text.lower() or (
        "connect independently" in text.lower()
    )
    assert "never guessed" in text.lower()
