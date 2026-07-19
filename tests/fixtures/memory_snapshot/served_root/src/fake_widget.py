"""Synthetic fixture module (fake_widget) — not real project code.

Used only by apps/api/tests/test_build_memory_snapshot.py to give the
served-content manifest (P24.10 Slice 2) real, fixed bytes to hash. Mirrors
the fake node/rationale content already committed in
tests/fixtures/memory_snapshot/graph/graph.json.
"""


def fake_widget_marker() -> str:
    return "fake-widget-fixture"
