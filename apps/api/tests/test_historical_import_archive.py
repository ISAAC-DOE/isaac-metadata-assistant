"""THE ARCHIVE SOURCE KIND — the model, its bounds, and the claim it corrected.

``historical_import`` grew a THIRD ``SOURCE_KIND`` because one source per file
does not fit and should not: ``MAX_SOURCES_PER_SESSION`` is 500 and the measured
BL15-2 corpus is 1,192 files, and raising the ceiling would have satisfied the
letter of the manifest requirement while defeating its purpose. A folder or ZIP
is ONE manifest entry whose parse RESULT is an inventory.

WHAT THIS FILE PINS THAT THE ROUTE-LEVEL WALK DOES NOT
======================================================

The end-to-end walk (``test_bl15_import_acceptance_walk.py``) proves the chain
over HTTP. This file pins the things that live BELOW a route: the allowlist and
its traversal boundary, the persistence split that keeps each candidate written
exactly once, the two bounds whose numbers were measured rather than chosen, and
the claim correction the archive kind forced.

DATA BOUNDARY: none. The only archive read is the committed sanitized
``tests/fixtures/bl15/gold/mini_corpus``; one test builds a ZIP inside
``tmp_path`` from files it writes itself. No database connection is opened.
"""

from __future__ import annotations

import json
import pathlib
import re
import zipfile

import pytest

import isaac_api.historical_import as hist
import isaac_api.workspace as ws

ARCHIVE = "bl15_synthetic_mini_corpus"
NOW = "2026-09-16T00:00:00Z"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def session(workspace):
    return hist.new_session(label="BL15-2", now_utc=NOW)


def _with_archive(session, **over):
    body = {
        "kind": hist.SOURCE_KIND_ARCHIVE,
        "fixture_name": ARCHIVE,
        "recorded_utc": NOW,
        "now_utc": NOW,
    }
    body.update(over)
    return hist.add_source(session, **body)


# --- the kind, and the allowlist ---------------------------------------------


def test_there_are_exactly_three_source_kinds(workspace):
    """A closed enumeration, and the docstring's old "exactly two" is corrected.

    Asserted as a SET rather than a length, so adding a fourth without deciding
    what it means fails here rather than passing a count check.
    """
    assert hist.SOURCE_KINDS == {"reference", "synthetic_fixture", "archive"}


def test_the_archive_allowlist_is_a_mapping_and_the_caller_supplies_only_a_key(
    workspace,
):
    """THE TRAVERSAL BOUNDARY, and why it is not a directory listing.

    ``fixture_names`` derives its allowlist from a flat directory because every
    entry is a bare filename. An archive fixture is a NESTED path, so a derived
    allowlist would have to admit ``/`` — and once a caller-supplied string may
    contain a separator it has stopped being the boundary. Here the caller
    supplies a KEY and the path is the module's own literal.
    """
    assert ARCHIVE in hist.archive_names()
    for name, relative in hist.ARCHIVE_FIXTURES.items():
        assert not relative.startswith("/"), name
        assert ".." not in relative.split("/"), name
        resolved = hist.archive_root_for(name).resolve()
        assert resolved.is_relative_to(ws.REPO_ROOT.resolve()), name


@pytest.mark.parametrize(
    "name",
    [
        "../../../etc/passwd",
        "/etc/passwd",
        "tests/fixtures/bl15",
        "bl15_synthetic_mini_corpus/..",
        "",
        "does_not_exist",
    ],
)
def test_a_name_off_the_allowlist_is_refused_by_the_same_branch(session, name):
    """A name that LOOKS like a path and one that is merely absent, refused alike.

    The same branch for both is what stops this operation being used to find out
    what exists on the filesystem — ``fixture_path``'s reason, applied here.
    """
    with pytest.raises(hist.UnsupportedImport) as raised:
        _with_archive(session, fixture_name=name)
    assert raised.value.error in {"unknown_archive", "missing_field"}
    assert session.sources == []


def test_an_archive_source_records_a_repo_relative_reference(session):
    """An absolute path would carry this machine's home directory into a document."""
    entry = _with_archive(session)
    assert entry.kind == "archive"
    assert entry.reference == "tests/fixtures/bl15/gold/mini_corpus"
    assert not entry.reference.startswith("/")
    assert entry.parse_state == hist.PARSE_STATE_UNPARSED


