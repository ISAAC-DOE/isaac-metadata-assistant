"""Read-only JSON serializers for core dataclasses and draft structures.

The core (``draft_validator``, ``official``, ``portal_warnings``, ``export``, ``audit``)
exposes ``.render()`` and typed fields but no ``.to_dict()`` — by design (see
docs/ui-handoff/technical-architecture.md §11). This module owns ALL serialization so
no method is added to a core dataclass. It never re-implements a verdict: it only reshapes
what the core returned.

Serialization rules honored here (technical-architecture.md §3 / §9):
  - ``DraftReport.errors`` is ``[(where, msg)]``  -> ``{where, message}``.
  - ``OfficialReport.errors`` is ``[OfficialError(path, message)]`` -> ``{path, message}``.
  - ``PortalWarningReport`` exposes only ``.warnings`` + ``.advisory`` — the warning payload
    carries ``advisory:true, gating:false`` and NO ok/valid/passed field.
"""

from __future__ import annotations

from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES, DraftReport
from isaac_records.export import ExportResult, get_path
from isaac_records.official import OfficialReport
from isaac_records.portal_warnings import PortalWarningReport

from . import inferability

# --- report serializers -------------------------------------------------------


def draft_report_to_dict(report: DraftReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"where": w, "message": m} for w, m in report.errors],
        "warnings": [{"where": w, "message": m} for w, m in report.warnings],
    }


def official_report_to_dict(report: OfficialReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"path": e.path, "message": e.message} for e in report.errors],
    }


def warnings_to_dict(report: PortalWarningReport) -> dict:
    """Advisory, non-gating channel. Deliberately NO ok/valid/passed field."""
    return {
        "advisory": True,
        "gating": False,
        "warnings": [
            {"code": w.code, "where": w.where, "message": w.message}
            for w in report.warnings
        ],
    }


def export_result_to_dict(result: ExportResult, *, record: dict | None = None) -> dict:
    """Serialize an ExportResult (reports always; record/sidecar when produced).

    ``record`` OVERRIDES ``result.record`` in the output, and exists for exactly one
    caller: the export path, which writes a document the truth core did not produce.
    ``routes._write_record`` applies the server-owned ``attribution.uploaded_by`` stamp
    to a copy before writing (see :mod:`isaac_api.record_attribution`), so without this
    the operation that performs the write would report a document differing from the
    bytes it just produced, while a later read of ``/artifacts`` reported the truth.
    An independent review measured that divergence.

    It is an override rather than the default because ``result.record`` is right for
    every other caller — a dry run, a per-unit verdict, a validation report — none of
    which writes anything and none of which should imply a stamp that was not applied.
    """
    out: dict = {
        "ok": result.ok,
        "draft_report": draft_report_to_dict(result.draft_report),
        "official_report": (
            official_report_to_dict(result.official_report)
            if result.official_report is not None
            else None
        ),
    }
    if record is not None:
        out["record"] = record
    elif result.record is not None:
        out["record"] = result.record
    if result.sidecar is not None:
        out["sidecar"] = result.sidecar
    return out


def audit_to_dict(results, text: str) -> dict:
    """``audit_records`` returns [(name, OfficialReport, (covered, expected, uncovered, dangling))].

    Coverage is completeness reporting, never a verdict: ``evidence_present`` /
    ``evidence_expected`` are the honest record-derived denominator, and the
    ``uncovered`` / ``dangling`` key lists are passed through faithfully.
    """
    records = []
    for name, report, (covered, expected, uncovered, dangling) in results:
        records.append(
            {
                "name": name,
                "ok": report.ok,
                "schema_errors": [
                    {"path": e.path, "message": e.message} for e in report.errors
                ],
                "evidence_present": covered,
                "evidence_expected": expected,
                "uncovered": list(uncovered),
                "dangling": list(dangling),
            }
        )
    return {"records": records, "text": text}


# --- draft field grouping -----------------------------------------------------

# Draft ``fields`` keys are official dotted JSON-paths (verified against
# docs/samples/…evidence.json). We group by the top-level path segment into stable,
# human-titled sections. Order is fixed; any unmapped prefix lands in "Other".
_GROUP_TITLES: dict[str, str] = {
    "system": "System & Instrument",
    "timestamps": "Timestamps",
    "sample": "Sample",
    "context": "Environment & Context",
    "measurement": "Measurement",
    "assets": "Assets & Files",
    "descriptors": "Descriptors",
    "attribution": "Attribution",
}
_GROUP_ORDER = list(_GROUP_TITLES.keys())
_OTHER = "Other"


def _label(path: str) -> str:
    """Humanize the last path segment (e.g. ``sample.material.formula`` -> ``Formula``)."""
    last = path.split(".")[-1]
    return last.replace("_", " ").strip().title()


def _source_types(evidence) -> list[str]:
    seen: list[str] = []
    for e in evidence or []:
        st = e.get("source_type") if isinstance(e, dict) else None
        if st and st not in seen:
            seen.append(st)
    return seen


def _draft_field(path: str, env: dict) -> dict:
    evidence = env.get("evidence") or []
    return {
        "path": path,
        "label": _label(path),
        "value": env.get("value"),
        "status": env.get("status"),
        "evidence_count": len(evidence),
        "source_types": _source_types(evidence),
    }


