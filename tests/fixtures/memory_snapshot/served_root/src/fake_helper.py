"""Synthetic fixture module (fake_helper) — not real project code.

Used only by apps/api/tests/test_build_memory_snapshot.py to give the
served-content manifest (P24.10 Slice 2) real, fixed bytes to hash.
"""


def do_helper_thing() -> str:
    return "fake-helper-fixture"