def test_the_provenance_says_the_bytes_were_read(session):
    """An archive IS read, and the provenance says so rather than leaving it inferred.

    It is a third kind precisely so that being read does not weaken the pointer's
    "NO BYTES, EVER" rule for the other two — which means the honesty has to be
    stated per entry, not per application.
    """
    archive = _with_archive(session)
    pointer = hist.add_source(
        session,
        kind=hist.SOURCE_KIND_REFERENCE,
        filename="scan.mac",
        reference="/nfs/somewhere/scan.mac",
        recorded_utc=NOW,
        now_utc=NOW,
    )
    assert archive.provenance["bytes_read_by_this_application"] is True
    assert pointer.provenance["bytes_read_by_this_application"] is False
    assert "walked it" in archive.provenance["recorded_how"]
    # NO ACTOR IS STAMPED, for the reason the module gives: no trusted
    # authentication boundary exists, so a name here would be forgeable.
    assert archive.provenance["recorded_by"] == hist.PROVENANCE_NO_ACTOR


# --- THE CLAIM CORRECTION, MADE MECHANICAL -----------------------------------


def test_an_archive_sources_sha256_is_none_unless_the_scientist_supplied_one(session):
    """THE TEST THE MODULE DOCSTRING CITES. The distinction is a mechanism.

    ``historical_import``'s docstring asserted *"A DIGEST IS NEVER COMPUTED HERE,
    not even for a fixture this module does read."* The archive walk made that
    false: it computes a SHA-256 of every member, and it must, because content
    hashing is the only thing that stops the corpus doubling and the only correct
    way to recognise the 96 duplicate groups.

    The corrected claim is narrower and this is what holds it: a member digest is
    computed inside the parse, for structural deduplication, and is NEVER
    published as a manifest ``sha256`` for any source of any kind.

    MUTATION: assigning any member's digest to the manifest entry's ``sha256``
    makes this RED.
    """
    entry = _with_archive(session)
    assert entry.sha256 is None
    hist.parse_session(session, now_utc=NOW)
    # STILL NONE AFTER THE PARSE, which is the half that matters: the parse is
    # where the hashing happens.
    assert session.sources[0].sha256 is None
    assert session.sources[0].parse_state == hist.PARSE_STATE_PARSED

    # AND THE MEMBER DIGESTS DO EXIST — so this is a scoping of the claim and not
    # a restatement of it.
    reading = session.archive_reading
    assert reading is not None
    digests = {row["content_sha256"] for row in reading.manifest}
    assert len(digests) >= 10
    assert all(isinstance(d, str) and len(d) == 64 for d in digests)
    # NOT ONE OF THEM REACHES A MANIFEST ENTRY.
    assert session.sources[0].sha256 not in digests


def test_a_supplied_digest_is_recorded_verbatim_and_shape_checked(session):
    """The negative control: absence above is a decision, not an inability."""
    entry = _with_archive(session, sha256="b" * 64)
    assert entry.sha256 == "b" * 64
    with pytest.raises(hist.UnsupportedImport) as raised:
        _with_archive(session, sha256="B" * 64)
    assert raised.value.error == "malformed_sha256"


# --- the parse: bounds, and the persistence split ----------------------------


def test_the_archive_is_one_manifest_entry_and_the_ceiling_is_untouched(session):
    """The 500-source ceiling still bounds MANIFEST ENTRIES, not archive members."""
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    assert len(session.sources) == 1
    assert session.archive_reading.inventory["entry_count"] > 1
    assert hist.MAX_SOURCES_PER_SESSION == 500