def draft_to_groups(draft: dict) -> dict:
    """Group draft scalar fields into stable UI sections for the Review Record screen."""
    fields = draft.get("fields") or {}
    buckets: dict[str, list[dict]] = {}
    for path, env in fields.items():
        if not isinstance(env, dict):
            continue
        top = path.split(".")[0]
        title = _GROUP_TITLES.get(top, _OTHER)
        buckets.setdefault(title, []).append(_draft_field(path, env))

    ordered_titles = [
        _GROUP_TITLES[k] for k in _GROUP_ORDER if _GROUP_TITLES[k] in buckets
    ]
    if _OTHER in buckets:
        ordered_titles.append(_OTHER)

    groups = [{"title": t, "fields": buckets[t]} for t in ordered_titles]
    return {"groups": groups}


# --- pending blockers ---------------------------------------------------------

_DEMO_LABEL = "Example answer"

#: Provenance carried BY the example answer itself, so a reader (and a test) can
#: check what it is without inferring it from a label. Every claim here is
#: machine-checkable and every one of them is a limitation.
EXAMPLE_ANSWER_PROVENANCE: dict = {
    "source": "tutorial_example_fixture",
    "is_evidence_for_this_record": False,
    "auto_applied": False,
    "requires_user_confirmation": True,
}


def _demo_answer_for(entry: dict, demo_answers: dict, *, example_scope: bool):
    """The labeled example answer for a blocker, or None. Never auto-applied.

    SCOPE IS ENFORCED HERE, and it did not used to be. The endpoint documentation
    has always promised this value "for the built-in examples only", but only the
    ``asset`` branch was incidentally scoped (it keys on the blocker's own URI
    against the fixture's URI map, so a foreign URI missed). The ``series`` and
    ``descriptor`` branches read the fixture unconditionally and returned it for
    ANY record — a fabricated 7-point spectrum and a fabricated descriptor value
    with an uncertainty, offered as the answer to a scientific question about a
    record they have nothing to do with. That is precisely what CLAUDE.md §5
    forbids ("Never invent or guess: scientific values, units, ... descriptor
    values, uncertainty values"), and the promise in the docstring made it worse
    by asserting a boundary the code did not have.

    ``example_scope`` is now required and defaults, at every caller, to False —
    fail-closed, so a caller that forgets it withholds the example rather than
    leaking it. The example content remains available on the five canonical
    walkthrough records, which is what it was authored for.
    """
    if not example_scope:
        return None
    kind = entry.get("kind")
    if kind == "asset":
        value = (demo_answers.get("asset_sha256") or {}).get(entry.get("uri"))
    elif kind == "series":
        value = demo_answers.get("series")
    elif kind == "descriptor":
        value = demo_answers.get("descriptor")
    else:
        value = None
    if value is None:
        return None
    return {"value": value, "label": _DEMO_LABEL, "provenance": dict(EXAMPLE_ANSWER_PROVENANCE)}


def blocker_id(entry: dict) -> str:
    """Stable id used as the answer key. Asset blockers key on their URI."""
    kind = entry.get("kind")
    if kind == "asset":
        return entry.get("uri") or "asset"
    return kind or "blocker"


def _blocker_about(entry: dict):
    return entry.get("uri") or entry.get("blocker")


def pending_to_list(
    draft: dict,
    demo_answers: dict,
    *,
    example_scope: bool = False,
    entries: list | None = None,
) -> dict:
    """The open blocking questions, each with its explicit inferability decision.

    ``example_scope`` gates the walkthrough example answer (see
    :func:`_demo_answer_for`) and DEFAULTS TO FALSE so the leak-safe behaviour is
    the one you get by forgetting.

    Two channels, deliberately kept apart:

    * ``inferability`` — can ISAAC determine this value from the record's own
      evidence? For every blocker kind the honest answer is no, and the state says
      which flavour of no. It carries no value: ``Inferability.__post_init__``
      refuses one for any state but ``supported_suggestion``, and
      ``blocker_inferability`` cannot return that state at all.
    * ``demo_answer`` — is there illustrative walkthrough content the user may
      click? Example-scope only, provenance-carrying, never auto-applied.

    They cannot contradict each other because the second one's existence is fed
    INTO the first (``example_available``), so the refusal is written knowing the
    example is on screen and says so in the same sentence.

    NOT served here: the rule set's per-field decisions (``inferability.infer_all``).
    An earlier revision added them as an ``inferences`` block on this response, and
    they reached three endpoints with no consumer anywhere in the client — an
    unread payload that shipped concrete values and bypassed the client's own
    re-check, which only ever ran over ``item.inferability``. ``infer_all``
    remains available to a caller that has a use for it; serving it by default was
    speculative surface, so it is gone rather than guarded.

    ENTRIES OVERRIDE ``draft["pending"]``, and exist because this function was
    RUN-BLIND. ``Experiment.pending()`` aggregates the record's own questions and every
    run's, and withholds the record's own run-level ones once a run exists — while this
    read ``draft["pending"]`` directly. So ``GET /pending`` and the ``pending_count`` on
    the detail response disagreed the moment a record had a run: the screen a scientist
    answers questions on showed the record's questions, which by then were the ones that
    could no longer be answered into anything that ships, and hid the run's, which were
    the real ones.

    The default is unchanged, so every caller that legitimately holds one draft — a dry
    run, the assistant's context — behaves exactly as before.
    """
    pending = []
    for entry in (draft.get("pending") if entries is None else entries) or []:
        demo = _demo_answer_for(entry, demo_answers, example_scope=example_scope)
        pending.append(
            {
                "id": blocker_id(entry),
                "kind": entry.get("kind"),
                "question": entry.get("question"),
                "about": _blocker_about(entry),
                "demo_answer": demo,
                "inferability": inferability.blocker_inferability(
                    entry, example_available=demo is not None
                ).to_dict(),
                # Carried through when present. `Experiment.pending()` tags a
                # run-sourced entry so a caller can address the question to the run
                # that owns it; dropping the tag here would leave a client unable to
                # tell whose question it is answering.
                "run_id": entry.get("run_id"),
                "run_label": entry.get("run_label"),
                # A KEY THAT IS UNIQUE ACROSS OWNERS, because `id` is NOT.
                #
                # `id` is the blocker KIND (or an asset URI) and it is the key a caller
                # puts in the `answers` BODY, so it cannot be made unique without
                # breaking the write contract. But three runs each needing a spectrum
                # produce three entries whose `id`, `question` and `about` are
                # byte-identical, and an independent review measured what a client does
                # with that: the completion screen keys staged input, the skip set, its
                # React keys and its "was this applied?" test off `id`, so answering one
                # run's verdict was reported as NOT APPLIED (another run's identical
                # entry was still in the list), one typed value was shared by every run's
                # question, and skipping one skipped all of them.
                #
                # So: `id` stays the ANSWER key, `blocker_key` is the IDENTITY key. A
                # record-level question's two values are equal, which keeps a zero-run
                # record's payload semantically unchanged.
                "blocker_key": (
                    f"{entry.get('run_id')}:{blocker_id(entry)}"
                    if entry.get("run_id")
                    else blocker_id(entry)
                ),
            }
        )
    return {"pending": pending}


