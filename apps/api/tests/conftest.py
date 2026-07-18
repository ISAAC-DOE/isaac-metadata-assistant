"""Shared fixtures for ``apps/api/tests``.

Autouse seam-neutralizer (P24.9-impl-4)
----------------------------------------
``apps/api/isaac_api/data/memory-snapshot.json`` is now a real, committed
sanitized snapshot (P24.9-impl-4). Per ``isaac_api.memory._resolve_reader_choice``'s
documented precedence, its mere presence on disk makes
``memory.get_default_reader()`` select :class:`~isaac_api.memory.SanitizedSnapshotSource`
over it by default — ahead of ``ISAAC_MEMORY_DIR`` and the repo's
``graphify-out/`` fallback (precedence step 2, ahead of steps 3/4).

Most of ``apps/api/tests`` predates that file's existence and drives the
*live-graph* provider deliberately (via ``ISAAC_MEMORY_DIR`` pointed at a
synthetic fixture, or an absent ``graphify-out/``), asserting on
``provider_kind == "local-graph"`` and related shapes. Those tests are not
wrong — they intentionally exercise precedence steps 3/4 and must keep doing
so regardless of whether a packaged snapshot happens to exist in the
checkout. So every test gets the packaged-snapshot precedence step
neutralized by default: ``memory._PACKAGED_SNAPSHOT`` is pointed at a path
that is guaranteed not to exist (a name under ``tmp_path``, never created),
so ``_resolve_reader_choice()`` falls through to
``ISAAC_MEMORY_SNAPSHOT`` / ``ISAAC_MEMORY_DIR`` / ``graphify-out/`` exactly as
before that file existed. The memoized ``_default_reader``/``_default_choice``
are also reset so ``get_default_reader()`` re-resolves for every test instead
of reusing a reader instance memoized by an earlier test.

A test that specifically wants to exercise the packaged-snapshot step itself
(none currently do outside ``test_snapshot_source.py``'s own seam tests, which
already monkeypatch ``memory._PACKAGED_SNAPSHOT`` explicitly to whatever path
they need) can simply monkeypatch ``memory._PACKAGED_SNAPSHOT`` again to
override this fixture's value — monkeypatch calls stack, so the last one set
within a test wins.

This fixture does not touch the real snapshot file itself, nor any of the
truth/export/validation path; it only neutralizes a *default-selection* seam
in ``isaac_api.memory`` for the duration of each test.
"""

from __future__ import annotations

import pytest

from isaac_api import memory


@pytest.fixture(autouse=True)
def _neutralize_packaged_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nonexistent-packaged-snapshot.json")
    monkeypatch.setattr(memory, "_default_reader", None)
    monkeypatch.setattr(memory, "_default_choice", None)
    yield
