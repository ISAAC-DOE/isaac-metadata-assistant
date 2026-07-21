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
 * `review` (Record Workbench, P25.1), `export` (Ready to Export, P25.4),
 * `evidence` (Evidence Explorer, P25.5) and `complete` (Guided Completion,
 * P25.6) are wired. The remaining context (`memory`) is TYPE-declared in the
 * GroundingState union but throws here until its slice lands.
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

// --- Evidence Explorer (context: 'evidence'; state = getEvidenceBundle) ------
// Three chips explain the evidence trail without asserting any provenance the
// screen hasn't already shown: the multiplicity chip echoes ONLY the count +
// source types of the selected field (never a source_file / locator / quote),
// the sidecar chip is a static convention statement, and the artifacts chip
// echoes only path strings that are actually present. No chip states a verdict.

// Shared verbatim by the multiplicity chip so the "select a field" guidance is
// identical whether nothing is selected or the selection isn't in the bundle.
const SELECT_A_FIELD: AssistantMessage = {
  text: 'Select a field in the Evidence Trail to see its supporting entries.',
  answeredFrom: 'files',
};

export const EVIDENCE_CATALOG: GroundedChip[] = [
  {
    id: 'evidence_multiplicity',
    label: 'Why multiple evidence entries?',
    source: 'files',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'evidence') return null;
      const { selectedPath } = state;
      if (!isUsableStr(selectedPath)) return SELECT_A_FIELD;
      const entry = state.bundle.evidence.find((e) => e.path === selectedPath);
      if (!entry) return SELECT_A_FIELD;

      const entries = entry.evidence ?? [];
      if (entries.length === 0) {
        return {
          text: `${entry.path} has no separate evidence entries recorded.`,
          answeredFrom: 'files',
        };
      }
      // Display tokens are source_type ONLY — never source_file / locator /
      // quote — so the chip can't claim any file-level provenance. source_type
      // is guarded defensively (like every other interpolated value) so an
      // unusable one becomes 'unspecified source' rather than leaking; the shown
      // count and the listed items therefore always agree (the 6b invariant).
      const tokens = entries.map((e) =>
        isUsableStr(e.source_type) ? e.source_type : 'unspecified source',
      );
      if (entries.length === 1) {
        return {
          text: `${entry.path} has ${count(1, 'evidence entry', 'evidence entries')}: ${tokens[0]}.`,
          answeredFrom: 'files',
        };
      }
      return {
        text: `${entry.path} has ${count(entries.length, 'evidence entry', 'evidence entries')}: ${joinCapped(tokens)}. Multiple entries can provide separate support for the same field.`,
        answeredFrom: 'files',
      };
    },
  },
  {
    id: 'sidecar_convention',
    label: 'What is the evidence sidecar?',
    source: 'files',
    // Static convention statement — never null within the evidence context. It
    // is deliberately NOT an official ISAAC standard, and says nothing about
    // whether the record validates.
    resolve(state): AssistantMessage | null {
      if (state.context !== 'evidence') return null;
      return {
        text:
          'The evidence sidecar is an ISAAC assistant convention, not part of the official ISAAC ' +
          'schema. It preserves field-level evidence that the official record has no dedicated ' +
          'place to store.',
        answeredFrom: 'files',
      };
    },
  },
  {
    id: 'artifact_paths',
    label: 'Where are the exported artifacts?',
    source: 'workflow',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'evidence') return null;
      const { record_path, sidecar_path } = state.bundle.artifacts;
      // isUsableStr uniformly handles null / undefined / empty-string, so a path
      // is echoed ONLY when it is a present, non-empty string.
      const hasRecord = isUsableStr(record_path);
      const hasSidecar = isUsableStr(sidecar_path);
      if (hasRecord && hasSidecar) {
        return {
          text: `Exported: record ${record_path} and its evidence sidecar ${sidecar_path}.`,
          answeredFrom: 'workflow',
        };
      }
      if (hasRecord) {
        return {
          text: `Exported: record ${record_path}. No evidence sidecar path is recorded.`,
          answeredFrom: 'workflow',
        };
      }
      if (hasSidecar) {
        return {
          text: `Exported: evidence sidecar ${sidecar_path}. No record path is recorded.`,
          answeredFrom: 'workflow',
        };
      }
      return {
        text: 'Not exported yet — export writes the record plus its evidence sidecar.',
        answeredFrom: 'workflow',
      };
    },
  },
];

