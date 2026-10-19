"""THE RECORD FIELDS LABELS KEEP THE SCHEMA'S OWN CASING — QA A-16 (2026-10-12).

``serialize._label`` humanized a path's last segment with ``str.title()``, which
LOWERCASES every letter after a word's first: ``CuO2_mass_fraction`` read
"Cuo2 Mass Fraction" (a formula the schema spells ``CuO2``), ``pellet_diameter_mm``
read "Pellet Diameter Mm" (a unit), and ``acquired_start_utc`` read "Acquired Start
Utc". The same three paths read differently on other screens of the same record.

PRESENTATION ONLY: the label is what a row is CALLED. No path, value or stored key
changes, and every output word is an input word in a different case — a unit token is
additionally parenthesised, which adds punctuation and no word.
"""

from __future__ import annotations

import pytest

from isaac_api.serialize import _label


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("sample.composition.CuO2_mass_fraction", "CuO2 Mass Fraction"),
        ("sample.geometry.pellet_diameter_mm", "Pellet Diameter (mm)"),
        ("timestamps.acquired_start_utc", "Acquired Start UTC"),
        ("timestamps.created_utc", "Created UTC"),
        ("context.temperature_K", "Temperature (K)"),
        # Negative controls: an ordinary word is unchanged from the old behaviour.
        ("sample.material.formula", "Formula"),
        ("sample.sample_form", "Sample Form"),
        ("system.facility.facility_name", "Facility Name"),
    ],
)
def test_a_label_keeps_the_schema_casing_and_spells_units(path: str, label: str) -> None:
    assert _label(path) == label


def test_every_output_word_is_an_input_word():
    """No word is invented: case and the unit's parentheses are the only changes."""
    for path in (
        "sample.composition.CuO2_mass_fraction",
        "sample.geometry.pellet_diameter_mm",
        "timestamps.acquired_end_utc",
        "context.thermodynamics.atmosphere",
    ):
        words_in = [w.lower() for w in path.split(".")[-1].split("_") if w]
        words_out = [w.strip("()").lower() for w in _label(path).split(" ")]
        assert words_out == words_in
