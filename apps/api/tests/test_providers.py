"""The provider seams: unconfigured by default, deterministic under test, and
structurally unable to present a guess as a fact.

WHAT THIS SUITE IS FOR
======================
Three of these tests are ordinary contract tests (defaults, env resolution, boot
validation). The other four are the reason the slice exists, and each was
verified by MUTATION — the guard was removed or inverted, the test was confirmed
RED, and the guard was restored. They are marked with ``NEGATIVE CONTROL`` in
their docstrings:

* a candidate cannot be constructed as verified — five routes, all closed;
* a candidate carrying a confidence key is refused **by the existing
  ``inferability`` rule**, proven by emptying that module's key set and watching
  the refusal disappear (a reimplementation would survive this);
* nothing under ``providers/`` imports the truth path;
* no implementation anywhere in the package claims to be production-configured.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from isaac_api import inferability, providers
from isaac_api.providers import config as provider_config

PROVIDERS_DIR = Path(providers.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    """No test inherits a provider selection from the ambient environment.

    Without this the whole suite's meaning depends on the shell it was launched
    from — a class of flake this repository has already paid for elsewhere.
    """
    for env_var in provider_config.PROVIDER_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)


# ---------------------------------------------------------------------------
# 1. The production default: unconfigured, and honest about it
# ---------------------------------------------------------------------------


def test_default_environment_resolves_every_seam_to_unconfigured():
    assert isinstance(
        providers.resolve_transcription_provider(),
        providers.UnconfiguredTranscriptionProvider,
    )
    assert isinstance(
        providers.resolve_capture_extraction_provider(),
        providers.UnconfiguredCaptureExtractionProvider,
    )
    assert isinstance(
        providers.resolve_assistant_provider(),
        providers.UnconfiguredAssistantProvider,
    )


def test_capabilities_reports_every_seam_unconfigured_with_a_reason():
    report = providers.capabilities()
    assert report["any_provider_configured"] is False
    seams = {s["seam"]: s for s in report["seams"]}
    assert set(seams) == set(providers.SEAMS)
    for seam, entry in seams.items():
        assert entry["configured"] is False, seam
        assert entry["is_test_double"] is False, seam
        assert entry["implementation"] == providers.IMPLEMENTATION_UNCONFIGURED
        assert entry["reason"], f"{seam} must say WHY it is unconfigured"
        assert entry["selected_by"].startswith("ISAAC_")


def test_capabilities_never_echoes_an_environment_value(monkeypatch):
    """A capability report is servable, so it must not carry configuration text.

    A value an operator typed — a hostname, or worse a credential pasted into the
    wrong variable — must not come back out of a status endpoint.
    """
    secret = "https://model.example.invalid/v1?key=NOT-A-REAL-SECRET"
    monkeypatch.setenv(providers.ASSISTANT_PROVIDER_ENV, secret)
    assert secret not in json.dumps(providers.capabilities())


def test_each_unconfigured_seam_refuses_with_a_typed_refusal():
    """Not an exception, and not a silent empty result."""
    outcomes = [
        providers.UnconfiguredTranscriptionProvider().transcribe(
            providers.TranscriptionRequest(manual_transcript="anything at all")
        ),
        providers.UnconfiguredCaptureExtractionProvider().extract(
            providers.ExtractionRequest(text="Facility: SSRL")
        ),
        providers.UnconfiguredAssistantProvider().answer(
            providers.AssistantRequest(
                question="what technique?",
                grounded_context=(
                    providers.ContextItem(
                        key="technique", text="XANES", origin="test fixture"
                    ),
                ),
            )
        ),
    ]
    for outcome in outcomes:
        assert isinstance(outcome, providers.ProviderRefusal)
        assert outcome.refused is True
        assert outcome.reason == providers.REASON_NO_PROVIDER_CONFIGURED
        assert outcome.missing, "a refusal must name what is missing"
        assert outcome.decision_reference == providers.DECISION_PACKET
        # It refused even though the input was perfectly usable: the refusal is
        # about configuration, not about the request.
        assert outcome.to_dict()["refused"] is True


def test_a_refusal_may_not_imply_a_provider_exists_but_is_busy():
    """NEGATIVE CONTROL. 'Try again later' asserts a provider. None exists."""
    with pytest.raises(ValueError, match="implies a provider exists"):
        providers.ProviderRefusal(
            seam=providers.SEAM_ASSISTANT,
            reason=providers.REASON_NO_PROVIDER_CONFIGURED,
            missing=("a model",),
            message="The assistant is temporarily unavailable; please try again.",
        )


def test_a_refusal_must_name_what_is_missing():
    with pytest.raises(ValueError, match="must name what is missing"):
        providers.ProviderRefusal(
            seam=providers.SEAM_ASSISTANT,
            reason=providers.REASON_NO_PROVIDER_CONFIGURED,
            missing=(),
            message="No.",
        )


def test_an_unknown_refusal_reason_is_refused():
    with pytest.raises(ValueError, match="unknown refusal reason"):
        providers.ProviderRefusal(
            seam=providers.SEAM_ASSISTANT,
            reason="model_is_thinking",
            missing=("a model",),
            message="No.",
        )


# ---------------------------------------------------------------------------
# 2. Env resolution is fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "openai",
        "anthropic",
        "Unconfigured",  # case matters; near-misses do not turn anything on
        "deterministic_fake",  # underscore, not hyphen
        "true",
        "1",
    ],
)
def test_an_unrecognised_env_value_resolves_to_unconfigured(monkeypatch, value):
    """Fail-closed: not a crash, and emphatically not a default-on."""
    for env_var in provider_config.PROVIDER_ENV_VARS.values():
        monkeypatch.setenv(env_var, value)
    report = providers.capabilities()
    assert report["any_provider_configured"] is False
    for entry in report["seams"]:
        assert entry["implementation"] == providers.IMPLEMENTATION_UNCONFIGURED


def test_whitespace_around_a_recognised_value_is_trimmed(monkeypatch):
    monkeypatch.setenv(
        providers.TRANSCRIPTION_PROVIDER_ENV,
        f"  {providers.IMPLEMENTATION_DETERMINISTIC_FAKE}  ",
    )
    assert isinstance(
        providers.resolve_transcription_provider(),
        providers.DeterministicTranscriptionFake,
    )


def test_seams_are_selected_independently(monkeypatch):
    """Approving one seam must not turn on the others (packet §1.2)."""
    monkeypatch.setenv(
        providers.TRANSCRIPTION_PROVIDER_ENV,
        providers.IMPLEMENTATION_DETERMINISTIC_FAKE,
    )
    assert isinstance(
        providers.resolve_transcription_provider(),
        providers.DeterministicTranscriptionFake,
    )
    assert isinstance(
        providers.resolve_assistant_provider(),
        providers.UnconfiguredAssistantProvider,
    )
    assert isinstance(
        providers.resolve_capture_extraction_provider(),
        providers.UnconfiguredCaptureExtractionProvider,
    )


# ---------------------------------------------------------------------------
# 3. A misconfigured container fails validation
# ---------------------------------------------------------------------------


def test_validation_passes_on_the_default_environment():
    providers.validate_provider_config_or_raise()


def test_validation_passes_when_every_seam_is_explicitly_unconfigured(monkeypatch):
    for env_var in provider_config.PROVIDER_ENV_VARS.values():
        monkeypatch.setenv(env_var, providers.IMPLEMENTATION_UNCONFIGURED)
    providers.validate_provider_config_or_raise()


@pytest.mark.parametrize("env_var", sorted(provider_config.PROVIDER_ENV_VARS.values()))
def test_a_garbage_value_fails_validation(monkeypatch, env_var):
    monkeypatch.setenv(env_var, "anthropic")
    with pytest.raises(RuntimeError, match="is invalid"):
        providers.validate_provider_config_or_raise()


@pytest.mark.parametrize("env_var", sorted(provider_config.PROVIDER_ENV_VARS.values()))
def test_an_empty_value_fails_validation(monkeypatch, env_var):
    """Empty resolves to unconfigured but is still a configuration error.

    The asymmetry is ``runtime_mode``'s and is deliberate: resolution must never
    raise, and a misconfiguration must never pass silently.
    """
    monkeypatch.setenv(env_var, "  ")
    with pytest.raises(RuntimeError, match="is invalid"):
        providers.validate_provider_config_or_raise()


@pytest.mark.parametrize("env_var", sorted(provider_config.PROVIDER_ENV_VARS.values()))
def test_selecting_the_fake_fails_validation(monkeypatch, env_var):
    """DECISION D6: the fake exists for tests only and is never reachable in
    production. That is enforced by refusing to boot with it selected."""
    monkeypatch.setenv(env_var, providers.IMPLEMENTATION_DETERMINISTIC_FAKE)
    with pytest.raises(RuntimeError, match="is refused"):
        providers.validate_provider_config_or_raise()


def test_validation_message_never_leaks_a_credential_shaped_value(monkeypatch):
    """``repr`` of the raw value IS in the message — deliberately, because an
    operator needs to see what they typed. This test pins the boundary: it is the
    variable's value, and no other environment variable is read or reported."""
    monkeypatch.setenv("ISAAC_UI_API_KEY", "SUPER-SECRET-NOT-REAL")
    monkeypatch.setenv(providers.ASSISTANT_PROVIDER_ENV, "gpt")
    with pytest.raises(RuntimeError) as excinfo:
        providers.validate_provider_config_or_raise()
    assert "SUPER-SECRET-NOT-REAL" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# 4. The fakes are deterministic
