"""The one place a reader turns a reading into a :class:`SourceEvidence`.

**NOT A READER, AND NOT PART OF THE PUBLIC CONTRACT** — hence the underscore.
Five readers in this package share three mechanics, and each of the three is the
kind of thing that drifts when it is written five times:

1. **The evidence-id convention.** :class:`~isaac_api.bl15.evidence.SourceEvidence`
   requires an ``evidence_id`` while its own docstring says the id belongs to the
   caller that assembled the import session, *"so a reader stays a pure function
   of text"*. Both hold here: the reader mints a **deterministic,
   locator-ordinal** id (``<prefix><parser_id>#<n>``) that is stable for the same
   bytes on every run and carries no clock, no random source and no process
   state. A session is free to re-key it; nothing downstream may assume the
   reader's id is session-unique.
2. **The evidence ceiling.** :data:`~isaac_api.bl15.evidence.MAX_EVIDENCE_PER_SOURCE`
   is not hypothetical in this corpus — the measured ``alignment`` acquisition
   carries **233 scans x 172 motor positions**, about 40,000 candidate items, so
   the ceiling IS reached by a real file. Truncating silently would report a
   partial reading as a whole one; the builder counts what it suppressed and
   :meth:`result` states it under ``skipped`` without the reader having to
   remember.
3. **The skipped-entry shape.** ``{"reason", "locator", ...}``, so a review
   surface can group refusals by reason across every reader.
"""

from __future__ import annotations

from typing import Any

from .evidence import (
    DETERMINISM_READ,
    MAX_EVIDENCE_PER_SOURCE,
    SCOPE_MEASUREMENT,
    ReaderResult,
    SourceEvidence,
)

#: Reported under ``skipped`` when the per-source evidence ceiling truncated a
#: reading. A closed reason string so a surface can special-case it: unlike every
#: other skip, it means *the source was understood and the REPORT is partial*.
SKIP_EVIDENCE_CEILING = "evidence_ceiling_reached"


class EvidenceBuilder:
    """Accumulates evidence and skips for ONE source, under the ceiling."""

    def __init__(
        self,
        *,
        source_path: str,
        source_type: str,
        parser_id: str,
        id_prefix: str = "",
        max_items: int = MAX_EVIDENCE_PER_SOURCE,
        profile_id: str | None = None,
        profile_version: str | None = None,
    ) -> None:
        self.source_path = source_path
        self.source_type = source_type
        self.parser_id = parser_id
        self.id_prefix = id_prefix
        self.max_items = max_items
        self.profile_id = profile_id
        self.profile_version = profile_version
        self._items: list[SourceEvidence] = []
        self._skipped: list[dict] = []
        self._suppressed = 0
        self._first_suppressed_locator: str | None = None

    # -- evidence -------------------------------------------------------------

    def add(
        self,
        *,
        locator: str,
        raw_literal: str,
        concept: str,
        determinism: str = DETERMINISM_READ,
        scope: str = SCOPE_MEASUREMENT,
        normalized_value: Any = None,
        unit: str | None = None,
        normalization_rule: str | None = None,
        timestamp_utc: str | None = None,
        measurement_stem: str | None = None,
    ) -> bool:
        """Append one statement. ``False`` means the ceiling refused it.

        A refusal is COUNTED, not raised and not dropped silently —
        :meth:`result` turns the count into a ``skipped`` entry.
        """
        if len(self._items) >= self.max_items:
            self._suppressed += 1
            if self._first_suppressed_locator is None:
                self._first_suppressed_locator = locator
            return False
        self._items.append(
            SourceEvidence(
                evidence_id=f"{self.id_prefix}{self.parser_id}#{len(self._items)}",
                source_path=self.source_path,
                source_type=self.source_type,
                locator=locator,
                raw_literal=raw_literal,
                concept=concept,
                parser_id=self.parser_id,
                determinism=determinism,
                scope=scope,
                normalized_value=normalized_value,
                unit=unit,
                normalization_rule=normalization_rule,
                profile_id=self.profile_id,
                profile_version=self.profile_version,
                timestamp_utc=timestamp_utc,
                measurement_stem=measurement_stem,
            )
        )
        return True

    # -- skips ----------------------------------------------------------------

    def skip(self, *, reason: str, locator: str, **detail: Any) -> None:
        entry: dict = {"reason": reason, "locator": locator}
        entry.update(detail)
        self._skipped.append(entry)

    # -- result ---------------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def suppressed_count(self) -> int:
        return self._suppressed

    def result(self, *, refused_reason: str | None = None) -> ReaderResult:
        skipped = list(self._skipped)
        if self._suppressed:
            skipped.append(
                {
                    "reason": SKIP_EVIDENCE_CEILING,
                    "locator": self._first_suppressed_locator or "",
                    "detail": (
                        f"{self._suppressed} further statements were not "
                        f"reported: this source reached the per-source ceiling "
                        f"of {self.max_items} evidence items. The reading is "
                        f"PARTIAL and must not be treated as complete."
                    ),
                    "suppressed_count": self._suppressed,
                    "ceiling": self.max_items,
                }
            )
        return ReaderResult(
            source_path=self.source_path,
            parser_id=self.parser_id,
            evidence=tuple(self._items),
            skipped=tuple(skipped),
            refused_reason=refused_reason,
        )


def refusal(
    *, source_path: str, parser_id: str, reason: str
) -> ReaderResult:
    """A whole-source refusal with nothing read. Never an exception."""
    return ReaderResult(
        source_path=source_path, parser_id=parser_id, refused_reason=reason
    )


def oversize_reason(measured_bytes: int, ceiling: int) -> str:
    """The one wording for a size refusal, with both numbers in it."""
    return (
        f"source_too_large: {measured_bytes} bytes exceeds the per-source "
        f"ceiling of {ceiling} bytes; nothing was read, so no partial reading "
        f"is reported as whole"
    )
