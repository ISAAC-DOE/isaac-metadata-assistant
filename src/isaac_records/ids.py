"""Record identifiers.

Official ISAAC `record_id` is a ULID: 26 Crockford-base32 chars. The vendored
official schema declares it as `pattern: "^[0-9A-Z]{26}$"`.

`RECORD_ID_RE` IS DELIBERATELY STRICTER THAN THAT PATTERN, and the difference is
one character. Python's `$` also matches immediately BEFORE a trailing newline, so
`^[0-9A-Z]{26}$` applied with `.match()` accepted the 27-character string
`"A"*26 + "\\n"`. That is not an obscure corner: `is_record_id` is the path-traversal
boundary for the whole record namespace (`workspace.py` derives directory names from
ids), the shape gate on a caller-supplied `record_id` at export, and the predicate
that decides which files an artifact prune may delete.

Nothing downstream caught it either. MEASURED against the vendored schema with the
project's own `validate_official`: `record_id = "A"*26 + "\\n"` validates **ok**,
because the schema's `$` is lenient in exactly the same way. A leading newline, an
embedded newline and a trailing `\\r\\n` are all correctly refused by the schema — so
the mechanism is `$`'s newline tolerance, not JSON Schema's unanchored `pattern`
matching. The vendored schema is upstream-owned (`CLAUDE.md` §1) and is NOT changed
here; this predicate is where our code defends.

The exactness lives in the PATTERN rather than in a `fullmatch` call site so that
every present and future consumer of this constant is exact by construction; a new
`.match()` caller cannot reintroduce the hole. `draft_validator._SHA256_RE`,
`complete._SHA256_RE` and `format_shadow._RFC3339_SHAPE` took the same decision for
the same reason.
"""

from __future__ import annotations

import re

from ulid import ULID

RECORD_ID_RE = re.compile(r"\A[0-9A-Z]{26}\Z")


def new_record_id() -> str:
    return str(ULID())


def is_record_id(value: str) -> bool:
    return isinstance(value, str) and bool(RECORD_ID_RE.match(value))
