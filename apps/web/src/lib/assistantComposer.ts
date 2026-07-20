/*
 * Grounded-assistant composer (P25.1) — a PURE, synchronous, side-effect-free
 * function over already-fetched bundle data. No fetch, no I/O, no graph/graphify
 * imports, zero truth-path change.
 *
 * The composer echoes state the screen already holds (counts, paths, cited
 * sources) into short, source-labeled replies. It NEVER validates, never states
 * a PASS/FAIL or a valid/invalid conclusion, and never echoes `validate.ok`.
 * Truth questions route to the deterministic surfaces. The panel still runs
 * `hasVerdictLanguage()` over the composed output as a structural backstop.
 *
 * P25.1 wires only the `review` context (Record Workbench). Other contexts are
 * TYPE-declared in the GroundingState union but throw here until later slices.
 */

import type {
  ApiValidateResult,
  AssistantMessage,
  ComposerOutput,
  GroundedChip,
  GroundingState,
  ScreenContext,
  SuggestedPrompt,
} from './types';

/**
 * Deterministic pluralization: "1 field" / "2 fields". `plural` defaults to
 * `singular + 's'`. No `field(s)` / `entr(y/ies)` placeholders ever survive to
 * rendered output.
 */
export function count(n: number, singular: string, plural?: string): string {
  const word = n === 1 ? singular : (plural ?? `${singular}s`);
  return `${n} ${word}`;
}

// Join the first ≤3 items with ", "; append ", …and K more" for the remainder.
function joinCapped(items: string[]): string {
  const shown = items.slice(0, 3);
  const rest = items.length - shown.length;
  const base = shown.join(', ');
  return rest > 0 ? `${base}, …and ${rest} more` : base;
}

// A string is "usable" only when it is present and non-empty after trim. This
// guards every interpolated field so `undefined` / `null` / an empty value can
// never reach rendered output (Fix 6a/6b).
function isUsableStr(x: unknown): x is string {
  return typeof x === 'string' && x.trim() !== '';
}

const ROUTE_TO_VALIDATE = 'Open Validate to run the deterministic schema check.';

/**
 * The blocking-paths answer, shared verbatim by the Record Workbench (§5.1) and
 * Ready to Export (§5.2 — "Same template as §5.1") so the two can never drift.
 * It states a COUNT of blocking paths + the first ≤3 paths + a route to the
 * deterministic check. It NEVER echoes `validate.ok` or concludes validity.
 * `null` when the validation payload is absent → the chip is disabled.
 */
function blockingPathsMessage(validate: ApiValidateResult | undefined | null): AssistantMessage | null {
  if (!validate) return null; // data absent → chip disabled
  const errors = validate.errors;
  if (errors.length === 0) {
    return {
      text: `No blocking paths are listed in the current validation response. ${ROUTE_TO_VALIDATE}`,
      answeredFrom: 'schema',
    };
  }
  const verb = errors.length === 1 ? 'is' : 'are';
  const paths = joinCapped(errors.map((e) => e.path));
  return {
    text: `${count(errors.length, 'path')} ${verb} listed as blocking export: ${paths}. ${ROUTE_TO_VALIDATE}`,
    answeredFrom: 'schema',
  };
}

// --- Record Workbench (context: 'review'; state = getRecordBundle) ----------

export const REVIEW_CATALOG: GroundedChip[] = [
  {
    id: 'pending_summary',
    label: 'What still needs me?',
    source: 'workflow',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      const { pending } = state.bundle;
      if (!pending) return null; // data absent → chip disabled
      if (pending.length === 0) {
        return { text: 'No pending fields are listed for this record.', answeredFrom: 'workflow' };
      }
      // One label per pending item (full-length; never drops an item for
      // lacking `about`). First usable value wins: about → question → id →
      // literal. joinCapped's "…and K more" is then computed over the FULL
      // list, so the shown count and the listed labels always agree (Fix 6b).
      const labels = pending.map((p) => {
        if (isUsableStr(p.about)) return p.about;
        if (isUsableStr(p.question)) return p.question;
        if (isUsableStr(p.id)) return p.id;
        return 'unnamed pending field';
      });
      const verb = pending.length === 1 ? 'needs' : 'need';
      return {
        text: `${count(pending.length, 'field')} still ${verb} you: ${joinCapped(labels)}.`,
        answeredFrom: 'workflow',
      };
    },
  },
  {
    id: 'blocking_paths',
    label: "What's left before export?",
    source: 'schema',
    routed: true,
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      return blockingPathsMessage(state.bundle.validate);
    },
  },
  {
    id: 'field_provenance',
    label: 'Trace a field to its source',
    source: 'files',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      const { evidence } = state.bundle;
      const entries = evidence ?? [];

      // Prefer the first field that carries a sub-entry with a usable
      // source_file; the honest file-level trace only comes from there.
      const fileField = entries.find((e) =>
        (e.evidence ?? []).some((fe) => isUsableStr(fe.source_file)),
      );
      if (fileField) {
        const fileEntry = fileField.evidence.find((fe) => isUsableStr(fe.source_file))!;
        const locator = isUsableStr(fileEntry.locator) ? ` (locator: ${fileEntry.locator})` : '';
        // Guard source_type like every other interpolated value: an unusable
        // one (only reachable via a type-illegal bundle) drops the whole clause
        // rather than rendering "source type: .". `fileField.path` is
        // contract-guaranteed non-optional (the sentence subject) — not guarded.
        const sourceType = isUsableStr(fileEntry.source_type)
          ? ` — source type: ${fileEntry.source_type}`
          : '';
        return {
          text: `${fileField.path} traces to ${fileEntry.source_file}${locator}${sourceType}.`,
          answeredFrom: 'files',
        };
      }

      // No field cites a usable file. Fall back to the first entry that has any
      // evidence at all and answer honestly — never claim a file-level trace.
      const entry = entries.find((e) => (e.evidence?.length ?? 0) > 0);
      if (!entry) {
        return { text: 'No cited source is recorded for a field yet.', answeredFrom: 'files' };
      }
      const sourceTypes = [
        ...new Set((entry.evidence ?? []).map((fe) => fe.source_type).filter(isUsableStr)),
      ];
      if (sourceTypes.length === 0) {
        return { text: 'No cited source file is recorded for this field.', answeredFrom: 'files' };
      }
      const typeWord = sourceTypes.length === 1 ? 'source type' : 'source types';
      return {
        text: `${entry.path} has ${count(entry.evidence.length, 'evidence entry', 'evidence entries')} but no cited source file — ${typeWord}: ${joinCapped(sourceTypes)}.`,
        answeredFrom: 'files',
      };
    },
  },
];

