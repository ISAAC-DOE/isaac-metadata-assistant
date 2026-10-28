"""The ISAAC Local Import Bundle: what ``isaac import`` writes on a scientist's machine.

Two modules:

* :mod:`.bundle` — the v1 contract: builder, loader, validator, and the value-state
  derivation (``bundle-v1.schema.json`` beside it is the JSON Schema).
* :mod:`.cli` — ``isaac import`` and ``isaac bundle list|show|check``.

A bundle is NOT an official ISAAC record (``is_official_record: false``, a schema
constant). Contract and rationale: ``docs/local-import-bundle-contract.md``.

Nothing here imports FastAPI or ``isaac_api.routes``; the reading is
:func:`isaac_api.historical_import.read_local_archive`, the server's own chain.
"""