# --- bounding the pending list ------------------------------------------------
#
# THE MEASURED DEFECT. `pending_to_list` serialises EVERY open blocking question of
# the whole record, and a record's question count is `3 x runs`. Measured over HTTP
# on `c153ec9`, in-process, against a record created through `POST /api/experiments`
# with N runs each carrying the three seeded run-level questions:
#
#      runs   GET /pending B   entries   POST /runs/{id}/answers B   entries
#        25           44,236        75                     44,840        74
#       100          176,989       300                    177,592       299
#       250          442,939       750                    443,542       749
#       500          886,189     1,500                    886,792     1,499
#      1000        1,772,692     3,000                  1,773,294     2,999
#
# ~~627 bytes per entry, flat, and 71% of them are `inferability` + `question`~~ —
# BOTH NUMBERS WERE OVERSTATED AND ARE CORRECTED IN PLACE. An independent review
# re-derived them from THIS TABLE and could not reach either: the marginal cost is
# **591.0 bytes per entry** — `(1,772,692 - 176,989) / 2,700`, and every other
# adjacent pair of rows above gives the same 591.0 (the 25 -> 100 pair gives 590.0,
# because the run labels are still one digit shorter there). `inferability` +
# `question` are **63.5%** of the served bytes by value, **68.1%** counting their keys
# and separators. Still three fixed question templates repeated once per run — which
# is the fact those percentages were carrying, and it is unaffected; only their sizes
# were wrong.
#
# RE-DERIVE IT RATHER THAN TRUST IT, and note the harness with the number, because
# the bytes move with the harness. The runs above were created with NO explicit
# label, so each carries the server's own `Run N`; passing a label of a different
# length moves every figure in the table (`{"label": f"run {i:04d}"}` gives 44,413 /
# 177,613 instead of 44,236 / 176,989).
#
#     PYTHONPATH=apps/api .venv/bin/python - <<'PY'
#     import json, os, tempfile
#     os.environ["ISAAC_UI_WORKSPACE"] = tempfile.mkdtemp()
#     from fastapi.testclient import TestClient
#     from isaac_api.app import create_app
#     c = TestClient(create_app())
#     eid = c.post("/api/experiments", json={"title": "scale envelope"}).json()["id"]
#     for _ in range(1000):
#         et = c.get(f"/api/experiments/{eid}").headers["ETag"]
#         c.post(f"/api/experiments/{eid}/runs", json={}, headers={"If-Match": et})
#     body = c.get(f"/api/experiments/{eid}/pending").content
#     items = json.loads(body)["pending"]
#     blob = lambda o: len(json.dumps(o, separators=(",", ":")))
#     val = sum(blob(e["question"]) + blob(e["inferability"]) for e in items)
#     keyed = val + len(items) * len('"question":,"inferability":')
#     print(len(body), len(items), 100 * val / len(body), 100 * keyed / len(body))
#     PY
#
#     -> 1772692 3000 63.5 68.1
#
# THE WORSE HALF IS THE SECOND COLUMN, and it is the half the original scale work
# missed. `POST /answers`, `POST /edit`, `POST /runs/{run_id}/answers` and
# `POST /runs/{run_id}/edit` all return that same whole-record list, so a scientist
# answering ONE question on ONE run downloaded ~1.77 MB per submission on the WRITE
# path, repeatedly, for a response whose only per-field statement they read is
# whether the one question they just answered is still open.
#
# WHAT IS AND IS NOT BOUNDED HERE, because the two are different decisions:
#
#   * `GET /pending` WITHOUT PARAMETERS IS UNCHANGED — same keys, same bytes. A
#     client asking "what is unresolved on this record?" gets the truth, and a
#     consumer that does not know to page is never handed a page it might read as
#     the whole set. Bounding is opt-in there (`run_id`, `offset`, `limit`).
#   * THE MUTATION RESPONSES ARE BOUNDED BY POLICY, and that is a contract change.
#     They always carry `pending_page`, so the response states whether `pending` is
#     the whole set even when it is.
#
# NOTHING IS EVER SILENTLY TRUNCATED. Both shapes carry `pending_page`, which states
# the total, how many were returned, and how many were WITHHELD — so a page cannot be
# mistaken for the set. `pending_count`, `status` and `export_ready` continue to be
# derived from `Experiment.pending()` in full and are untouched by any of this; the
# bounding happens strictly at serialization, after every verdict is computed.
#
# WHAT WAS CONSIDERED AND REJECTED: DEDUPLICATING THE REPEATED CATALOG.
#
# ~~71%~~ **63.5%** of the payload is `question` + `inferability` (68.1% with their
# keys — see the correction above the table), byte-identical per blocker KIND, so a
# keyed `{kind: {question, inferability}}` map beside a stripped list is a real and
# large saving. MEASURED rather than argued, by building that exact shape from a
# served response — `GET /pending?limit=50` on a 1,000-run record:
#
#     bounded as served   29,590 B
#     bounded deduplicated 10,794 B      (64% smaller)
#
# IT IS STILL NOT DONE, and the reasons are properties of THIS change rather than
# objections to the idea. First, what it saves is now a CONSTANT FACTOR on a payload
# that is already O(1) in the run count: 64% of 29 KB, against the 1.77 MB the bound
# itself removed. Second, it is a response-shape change for EVERY consumer of the
# list — including the unbounded default, whose byte-identical shape is the thing this
# slice most deliberately preserved — and a client-side join can MISS, which renders
# an entry with no question text: a surface answering less than it claims, the exact
# failure class this module's `unavailable` handling exists to prevent.
#
# So it is a legitimate future optimisation, it is worth roughly 19 KB per bounded
# request, and it is deliberately NOT smuggled in here.