def test_every_supporting_statement_list_is_a_window_or_complete_and_says_which(
    session,
):
    """A trimmed list must never be reported as a whole one.

    ``supporting_statement_total`` is ``None`` exactly when the list is complete,
    and is the TRUE count otherwise. Any count of witnesses reads that field,
    never ``len(supporting_statements)``.

    MUTATION: windowing without setting the total makes this RED.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    candidates = session.archive_candidates
    assert candidates

    windowed = 0
    for candidate in candidates:
        held = len(candidate.supporting_statements)
        assert held <= hist.MAX_STATEMENTS_PER_CANDIDATE, candidate.candidate_id
        total = candidate.supporting_statement_total
        if total is None:
            # COMPLETE: the list IS all of them. `held` may equal the ceiling —
            # a candidate resting on exactly five statements is whole, not
            # windowed — which is why this asserts nothing beyond the `<=` above.
            # The first version of this assertion read `held < ceiling` and went
            # RED on a real candidate with exactly five witnesses.
            pass
        else:
            windowed += 1
            assert total > held, (candidate.candidate_id, total, held)
            assert held == hist.MAX_STATEMENTS_PER_CANDIDATE
    # THE WINDOW IS ACTUALLY REACHED by this corpus, so the branch above is
    # exercised rather than merely written.
    assert windowed >= 1, "no candidate reached the statement window"


def test_a_conflicted_candidates_disagreement_is_never_windowed(session):
    """EVERY competing reading survives. Windowing this would be the one thing
    this whole feature exists not to do — turning "the sources disagree, here is
    each one" into "here are some of them".
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    conflicted = [c for c in session.archive_candidates if c.disagreement]
    assert conflicted
    for candidate in conflicted:
        assert len(candidate.disagreement) >= 2, candidate.candidate_id
        assert candidate.proposed_value is None
        assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE


def test_a_reading_row_reports_what_a_reader_suppressed_and_whether_it_is_partial(
    session,
):
    """``len(evidence)`` is not a completeness claim, and the row says so.

    A reader's evidence list can be a PARTIAL reading — one real acquisition
    suppresses ~41,000 statements at its per-source ceiling — so anything counting
    statements must read the skip entry rather than trusting the list's length.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    assert reading.reading
    for row in reading.reading:
        # EVERY ROW CARRIES BOTH, on every path, so a consumer never learns
        # whether a reading was partial by a key's presence.
        assert "partial" in row and isinstance(row["partial"], bool)
        assert row["statements_suppressed"] >= 0
        assert row["skipped_total"] >= len(row["skipped"])
        assert row["partial"] is (row["statements_suppressed"] > 0)
    assert reading.partial_reading_count() == sum(
        1 for row in reading.reading if row["partial"]
    )


def test_a_source_this_build_has_no_reader_for_is_listed_not_passed_over(session):
    """`.mca` content is deliberately not read, and the row says a reader did not run.

    A manifest that showed only what was read could not be told from a smaller
    archive, which is ``HIST-004``'s banned pattern in miniature.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    paths_with_rows = {row["archive_path"] for row in reading.reading}
    paths_in_manifest = {row["archive_path"] for row in reading.manifest}
    # EVERY accepted entry has a reading row. None is silently skipped.
    assert paths_with_rows == paths_in_manifest


def test_each_candidate_is_persisted_exactly_once_and_the_union_round_trips(session):
    """THE PERSISTENCE SPLIT, which exists so one document does not hold ~1,000
    candidates twice — and so the two copies cannot disagree about what was found.

    ``reconstruction`` holds the UNION in memory; ``to_state`` writes the
    PROVIDER's half there and the ARCHIVE's half under ``archive_reading``;
    ``from_state`` re-composes.

    MUTATION: writing the union in both places makes the byte-count assertion
    RED; dropping the re-composition makes the round-trip assertion RED.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    hist.reconstruct_session(session, now_utc=NOW)

    archive_ids = {c.candidate_id for c in session.archive_candidates}
    assert archive_ids
    state = session.to_state()

    # NOT ONE archive candidate appears under `reconstruction`.
    written = {c["candidate_id"] for c in state["reconstruction"]["candidates"]}
    assert written.isdisjoint(archive_ids), sorted(written & archive_ids)
    # All of them appear under `archive_reading`, exactly once each.
    stored = [c["candidate_id"] for c in state["archive_reading"]["candidates"]]
    assert sorted(stored) == sorted(archive_ids)
    assert len(stored) == len(set(stored))

    hist.save_session(session)
    again = hist.load_session(session.import_id)
    assert again is not None
    # THE UNION IS BACK, and the whole document is byte-identical.
    assert {c.candidate_id for c in hist.candidates_of(again)} == archive_ids | written
    assert again.to_state() == state
    assert len(again.archive_reading.units) == len(session.archive_reading.units)


def test_an_unreadable_archive_reading_is_dropped_rather_than_crashing_the_read(
    session, tmp_path
):
    """A reading is DERIVED, so losing one costs a re-parse and never a scientist's work.

    The asymmetry against ``_hydrate_sources`` (which preserves verbatim) is
    deliberate and is the same one ``_hydrate_parsed`` already makes.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    hist.save_session(session)

    path = hist._session_dir(session.import_id, None) / hist.SESSION_FILE
    document = json.loads(path.read_text())
    document["archive_reading"] = {"units": [{"stem": 7}]}  # no required strings
    path.write_text(json.dumps(document))

    again = hist.load_session(session.import_id)
    # THE SESSION STILL LOADS. The MANIFEST ENTRY survives, so re-parsing
    # reconstructs everything that was dropped.
    assert again is not None
    assert again.archive_reading is None
    assert len(again.sources) == 1
    assert again.sources[0].kind == "archive"