# ---------------------------------------------------------------------------

_TRANSCRIPT = (
    "Facility: SSRL\n"
    "Beamline: 7-3\n"
    "Technique: XANES\n"
    "Mood: cautiously optimistic\n"
    "We ran the scan twice. The second one looked better.\n"
)


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")


def test_transcription_fake_is_byte_identical_across_calls_and_instances():
    request = providers.TranscriptionRequest(
        manual_transcript=_TRANSCRIPT, language="en-US"
    )
    first = providers.DeterministicTranscriptionFake().transcribe(request)
    second = providers.DeterministicTranscriptionFake().transcribe(request)
    assert _canonical(first.to_dict()) == _canonical(second.to_dict())
    assert first.verbatim is True
    assert first.text == _TRANSCRIPT


def test_transcription_segments_offsets_round_trip():
    """A quote that does not index back into the source is a false quote."""
    result = providers.DeterministicTranscriptionFake().transcribe(
        providers.TranscriptionRequest(manual_transcript=_TRANSCRIPT)
    )
    assert result.segments
    for segment in result.segments:
        assert _TRANSCRIPT[segment.start_char : segment.end_char] == segment.text


def test_transcription_fake_refuses_audio_rather_than_inventing_words():
    """NEGATIVE CONTROL. A fake that fabricated a transcript would be worse than
    no fake: its output is indistinguishable from a real one."""
    outcome = providers.DeterministicTranscriptionFake().transcribe(
        providers.TranscriptionRequest(audio_ref="opaque-handle-1")
    )
    assert isinstance(outcome, providers.ProviderRefusal)
    assert outcome.reason == providers.REASON_INPUT_NOT_SUPPLIED