#: How many open questions a MUTATION response carries back before it starts
#: withholding. Not a tuning knob and deliberately not caller-settable: `GET /pending`
#: is where a client asks for the shape it wants, and a second way to ask is a second
#: thing to keep honest.
#:
#: 50 is chosen so that NO EXISTING RECORD'S RESPONSE CHANGES. The five canonical
#: walkthrough records carry at most five open questions and a record created through
#: `POST /api/experiments` carries three per run, so a response is only ever truncated
#: past ~17 runs — a state that today costs 30 KB and climbs linearly. It is also far
#: above ~~the 3-or-4 questions~~ **the five questions** a single unit can owe TODAY,
#: which is what makes the anchoring guarantee below cost nothing in practice.
#:
#: **"AT MOST FIVE" IS A MEASUREMENT OF TODAY'S RECORDS, NOT A BOUND THE CODE
#: ENFORCES**, and the two used to be written as if they were the same thing — this
#: comment said "at most five" three lines above one that said "three or four", which
#: is how an independent review noticed that neither was load-bearing. The measured
#: worst case is the canonical seed `01SYNTHXANESSEED0000000001`, whose record-level
#: unit owes **5**: three `asset` sha256 questions, one `series`, one `descriptor`.
#:
#:     # runs the worked-example session and counts per unit
#:     .venv/bin/pytest apps/api/tests/test_pending_reads_are_boundable.py \
#:       -q -k anchored_set_is_not_capped
#:
#: `pending_mutation_window` does NOT cap the anchored set, so a unit owing more than
#: `PENDING_WINDOW` questions returns more than `PENDING_WINDOW` entries. That is
#: deliberate and is argued where it is implemented; see that function's docstring for
#: what the response IS flat in, and what it is not.
PENDING_WINDOW = 50


def _matches_run(entry, run_id) -> bool:
    """Does this entry belong to ``run_id`` (``None`` meaning the record itself)?

    A NON-DICT ENTRY MATCHES NOTHING. ``Experiment.pending()`` deliberately passes a
    malformed persisted entry through as-is ("this is a derived view, not a place to
    start repairing documents") and ``pending_count`` counts it — but it carries no
    owner, so it can neither satisfy a ``run_id`` filter nor anchor a window.

    ~~so it must keep being counted in the totals below~~ **— TRUE OF
    ``record_total`` AND OF AN UNFILTERED ``total``; NOT TRUE OF A FILTERED ONE**, and
    an independent review measured the difference rather than reasoning about it. On a
    run that owns three well-formed questions plus one junk entry,
    ``?run_id=<that run>`` reports ``total: 3`` while :func:`workspace.run_questions`
    returns 4. The behaviour is the defensible one — a filter cannot claim an entry
    that names no owner — but the sentence claimed more than the code does, so it is
    corrected here rather than left to be read as a guarantee.

    KNOWN AND DELIBERATELY NOT FIXED HERE: the UNBOUNDED read raises on such a record,
    because :func:`pending_to_list` reads each entry's keys without a shape check. That
    is unchanged from ``main`` — it is pre-existing rather than a regression of the
    bound — and repairing it is a separate slice with its own blast radius.
    """
    return isinstance(entry, dict) and entry.get("run_id") == run_id