// Neutral, source-labeled fallback when every review chip resolves to null.
const REVIEW_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'workflow',
};

// --- Ready to Export (context: 'export'; state = getExportReadiness) --------
// Three chips explain the DISTINCT audit / schema / advisory planes (§5.2).
// The panel-level `note` stays `ROUTE_TO_CLI_NOTE` (set by the screen); the
// blocker chip additionally routes truth in its own copy. No chip ever echoes
// `validate.ok` or concludes validity.

export const EXPORT_CATALOG: GroundedChip[] = [
  {
    id: 'coverage_vs_validity',
    label: 'Is coverage the same as valid?',
    source: 'audit',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'export') return null;
      const { audit } = state.bundle;
      if (!audit) return null; // audit payload absent → chip disabled
      const record = audit.records[0];
      if (!record) {
        // Pre-export: `records:[]` — nothing has been exported/audited yet.
        // An honest, present-but-empty answer (mirrors the review empty-state
        // precedent); coverage is a count, NEVER a validity determination.
        return {
          text: 'No coverage figures yet — coverage appears after export.',
          answeredFrom: 'audit',
        };
      }
      return {
        text: `Coverage is ${record.evidence_present}/${record.evidence_expected} evidenced fields. It describes how many expected fields carry evidence; the schema check is separate.`,
        answeredFrom: 'audit',
      };
    },
  },
  {
    id: 'blocking_paths',
    label: "What's left before export?",
    source: 'schema',
    routed: true,
    // Same template as §5.1 (shared helper); the panel `note = ROUTE_TO_CLI_NOTE`
    // routes to the CLI. Never echoes `validate.ok`.
    resolve(state): AssistantMessage | null {
      if (state.context !== 'export') return null;
      return blockingPathsMessage(state.bundle.validate);
    },
  },
  {
    id: 'advisory_detail',
    label: 'Explain the advisory warning',
    source: 'advisory',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'export') return null;
      const { warnings } = state.bundle;
      if (!warnings) return null; // advisory payload absent → chip disabled
      const list = warnings.warnings ?? [];
      if (list.length === 0) {
        return { text: 'No advisory warnings on this record.', answeredFrom: 'advisory' };
      }
      const w = list[0];
      const more = list.length - 1;
      const moreClause = more > 0 ? `. …and ${more} more` : '';
      return {
        text: `${w.code} — ${w.message} (advisory, non-gating; where: ${w.where})${moreClause}.`,
        answeredFrom: 'advisory',
      };
    },
  },
];

// Neutral fallback when every export chip resolves to null (defensive — the
// real bundle always carries audit/validate/warnings).
const EXPORT_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'audit',
};

// Per-context chip catalog + neutral fallback. Contexts not yet wired throw.
function pickCatalog(context: ScreenContext): {
  catalog: GroundedChip[];
  fallback: AssistantMessage;
} {
  switch (context) {
    case 'review':
      return { catalog: REVIEW_CATALOG, fallback: REVIEW_FALLBACK };
    case 'export':
      return { catalog: EXPORT_CATALOG, fallback: EXPORT_FALLBACK };
    default:
      throw new Error('compose: context not implemented yet');
  }
}

/**
 * Compose the reply + guided prompts for a screen from its already-fetched
 * state. `review` (P25.1) and `export` (P25.4) are wired; evidence / complete /
 * memory throw until their slices land.
 */
export function compose(state: GroundingState): ComposerOutput {
  const { catalog, fallback } = pickCatalog(state.context);

  const prompts: SuggestedPrompt[] = catalog.map((chip) => ({
    text: chip.label,
    answeredFrom: chip.source,
    // null answer → undefined → chip disabled by the panel's `disabled={!p.answer}`.
    answer: chip.resolve(state) ?? undefined,
  }));

  // reply = first chip with a non-null answer, in catalog priority order; else
  // the neutral grounded fallback.
  const reply = prompts.find((p) => p.answer)?.answer ?? fallback;

  return { reply, prompts };
}
