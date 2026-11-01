"""Draft scientific XAS processing for record groups — protocol ``isaac.xas.v0``.

**DRAFT — not reviewed by a beamline scientist; Oscar's protocol supersedes on arrival.**
Every result is ``protocol_status: draft_unreviewed`` and ``state: needs_review``.

Entry points (plain functions; the ``isaac bundle group`` / ``isaac process`` CLI wiring
lives with the bundle CLI):

* :func:`.cli_entry.run_group` — propose record groups for a bundle directory.
* :func:`.cli_entry.run_process` — run the protocol over them (needs the optional
  ``processing`` extra: numpy + xraylarch; without it the result is
  ``processing_unavailable``).
* :func:`.evaluate.evaluate_folder` — ISAAC-vs-Athena agreement over many bundles.

Importing this package imports neither numpy nor larch.
"""

from .protocol import PROTOCOL_ID, PROTOCOL_STATUS, PROTOCOL_VERSION  # noqa: F401