def _page_block(*, total: int, returned: int, offset: int, limit: int | None,
                run_id: str | None, record_total: int) -> dict:
    """The self-description that makes a bounded list safe to read.

    ``withheld`` and ``complete`` are both derivable from the other three, and they are
    served anyway because they are the two statements the bound has to make out loud:
    how many questions REMAIN AFTER this page, and whether it is showing all of them.

    ~~how many questions this response is NOT showing~~ **— THE CODE HAS NEVER SAID
    THAT AND THE SENTENCE IS CORRECTED IN PLACE.** ``withheld`` is
    ``max(total - offset - returned, 0)``, which counts what is still ahead, not what
    was SKIPPED to reach this page. Measured: ``?run_id=X&offset=2&limit=5`` on a
    3-question run reports ``withheld: 0`` while two of that run's questions are not in
    the response. That is the right number for "is there more to fetch?", which is what
    a pager asks; it is the wrong number for "how much am I not showing?", which is
    what this sentence promised. ``types.ts``'s ``ApiPendingPage`` states the formula
    correctly and did not need changing. **THE FIX IS TO THE SENTENCE, NOT TO THE
    CODE** — an offset is something a caller chose, and a client that skipped two
    questions knows it skipped them.

    A client that reads only ``complete`` cannot mistake a page for the SET IT ASKED
    FOR, and a client that reads only ``withheld`` cannot report "nothing left" over
    work still ahead of it. **``complete`` IS RELATIVE TO THE FILTER**, and the
    unqualified version of that sentence overstated it: under a ``run_id`` filter,
    ``complete: true`` means "this run has nothing further", never "this record has
    nothing further". ``record_total`` is the mitigation and is served on every page
    precisely so the two can be told apart. Everything else a pager needs is arithmetic
    on ``offset + returned``, and is not served — see this module's note on the
    ``inferences`` block for why a key with no reader is removed rather than guarded.

    ``record_total`` is separate from ``total`` and is NOT redundant: under a ``run_id``
    filter ``total`` is that run's count, and a screen that rendered it as "N still to
    confirm" would understate the record. Unfiltered they are equal by construction.
    """
    withheld = max(total - offset - returned, 0)
    return {
        "total": total,
        "returned": returned,
        "offset": offset,
        "limit": limit,
        "withheld": withheld,
        "complete": withheld == 0 and offset == 0,
        "run_id": run_id,
        "record_total": record_total,
    }


def pending_slice(entries: list, *, run_id: str | None = None, offset: int = 0,
                  limit: int | None = None) -> tuple[list, dict]:
    """A contiguous, optionally run-filtered page of ``entries``, plus its page block.

    THE READ path's bounding, and it is a plain slice on purpose: a client that asks
    for ``offset``/``limit`` is paging, and paging over anything but a stable order in
    stable positions cannot reach every element. ``Experiment.pending()``'s order is
    the record's own questions followed by each run's in ``sorted_runs()`` order, which
    is a function of the stored document rather than of the request.
    """
    matching = entries if run_id is None else [e for e in entries if _matches_run(e, run_id)]
    window = matching[offset:] if limit is None else matching[offset : offset + limit]
    return window, _page_block(
        total=len(matching),
        returned=len(window),
        offset=offset,
        limit=limit,
        run_id=run_id,
        record_total=len(entries),
    )