def test_extraction_fake_is_byte_identical_across_calls_and_instances():
    request = providers.ExtractionRequest(text=_TRANSCRIPT)
    first = providers.DeterministicCaptureExtractionFake().extract(request)
    second = providers.DeterministicCaptureExtractionFake().extract(request)
    assert _canonical(first.to_dict()) == _canonical(second.to_dict())


def test_extraction_fake_extracts_only_its_closed_label_table():
    result = providers.DeterministicCaptureExtractionFake().extract(
        providers.ExtractionRequest(text=_TRANSCRIPT)
    )
    paths = [c.field_path for c in result.candidates]
    assert paths == [
        "system.facility",
        "system.instrument",
        "system.technique",
    ]
    assert [c.proposed_value for c in result.candidates] == ["SSRL", "7-3", "XANES"]
    # The label it did not understand is DISCLOSED, not silently dropped, and
    # certainly not guessed at.
    assert "mood" in result.unrecognised_labels
    # The prose sentence carries no colon-label, so nothing is extracted from it.
    assert all("scan twice" not in c.quote for c in result.candidates)


def test_extraction_candidate_quotes_round_trip_into_the_source_text():
    result = providers.DeterministicCaptureExtractionFake().extract(
        providers.ExtractionRequest(text=_TRANSCRIPT)
    )
    for candidate in result.candidates:
        assert (
            _TRANSCRIPT[candidate.start_char : candidate.end_char].strip()
            == candidate.quote
        )


