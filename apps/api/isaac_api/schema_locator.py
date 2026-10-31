"""ONE place that answers "where is the vendored official schema?" (2026-10-28).

Before this module the historical-import stack answered that question in three
ways: ``workspace._find_repo_root`` walked up from its own file, and
``bl15/mapping.py`` and ``bl15/evaluate.py`` each computed
``Path(__file__).resolve().parents[4]`` — a guess about how deep the file sits,
which is right in a checkout and in the image (``/app/apps/api/isaac_api/bl15``)
and wrong the moment the package is laid out any other way (a local CLI install,
a wheel). This module is the one resolver those two ``parents[4]`` sites now use.

THE ORDER, and it is the whole contract:

1. ``ISAAC_SCHEMA_PATH`` — an explicit override, for a layout where the schema is
   not above the code. Honoured ONLY in the local CLI process
   (:func:`enable_local_cli_override`); the server ignores it. When it is SET it is authoritative: a value that does not
   name a readable file is an error, never a silent fall-through to the search, so
   a mistyped override cannot quietly read a different schema.
2. otherwise walk UP from this file until ``schema/isaac_record_v1.json`` is found
   — the same rule ``workspace._find_repo_root`` applies.
3. otherwise **fail closed** with :class:`SchemaNotFound`, whose message says what
   was looked for and how to fix it. It subclasses :class:`FileNotFoundError`, so
   every existing ``except (OSError, ValueError)`` fail-closed handler around a
   schema read keeps treating it exactly as it treated a missing file.

Stdlib only, deliberately: ``bl15`` is the lowest layer of the import stack and
must not pull in the record engine to find one file.

THIS DOES NOT CHANGE THE TRUTH PLANE. ``isaac_records.official.schema_path`` and
``validate_official`` are untouched and still take an explicit root.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The environment variable that overrides the search.
SCHEMA_PATH_ENV = "ISAAC_SCHEMA_PATH"

#: Where the vendored schema sits relative to a repository root.
SCHEMA_RELATIVE_PATH = Path("schema") / "isaac_record_v1.json"


#: The override is honoured ONLY in the local CLI process (review minor): the web server
#: and the truth plane (`isaac_records.official`, which takes an explicit root) must never
#: read a different schema because an environment variable happens to be set.
_LOCAL_CLI_CONTEXT = False


def enable_local_cli_override() -> None:
    """Called by ``isaac_api.local_import.cli.main`` only."""
    global _LOCAL_CLI_CONTEXT
    _LOCAL_CLI_CONTEXT = True


def local_cli_override_enabled() -> bool:
    return _LOCAL_CLI_CONTEXT


class SchemaNotFound(FileNotFoundError):
    """The vendored official schema could not be located. Fail-closed."""


def find_repo_root(start: Path | None = None) -> Path | None:
    """The nearest directory at or above ``start`` holding the vendored schema.

    ``None`` when there is none — the caller decides whether that is fatal.
    """
    here = Path(start if start is not None else __file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / SCHEMA_RELATIVE_PATH).is_file():
            return candidate
    return None


def resolve_schema_path() -> Path:
    """The vendored official schema's path, by the order in the module docstring.

    Raises :class:`SchemaNotFound` rather than returning a path that does not exist.
    """
    override = os.environ.get(SCHEMA_PATH_ENV) if _LOCAL_CLI_CONTEXT else None
    if override is not None and override.strip():
        candidate = Path(override.strip()).expanduser()
        if not candidate.is_file():
            raise SchemaNotFound(
                f"{SCHEMA_PATH_ENV} is set but does not name a readable file "
                f"({override.strip()!r}). Point it at isaac_record_v1.json, or unset "
                "it to search upward from the installed code."
            )
        return candidate
    root = find_repo_root()
    if root is None:
        raise SchemaNotFound(
            f"Could not find {SCHEMA_RELATIVE_PATH.as_posix()} in any directory above "
            f"{Path(__file__).resolve().parent}. Run from an ISAAC checkout, or set "
            f"{SCHEMA_PATH_ENV} to the vendored schema file."
        )
    return root / SCHEMA_RELATIVE_PATH