def pending_mutation_window(entries: list, *, unit_run_id: str | None,
                            limit: int = PENDING_WINDOW) -> tuple[list, dict]:
    """The head of ``entries``, ANCHORED so it always contains the written unit's own
    open questions, plus its page block.

    THE ANCHOR IS THE WHOLE REASON THIS IS NOT `pending_slice(entries, limit=...)`,
    and dropping it would reintroduce a defect this repository has already had to fix
    once. `GuidedCompletion.answerWasApplied` reads the recomputed list to decide
    whether the question it just answered is still open::

        const stillOpen = resp.pending.some((p) => (p.blocker_key ?? p.id) === blockerKey);
        return resp.invalidation.changed === true && !stillOpen;

    A plain head-of-list window on a 1000-run record would not contain run 900's
    questions at all, so an answer the core REFUSED (a wrong-typed series, an off-enum
    qc — `apply_answers` leaves those unapplied and puts the blocker straight back)
    would read as absent-from-the-list, i.e. as APPLIED. The screen would put a
    "Confirmed by You" chip over a value the record does not hold. That is strictly
    worse than the payload it would have saved.

    So the guarantee this function makes, and that a test pins: **every still-open
    question of the unit that was just written is in the returned window**, whatever
    the record's size.

    **WHAT THE RESPONSE IS FLAT IN, STATED PRECISELY, BECAUSE THIS PARAGRAPH USED TO
    STATE IT LOOSELY.** ~~A unit owes at most three or four questions and ``limit`` is
    50, so on every record that exists today the anchor selects nothing the head did
    not already contain — it is a guarantee, not a cost.~~ The premise was false and
    was contradicted three lines of this file away, where ``PENDING_WINDOW``'s own
    comment said "at most five": the canonical seed ``01SYNTHXANESSEED0000000001``
    owes **5** on its record-level unit (three ``asset``, one ``series``, one
    ``descriptor``). The correct statement is two clauses, not one:

    * **FLAT IN THE RUN COUNT.** This is the defect that was measured and closed. A
      1,000-run record returns the same window as a 25-run one, because the head is
      ``PENDING_WINDOW`` and the anchor selects one unit.
    * **LINEAR IN ONE UNIT'S OPEN-QUESTION COUNT, UNCAPPED.** Every entry the written
      unit owns is in the window, however many that is. Constructed measurement, 60
      runs with 80 extra ``asset`` questions injected on run 60, answering ``qc`` on
      run 60: **``returned: 132``** (50 head + that run's 82 still-open), and **87,082
      bytes** with the fixture URIs ``test_the_anchored_set_is_not_capped`` uses —
      past ``PENDING_WINDOW`` and past the 60 KB ceiling this module's tests assert for
      the run-count sweep. The ENTRY COUNT is a property of the construction; the BYTE
      figure moves with the injected URIs' length (an independent review measured
      83,672 with its own), which is why the test pins the count and not the bytes.

    **THE CAP WAS CONSIDERED AND REJECTED, and the reason is the anchor itself.** A cap
    would have to drop some of the written unit's still-open questions, and this
    function does not know WHICH question was answered — it is given ``unit_run_id``
    and nothing finer. So a cap could drop the very entry ``answerWasApplied`` looks
    for, and a dropped entry reads as absent, i.e. as APPLIED: the "Confirmed by You"
    chip over a value the record does not hold, which is the exact defect the anchor
    exists to prevent and is strictly worse than the bytes it would save. A cap that
    was safe would need the answered keys threaded down here — a larger change, and one
    whose benefit is a state no shipped capture path can produce: an ``asset``
    question comes from an ingested file listing, ``POST /api/uploads`` refuses every
    upload, and ``POST /ingestion/csv/preview`` has no route that APPLIES a preview.
    The residue is therefore **latent, not live**, and it is named here rather than
    left for the next reader to measure.

    **NOTHING ABOUT THIS IS SILENT.** ``pending_page`` reports ``returned`` as the
    number actually returned and ``limit`` as the policy applied, so a response
    carrying 132 entries under a ``limit`` of 50 SAYS SO. Truncation is what a page
    block exists to disclose; this is the opposite case — more than the policy, and
    disclosed just as plainly.

    ``unit_run_id`` is ``None`` for a record-level write, which selects the record's
    own entries. Those already sort first, so the anchor is a no-op there too; it is
    expressed as the same rule rather than special-cased so that a future change to
    ``Experiment.pending()``'s order cannot quietly break the guarantee.

    THE WINDOW IS NOT REORDERED. Indices are taken as a set and walked in ascending
    order, so the returned entries are in exactly the order ``entries`` had them —
    a client's "next question" cannot jump because a different unit was written.
    """
    head = set(range(min(limit, len(entries))))
    anchored = {i for i, e in enumerate(entries) if _matches_run(e, unit_run_id)}
    chosen = sorted(head | anchored)
    return [entries[i] for i in chosen], _page_block(
        total=len(entries),
        returned=len(chosen),
        offset=0,
        # The window is anchored rather than sliced, so `returned` can exceed this by
        # the number of anchored entries beyond the head. `limit` reports the policy
        # that was applied; `returned` reports what came back. They are different
        # facts and collapsing them would make one of the two a lie.
        limit=limit,
        run_id=None,
        record_total=len(entries),
    )


# --- evidence trail -----------------------------------------------------------


def _status_from_evidence(evidence) -> str:
    """Derive a display status from evidence types (mirrors draft_validator semantics).

    An observed source (incl. user_confirmation) => verified; derivation-only => inferred.
    """
    types = {e.get("source_type") for e in (evidence or []) if isinstance(e, dict)}
    if types & set(OBSERVED_SOURCE_TYPES):
        return "verified"
    if "derivation" in types:
        return "inferred"
    return "verified"


# --- per-item isolation (one bad entry must not take the trail down) -----------
#
# MEASURED DEFECT this section exists to fix. Both builders below used to read
# each stored evidence payload with no shape check at all, so ONE malformed entry
# destroyed the WHOLE trail — and the trail is the whole Evidence screen:
#
#   * a payload that is not iterable (``{"system.facility.beamline": 7}`` in a
#     sidecar, or ``implicit: [7]`` in a draft) raised out of ``get_evidence``,
#     i.e. an unhandled 500 on a GET. Measured on `77820bf`: with 36 good sidecar
#     entries and one ``7``, ``GET /experiments/{id}/evidence`` raised
#     ``TypeError: 'int' object is not iterable`` and returned NOTHING. In the
#     browser that GET shares a ``Promise.all`` with four siblings, so the whole
#     bundle rejected and the screen rendered "Backend Not Running" — a false
#     statement about the server, caused by one field's stored evidence.
#   * a payload that is iterable but not a list of objects (a dict, a string, a
#     list containing a string) did NOT raise here; it was passed through
#     verbatim and crashed the CLIENT instead. Also measured: the Evidence view
#     rendered as an EMPTY DOM.
#   * a draft field envelope that is not a dict was silently ``continue``d — the
#     field vanished from the trail with no statement that anything was dropped,
#     which is the failure mode a scientist cannot even notice.
#
# The rule now: an entry whose stored evidence cannot be read is still SERVED,
# still carries its own identity (path/id/position) and whatever else about it
# IS readable, and says so explicitly via ``unavailable`` + ``unavailable_reason``.
# Nothing is invented for it — no value, no source, no citation, no status that
# implies support it does not have (CLAUDE.md §5).
#
# A BUNDLE-level failure is deliberately NOT absorbed here. If ``draft["fields"]``
# or ``sidecar["evidence"]`` is not a mapping at all — or ``draft["implicit"]`` /
# ``draft["assets"]`` is not a list — there is no per-item question to answer and
# these functions still raise, so the caller fails the whole read instead of
# reporting a misleading partial success. (The route's own artifact-pair
# tolerance — ``routes._read_artifact_json`` — is unchanged and still degrades an
# unreadable sidecar to the draft trail.)
#
# ``implicit``/``assets`` needed an EXPLICIT guard where the two mappings did not.
# ``(draft.get("fields") or {}).items()`` raises on its own for any non-mapping,
# but ``enumerate(draft.get("implicit") or [])`` happily walks a dict's KEYS or a
# string's CHARACTERS. Measured on `ba8e38e` before this guard existed:
# ``{"implicit": {"x": 1, "y": 2}}`` produced TWO entries ``implicit:#0`` and
# ``implicit:#1``, each stating "the stored implicit claim at position 0 is a
# string, not an implicit claim" — a per-position claim about positions that do
# not exist, invented out of dict keys. ``{"implicit": "abc"}`` produced THREE,
# one per character. That is a fabricated partial success, which is worse than the
# failure it replaced (base `77820bf` raised on all of them).

