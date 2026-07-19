"""Tests for the P24.10 memory-input fingerprint + served-content-manifest
primitives in ``isaac_api.memory``.

These cover only the pure primitives added in P24.10 Slice 1 (no generator /
reader / route / frontend wiring — that is later slices):

* :func:`~isaac_api.memory.compute_memory_policy_fingerprint` — a stable sha256
  over the exclusion policy + version stamps.
* :func:`~isaac_api.memory.compute_served_content_manifest` — a deterministic,
  path-safe, served-allowlist-gated ``[{"path", "sha256"}]`` list.
* :func:`~isaac_api.memory.compute_served_manifest_fingerprint` — an aggregate
  sha256 over that list, order-independent.

All fingerprints are proven by recomputing the algorithm independently in the
test (never asserting a hardcoded hex), so the tests pin the *algorithm*.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from isaac_api import memory
from isaac_api.memory import (
    compute_memory_policy_fingerprint,
    compute_served_content_manifest,
    compute_served_manifest_fingerprint,
    _policy_fingerprint_payload,
)


# --- helpers ------------------------------------------------------------------


def _canonical_sha(payload: dict) -> str:
    """Independently recompute the policy-fingerprint algorithm from a payload."""
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- 1. policy fingerprint: shape + stability ---------------------------------


def test_policy_fingerprint_is_64_char_lowercase_hex():
    fp = compute_memory_policy_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert fp == fp.lower()
    # every char a lowercase hex digit
    assert all(c in "0123456789abcdef" for c in fp)


def test_policy_fingerprint_is_stable_across_repeated_calls():
    assert compute_memory_policy_fingerprint() == compute_memory_policy_fingerprint()


def test_policy_fingerprint_matches_independent_recompute():
    """Proves the algorithm (canonical json -> sha256 hex), not a hardcoded value."""
    payload = _policy_fingerprint_payload()
    assert compute_memory_policy_fingerprint() == _canonical_sha(payload)


def test_policy_fingerprint_payload_has_expected_keys_and_versions():
    payload = _policy_fingerprint_payload()
    assert payload == {
        "schema_version": memory.SUPPORTED_SNAPSHOT_SCHEMA_VERSION,
        "policy_version": memory.MEMORY_INPUTS_POLICY_VERSION,
        "projection_version": memory.PROJECTION_VERSION,
        "algo_version": memory.FINGERPRINT_ALGO_VERSION,
        "excluded_prefixes": sorted(memory.EXCLUDED_PREFIXES),
        "excluded_exact": sorted(memory.EXCLUDED_EXACT),
        "binary_exts": sorted(memory.BINARY_EXTS),
        "secret_exts": sorted(memory.SECRET_EXTS),
        "secret_basenames": sorted(memory.SECRET_BASENAMES),
        "max_rationale_chars": memory.MAX_RATIONALE_CHARS,
    }
    assert memory.MAX_RATIONALE_CHARS == 280


# --- 2. policy fingerprint: sensitivity (every field participates) ------------


def _mutations(payload: dict):
    """Yield (label, mutated_payload) — one materially-changed copy per field."""
    yield "schema_version", {**payload, "schema_version": payload["schema_version"] + 1}
    yield "policy_version", {**payload, "policy_version": payload["policy_version"] + 1}
    yield "projection_version", {**payload, "projection_version": payload["projection_version"] + 1}
    yield "algo_version", {**payload, "algo_version": payload["algo_version"] + 1}
    yield "excluded_prefixes", {**payload, "excluded_prefixes": payload["excluded_prefixes"][1:]}
    yield "excluded_exact", {**payload, "excluded_exact": payload["excluded_exact"][1:]}
    yield "binary_exts", {**payload, "binary_exts": payload["binary_exts"][1:]}
    yield "secret_exts", {**payload, "secret_exts": payload["secret_exts"][1:]}
    yield "secret_basenames", {**payload, "secret_basenames": payload["secret_basenames"][1:]}
    yield "max_rationale_chars", {**payload, "max_rationale_chars": payload["max_rationale_chars"] + 1}


def test_policy_fingerprint_is_sensitive_to_every_field():
    real = compute_memory_policy_fingerprint()
    payload = _policy_fingerprint_payload()
    # sanity: the lists we drop from are all non-empty, so the drop is material
    for k in ("excluded_prefixes", "excluded_exact", "binary_exts",
              "secret_exts", "secret_basenames"):
        assert len(payload[k]) >= 1
    for label, mutated in _mutations(payload):
        assert _canonical_sha(mutated) != real, f"fingerprint insensitive to {label}"


# --- 3. served content manifest -----------------------------------------------


def _write(root, rel: str, data: bytes):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return data


def test_content_manifest_sorted_with_correct_sha256(tmp_path):
    a = _write(tmp_path, "src/mod_a.py", b"print('a')\n")
    b = _write(tmp_path, "docs/notes.md", b"# notes\nhello\n")
    c = _write(tmp_path, "README.md", b"readme bytes")

    # deliberately unsorted input order
    manifest = compute_served_content_manifest(
        ["src/mod_a.py", "README.md", "docs/notes.md"], tmp_path
    )

    assert manifest == [
        {"path": "README.md", "sha256": _sha256_bytes(c)},
        {"path": "docs/notes.md", "sha256": _sha256_bytes(b)},
        {"path": "src/mod_a.py", "sha256": _sha256_bytes(a)},
    ]
    # sorted by path
    assert manifest == sorted(manifest, key=lambda e: e["path"])
    # posix-normalized (no backslashes anywhere)
    assert all("\\" not in e["path"] for e in manifest)


def test_content_manifest_is_deterministic_byte_identical(tmp_path):
    _write(tmp_path, "src/x.py", b"x")
    _write(tmp_path, "src/y.py", b"y")
    m1 = compute_served_content_manifest(["src/x.py", "src/y.py"], tmp_path)
    m2 = compute_served_content_manifest(["src/y.py", "src/x.py"], tmp_path)
    assert m1 == m2
    assert json.dumps(m1) == json.dumps(m2)


def test_content_manifest_missing_file_raises(tmp_path):
    _write(tmp_path, "src/present.py", b"here")
    with pytest.raises((ValueError, OSError)):
        compute_served_content_manifest(["src/present.py", "src/absent.py"], tmp_path)


# --- 4. served content manifest: security guards ------------------------------


def test_content_manifest_rejects_non_served_path(tmp_path):
    # governance-excluded prefix (examples/) — even if the bytes exist
    _write(tmp_path, "examples/secret.txt", b"top secret")
    with pytest.raises(ValueError):
        compute_served_content_manifest(["examples/secret.txt"], tmp_path)


def test_content_manifest_rejects_secret_basename(tmp_path):
    _write(tmp_path, ".env", b"TOKEN=abc")
    with pytest.raises(ValueError):
        compute_served_content_manifest([".env"], tmp_path)


def test_content_manifest_rejects_absolute_path(tmp_path):
    _write(tmp_path, "etc/passwd", b"root")
    abs_path = str((tmp_path / "etc" / "passwd").resolve())
    assert abs_path.startswith("/")
    with pytest.raises(ValueError):
        compute_served_content_manifest([abs_path], tmp_path)


def test_content_manifest_rejects_traversal_path(tmp_path):
    with pytest.raises(ValueError):
        compute_served_content_manifest(["../escape.py"], tmp_path)


# --- 5. aggregate served-manifest fingerprint ---------------------------------


def _expected_aggregate(manifest) -> str:
    pairs = sorted((e["path"], e["sha256"]) for e in manifest)
    joined = "\n".join(f"{path}\0{sha256}" for path, sha256 in pairs)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def test_aggregate_fingerprint_matches_independent_recompute():
    manifest = [
        {"path": "a.py", "sha256": "aa" * 32},
        {"path": "b.py", "sha256": "bb" * 32},
    ]
    fp = compute_served_manifest_fingerprint(manifest)
    assert len(fp) == 64
    assert fp == _expected_aggregate(manifest)


def test_aggregate_fingerprint_is_order_independent():
    ordered = [
        {"path": "a.py", "sha256": "11" * 32},
        {"path": "b.py", "sha256": "22" * 32},
        {"path": "c.py", "sha256": "33" * 32},
    ]
    shuffled = [ordered[2], ordered[0], ordered[1]]
    assert (compute_served_manifest_fingerprint(ordered)
            == compute_served_manifest_fingerprint(shuffled))


def test_aggregate_fingerprint_changes_when_any_sha_changes():
    base = [
        {"path": "a.py", "sha256": "11" * 32},
        {"path": "b.py", "sha256": "22" * 32},
    ]
    changed = [
        {"path": "a.py", "sha256": "11" * 32},
        {"path": "b.py", "sha256": "23" * 32},  # one byte flipped
    ]
    assert (compute_served_manifest_fingerprint(base)
            != compute_served_manifest_fingerprint(changed))


def test_aggregate_fingerprint_changes_when_path_changes():
    base = [{"path": "a.py", "sha256": "11" * 32}]
    changed = [{"path": "z.py", "sha256": "11" * 32}]
    assert (compute_served_manifest_fingerprint(base)
            != compute_served_manifest_fingerprint(changed))


# --- 6. end-to-end: manifest -> aggregate is deterministic --------------------


def test_manifest_then_aggregate_is_deterministic(tmp_path):
    _write(tmp_path, "src/one.py", b"one")
    _write(tmp_path, "src/two.py", b"two")
    m = compute_served_content_manifest(["src/two.py", "src/one.py"], tmp_path)
    fp1 = compute_served_manifest_fingerprint(m)
    fp2 = compute_served_manifest_fingerprint(m)
    assert fp1 == fp2 == _expected_aggregate(m)