def test_removing_the_archive_source_drops_its_reading(session):
    """A reading of a bundle the bundle no longer matches is a stale claim."""
    entry = _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    assert session.archive_reading is not None
    assert hist.remove_source(session, entry.source_id, now_utc=NOW) is True
    assert session.archive_reading is None
    assert session.archive_candidates == []


def test_reconstructing_an_archive_only_bundle_is_not_refused_as_nothing_parsed(
    session,
):
    """`session.parsed` is empty for an archive-only bundle, and it has evidence.

    MUTATION: restoring the `if not session.parsed` guard alone makes this RED.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    assert session.parsed == []
    reconstruction = hist.reconstruct_session(session, now_utc=NOW)
    assert reconstruction.candidates
    # THE PROVIDER IS STILL NAMED, so `provider_id`'s meaning does not depend on
    # what the bundle happened to contain.
    assert reconstruction.provider_id == hist.PROVIDER.provider_id
    assert reconstruction.applied is False


def test_a_bundle_with_neither_a_parse_nor_an_archive_is_still_refused(session):
    """The negative control for the test above: the guard was NARROWED, not removed."""
    hist.add_source(
        session,
        kind=hist.SOURCE_KIND_REFERENCE,
        filename="scan.mac",
        reference="/nfs/somewhere/scan.mac",
        recorded_utc=NOW,
        now_utc=NOW,
    )
    hist.parse_session(session, now_utc=NOW)
    with pytest.raises(hist.UnsupportedImport) as raised:
        hist.reconstruct_session(session, now_utc=NOW)
    assert raised.value.error == "nothing_parsed"


# --- the digest ---------------------------------------------------------------


def test_every_digest_number_is_counted_from_the_payload(session):
    """Not one figure is a literal, and this test is how that stays true.

    Each assertion re-derives the number from the persisted collection the digest
    claims to describe, so a hard-coded value would disagree with its own source.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    digest = hist.corpus_digest(session)
    assert digest is not None

    assert digest["total_sources"] == len(reading.manifest)
    assert digest["refused_count"] == len(digest["refused"])
    assert sum(digest["by_source_type"].values()) == len(reading.manifest)
    assert sum(digest["by_classification_confidence"].values()) == len(reading.manifest)
    assert digest["measurement_units"] == len(reading.units)
    assert digest["run_candidate_units"] == sum(
        1 for u in reading.units if u.run_candidate
    )
    assert digest["statements_suppressed"] == sum(
        row["statements_suppressed"] for row in reading.reading
    )
    assert digest["partial_readings"] == sum(
        1 for row in reading.reading if row["partial"]
    )
    # THE CANDIDATE TOTAL IS THE RECONSTRUCTION'S, NOT THE STORED COUNT. A
    # surface reporting the stored count as the total would understate the corpus
    # by exactly what the ceiling withheld.
    assert digest["candidates"] == reading.candidate_total
    assert digest["candidates_stored"] == len(session.archive_candidates)
    assert digest["candidates_truncated"] is (
        digest["candidates"] > digest["candidates_stored"]
    )