#: ``status`` for an entry whose stored evidence yielded NO readable support.
#: A separate value rather than one of the draft's own statuses: the trail's
#: ``status`` is a statement about the support behind the entry, and no such
#: statement can be made about evidence that could not be read. "verified" — what
#: ``_status_from_evidence`` returns for an empty list — would have been a claim
#: this code is in no position to make. The field's own stored status is not lost:
#: ``/experiments/{id}/draft`` carries it independently.
UNAVAILABLE_STATUS = "unavailable"

#: Neutral English for a JSON type, for the reason string. The stored VALUE is
#: never interpolated — the reader is told what shape was found, not handed
#: arbitrary content to read as if it were a citation.
_JSON_KIND = {
    bool: "a boolean",
    int: "a number",
    float: "a number",
    str: "a string",
    dict: "an object",
    list: "a list",
    type(None): "null",
}


def _kind(value) -> str:
    return _JSON_KIND.get(type(value), "an unreadable value")


def _readable_evidence(payload) -> tuple[list[dict], str | None]:
    """Split a stored evidence payload into (readable entries, reason it is partial).

    ``None``/absent is NOT a failure — a field legitimately carries no citation,
    and reporting that as unavailable would cry wolf on every uncited entry.
    """
    if payload is None:
        return [], None
    if isinstance(payload, list):
        readable = [e for e in payload if isinstance(e, dict)]
        if len(readable) == len(payload):
            return readable, None
        unreadable = len(payload) - len(readable)
        return readable, (
            f"{unreadable} of {len(payload)} stored evidence entries cannot be "
            f"shown: not an evidence object"
        )
    return [], (
        f"the stored evidence for this entry is {_kind(payload)}, not a list of "
        f"evidence entries"
    )


def _trail_entry(path: str, value, status, payload) -> dict:
    """One trail entry, with its evidence read defensively.

    ``status`` is the caller's own answer for a well-formed entry; it is replaced
    by :data:`UNAVAILABLE_STATUS` only when the payload yielded no readable
    support at all.

    A PARTIALLY readable payload KEEPS ``status`` and additionally discloses what
    could not be shown. What that status means then depends on which caller
    supplied it, and the two are not the same — an earlier revision of this
    docstring said "keeps the status its readable entries justify", which is true
    of only two of the three callers:

    * implicit claims and assets, and every sidecar key, pass
      ``_status_from_evidence(_readable_evidence(payload)[0])`` — a status
      RE-DERIVED from the readable entries alone, so it does describe exactly
      what is on screen.
    * a draft ``fields`` envelope passes ``env.get("status")`` VERBATIM. Nothing
      is re-derived, so the status is the author's stored answer about the whole
      payload, not about its readable part. Measured: ``evidence: [<good>, 7]``
      stored ``verified`` is served ``status: "verified"`` with
      ``unavailable: true``.

    The draft-fields behaviour is deliberate — the stored status is the author's
    own record and this view does not overwrite it — and it is defensible only
    BECAUSE ``unavailable``/``unavailable_reason`` travel with it. Nothing here
    may present that status as fully justified support.
    """
    readable, reason = _readable_evidence(payload)
    entry = {
        "path": path,
        "value": value,
        "status": UNAVAILABLE_STATUS if reason is not None and not readable else status,
        "evidence": readable,
    }
    if reason is not None:
        entry["unavailable"] = True
        entry["unavailable_reason"] = reason
    return entry


def _unreadable_entry(path: str, reason: str) -> dict:
    """An entry nothing could be read from except its position in the document.

    Kept in the trail on purpose. Dropping it would silently shorten a scientist's
    evidence trail; ``value``/``evidence`` stay empty because inventing either is
    exactly what CLAUDE.md §5 forbids.
    """
    return {
        "path": path,
        "value": None,
        "status": UNAVAILABLE_STATUS,
        "evidence": [],
        "unavailable": True,
        "unavailable_reason": reason,
    }


