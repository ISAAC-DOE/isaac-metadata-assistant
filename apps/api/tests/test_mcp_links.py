"""`mcp/links.py` — the relative deep links an agent hands a scientist. **MCP-006.**

THREE CLASSES OF CLAIM ARE PINNED HERE, and they fail for different reasons:

1. **Shape.** The link an agent receives is the link the WEBSITE would mint. Checked
   against the frontend's own literals, read off `apps/web/src/lib/routes.ts` — not
   against a copy in this file, because a transcribed literal is exactly what would
   drift.
2. **Relativeness.** No scheme, no host, no port, no base path. This is the property
   that makes a link usable in both deployments, and the one whose violation looks
   harmless (`http://localhost:8000/...` is a perfectly good string).
3. **Refusal.** An entity-specific builder handed no id returns `None` rather than a
   BROADER link under a NARROWER name. That defect was written during this slice and
   caught before it shipped: `run_link(eid, None)` would have produced `/record/<id>`
   — the record — labelled `"run"`, and the label is what an agent repeats aloud.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from isaac_api.mcp import links

#: The frontend module this file holds the Python copy against.
_ROUTES_TS = (
    pathlib.Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "routes.ts"
)

_EID = "01SYNTHEXAMPLEEXAMPLEEXAMP"
_RID = "01SYNTHRUNRUNRUNRUNRUNRUNR"
_PID = "01SYNTHPROPOSALPROPOSALPRO"


def _ts() -> str:
    """The frontend source. Read with `errors="replace"` rather than assumed clean.

    `CLAUDE.md` §11 records a `grep` sweep of `apps/web/src` returning zero hits and
    exiting 0 on a file holding a NUL byte, three sessions in a row. A reader that
    cannot fail silently is the remedy that was settled on.
    """
    assert _ROUTES_TS.exists(), _ROUTES_TS
    return _ROUTES_TS.read_text(encoding="utf-8", errors="replace")


# ==========================================================================
# 1. shape — against the frontend's own literals
# ==========================================================================

def test_the_python_literals_are_the_frontends_own():
    """THE ANTI-DRIFT PROPERTY. Python cannot import TypeScript, so the two copies are
    held against each other rather than trusted.

    A mismatch here means an agent is handing scientists a URL the website does not
    read — which fails silently, because an unrecognised query parameter is ignored
    and the screen simply does not focus anything.
    """
    source = _ts()
    declared = dict(re.findall(r"export const (\w+) = '([^']+)'", source))
    mine = links.link_literals()

    for name in ("RECORD_VIEW_PARAM", "RECORD_RUN_PARAM", "RECORD_PROPOSAL_PARAM"):
        assert name in declared, f"{name} is gone from routes.ts"
        assert declared[name] == mine[name], (name, declared[name], mine[name])

    # AND `capture` IS A REAL WORKSPACE ID, not a value this module invented.
    ids = re.search(r"RECORD_VIEW_IDS = \[([^\]]+)\]", source)
    assert ids is not None, "RECORD_VIEW_IDS is gone from routes.ts"
    assert f"'{links.CAPTURE_VIEW}'" in ids.group(1), ids.group(1)


def test_the_proposal_link_matches_the_frontends_canonical_mint():
    """THE WHOLE POINT, AS ONE STRING COMPARISON.

    `routes.ts` exposes `ROUTES.recordProposal(id, proposalId)`. Its template is
    parsed out and rebuilt here, so this fails if EITHER side changes the ordering,
    the separator or the parameter names — not merely if a name changes.
    """
    source = _ts()
    mint = re.search(
        r"recordProposal:\s*\([^)]*\)\s*=>\s*\n?\s*`([^`]+)`", source
    )
    assert mint is not None, "ROUTES.recordProposal is gone from routes.ts"
    template = mint.group(1)
    expected = (
        template.replace("${id}", _EID)
        .replace("${RECORD_VIEW_PARAM}", links.VIEW_PARAM)
        .replace("${RECORD_PROPOSAL_PARAM}", links.PROPOSAL_PARAM)
        .replace("${encodeURIComponent(proposalId)}", _PID)
    )
    assert "${" not in expected, f"unsubstituted placeholder: {expected}"
    assert links.proposal_link(_EID, _PID) == expected, (
        links.proposal_link(_EID, _PID),
        expected,
    )


def test_each_builder_addresses_what_its_name_says():
    assert links.experiment_link(_EID) == f"/record/{_EID}"
    assert links.capture_link(_EID) == f"/record/{_EID}?view=capture"
    assert links.run_link(_EID, _RID) == f"/record/{_EID}?run={_RID}"
    assert (
        links.proposal_link(_EID, _PID)
        == f"/record/{_EID}?view=capture&proposal={_PID}"
    )


def test_the_ambiguity_link_is_the_proposal_link_and_that_is_deliberate():
    """MEASURED BEFORE IT WAS WRITTEN: this build has no separate ambiguity entity and
    no route that serves one. An ambiguity is a proposal whose value the reader must
    disambiguate, reviewed on the same screen under the same id.

    So the alias is asserted as an alias. Minting a second parameter would publish a
    navigational distinction the application does not make — a link that looked like
    it opened a different surface and opened the same one.
    """
    assert links.ambiguity_link(_EID, _PID) == links.proposal_link(_EID, _PID)
    assert links.AMBIGUITY_PARAM == links.PROPOSAL_PARAM


# ==========================================================================
# 2. relativeness
# ==========================================================================

@pytest.mark.parametrize(
    "href",
    [
        links.experiment_link(_EID),
        links.capture_link(_EID),
        links.run_link(_EID, _RID),
        links.proposal_link(_EID, _PID),
        links.ambiguity_link(_EID, _PID),
    ],
)
def test_no_link_carries_an_origin_or_a_base_path(href):
    """The router `basename` is `''` locally and `/krish` deployed, and it is the ONE
    place that prefix is known. A link carrying either would be wrong in the other
    deployment — and wrong in the way that looks right, because it is clickable."""
    assert href.startswith("/"), href
    assert not href.startswith("//"), href  # a protocol-relative URL is an origin
    for forbidden in ("http:", "https:", "localhost", "127.0.0.1", "/krish", "://"):
        assert forbidden not in href, (forbidden, href)


def test_an_id_is_percent_encoded_so_it_cannot_forge_a_second_parameter():
    """An id containing `&` or `=` would otherwise inject a parameter into the link.

    Not a hypothetical injection worry about ULIDs — it is the property that makes the
    builder safe to hand any id a route returned, which is what the module's docstring
    promises when it says nothing is validated.
    """
    href = links.proposal_link("E 1/a", "P&view=runs")
    assert "P%26view%3Druns" in href, href
    # The `view` the builder itself set is the ONLY `view=` in the link.
    assert href.count("view=") == 1, href
    assert href.count("?") == 1 and href.count("&") == 1, href


# ==========================================================================
# 3. refusal — the defect caught during this slice
# ==========================================================================

@pytest.mark.parametrize("missing", [None, "", "   "])
def test_an_entity_builder_returns_None_rather_than_a_broader_link(missing):
    """THE DEFECT THIS SLICE WROTE AND CAUGHT.

    `_record_path` omits a parameter whose value is blank — correct for
    `experiment_link`, and WRONG for the entity builders, where it silently widens the
    link while keeping the narrow name. `run_link(eid, None)` would have returned
    `/record/<id>`: the record, labelled "run". The label is what an agent repeats to
    a scientist, so a link that widens its own scope is worse than no link.
    """
    assert links.run_link(_EID, missing) is None
    assert links.proposal_link(_EID, missing) is None
    assert links.ambiguity_link(_EID, missing) is None


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_no_builder_produces_a_link_without_a_record(missing):
    """Every link here is a link to a record. With no record there is nothing to
    address, and a `/record/` with an empty segment is a dead route."""
    assert links.experiment_link(missing) is None
    assert links.capture_link(missing) is None
    assert links.run_link(missing, _RID) is None
    assert links.proposal_link(missing, _PID) is None


def test_a_wrong_typed_id_is_refused_rather_than_stringified():
    """Nothing is coerced. `str(7)` would build `/record/7` — a link to a record that
    does not exist, which is indistinguishable from a link to one that does."""
    for bad in (7, 7.5, True, [], {}, object()):
        assert links.experiment_link(bad) is None, bad
        assert links.proposal_link(_EID, bad) is None, bad