// Neutral fallback when every evidence chip resolves to null (defensive — the
// sidecar chip always answers within the evidence context).
const EVIDENCE_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'files',
};

// --- Complete Missing Fields (context: 'complete'; state = {detail, pending}) -
// Advisory only — the assistant NEVER submits, validates, or mutates a field. It
// grounds entirely in the pending list the screen already holds (Q-D: NO
// validate / audit / graph fetch is added here). Two chips echo the pending
// queue (workflow) and one routes the honest-missing / does-it-block question to
// the deterministic schema check (schema). No chip drives propose→stage→confirm.

// Shared verbatim by explain_pending_item whether nothing is selected or the
// selected id isn't in the pending list.
const SELECT_A_PENDING_FIELD: AssistantMessage = {
  text: 'Select a field below to see what it asks.',
  answeredFrom: 'workflow',
};

export const COMPLETE_CATALOG: GroundedChip[] = [
  {
    id: 'pending_summary',
    label: 'Which fields still need me?',
    source: 'workflow',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'complete') return null;
      const { pending } = state;
      if (!pending) return null; // data absent → chip disabled
      if (pending.length === 0) {
        return {
          text: 'This draft currently has no pending fields listed.',
          answeredFrom: 'workflow',
        };
      }
      // Mirror REVIEW_CATALOG.pending_summary's about → question → id ladder so
      // every item shows a usable label and the shown count always agrees with
      // the listed labels (joinCapped computes "…and K more" over the FULL list).
      const labels = pending.map((p) => {
        if (isUsableStr(p.about)) return p.about;
        if (isUsableStr(p.question)) return p.question;
        if (isUsableStr(p.id)) return p.id;
        return 'unnamed pending field';
      });
      const verb = pending.length === 1 ? 'needs' : 'need';
      return {
        text: `${count(pending.length, 'field')} ${verb} you: ${joinCapped(labels)}. Confirm or skip each below.`,
        answeredFrom: 'workflow',
      };
    },
  },
  {
    id: 'explain_pending_item',
    label: 'What does this question want?',
    source: 'workflow',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'complete') return null;
      const { pending, selectedPendingId } = state;
      const item = isUsableStr(selectedPendingId)
        ? (pending ?? []).find((p) => p.id === selectedPendingId)
        : undefined;
      if (!item) return SELECT_A_PENDING_FIELD;
      // `question` is the contract-guaranteed subject (ApiPendingItem.question is
      // non-optional) — not guarded; `about` is optional, so its clause drops
      // rather than render "about undefined". Terminate the first sentence with a
      // period only when it doesn't already end in terminal punctuation, so a
      // dropped about-clause never yields a double "?." (the question already
      // ends with "?").
      const lead = `${item.question}${isUsableStr(item.about) ? ` — about ${item.about}` : ''}`;
      const terminated = /[.!?]$/.test(lead) ? lead : `${lead}.`;
      return {
        text: `${terminated} Answer via propose → stage → confirm below.`,
        answeredFrom: 'workflow',
      };
    },
  },
  {
    id: 'missing_field_behavior',
    label: 'What if I leave one missing?',
    source: 'schema',
    routed: true,
    // Static/routed — never null within the complete context. States the
    // honest-missing behavior and routes the "does it block export?" truth
    // question to the deterministic schema check. Never echoes `validate.ok`.
    // (Does not reuse ROUTE_TO_VALIDATE: the approved copy uses a mid-sentence
    // lowercase "open Validate", not the const's sentence-leading "Open Validate".)
    resolve(state): AssistantMessage | null {
      if (state.context !== 'complete') return null;
      return {
        text:
          'Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks ' +
          'export is a schema question — open Validate to run the deterministic schema check.',
        answeredFrom: 'schema',
      };
    },
  },
];

// Neutral fallback when every complete chip resolves to null (defensive — the
// missing-field chip always answers within the complete context).
const COMPLETE_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'workflow',
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
    case 'evidence':
      return { catalog: EVIDENCE_CATALOG, fallback: EVIDENCE_FALLBACK };
    case 'complete':
      return { catalog: COMPLETE_CATALOG, fallback: COMPLETE_FALLBACK };
    default:
      throw new Error('compose: context not implemented yet');
  }
}

/**
 * Compose the reply + guided prompts for a screen from its already-fetched
 * state. `review` (P25.1), `export` (P25.4), `evidence` (P25.5) and `complete`
 * (P25.6) are wired; memory throws until its slice lands.
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