def test_a_bundle_with_no_archive_has_no_digest_rather_than_an_empty_one(session):
    """`None` is an honest absence; zeroes would read as a corpus with nothing in it."""
    hist.add_source(
        session,
        kind=hist.SOURCE_KIND_REFERENCE,
        filename="scan.mac",
        reference="/nfs/somewhere/scan.mac",
        recorded_utc=NOW,
        now_utc=NOW,
    )
    assert hist.corpus_digest(session) is None
    view = hist.session_view(session)
    assert view["corpus_digest"] is None
    assert view["archive"] is None


def test_the_served_pages_carry_totals_so_no_count_can_understate(session):
    """THE WINDOW BOUNDS WHAT IS FETCHED, NEVER WHAT IS CLAIMED.

    Measured at the real corpus's cardinality, an unbounded session view was
    6,410,701 bytes. Every page therefore carries its own ``total``, read off the
    whole persisted collection — a surface counting the rows it RECEIVED would
    report a 1,192-file corpus as 200 files.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    hist.reconstruct_session(session, now_utc=NOW)
    view = hist.session_view(session)
    reading = session.archive_reading

    for key, whole in (
        ("manifest_page", reading.manifest),
        ("reading_page", reading.reading),
        ("units_page", reading.units),
    ):
        page = view["archive"][key]
        assert page["total"] == len(whole), key
        assert len(page["rows"]) <= hist.ARCHIVE_PAGE_WINDOW, key
        assert page["limit"] == hist.ARCHIVE_PAGE_WINDOW, key
        assert page["truncated"] is (page["total"] > page["limit"]), key

    candidate_page = view["reconstruction"]["candidate_page"]
    assert candidate_page["total"] == len(session.reconstruction.candidates)
    assert len(view["reconstruction"]["candidates"]) <= candidate_page["limit"]


def test_paging_the_view_does_not_make_a_candidate_unproposable(session, monkeypatch):
    """A candidate OUTSIDE the served window is still resolvable by id.

    Both propose operations resolve against the LOADED SESSION, never against the
    view, which is what makes the window safe. Proven by shrinking the window to
    1 and confirming every candidate still resolves.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    hist.reconstruct_session(session, now_utc=NOW)
    ids = [c.candidate_id for c in session.reconstruction.candidates]
    assert len(ids) > 1

    monkeypatch.setattr(hist, "ARCHIVE_PAGE_WINDOW", 1)
    view = hist.session_view(session)
    assert len(view["reconstruction"]["candidates"]) == 1
    assert view["reconstruction"]["candidate_page"]["total"] == len(ids)
    assert view["reconstruction"]["candidate_page"]["truncated"] is True
    # EVERY id still resolves on the session, including the ones the view withheld.
    for candidate_id in ids:
        assert session.candidate(candidate_id) is not None, candidate_id


# --- the run label ------------------------------------------------------------