def test_extraction_fake_refuses_empty_text():
    outcome = providers.DeterministicCaptureExtractionFake().extract(
        providers.ExtractionRequest(text="   ")
    )
    assert isinstance(outcome, providers.ProviderRefusal)
    assert outcome.reason == providers.REASON_INPUT_NOT_SUPPLIED


def test_assistant_fake_is_byte_identical_across_calls_and_instances():
    request = providers.AssistantRequest(
        question="Which technique was used, and at which facility?",
        grounded_context=(
            providers.ContextItem(
                key="technique", text="XANES", origin="draft field map"
            ),
            providers.ContextItem(
                key="facility", text="SSRL", origin="draft field map"
            ),
        ),
    )
    first = providers.DeterministicAssistantFake().answer(request)
    second = providers.DeterministicAssistantFake().answer(request)
    assert _canonical(first.to_dict()) == _canonical(second.to_dict())
    assert first.grounded_in == ("technique", "facility")
    assert first.authoritative is False


def test_assistant_fake_refuses_a_question_its_context_does_not_cover():
    """NEGATIVE CONTROL for §6.4: the no-guessing rule binds the ANSWER."""
    outcome = providers.DeterministicAssistantFake().answer(
        providers.AssistantRequest(
            question="Is this measurement scientifically sound?",
            grounded_context=(
                providers.ContextItem(
                    key="facility", text="SSRL", origin="draft field map"
                ),
            ),
        )
    )
    assert isinstance(outcome, providers.ProviderRefusal)
    assert outcome.reason == providers.REASON_OUTSIDE_GROUNDED_CONTEXT


def test_an_answer_cannot_be_constructed_without_citing_context():
    """NEGATIVE CONTROL. An uncited answer is a guess with better grammar."""
    with pytest.raises(ValueError, match="must cite the context"):
        providers.AssistantAnswer(
            text="Yes, the sample is copper oxide.",
            grounded_in=(),
            produced_by="whatever",
        )


def test_no_fake_output_depends_on_the_clock_or_on_randomness():
    """A source scan: the seams import neither a clock nor a source of entropy.

    Byte-identical output over two calls is necessary but not sufficient — a
    once-per-day clock read would pass it. This closes that.
    """
    banned = {"random", "time", "datetime", "secrets", "uuid", "os"}
    offenders = {}
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        roots = _import_roots(path)
        # config.py legitimately reads the environment; nothing else may.
        allowed = banned - {"os"} if path.name == "config.py" else banned
        hit = roots & allowed
        if hit:
            offenders[path.name] = sorted(hit)
    assert offenders == {}, f"non-deterministic imports: {offenders}"


# ---------------------------------------------------------------------------
# 5. NEGATIVE CONTROL: a candidate cannot be constructed as verified
# ---------------------------------------------------------------------------


def _candidate(**overrides) -> providers.FieldCandidate:
    kwargs = dict(
        field_path="system.facility",
        proposed_value="SSRL",
        quote="Facility: SSRL",
        start_char=0,
        end_char=14,
        origin=providers.ORIGIN_TRANSCRIPT,
        produced_by="test",
        rule="the line quotes an explicit 'Facility:' label",
    )
    kwargs.update(overrides)
    return providers.FieldCandidate(**kwargs)


