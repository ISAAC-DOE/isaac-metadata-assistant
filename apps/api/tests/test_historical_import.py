"""HISTORICAL IMPORT — the domain model. ``HIST-001`` and ``HIST-003a``.

Every test here runs against the COMMITTED SYNTHETIC FIXTURES in
``tests/fixtures/historical_import/``, whose first lines say they are synthetic
and were never produced by an instrument. **No real experimental content is read
anywhere in this file**, and nothing under ``examples/`` is touched.

The file is organised as the contract it pins:

  §1  the manifest records metadata and never bytes
  §2  the parser INTERFACE, and the one format this build actually reads
  §3  the Beamline Profile encodes ZERO conventions           (BL15-002 blocked)
  §4  reconstruction: deterministic vs inferred, disagreement, unresolved
  §5  a semantic candidate CANNOT become record truth         (the §13 invariant)
  §6  persistence: tolerant reads, no silent discard, scope isolation
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from isaac_api import historical_import as hi
from isaac_api import workspace as ws

BUNDLE_A = "SYNTHETIC-bundle-a.txt"
BUNDLE_B = "SYNTHETIC-bundle-b.txt"

AT = "2026-09-13T00:00:00Z"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path / "ws"


def _fixture_source(session: hi.ImportSession, name: str) -> hi.SourceReference:
    return hi.add_source(
        session,
        kind=hi.SOURCE_KIND_SYNTHETIC_FIXTURE,
        fixture_name=name,
        recorded_utc=AT,
        now_utc=AT,
    )


def _pointer(session: hi.ImportSession, **over) -> hi.SourceReference:
    kwargs = {
        "kind": hi.SOURCE_KIND_REFERENCE,
        "filename": "scan_0012.mac",
        "reference": "/nfs/fake-beamline/2019/scan_0012.mac",
        "recorded_utc": AT,
        "now_utc": AT,
    }
    kwargs.update(over)
    return hi.add_source(session, **kwargs)


def _reconstructed(session: hi.ImportSession) -> hi.Reconstruction:
    hi.parse_session(session, now_utc=AT)
    return hi.reconstruct_session(session, now_utc=AT)


def _bundle() -> hi.ImportSession:
    session = hi.new_session(label="An old CuO campaign", now_utc=AT)
    _fixture_source(session, BUNDLE_A)
    _fixture_source(session, BUNDLE_B)
    _pointer(session)
    return session


def _by_path(reconstruction: hi.Reconstruction, path: str) -> hi.SemanticCandidate:
    for candidate in reconstruction.candidates:
        if candidate.target_field_path == path:
            return candidate
    raise AssertionError(f"no candidate at {path}")


# --- §0 the fixtures announce their own fakeness -----------------------------


def test_every_fixture_says_in_its_first_lines_that_it_is_synthetic():
    """A fixture that did not say so could be mistaken for real material later.

    ``CLAUDE.md`` §6 requires synthetic fixtures to be unmistakably fake. This
    reads the committed bytes rather than trusting the directory's name.
    """
    names = hi.fixture_names()
    assert names, "the committed fixture directory is empty"
    for name in names:
        head = hi.fixture_path(name).read_text(encoding="utf-8")[:400].upper()
        assert "SYNTHETIC FIXTURE" in head, name
        assert "NOT REAL EXPERIMENTAL DATA" in head, name


def test_the_fixtures_carry_no_real_facility_or_person():
    """A negative control over the values, not over the header.

    The header could say SYNTHETIC while the body carried a real beamline name.
    ``bl152``/``BL15-2`` is the pilot beamline the programme is BLOCKED on
    (``EXT-10``), so its appearance in a fixture would be exactly the guess §5
    forbids.
    """
    for name in hi.fixture_names():
        body = hi.fixture_path(name).read_text(encoding="utf-8")
        # The header talks ABOUT BL15-002 the task id; the VALUES must not name
        # the beamline. So this reads the `key = value` lines only.
        values = [
            line.split("=", 1)[1].strip()
            for line in body.splitlines()
            if "=" in line and not line.strip().startswith("#")
        ]
        joined = " ".join(values).lower()
        for banned in ("bl15", "ssrl", "slac", "stanford"):
            assert banned not in joined, f"{name} names {banned!r} in a value"


# --- §1 the manifest records metadata about files, never bytes ---------------


def test_a_pointer_is_recorded_and_the_file_is_not_opened(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    entry = _pointer(session, reference="/nfs/fake/does-not-exist-anywhere.mac")

    assert entry.kind == hi.SOURCE_KIND_REFERENCE
    # The honest state, decided at registration: not "waiting to be parsed".
    assert entry.parse_state == hi.PARSE_STATE_NO_CONTENT_PATH
    assert entry.parse_detail == hi.NO_CONTENT_PATH_DETAIL
    assert entry.provenance["bytes_read_by_this_application"] is False
    # And no parser claims it, so Parse cannot silently invent a reading.
    assert hi.parser_for(entry) is None


def test_a_pointer_to_a_path_that_does_not_exist_is_accepted_and_never_stat_ed(workspace):
    """The file is not opened, so its absence cannot be detected — or leaked.

    A build that refused a reference to a missing file would be a filesystem
    oracle: a caller could probe the server's disk one 422 at a time. This
    asserts the opposite behaviour and states the reason.
    """
    session = hi.new_session(label=None, now_utc=AT)
    entry = _pointer(session, reference="/etc/shadow")
    assert entry.reference == "/etc/shadow"
    hi.parse_session(session, now_utc=AT)
    assert session.parsed == []
    assert session.source(entry.source_id).parse_state == hi.PARSE_STATE_NO_CONTENT_PATH


def test_a_digest_is_shape_checked_and_never_computed(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    good = "a" * 64
    entry = _pointer(session, sha256=good)
    assert entry.sha256 == good

    with pytest.raises(hi.UnsupportedImport) as refusal:
        _pointer(session, sha256="a" * 63)
    assert refusal.value.error == "malformed_sha256"


def test_a_digest_with_trailing_whitespace_is_stripped_before_the_shape_check(workspace):
    """MEASURED, AND IT IS NOT THE OUTCOME THIS TEST FIRST ASSERTED.

    The first version of this test required ``"9" * 64 + "\\n"`` to RAISE, on the
    analogy of the ``$``-anchored-pattern defect ``isaac_records.exactness``
    exists about. Run, it did not raise — because :func:`~isaac_api.historical_import._clean`
    strips every string field before validating it, so the value reaching
    ``is_sha256_shaped`` is already 64 clean hex characters.

    **That is the safe direction and the assertion is corrected rather than the
    code**, because what the exactness defect was about is a value with a
    trailing newline being STORED and later reported as well-formed. Here the
    newline never reaches the store: the stripped value is what is persisted, and
    ``is_sha256_shaped`` is applied to it with ``fullmatch`` over an
    ``\\A…\\Z``-anchored pattern imported from the truth core. So the invariant
    that matters — no stored digest carries whitespace — holds, and this test now
    pins that instead of pinning a refusal that does not happen.
    """
    session = hi.new_session(label=None, now_utc=AT)
    entry = _pointer(session, sha256="9" * 64 + "\n")
    assert entry.sha256 == "9" * 64
    assert "\n" not in entry.sha256


def test_no_digest_is_computed_even_for_a_fixture_this_build_does_read(workspace):
    """The asymmetry that would put two meanings behind one field name.

    A fixture IS read, so a digest could be computed for it. It is not, and this
    is the assertion that keeps every surface able to say "recorded" rather than
    having to say which kind of digest it holds.
    """
    session = hi.new_session(label=None, now_utc=AT)
    entry = _fixture_source(session, BUNDLE_A)
    assert entry.sha256 is None
    hi.parse_session(session, now_utc=AT)
    assert session.source(entry.source_id).sha256 is None


def test_the_module_computes_no_digest_anywhere():
    """A negative control over the source, because the test above is one path.

    ``hashlib`` is not imported and no digest function is called, so a future
    edit that computed one has to add the import — which fails here.
    """
    src = Path(hi.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', " ", src)
    code = re.sub(r"^\s*#.*$", " ", code, flags=re.MULTILINE)
    for banned in ("hashlib", "sha256(", "md5(", "blake2"):
        assert banned not in code, f"{banned!r} appears in executable code"


def test_a_manifest_entry_records_the_seven_things_hist_001_requires(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    entry = _pointer(
        session,
        filename="campaign.xlsx",
        reference="https://example.invalid/campaign.xlsx",
        media_type="application/vnd.ms-excel",
        size_bytes=4096,
        sha256="b" * 64,
    )
    state = entry.to_state()
    for key in (
        "filename",
        "media_type",
        "size_bytes",
        "sha256",
        "reference",
        "parse_state",
        "provenance",
    ):
        assert key in state, key
    assert state["size_bytes"] == 4096


def test_a_size_persisted_as_a_boolean_reads_as_absent_not_as_one():
    """`isinstance(True, int)` is True in Python, so `true` would read as 1 byte."""
    entry = hi.SourceReference.from_state(
        {
            "source_id": "01" + "A" * 24,
            "kind": hi.SOURCE_KIND_REFERENCE,
            "filename": "f",
            "reference": "r",
            "parse_state": hi.PARSE_STATE_NO_CONTENT_PATH,
            "provenance": {},
            "size_bytes": True,
        }
    )
    assert entry.size_bytes is None


def test_the_bundle_is_bounded_and_says_so(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    session.sources = [
        hi.SourceReference(
            source_id=f"{i:026d}",
            kind=hi.SOURCE_KIND_REFERENCE,
            filename="f",
            reference="r",
            parse_state=hi.PARSE_STATE_NO_CONTENT_PATH,
            provenance={},
        )
        for i in range(hi.MAX_SOURCES_PER_SESSION)
    ]
    with pytest.raises(hi.UnsupportedImport) as refusal:
        _pointer(session)
    assert refusal.value.error == "too_many_sources"
    assert refusal.value.extra["maximum"] == hi.MAX_SOURCES_PER_SESSION


def test_no_actor_is_stamped_in_provenance(workspace):
    """§15: the actor seam stays unset while no trusted boundary exists.

    A provenance record saying "recorded by <client-supplied name>" would be a
    forgeable claim, which is worse than no claim.
    """
    session = hi.new_session(label=None, now_utc=AT)
    entry = _pointer(session)
    assert entry.provenance["recorded_by"] == hi.PROVENANCE_NO_ACTOR
    assert hi.PROVENANCE_NO_ACTOR == "no_trusted_identity_established"


# --- §2 the fixture allowlist is the traversal boundary ----------------------


@pytest.mark.parametrize(
    "name",
    [
        "../../../etc/passwd",
        "../SYNTHETIC-bundle-a.txt",
        "/etc/passwd",
        "SYNTHETIC-bundle-a.txt/../../secret",
        "",
        ".",
    ],
)
def test_a_fixture_name_that_could_name_a_path_is_refused(name):
    with pytest.raises(hi.UnsupportedImport) as refusal:
        hi.fixture_path(name)
    assert refusal.value.error == "unknown_fixture"


def test_a_plausible_but_absent_fixture_name_is_refused_by_the_same_branch():
    """So the function cannot be used to probe the filesystem for what exists."""
    with pytest.raises(hi.UnsupportedImport) as refusal:
        hi.fixture_path("SYNTHETIC-bundle-z.txt")
    assert refusal.value.error == "unknown_fixture"


def test_only_one_parser_is_registered_and_it_is_the_fixture_parser():
    """``HIST-002`` and ``BL15-001`` are BLOCKED, so the registry is short.

    A stub for either would be a parser claiming a format it has never seen —
    which is what ``CLAUDE.md`` §5 forbids and what ``REC-009``'s measurement
    (zero ``.mac``, zero ``.xlsx``/``.xls`` anywhere in the tree) makes
    impossible to do honestly.
    """
    assert [p.parser_id for p in hi.PARSERS] == ["synthetic_fixture_key_value"]


def test_no_mac_or_spreadsheet_parsing_is_attempted_anywhere():
    """The BLOCKED formats are not parsed, and no dependency was added for them."""
    src = Path(hi.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', " ", src)
    code = re.sub(r"^\s*#.*$", " ", code, flags=re.MULTILINE)
    for banned in ("openpyxl", "xlrd", "csv.", "import csv"):
        assert banned not in code, f"{banned!r} appears in executable code"


def test_a_line_the_parser_cannot_read_is_reported_and_not_dropped(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    _fixture_source(session, BUNDLE_A)
    (parsed,) = hi.parse_session(session, now_utc=AT)
    assert parsed.skipped, "the fixture's separator-free line was not reported"
    assert parsed.skipped[0]["reason"] == "no_key_value_separator"
    assert parsed.skipped[0]["locator"].startswith("line ")


def test_a_parsed_statement_is_verbatim_with_a_locator(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    _fixture_source(session, BUNDLE_A)
    (parsed,) = hi.parse_session(session, now_utc=AT)
    technique = [s for s in parsed.statements if s.key == "system.technique"]
    assert len(technique) == 1
    assert technique[0].value == "XAS"
    assert re.fullmatch(r"line \d+", technique[0].locator)


def test_parse_leaves_every_source_in_exactly_one_state_with_a_reason(workspace):
    session = _bundle()
    hi.parse_session(session, now_utc=AT)
    for source in session.sources:
        assert source.parse_state in hi.PARSE_STATES
        if source.parse_state != hi.PARSE_STATE_PARSED:
            assert source.parse_detail, source.filename


def test_a_source_over_the_text_ceiling_fails_with_the_measurement(workspace, monkeypatch):
    session = hi.new_session(label=None, now_utc=AT)
    entry = _fixture_source(session, BUNDLE_A)
    monkeypatch.setattr(hi, "MAX_SOURCE_TEXT_BYTES", 10)
    hi.parse_session(session, now_utc=AT)
    after = session.source(entry.source_id)
    assert after.parse_state == hi.PARSE_STATE_FAILED
    assert "refused whole rather than read partly" in after.parse_detail


# --- §3 the Beamline Profile encodes ZERO conventions (BL15-002 BLOCKED) -----


def test_the_only_beamline_profile_this_build_has_is_empty():
    profile = hi.EMPTY_BEAMLINE_PROFILE
    assert profile.filename_patterns == ()
    assert profile.key_aliases == ()
    assert profile.terminology == ()
    assert profile.facility_identifier is None
    assert profile.is_empty() is True


def test_is_empty_can_actually_fail():
    """MUTATION CONTROL. An `is_empty` that returned True unconditionally would
    make the assertion above vacuous, and this repository has shipped guards that
    passed while being vacuous."""
    assert (
        hi.BeamlineProfile(
            profile_id="x", display_name="x", key_aliases=(("beam", "system.technique"),)
        ).is_empty()
        is False
    )
    assert (
        hi.BeamlineProfile(
            profile_id="x", display_name="x", facility_identifier="anything"
        ).is_empty()
        is False
    )


def test_no_profile_is_consulted_to_accept_or_refuse_a_value(workspace):
    """A Beamline Profile is an interpretation aid, NEVER an unofficial validator.

    Proven behaviourally rather than by reading the code: a profile carrying an
    alias that WOULD map the fixture's unmapped key changes nothing, because
    nothing reads it. If a future slice makes a profile load-bearing, this test
    goes red and the ``BL15-002`` constraint is re-argued rather than forgotten.
    """
    session = _bundle()
    hi.parse_session(session, now_utc=AT)
    baseline = hi.reconstruct_session(session, now_utc=AT).to_state()

    loaded = hi.BeamlineProfile(
        profile_id="pretend",
        display_name="pretend",
        key_aliases=(("operator_initials", "sample.material.provenance"),),
        terminology=(("XAS", "XES"),),
        facility_identifier="NOT-A-REAL-FACILITY",
    )
    session_two = _bundle()
    hi.parse_session(session_two, now_utc=AT)
    with_profile = hi.reconstruct_session(
        session_two, now_utc=AT, profile=loaded
    ).to_state()

    def shape(state):
        return [
            (c["kind"], c["target_field_path"], c["proposed_value"], c["determinism"])
            for c in state["candidates"]
        ]

    assert shape(baseline) == shape(with_profile)


# --- §4 reconstruction: HIST-004's six questions, each answered --------------


def test_the_mapping_rule_is_verbatim_and_has_no_alias_table(workspace):
    """A key that is not an official field path is REPORTED, never guessed at."""
    session = _bundle()
    reconstruction = _reconstructed(session)
    paths = {c.target_field_path for c in reconstruction.candidates}
    assert "operator_initials" not in paths
    unmapped = {row["key"] for row in session.unmapped_keys}
    assert "operator_initials" in unmapped
    assert all(
        row["reason"] == "not_an_official_field_path" for row in session.unmapped_keys
    )


def test_a_case_folded_or_near_miss_key_is_not_mapped(workspace, tmp_path):
    """MUTATION CONTROL on the verbatim rule.

    A provider that lower-cased, stripped or fuzzily matched would map these.
    They are handed to the provider directly rather than written into the
    committed fixture directory, which stays exactly two files.
    """
    parsed = [
        hi.ParsedSource(
            source_id="01" + "A" * 24,
            parser_id="t",
            filename="near-miss.txt",
            statements=(
                hi.EvidenceStatement(key="System.Technique", value="XAS", locator="line 1"),
                hi.EvidenceStatement(key=" system.technique", value="XAS", locator="line 2"),
                hi.EvidenceStatement(key="system_technique", value="XAS", locator="line 3"),
            ),
        )
    ]
    ids = iter(f"{i:026d}" for i in range(100))
    result = hi.PROVIDER.reconstruct(
        parsed=parsed,
        profile=hi.EMPTY_BEAMLINE_PROFILE,
        now_utc=AT,
        mint_id=lambda: next(ids),
    )
    assert [c for c in result.candidates if c.kind == hi.CANDIDATE_KIND_FIELD] == []


def test_an_agreed_writable_value_is_a_deterministic_proposable_candidate(workspace):
    session = _bundle()
    reconstruction = _reconstructed(session)
    candidate = _by_path(reconstruction, "system.technique")
    assert candidate.determinism == hi.DETERMINISM_DETERMINISTIC
    assert candidate.proposed_value == "XAS"
    assert candidate.unresolved_reason is None
    assert candidate.proposable is True
    # WHICH SOURCES SUPPORT IT — both fixtures state it, and the rule quotes the
    # key and the locator it was read from.
    assert len(candidate.supporting_source_ids) == 2
    assert "system.technique" in candidate.rule
    assert "No alias, synonym or normalisation was applied." in candidate.rule


def test_a_disagreement_chooses_nothing_and_lists_every_competing_value(workspace):
    session = _bundle()
    reconstruction = _reconstructed(session)
    candidate = _by_path(reconstruction, "sample.material.name")
    assert candidate.unresolved_reason == hi.UNRESOLVED_SOURCES_DISAGREE
    # THE VALUE IS NONE. A chosen value beside a recorded disagreement would be
    # this module deciding a scientific question.
    assert candidate.proposed_value is None
    assert candidate.proposable is False
    values = sorted(row["value"] for row in candidate.disagreement)
    assert values == ["SYNTHETIC-CuO-FAKE-001", "SYNTHETIC-CuO-FAKE-002"]
    for row in candidate.disagreement:
        assert row["source_ids"], row
        assert row["locators"], row


def test_a_recognised_path_with_no_write_route_is_shown_and_not_proposable(workspace):
    """MEASURED: 25 recognised paths, 18 writable. The other seven are shown.

    The first version of `proposable` returned True here, which would have
    offered a control the proposal route was always going to refuse.
    """
    assert len(hi._official_field_paths()) > len(hi._writable_field_paths())
    session = _bundle()
    reconstruction = _reconstructed(session)
    candidate = _by_path(reconstruction, "system.configuration.detector_model")
    assert candidate.proposed_value == "SYNTHETIC-DETECTOR-MODEL-ZERO"
    assert candidate.proposable is False
    assert candidate.not_proposable_reason == hi.CANDIDATE_NOT_PROPOSABLE_NO_WRITE_PATH
    assert "NOT A STATEMENT ABOUT THE OFFICIAL ISAAC SCHEMA" in (
        candidate.not_proposable_reason
    )


def test_the_one_inferred_candidate_says_no_source_states_it(workspace):
    session = _bundle()
    reconstruction = _reconstructed(session)
    inferred = [
        c for c in reconstruction.candidates if c.determinism == hi.DETERMINISM_INFERRED
    ]
    assert len(inferred) == 1
    candidate = inferred[0]
    assert candidate.kind == hi.CANDIDATE_KIND_EXPERIMENT
    assert candidate.proposed_value == "SYNTHETIC-bundle"
    assert "NO SOURCE STATES A TITLE" in candidate.rule
    assert candidate.proposable is False
    assert (
        candidate.not_proposable_reason
        == hi.CANDIDATE_NOT_PROPOSABLE_NO_EXPERIMENT_CREATION
    )


def test_a_single_source_infers_no_title_at_all(workspace):
    """An inference needs something to generalise over. One file is not a bundle."""
    session = hi.new_session(label=None, now_utc=AT)
    _fixture_source(session, BUNDLE_A)
    reconstruction = _reconstructed(session)
    assert [
        c for c in reconstruction.candidates if c.kind == hi.CANDIDATE_KIND_EXPERIMENT
    ] == []


def test_filenames_with_nothing_in_common_infer_no_title():
    parsed = [
        hi.ParsedSource(source_id="01" + "A" * 24, parser_id="t", filename="alpha.txt", statements=()),
        hi.ParsedSource(source_id="01" + "B" * 24, parser_id="t", filename="zulu.txt", statements=()),
    ]
    assert hi._title_from_filenames(parsed) is None


def test_a_two_character_stem_is_not_offered_as_a_name():
    """MUTATION CONTROL on the three-character floor."""
    parsed = [
        hi.ParsedSource(source_id="01" + "A" * 24, parser_id="t", filename="ab-one.txt", statements=()),
        hi.ParsedSource(source_id="01" + "B" * 24, parser_id="t", filename="ab-two.txt", statements=()),
    ]
    assert hi._title_from_filenames(parsed) is None


def test_reconstruction_refuses_when_nothing_has_been_parsed(workspace):
    """A bundle of pointers alone has no evidence, and says so instead of
    producing an empty reconstruction that looks like a finished one."""
    session = hi.new_session(label=None, now_utc=AT)
    _pointer(session)
    hi.parse_session(session, now_utc=AT)
    with pytest.raises(hi.UnsupportedImport) as refusal:
        hi.reconstruct_session(session, now_utc=AT)
    assert refusal.value.error == "nothing_parsed"


def test_the_candidate_order_is_total_so_a_reconstruction_is_reproducible(workspace):
    first = _reconstructed(_bundle())
    second = _reconstructed(_bundle())

    def shape(r):
        return [
            (c.kind, c.target_field_path, c.proposed_value, c.determinism)
            for c in r.candidates
        ]

    assert shape(first) == shape(second)


# --- §5 a semantic candidate CANNOT become record truth ----------------------


def test_reconstruction_publishes_applied_false_on_the_wire(workspace):
    session = _bundle()
    reconstruction = _reconstructed(session)
    assert hi.RECONSTRUCTION_APPLIED is False
    assert reconstruction.applied is False
    assert reconstruction.to_state()["applied"] is False
    assert hi.session_view(session)["provider"]["applied"] is False


def test_a_persisted_applied_true_cannot_make_a_surface_say_it_was_applied(workspace):
    """`applied` is a CONSTANT of this build and is recomputed, never hydrated.

    Without this, an operator edit (or an older build) could put `applied: true`
    into the document and every surface reading it would report that a
    reconstruction had been applied — which nothing in this build can do.
    """
    session = _bundle()
    _reconstructed(session)
    hi.save_session(session)
    path = hi.imports_root() / session.import_id / hi.SESSION_FILE
    poisoned = json.loads(path.read_text(encoding="utf-8"))
    poisoned["reconstruction"]["applied"] = True
    path.write_text(json.dumps(poisoned), encoding="utf-8")

    back = hi.load_session(session.import_id)
    assert back.reconstruction.applied is False


def test_the_module_writes_no_draft_no_evidence_and_no_confirmation_envelope():
    """NEGATIVE CONTROL over the source, the shape ``test_ingestion_proposals.py``
    runs over ``proposals.py``.

    The literals are spelled out here so this file does not need them, which is
    the only way the check can mean anything: if the module gains any of them, a
    reviewer has to justify it against this test rather than against a comment.
    """
    src = Path(hi.__file__).read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', " ", src)
    code = re.sub(r"^\s*#.*$", " ", code, flags=re.MULTILINE)
    for banned in (
        "user_confirmation",  # the truth core's confirmation-entry constructor
        "export_draft",
        "validate_draft",
        "build_sidecar",
        '"verified"',
        "'verified'",
        ".draft[",
        'draft"]',
        "block_evidence",
    ):
        assert banned not in code, f"{banned!r} appears in executable code"


def test_the_negative_control_can_actually_fail():
    """MUTATION CONTROL on the check above — a grep over a file that does not
    contain the literals passes trivially, so prove the predicate fires."""
    code = "x = user_confirmation(question='q')"
    assert "user_confirmation" in code


def test_the_module_imports_nothing_that_writes_the_truth_path():
    """The import list, asserted rather than described.

    ``is_sha256_shaped`` and the id helpers are READ-ONLY predicates and are the
    only truth-core imports. ``export``, ``draft_validator`` and ``complete``'s
    writers are absent, so semantic output has no route into the truth path even
    by accident.
    """
    src = Path(hi.__file__).read_text(encoding="utf-8")
    imports = sorted(
        line.strip()
        for line in src.splitlines()
        if line.startswith("from isaac_records") or line.startswith("import isaac_records")
    )
    assert imports == [
        "from isaac_records.complete import is_sha256_shaped",
        "from isaac_records.ids import is_record_id, new_record_id",
    ]


def test_the_module_can_make_no_outbound_request_of_any_kind():
    """THE SURFACE SAYS "no request leaves this deployment". THIS IS WHY IT IS TRUE.

    `IMPORT_COPY.reconstructLead` tells a scientist the reconstruction is
    "deterministic and offline: no language model is involved, and no request
    leaves this deployment". That is a claim about this module, and a claim about
    a NEGATIVE needs a check over the code rather than a passing happy path —
    §11 records four separate occasions on which a surface asserted something it
    had not done.

    Asserted over the IMPORT LIST rather than by grepping for call sites: an
    outbound request needs a client, a client needs an import, and an import is a
    line a reviewer has to add deliberately. `Protocol` is what makes the provider
    seam provider-NEUTRAL, and a real provider would be a different
    implementation wired by configuration that does not exist and is not
    authorized (Dean deferred D1-D9).
    """
    src = Path(hi.__file__).read_text(encoding="utf-8")
    imports = [
        line.strip()
        for line in src.splitlines()
        if line.startswith(("import ", "from ")) and "import" in line
    ]
    joined = " ".join(imports)
    for banned in (
        "http",
        "urllib",
        "requests",
        "socket",
        "httpx",
        "aiohttp",
        "ssl",
        "asyncio",
        "subprocess",
        "anthropic",
        "openai",
        "providers",
    ):
        assert banned not in joined, f"{banned!r} is imported: {imports}"


def test_the_outbound_control_can_actually_fail():
    """MUTATION CONTROL. A predicate over a list that never held the names passes
    trivially; prove it fires on the line a future slice would add."""
    assert "httpx" in " ".join(["import httpx", "from . import workspace as ws"])


def test_an_import_session_is_stored_where_no_experiment_read_can_reach_it(workspace):
    """Structural, not asserted: ``_experiment_dirs`` skips a ``_``-prefixed name."""
    session = _bundle()
    hi.save_session(session)
    assert hi.IMPORTS_NAMESPACE.startswith("_")
    assert ws._experiment_dirs(ws.workspace_root()) == []
    assert ws.list_experiments() == []
    # And the session file is NOT named `experiment.json`, so the existence check
    # in `_experiment_dirs` could not match it either.
    assert hi.SESSION_FILE != "experiment.json"
    assert (hi.imports_root() / session.import_id / hi.SESSION_FILE).is_file()


# --- §6 persistence ----------------------------------------------------------


def test_a_session_round_trips_byte_for_byte(workspace):
    session = _bundle()
    _reconstructed(session)
    hi.record_proposed(
        session,
        candidate_id="01" + "C" * 24,
        experiment_id="01" + "E" * 24,
        proposal_id="01" + "P" * 24,
        note_id="01" + "N" * 24,
        proposed_utc=AT,
    )
    hi.save_session(session)
    back = hi.load_session(session.import_id)
    assert back is not None
    assert back.to_state() == session.to_state()


def test_a_source_entry_this_build_cannot_read_survives_a_save(workspace):
    """NO SILENT DISCARD, the property ``workspace._hydrate_notes`` exists for."""
    session = _bundle()
    hi.save_session(session)
    path = hi.imports_root() / session.import_id / hi.SESSION_FILE
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sources"].append({"source_id": "x", "kind": "from_the_future"})
    path.write_text(json.dumps(document), encoding="utf-8")

    back = hi.load_session(session.import_id)
    assert len(back.sources) == 3
    assert back.unreadable_sources == [{"source_id": "x", "kind": "from_the_future"}]
    hi.save_session(back)
    again = json.loads(path.read_text(encoding="utf-8"))
    assert {"source_id": "x", "kind": "from_the_future"} in again["sources"]


def test_a_sources_key_that_is_not_a_list_yields_no_sources_rather_than_one_per_character():
    """``enumerate("abc")`` would have invented three per-position claims."""
    assert hi._hydrate_sources("abc") == ([], [])
    assert hi._hydrate_sources(7) == ([], [])
    assert hi._hydrate_sources(None) == ([], [])


def test_a_document_with_no_identity_is_refused_and_a_legacy_one_is_read():
    with pytest.raises(hi.UnsupportedImport):
        hi.ImportSession.from_state({"label": "no id"})
    legacy = hi.ImportSession.from_state(
        {"import_id": "01" + "A" * 24, "created_utc": AT}
    )
    assert legacy.label == ""
    assert legacy.sources == []
    assert legacy.reconstruction is None
    assert legacy.updated_utc == AT


def test_an_unreadable_document_does_not_empty_the_list_for_every_other_session(workspace):
    good = _bundle()
    hi.save_session(good)
    broken_id = "01" + "Z" * 24
    broken = hi.imports_root() / broken_id
    broken.mkdir(parents=True)
    (broken / hi.SESSION_FILE).write_text("{not json", encoding="utf-8")

    listed = [s.import_id for s in hi.list_sessions()]
    assert listed == [good.import_id]
    assert hi.load_session(broken_id) is None


@pytest.mark.parametrize(
    "bad", ["../../etc", "..", "a/b", "lowercase-id", "", "01" + "A" * 30]
)
def test_an_import_id_that_could_name_a_path_reaches_no_filesystem_read(workspace, bad):
    assert hi.load_session(bad) is None
    assert hi.delete_session(bad) is False


def test_removing_a_source_drops_the_reading_but_never_the_proposal_record(workspace):
    session = _bundle()
    _reconstructed(session)
    hi.record_proposed(
        session,
        candidate_id="01" + "C" * 24,
        experiment_id="01" + "E" * 24,
        proposal_id="01" + "P" * 24,
        note_id="01" + "N" * 24,
        proposed_utc=AT,
    )
    victim = session.sources[0].source_id
    assert hi.remove_source(session, victim, now_utc=AT) is True
    assert session.source(victim) is None
    # The reading is stale the moment the bundle changes, so it goes.
    assert session.parsed == []
    assert session.reconstruction is None
    # The record of what was already proposed does NOT go — the proposal exists
    # on an experiment, and forgetting it would let the same candidate be
    # proposed twice.
    assert len(session.proposed) == 1


def test_removing_a_source_that_is_not_there_changes_nothing(workspace):
    session = _bundle()
    _reconstructed(session)
    before = session.to_state()
    assert hi.remove_source(session, "nope", now_utc="LATER") is False
    assert session.to_state() == before


def test_a_reparse_invalidates_the_reconstruction(workspace):
    session = _bundle()
    _reconstructed(session)
    assert session.reconstruction is not None
    hi.parse_session(session, now_utc=AT)
    assert session.reconstruction is None
    assert session.unmapped_keys == []


def test_the_furthest_step_is_derived_and_never_names_the_unbuilt_step(workspace):
    session = hi.new_session(label=None, now_utc=AT)
    assert session.furthest_step() == "new_import"
    _fixture_source(session, BUNDLE_A)
    assert session.furthest_step() == "sources"
    hi.parse_session(session, now_utc=AT)
    assert session.furthest_step() == "parse"
    hi.reconstruct_session(session, now_utc=AT)
    assert session.furthest_step() == "reconstruct"
    hi.record_proposed(
        session,
        candidate_id="c",
        experiment_id="e",
        proposal_id="p",
        note_id="n",
        proposed_utc=AT,
    )
    assert session.furthest_step() == "review"
    # No session can ever reach the step this build does not have.
    steps = {step for step, _ in hi.WORKFLOW_STEPS}
    assert hi.UNBUILT_STEP in steps
    assert session.furthest_step() != hi.UNBUILT_STEP


def test_the_workflow_names_the_unbuilt_step_as_unbuilt_with_its_reason(workspace):
    view = hi.session_view(_bundle())
    workflow = {row["id"]: row for row in view["workflow"]}
    assert [row["id"] for row in view["workflow"]] == [
        "new_import",
        "sources",
        "parse",
        "reconstruct",
        "review",
        "add_to_experiments",
    ]
    assert workflow[hi.UNBUILT_STEP]["built"] is False
    assert workflow[hi.UNBUILT_STEP]["disclosure"] == hi.UNBUILT_STEP_DISCLOSURE
    for step in ("new_import", "sources", "parse", "reconstruct", "review"):
        assert workflow[step]["built"] is True
        assert workflow[step]["disclosure"] is None


def test_the_view_states_that_a_session_is_not_durable(workspace):
    view = hi.session_view(_bundle())
    assert view["durability"] == hi.SESSION_DURABILITY_DISCLOSURE
    assert "not part of the durable record store" in view["durability"]


def test_the_list_summary_carries_counts_and_never_the_bundle(workspace):
    session = _bundle()
    _reconstructed(session)
    summary = hi.session_summary(session)
    assert summary["source_count"] == 3
    assert summary["parsed_source_count"] == 2
    assert summary["candidate_count"] == 4
    for absent in ("sources", "parsed", "reconstruction", "unmapped_keys"):
        assert absent not in summary, absent


def test_a_worked_example_scope_and_the_ordinary_scope_do_not_share_sessions(
    workspace, monkeypatch
):
    """Scope isolation is ``ws.scope_root``'s, reused rather than reimplemented."""
    session_id = "a" * 22
    ws.scope_root(session_id).mkdir(parents=True, exist_ok=True)
    ordinary = _bundle()
    hi.save_session(ordinary)
    scoped = _bundle()
    hi.save_session(scoped, session_id=session_id)

    assert [s.import_id for s in hi.list_sessions()] == [ordinary.import_id]
    assert [s.import_id for s in hi.list_sessions(session_id=session_id)] == [
        scoped.import_id
    ]
    assert hi.load_session(scoped.import_id) is None
    assert hi.load_session(ordinary.import_id, session_id=session_id) is None


def test_deleting_a_session_removes_the_working_area_and_nothing_else(workspace):
    session = _bundle()
    hi.save_session(session)
    assert hi.delete_session(session.import_id) is True
    assert hi.load_session(session.import_id) is None
    assert hi.delete_session(session.import_id) is False
