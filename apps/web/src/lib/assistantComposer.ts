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
  AssistantMessage,
  ComposerOutput,
  GroundedChip,
  GroundingState,
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
      const { validate } = state.bundle;
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

/**
 * Compose the reply + guided prompts for a screen from its already-fetched
 * state. P25.1 implements only the `review` context; any other context throws.
 */
export function compose(state: GroundingState): ComposerOutput {
  if (state.context !== 'review') {
    throw new Error('compose: context not implemented in P25.1');
  }

  const prompts: SuggestedPrompt[] = REVIEW_CATALOG.map((chip) => ({
    text: chip.label,
    answeredFrom: chip.source,
    // null answer → undefined → chip disabled by the panel's `disabled={!p.answer}`.
    answer: chip.resolve(state) ?? undefined,
  }));

  // reply = first chip with a non-null answer, in catalog priority order
  // (pending → blocking → provenance); else the neutral grounded fallback.
  const reply = prompts.find((p) => p.answer)?.answer ?? REVIEW_FALLBACK;

  return { reply, prompts };
}