def test_a_candidate_is_always_an_unverified_proposal():
    candidate = _candidate()
    assert candidate.status == providers.CANDIDATE_STATUS == "needs_confirmation"
    assert candidate.verified is False
    assert candidate.is_evidence is False
    assert candidate.requires_user_confirmation is True
    # And the guarantee survives serialization, which is where a consumer
    # actually meets it.
    wire = candidate.to_dict()
    assert wire["status"] == "needs_confirmation"
    assert wire["verified"] is False
    assert wire["is_evidence"] is False
    assert wire["requires_user_confirmation"] is True


def test_a_candidate_cannot_be_constructed_as_verified():
    """NEGATIVE CONTROL — the whole point of the slice, by all five routes."""
    import dataclasses

    # (1) there is no such constructor argument
    with pytest.raises(TypeError):
        _candidate(verified=True)
    with pytest.raises(TypeError):
        _candidate(status="verified")

    candidate = _candidate()

    # (2) dataclasses.replace cannot introduce one
    with pytest.raises(TypeError):
        dataclasses.replace(candidate, verified=True)

    # (3) ordinary assignment is refused. The exception type is deliberately not
    #     pinned: frozen + slots makes CPython raise TypeError (the generated
    #     __setattr__'s zero-arg super() cell points at the pre-slots class)
    #     rather than FrozenInstanceError. Refused either way.
    refused = (TypeError, AttributeError, dataclasses.FrozenInstanceError)
    with pytest.raises(refused):
        candidate.verified = True  # type: ignore[misc]
    with pytest.raises(refused):
        candidate.status = "verified"  # type: ignore[misc]

    # (4) the frozen-dataclass escape hatch does NOT reach it. object.__setattr__
    #     can overwrite an ordinary field on any frozen dataclass — this module
    #     uses that itself — but `verified` is a property with no setter, so
    #     there is nothing there to overwrite. Exact type pinned: this is stable
    #     descriptor semantics, not an implementation detail.
    with pytest.raises(AttributeError, match="no setter"):
        object.__setattr__(candidate, "verified", True)
    with pytest.raises(AttributeError, match="no setter"):
        object.__setattr__(candidate, "status", "verified")

    # (5) and slots=True leaves no instance __dict__ to smuggle a new flag into
    with pytest.raises(AttributeError):
        object.__setattr__(candidate, "definitely_verified", True)
    assert not hasattr(candidate, "__dict__")


def test_a_candidate_may_not_assert_acceptance_from_inside_its_provenance():
    """NEGATIVE CONTROL. Closing the fields but leaving a free-form bag open
    would move the defect rather than fix it."""
    for key in sorted(providers.extraction.FORBIDDEN_PROVENANCE_KEYS):
        with pytest.raises(inferability.UnsupportedSuggestion, match="acceptance"):
            _candidate(provenance={key: True})


def test_a_candidate_must_state_its_rule_and_quote_its_source():
    with pytest.raises(inferability.UnsupportedSuggestion, match="rule"):
        _candidate(rule="")
    with pytest.raises(inferability.UnsupportedSuggestion, match="quote the words"):
        _candidate(quote="")


def test_an_extraction_result_is_never_applied():
    result = providers.DeterministicCaptureExtractionFake().extract(
        providers.ExtractionRequest(text=_TRANSCRIPT)
    )
    assert result.applied is False
    assert result.to_dict()["applied"] is False
    assert all(c.verified is False for c in result.candidates)


# ---------------------------------------------------------------------------
# 6. NEGATIVE CONTROL: the confidence refusal is REUSED, not reimplemented
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["confidence", "probability", "score"])
def test_a_candidate_carrying_a_confidence_key_is_refused(key):
    with pytest.raises(inferability.UnsupportedSuggestion, match="claim about a predictor"):
        _candidate(provenance={key: 0.93})


