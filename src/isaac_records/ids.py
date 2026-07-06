"""Record identifiers.

Official ISAAC `record_id` is a ULID: 26 Crockford-base32 chars, `^[0-9A-Z]{26}$`.
"""

from __future__ import annotations

import re

from ulid import ULID

RECORD_ID_RE = re.compile(r"^[0-9A-Z]{26}$")


def new_record_id() -> str:
    return str(ULID())


def is_record_id(value: str) -> bool:
    return isinstance(value, str) and bool(RECORD_ID_RE.match(value))