#: Shape errors a single malformed stored entry can raise. Narrow on purpose (the
#: reasoning is ``routes._read_artifact_json``'s): a ``MemoryError`` or a genuine
#: programming error must not be reported to a scientist as "this item's evidence
#: is malformed", because that would be a false statement about their record.
_ITEM_SHAPE_ERRORS = (AttributeError, TypeError, ValueError, KeyError, IndexError)


def _bundle_list(draft: dict, key: str, noun: str) -> list:
    """A draft's ``implicit``/``assets`` container, or a BUNDLE-level failure.

    The mirror of what ``(draft.get("fields") or {}).items()`` does for free: a
    container that is not a list is not N unreadable items, it is one unreadable
    container, and there is no position to key an entry by. Raising is the same
    answer ``fields``/``evidence`` give and the same answer base ``77820bf`` gave.

    ``None``/absent stays legal (the key is optional). A non-list — dict, string,
    number, boolean — raises, INCLUDING the falsy ones (``""``, ``0``, ``False``):
    "the container is empty" and "the container is not a container" are different
    facts, and ``or []`` used to answer the second with the first.
    """
    container = draft.get(key)
    if container is None:
        return []
    if isinstance(container, list):
        return container
    raise TypeError(
        f"draft[{key!r}] is {_kind(container)}, not a list of {noun} — a "
        f"bundle-level failure, not a per-item one"
    )


def evidence_trail_from_draft(draft: dict) -> list[dict]:
    """Evidence trail for a not-yet-exported experiment: read the draft envelopes.

    Every entry is read in isolation: one malformed envelope, implicit claim or
    asset becomes ONE entry marked unavailable, never a lost trail. See the
    section comment above for the measured defect.
    """
    entries: list[dict] = []
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            # Was `continue` — a silent drop. The field is stated as unreadable
            # instead, so its absence from the record's evidence is visible.
            entries.append(
                _unreadable_entry(
                    str(path),
                    f"this field's stored draft envelope is {_kind(env)}, not an "
                    f"evidence envelope",
                )
            )
            continue
        try:
            entries.append(
                _trail_entry(path, env.get("value"), env.get("status"), env.get("evidence"))
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    str(path), f"this field's stored evidence could not be read ({type(exc).__name__})"
                )
            )
    for index, imp in enumerate(_bundle_list(draft, "implicit", "implicit claims")):
        if not isinstance(imp, dict):
            entries.append(
                _unreadable_entry(
                    f"implicit:#{index}",
                    f"the stored implicit claim at position {index} is {_kind(imp)}, "
                    f"not an implicit claim; it has no recorded subject to name",
                )
            )
            continue
        path = f"implicit:{imp.get('about', '?')}"
        try:
            payload = imp.get("evidence")
            entries.append(
                _trail_entry(path, imp.get("value"), _status_from_evidence(_readable_evidence(payload)[0]), payload)
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    path, f"this implicit claim could not be read ({type(exc).__name__})"
                )
            )
    for index, asset in enumerate(_bundle_list(draft, "assets", "assets")):
        if not isinstance(asset, dict):
            entries.append(
                _unreadable_entry(
                    f"assets:#{index}",
                    f"the stored asset at position {index} is {_kind(asset)}, not an "
                    f"asset; it has no recorded id or URI to name",
                )
            )
            continue
        aid = asset.get("asset_id", asset.get("uri", "?"))
        try:
            payload = asset.get("evidence")
            entries.append(
                _trail_entry(
                    f"assets:{aid}",
                    asset.get("sha256"),
                    _status_from_evidence(_readable_evidence(payload)[0]),
                    payload,
                )
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    f"assets:{aid}",
                    f"this asset's stored evidence could not be read ({type(exc).__name__})",
                )
            )
    return entries


def evidence_trail_from_sidecar(sidecar: dict, record: dict) -> list[dict]:
    """Evidence trail for an exported experiment: read the real sidecar faithfully.

    Sidecar keys are official dotted paths, or ``assets:``/``descriptors:``/``implicit:``
    namespaced keys. ``implicit:`` values are ``{value, evidence}``; the rest are evidence
    lists. Values are resolved from the record so sha256s are visible post-export.

    Read per key, in isolation: one malformed payload becomes ONE entry marked
    unavailable — keyed by the sidecar key it was stored under, so which entry
    failed and where it came from stay answerable. See the section comment above.
    """
    assets_by_id = {
        a.get("asset_id"): a for a in (record.get("assets") or []) if isinstance(a, dict)
    }
    entries: list[dict] = []
    for key, payload in (sidecar.get("evidence") or {}).items():
        try:
            if key.startswith("implicit:"):
                value = payload.get("value") if isinstance(payload, dict) else None
                evidence = payload.get("evidence") if isinstance(payload, dict) else payload
            else:
                evidence = payload
                if ":" in key:
                    namespace, _, name = key.partition(":")
                    if namespace == "assets":
                        value = (assets_by_id.get(name) or {}).get("sha256")
                    else:
                        value = None
                else:
                    value, _found = get_path(record, key)
            entries.append(
                _trail_entry(
                    key, value, _status_from_evidence(_readable_evidence(evidence)[0]), evidence
                )
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    str(key),
                    f"this sidecar entry could not be read ({type(exc).__name__})",
                )
            )
    return entries