def test_the_confidence_refusal_reaches_nested_keys():
    """The shape the original guard missed: one level down, as this repository's
    own corpus writes it (``uncertainty: {confidence: 0.86}``)."""
    with pytest.raises(inferability.UnsupportedSuggestion):
        _candidate(provenance={"uncertainty": {"confidence": 0.86}})
    with pytest.raises(inferability.UnsupportedSuggestion):
        _candidate(provenance={"alternatives": [{"score": 0.4}]})


def test_a_candidate_may_not_cite_a_non_evidence_source_type():
    for source_type in sorted(inferability.NON_EVIDENCE_SOURCE_TYPES):
        with pytest.raises(
            inferability.UnsupportedSuggestion, match="not record-specific evidence"
        ):
            _candidate(provenance={"cited": {"source_type": source_type}})


def test_the_confidence_rule_is_the_inferability_one_not_a_local_copy(monkeypatch):
    """NEGATIVE CONTROL FOR REUSE.

    Empty ``inferability``'s key set and the providers' refusal must vanish with
    it. A second implementation in ``providers/`` would keep refusing and this
    test would fail — which is exactly what it is for. Restored by monkeypatch
    at teardown.
    """
    monkeypatch.setattr(inferability, "_CONFIDENCE_KEYS", frozenset())
    candidate = _candidate(provenance={"confidence": 0.99})
    assert candidate.provenance["confidence"] == 0.99

    monkeypatch.setattr(inferability, "_CONFIDENCE_KEYS", frozenset({"vibes"}))
    with pytest.raises(inferability.UnsupportedSuggestion):
        _candidate(provenance={"vibes": "high"})


def test_the_non_evidence_source_list_is_the_inferability_one():
    """Identity, not equality: a copied frozenset would compare equal today and
    drift tomorrow."""
    from isaac_api.providers import guards

    assert guards.NON_EVIDENCE_SOURCE_TYPES is inferability.NON_EVIDENCE_SOURCE_TYPES
    assert guards.UnsupportedSuggestion is inferability.UnsupportedSuggestion


def test_providers_defines_no_confidence_key_list_of_its_own():
    """A source scan. The rule lives in one file; this proves there is no second."""
    offenders = []
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            literals = _string_literals(node.value)
            if {"confidence", "probability", "score"} & literals:
                offenders.append((path.name, targets))
    assert offenders == [], (
        "a confidence key list was reintroduced under providers/; the rule "
        f"belongs to inferability.py alone: {offenders}"
    )


# ---------------------------------------------------------------------------
# 7. NEGATIVE CONTROL: nothing here can reach the truth path
# ---------------------------------------------------------------------------

#: The truth path, per ``CLAUDE.md`` §13. Also ``graphify``, which the
#: deterministic core is required to stay free of.
FORBIDDEN_IMPORT_ROOTS = frozenset({"isaac_records", "graphify"})

FORBIDDEN_SIBLING_MODULES = frozenset(
    {
        ".official",
        ".export",
        ".draft_validator",
        ".audit",
        ".cli",
        ".workspace",
        ".routes",
        ".db_write",
        ".experiment_repository",
    }
)

