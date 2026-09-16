"""SSRL BL15-2 historical-source reading — the layer BELOW ``historical_import``.

**WHAT CHANGED, AND WHY THIS PACKAGE EXISTS AT ALL.** ``CLAUDE.md`` and
``ISAAC_EXECUTION_LEDGER.md`` recorded for months that ``BL15-001`` (a ``.mac``
parser) and ``HIST-002`` (first-wave deterministic parsers) were **BLOCKED** on
``EXT-10``: *"there is no representative BL15-2 corpus"*, and §5 forbids
designing a parser against zero examples. On **2026-09-16 the project owner
supplied one** — a real April-2025 Sokaras/IrOx beamtime archive. The blocker is
materially resolved **for the formats that archive contains** and for nothing
else; the measured inventory is
``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md``.

**THE RAW CORPUS IS NOT IN THIS REPOSITORY AND MUST NOT BE COMMITTED.** It is
real experimental data and real human notes (``CLAUDE.md`` §6). Everything in
this package is exercised in CI against **sanitized fixtures** under
``tests/fixtures/bl15/`` that reproduce the STRUCTURE and the ANOMALIES of the
real files at a fraction of the size, and whose sample names, potentials and
motor values are unmistakably synthetic.

**THE LAYERING, which is the part a future session must not collapse.**

.. code-block:: text

    bl15.archive     a safe inventory of a folder or ZIP           -> SourceRecord
    bl15.classify    what KIND of source each entry is             -> source_type
    bl15.profiles    one scientist's naming convention, versioned  -> concepts
    bl15.filenames   profile-driven token reading
    bl15.spec        the extensionless SPEC acquisition files
    bl15.scans       the per-scan ``.dat`` exports
    bl15.macros      ``.mac`` acquisition scripts, AS TEXT
    bl15.notes       ``readme.txt`` and the beamtime notes
                         |
                         v
    bl15.evidence    ONE representation every reader emits         -> SourceEvidence
                         |
    bl15.relate      stem <-> _dir <-> scans <-> newfile <-> notes
    bl15.reconstruct candidate Experiments and Runs
    bl15.mapping     source concept -> official ISAAC v1.05 path
                         |
                         v
    historical_import  the session, the review surface, the proposals

A reader NEVER decides a scientific question. It reads a file and says what the
file literally says, at a locator, with its profile stamped on it. Interpretation
happens exactly once, in :mod:`bl15.reconstruct`, and its output is a CANDIDATE
that a scientist reviews — never a value written into a record. Deterministic
ISAAC validation stays the only authority on validity (``CLAUDE.md`` §1).
"""

from __future__ import annotations
