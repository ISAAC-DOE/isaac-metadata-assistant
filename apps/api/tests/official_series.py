"""A series ITEM the official ISAAC schema admits, for tests whose subject is not series.

WHY THIS EXISTS (QA audit A-03, 2026-10-11). Until the answering and correcting routes
checked a structured answer against the official schema's own rule for its path
(``isaac_api.official_shape``), these tests answered with values such as
``{"energy_eV": 8979.0, "mu": 0.11, "series_id": "race-a"}`` — a list of objects with a
``series_id``, which is all the old storability guard asked, and which the official
schema REFUSES (``independent_variables`` and ``channels`` are required and
``additionalProperties`` is false). Those values were accepted, and every record they
were written into could never have exported. Their subject was concurrency, MCP routing,
size bounds or wrong-type refusals — never the series itself — so they now use this.

The two numbers a caller passes are kept, as ONE point each, so a test that told two
values apart by them still can: they are carried into ``values`` rather than invented.
"""

from __future__ import annotations


def official_series_item(series_id: str, energy_eV: float = 8979.0, mu: float = 0.11) -> dict:
    return {
        "series_id": series_id,
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [energy_eV]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [mu],
            }
        ],
    }


def official_series(series_id: str = "s1", energy_eV: float = 8979.0, mu: float = 0.11) -> list:
    return [official_series_item(series_id, energy_eV, mu)]