def test_the_run_label_is_the_legacy_number_then_verbatim_tokens(session):
    """No token is expanded, corrected or translated.

    ``ffilter35`` stays ``ffilter35`` and ``after1500Cycling`` stays
    ``after1500Cycling``, because writing "filter 35" or "After 1500 mV cycling"
    would be this module composing scientific prose out of a token in the one
    string a run is identified by. The normalisation exists and travels on the
    CANDIDATE, with its rule named beside it.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    labels = {u.stem: u.label for u in session.archive_reading.units}

    assert (
        labels["03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9"]
        == "Legacy 3 · 02 · SYN2 · base · after1500Cycling · ffilter35 · 1200mV"
    )
    assert (
        labels["01_01_SYN1_acid_beforeCycling_filter10_060mV"]
        == "Legacy 1 · 01 · SYN1 · acid · beforeCycling · filter10 · 060mV"
    )
    # A MEASUREMENT WITH NO LEGACY NUMBER falls back to its own stem rather than
    # letting `new_run` assign "Run 1" — an ordinal this import did not choose.
    assert labels["alignsynth"] == "alignsynth"
    # AND EVERY LABEL FITS THE ROUTE'S OWN BOUND.
    for label in labels.values():
        assert len(label) <= hist.MAX_LABEL_CHARS, label
        assert label.strip() == label


def test_run_candidacy_is_carried_from_the_classification_not_stored_separately(session):
    """Alignment and standards are NOT run candidates, and the flag is derived.

    ``MeasurementUnit.run_candidate`` is itself derived from ``source_type``, so
    carrying it across cannot disagree with the layer that decided it.
    """
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    units = {u.stem: u for u in session.archive_reading.units}
    assert units["alignsynth"].source_type == "alignment"
    assert units["alignsynth"].run_candidate is False
    # IT IS STILL A MEASUREMENT, fully assembled, with its own candidates.
    assert units["alignsynth"].candidate_ids
    assert len(session.archive_reading.run_candidate_units()) == 4
    assert len(session.archive_reading.units) == 5


def test_a_candidate_resolves_to_the_measurement_that_produced_it(session):
    """What the run-creating operation needs: candidate id -> its measurement."""
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    for unit in reading.units:
        for candidate_id in unit.candidate_ids:
            assert reading.unit_of_candidate(candidate_id) is unit, candidate_id
    # A SHARED (beamtime-scope) candidate belongs to NO measurement, and the
    # answer is `None` rather than a plausible-looking guess.
    for candidate_id in reading.shared_candidate_ids:
        assert reading.unit_of_candidate(candidate_id) is None, candidate_id


# --- the export blockers ------------------------------------------------------


def test_the_export_blockers_are_quoted_from_the_registry_not_rewritten(workspace):
    """Two of three are ``bl15.mapping``'s own constants, read at call time.

    So if that module's wording changes this follows it, and there is one wording
    per fact rather than two that can drift.
    """
    from isaac_api.bl15 import mapping as mp

    assert hist.export_blocked_reasons() == (
        mp.TEMPERATURE_ABSENT_REASON,
        hist.EXPORT_BLOCKED_NO_DESCRIPTORS,
        mp.ASSETS_BLOCKED_REASON,
    )
    # THE THIRD HAS NO HOME IN THE REGISTRY, and that is why it is local: it is a
    # property of the official schema's `record_type` conditional rather than of
    # any concept's mapping.
    assert "descriptors" in hist.EXPORT_BLOCKED_NO_DESCRIPTORS
    assert not any(
        hist.EXPORT_BLOCKED_NO_DESCRIPTORS == getattr(mp, name, None)
        for name in dir(mp)
        if name.isupper()
    )


# --- a ZIP walks the same way as a folder ------------------------------------


def test_a_zip_archive_walks_through_the_same_path_as_a_folder(
    session, tmp_path, monkeypatch
):
    """The suffix decides the walker; nothing else about the chain changes.

    THE ALLOWLIST IS MONKEYPATCHED and the ZIP is built here, because committing
    a binary fixture would add a second exemption to the repository's
    source-is-greppable guard for one test's benefit. What is under test is THIS
    module's branch, not ``bl15.archive``'s ZIP walk, which has its own suite.
    """
    corpus = tmp_path / "zip-corpus"
    corpus.mkdir()
    spec = (
        "#F 07_03_SYN3_acid_beforeCycling_filter10_100mV\n"
        "#E 4102444800\n"
        "#D Fri Jan 01 00:00:00 2099\n"
        "#O0 sy1  sy2\n"
        "#S 1 gscan 1000 1100 10 1\n"
        "#P0 1.0 2.0\n"
        "#N 2\n"
        "#L Energy  I0\n"
        "1000 100\n"
    )
    (corpus / "07_03_SYN3_acid_beforeCycling_filter10_100mV").write_text(spec)
    (corpus / "run07.mac").write_text(
        "def synrun '{\n  newfile 07_03_SYN3_acid_beforeCycling_filter10_100mV\n}'\n"
    )
    bundle = tmp_path / "corpus.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        for child in sorted(corpus.iterdir()):
            zf.write(child, arcname=f"zip-corpus/{child.name}")

    monkeypatch.setattr(hist, "ARCHIVE_FIXTURE_ROOT", tmp_path)
    monkeypatch.setattr(hist, "ARCHIVE_FIXTURES", {"zipped": "corpus.zip"})

    _with_archive(session, fixture_name="zipped")
    hist.parse_session(session, now_utc=NOW)
    reading = session.archive_reading
    assert reading is not None
    assert session.sources[0].parse_state == hist.PARSE_STATE_PARSED
    # BOTH MEMBERS INVENTORIED, with the common root stripped, and the
    # acquisition became the one measurement while the macro did not.
    assert {row["archive_path"] for row in reading.manifest} == {
        "07_03_SYN3_acid_beforeCycling_filter10_100mV",
        "run07.mac",
    }
    assert [u.stem for u in reading.units] == [
        "07_03_SYN3_acid_beforeCycling_filter10_100mV"
    ]
    assert reading.units[0].run_candidate is True
    # AND NO MEMBER DIGEST REACHED THE MANIFEST ENTRY here either.
    assert session.sources[0].sha256 is None


def test_an_archive_root_that_is_not_there_is_refused_not_crashed(
    session, tmp_path, monkeypatch
):
    """A scientist who chose the wrong thing is owed a readable answer about it."""
    monkeypatch.setattr(hist, "ARCHIVE_FIXTURE_ROOT", tmp_path)
    monkeypatch.setattr(hist, "ARCHIVE_FIXTURES", {"gone": "not-here"})
    # THE ALLOWLIST FILTERS ON EXISTENCE, so it is refused before any walk.
    assert hist.archive_names() == ()
    with pytest.raises(hist.UnsupportedImport) as raised:
        _with_archive(session, fixture_name="gone")
    assert raised.value.error == "unknown_archive"


# --- the review surface's payload, joined 2026-09-16 --------------------------


def _parsed(session):
    """An archive session, parsed and reconstructed, ready to serve a view."""
    _with_archive(session)
    hist.parse_session(session, now_utc=NOW)
    return hist.session_view(session)


def test_the_session_serves_the_shape_the_review_surface_consumes(session):
    """THE TWO HALVES NOW MEET, and this is the test that would have caught that
    they did not.

    The review surface's whole component tree rendered behind `data.corpus_review`
    and **no route ever set it** — `grep -rn corpus_review apps/api/` returned zero.
    Independent review found it, along with three comments justifying the gap with a
    reason that had gone false on the same branch. Nothing failed, because nothing
    on either side asserted that the other existed.
    """
    view = _parsed(session)
    review = view.get("corpus_review")
    assert review is not None, "no route emits corpus_review"
    assert set(review) == {
        "inventory",
        "relationships",
        "evidence",
        "evidence_readings_dropped",
        "evidence_scope",
        # `CTX-004`. The `DEC-41` level-4 block: how much landed at level 4 and the
        # three separate reasons a statement the archive made did not. Added here in
        # the same change that adds it to the payload — this test IS the "the two
        # halves meet" guard its own docstring describes, so a member reaching the
        # wire without reaching this set would be the exact failure it exists for.
        "extended_context",
        "mapping",
        # 2026-09-22, added in the same change that adds them to the payload, for this
        # test's own reason. `evidence_readings_thinned` is the dedup half that used
        # to be counted into `evidence_readings_dropped` (which now means the
        # distinct-literal cap alone); the rest are the historical-semantics blocks
        # the Historical Import UI renders — which convention applied where, the
        # temperature state (Not recorded unless a source said something, and never
        # a number by default), Data Quality Notes, the HERFD selection summary, the
        # people the sources name, and the rules that shaped the reading.
        "evidence_readings_thinned",
        "evidence_readings_cap_per_cell",
        "profile_applicability",
        "temperature",
        "data_quality_notes",
        "herfd_signal",
        "beamtime_contributors",
        "rules_applied",
    }
    # THE THREE COSTS ARE THREE, AND ARE NEVER A SUM. They were ONE server-side
    # integer until `CTX-004` measured the three sites that incremented it, while two
    # comments described that integer as the tail cap alone. Asserted as a key set so
    # a future change that re-merged them would fail here rather than in a scientist's
    # reading of a number that means three different things.
    assert set(review["extended_context"]) == {
        "available",
        "dropped",
        "thinned",
        "unplaceable",
        "ceiling",
        "not_official",
    }

    # A PROJECTION, NOT A SECOND SOURCE OF TRUTH: the two large members are the
    # identical dicts the archive view already serves, so they cannot drift.
    archive = view["archive"]
    assert review["inventory"] == archive["inventory"]
    assert review["relationships"] == archive["relationships"]

    # THE REGISTRY IS SERVED WHOLE — ~~45~~ 47 entries since 2026-09-22 (the
    # temperature and contributor statements), static and cheap — and REGENERATED
    # per call rather than cached, so a status correction cannot be published stale.
    mapping = review["mapping"]
    assert len(mapping["concepts"]) == 47
    assert mapping["coverage"]["concepts_total"] == 47
    assert mapping["temperature_absent_reason"]
    assert mapping["assets_blocked_reason"]
    assert mapping["cycling_state_no_field_reason"]


def test_a_session_with_no_archive_carries_no_corpus_review_key_at_all(session):
    """Absent, not `null`. A client must not have to tell an empty review from none."""
    assert "corpus_review" not in hist.session_view(session)


def test_the_served_evidence_is_the_five_columns_and_nothing_else(session):
    """THE BOUND THAT MAKES THE JOIN POSSIBLE.

    The whole evidence set is ~500,000 items at the real corpus's cardinality, which
    is why it is not persisted. The surface needs SIX concepts of the forty-five, for
    five scientific columns, and only for readings that name a measurement.
    """
    review = _parsed(session)["corpus_review"]

    assert set(review["evidence_scope"]) == set(hist.REVIEW_COLUMN_CONCEPTS)
    assert len(review["evidence_scope"]) == 6
    assert review["evidence"], "the bounded set is empty, so the columns render nothing"
    for row in review["evidence"]:
        assert row["concept"] in hist.REVIEW_COLUMN_CONCEPTS
        # A BEAMTIME-SCOPE READING IS EXCLUDED. Folding one into a unit would invent a
        # relationship `relate` declined to make, which the surface says explicitly.
        assert row["measurement_stem"], row


def test_the_evidence_cap_is_on_DISTINCT_literals_so_a_dispute_cannot_be_thinned(session):
    """THE WHOLE SAFETY ARGUMENT FOR THE CAP, asserted rather than described.

    The surface's cell is absent / read / disputed, and `disputed` fires on two or
    more DIFFERENT literals. A cap on the raw COUNT could drop the one reading that
    differed and turn a disputed cell into a settled one — a conflict silently
    resolved by a payload bound, which is the class of defect this feature exists to
    prevent. Capping distinct literals preserves the verdict whatever the corpus does.
    """
    review = _parsed(session)["corpus_review"]

    distinct: dict[tuple[str, str], set[str]] = {}
    served: dict[tuple[str, str], int] = {}
    for row in review["evidence"]:
        key = (row["measurement_stem"], row["concept"])
        distinct.setdefault(key, set()).add(row["raw_literal"])
        served[key] = served.get(key, 0) + 1

    for key, count in served.items():
        assert count <= hist.MAX_DISTINCT_COLUMN_READINGS, key
        assert count == len(distinct[key]), (
            f"{key} served {count} readings over {len(distinct[key])} distinct "
            "literals — a duplicate survived the cap, so the cap is on count"
        )

    # AND WHAT THE CAP REMOVED IS REPORTED, so the list is never a trimmed one
    # presented as whole.
    assert isinstance(review["evidence_readings_dropped"], int)
    assert review["evidence_readings_dropped"] >= 0


def test_the_served_concepts_match_the_clients_column_map():
    """One vocabulary, two languages — pinned so a sixth column cannot be added on
    one side only.

    `CLAUDE.md` records a rename that stranded three of four copies of a workflow
    vocabulary; this is the same hazard with a language boundary in between.
    """
    source = (
        pathlib.Path(__file__).resolve().parents[3]
        / "apps"
        / "web"
        / "src"
        / "lib"
        / "bl15Review.ts"
    ).read_text(encoding="utf-8")
    block = source.split("BL15_COLUMN_CONCEPTS = {", 1)[1].split("} as const", 1)[0]
    client_concepts = set(re.findall(r"'([a-z_]+)'", block))
    assert client_concepts == set(hist.REVIEW_COLUMN_CONCEPTS), (
        "the client's column concepts and the server's REVIEW_COLUMN_CONCEPTS have "
        f"drifted: client-only {sorted(client_concepts - set(hist.REVIEW_COLUMN_CONCEPTS))}, "
        f"server-only {sorted(set(hist.REVIEW_COLUMN_CONCEPTS) - client_concepts)}"
    )