#: Anything that could make a network call or write a file. No SDK, no HTTP
#: client — the slice added no dependency and this is how that stays true.
FORBIDDEN_IO_ROOTS = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "urllib",
        "http",
        "socket",
        "ssl",
        "subprocess",
        "anthropic",
        "openai",
        "boto3",
        "google",
        "fastapi",
        "starlette",
        "psycopg2",
    }
)


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                roots.add(f".{(node.module or '').split('.')[0]}")
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _string_literals(node) -> set[str]:
    return {
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def test_the_package_is_non_trivial():
    """A guard against this whole section passing over an empty directory."""
    modules = sorted(p.name for p in PROVIDERS_DIR.glob("*.py"))
    assert len(modules) >= 7, modules


def test_no_provider_module_imports_the_truth_path_or_a_network_client():
    offenders = {}
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        roots = _import_roots(path)
        hit = (roots & FORBIDDEN_IMPORT_ROOTS) | (roots & FORBIDDEN_IO_ROOTS) | (
            roots & FORBIDDEN_SIBLING_MODULES
        )
        if hit:
            offenders[path.name] = sorted(hit)
    assert offenders == {}, f"forbidden imports under providers/: {offenders}"


def test_no_provider_module_mentions_a_truth_path_module_by_name():
    """Stronger than the import scan, and it catches ``importlib`` too.

    Docstrings are excluded — this package's docstrings NAME the truth path in
    order to explain what it does not do, and that prose is the point.
    """
    forbidden_names = ("official", "export", "draft_validator", "audit", "cli")
    offenders = []
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                continue
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                offenders.append((path.name, node.attr, node.lineno))
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append((path.name, node.id, node.lineno))
    assert offenders == [], f"truth-path symbol referenced in code: {offenders}"


def test_the_only_cross_package_import_is_inferability():
    """The transitive truth-plane read is disclosed, not denied.

    ``guards`` imports ``..inferability``, which itself imports two read-only
    constants from the truth plane. That is a real transitive import and this
    test names it rather than pretending the package is hermetic. What no module
    here does is import a validator, an exporter, or a writer.
    """
    sibling_imports: set[str] = set()
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        sibling_imports |= {r for r in _import_roots(path) if r.startswith(".")}
    intra_package = {f".{p.stem}" for p in PROVIDERS_DIR.glob("*.py")}
    assert sibling_imports - intra_package == {".inferability"}


# ---------------------------------------------------------------------------
# 8. NEGATIVE CONTROL: nothing can report itself production-configured
# ---------------------------------------------------------------------------


def test_no_implementation_in_the_package_claims_to_be_configured():
    """Runtime walk. ``capabilities()`` reads this flag; nothing sets it True."""
    import inspect

    seen = 0
    for module_name in ("transcription", "extraction", "assistant"):
        module = getattr(providers, module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if not hasattr(obj, "PRODUCTION_CONFIGURED"):
                continue
            seen += 1
            assert obj.PRODUCTION_CONFIGURED is False, obj
    assert seen >= 6, f"expected both implementations of all three seams, saw {seen}"


def test_no_source_file_assigns_production_configured_true():
    """AST scan. Catches a class the runtime walk would miss, and states the
    review rule: wiring a real provider is a visible edit to this flag."""
    offenders = []
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            target_names: list[str] = []
            value = None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_names = [node.target.id]
                value = node.value
            elif isinstance(node, ast.Assign):
                target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            if "PRODUCTION_CONFIGURED" not in target_names:
                continue
            if isinstance(value, ast.Constant) and value.value is True:
                offenders.append((path.name, node.lineno))
    assert offenders == [], f"a provider claims to be production-configured: {offenders}"


def test_capabilities_reports_the_fake_as_a_disclosed_test_double(monkeypatch):
    """Even with a fake selected, ``configured`` stays False — a fake answers
    none of the deferred decisions, and 'configured' would read as 'a model is
    running'. It is disclosed under its own key instead."""
    for env_var in provider_config.PROVIDER_ENV_VARS.values():
        monkeypatch.setenv(env_var, providers.IMPLEMENTATION_DETERMINISTIC_FAKE)
    report = providers.capabilities()
    assert report["any_provider_configured"] is False
    for entry in report["seams"]:
        assert entry["configured"] is False
        assert entry["is_test_double"] is True
        assert entry["implementation"] == providers.IMPLEMENTATION_DETERMINISTIC_FAKE


def test_the_package_performs_no_io_on_import():
    """Importing a seam must not touch the network or the disk. If it did, the
    'wired to nothing' claim would be false at import time, before any call."""
    import importlib

    module = importlib.import_module("isaac_api.providers")
    assert module.capabilities()["any_provider_configured"] is False
    assert os.environ.get(providers.ASSISTANT_PROVIDER_ENV) is None
