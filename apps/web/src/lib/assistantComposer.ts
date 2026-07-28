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
 * `evidence` (Evidence Explorer, P25.5), `complete` (Guided Completion, P25.6)
 * and `memory` (Project Memory, P25.7) are all wired.
 */

import {
  NO_BLOCKING_ISSUES,
  VALIDATION_UNAVAILABLE_SUMMARY,
  blockingSummary,
  count,
  isValidationUnavailable,
  joinCapped,
  technicalPaths,
} from './assistantPaths';
import { ROUTES } from './routes';
import type {
  ApiValidateResult,
  AssistantAction,
  AssistantActionKind,
  AssistantMessage,
  ComposerOutput,
  GroundedChip,
  GroundingState,
  SuggestedPrompt,
} from './types';

// P36V.1 Unit B — `count` and `joinCapped` now live in `./assistantPaths`, so
// there is exactly ONE implementation of each per language (the blocker summary
// needs both, and duplicating them was how the two producers were free to drift).
// Re-exported unchanged: it is part of this module's existing public surface.
export { count };

// A string is "usable" only when it is present and non-empty after trim. This
// guards every interpolated field so `undefined` / `null` / an empty value can
// never reach rendered output (Fix 6a/6b).
function isUsableStr(x: unknown): x is string {
  return typeof x === 'string' && x.trim() !== '';
}

/**
 * P36V S-B — the ONE navigation action this composer can attach: open the
 * deterministic Validator (Governance & Safety → Validator).
 *
 * It REPLACES the retired prose sentence `'Open Validate to run the
 * deterministic schema check.'`, which was appended to exactly these routed
 * truth answers and named a control the app never rendered — the "action" was a
 * sentence, not a button. The producing CONDITIONS are unchanged: the same three
 * chips, under the same guards, in the same contexts.
 *
 * `to` is an in-app client route with a `?tab=` deep link, so the router's
 * `basename` (the deployed `/krish` base path) is applied automatically and the
 * Validator tab is genuinely selected on arrival. Offering it mutates nothing:
 * it validates nothing, runs nothing, and changes no validation result.
 *
 * `Object.freeze` is real, not decorative: this ONE descriptor object is shared
 * by every answer that carries the action (the composer hands out the same
 * reference, and `AssistantPanel.ask` copies that reference onto the live turn),
 * so a mutation anywhere would rewrite the navigation target everywhere. Frozen,
 * it cannot. (P36V review, M4 — a comment already described it as frozen.)
 */
export const OPEN_VALIDATOR_ACTION: AssistantAction = Object.freeze({
  kind: 'open-validator',
  label: 'Open Validator',
  to: `${ROUTES.governance}?tab=validator`,
});

/**
 * P36V.1 Unit B — the CLOSED local catalog of navigation actions, keyed by kind.
 *
 * It exists because the free-form Assistant answer now carries an action over the
 * WIRE (`AssistantQueryResponse.action`, emitted by
 * `apps/api/isaac_api/assistant_query.py`). The panel resolves a wire action
 * through this catalog rather than rendering the wire's own `label`/`to`, so the
 * frontend stays the single owner of the visible label and of the client route the
 * router resolves under its `basename`. A kind this build does not know is dropped,
 * never rendered.
 */
export const ASSISTANT_ACTIONS: Readonly<Record<AssistantActionKind, AssistantAction>> =
  Object.freeze({ 'open-validator': OPEN_VALIDATOR_ACTION });

/**
 * Resolve an UNTRUSTED wire action to this build's frozen descriptor for that
 * kind, or `undefined`. Total: never throws for any shape.
 *
 * The wire's `label`/`to` are deliberately NOT trusted for rendering — the backend
 * emits them so the API response is self-describing, and
 * `apps/api/tests/test_assistant_query.py` + `open-validator-action.test.tsx` pin
 * them equal to this catalog, but presentation and routing stay frontend-owned.
 */
export function resolveAssistantAction(raw: unknown): AssistantAction | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const kind = (raw as { kind?: unknown }).kind;
  if (typeof kind !== 'string') return undefined;
  return Object.prototype.hasOwnProperty.call(ASSISTANT_ACTIONS, kind)
    ? ASSISTANT_ACTIONS[kind as AssistantActionKind]
    : undefined;
}

/**
 * The blocking-paths answer, shared verbatim by the Record Workbench (§5.1) and
 * Ready to Export (§5.2 — "Same template as §5.1") so the two can never drift.
 * It states a COUNT of blocking locations + the first ≤3 locations + the Open
 * Validator ACTION (P36V S-B; previously a dead prose sentence). It NEVER echoes
 * `validate.ok` or concludes validity. `null` when the validation payload is
 * absent → the chip is disabled, so no action is offered either.
 *
 * P36V.1 Unit B — the locations are HUMANIZED by the shared formatter
 * (`./assistantPaths`, mirrored in `assistant_paths.py`) instead of interpolating
 * the raw JSONPath list. The old copy rendered a root-level violation as its
 * literal locator — "1 path is listed as blocking export: $." — which reads as a
 * field name and names nothing actionable. The EXACT locators are preserved on
 * `technicalPaths`, which the panel shows only inside a collapsed
 * `Technical Details` disclosure. No validation semantics changed: the same
 * `validate.errors` list, the same count, the same chip conditions.
 *
 * P36V.1 review IMPORTANT-1 — the CRASH SENTINEL is separated from a genuine
 * root-level finding before any of that. `POST /api/experiments/{id}/validate`
 * returns `[{path: '$', message: 'Validation could not be completed.'}]` when the
 * dry-run itself raised; read through the locator formatter that is
 * indistinguishable from a root-level violation, and the humanized copy told the
 * reader "1 record-level validation issue may be blocking export" when the
 * validator had located NO issue at all. The route is not changed (it is not this
 * unit's file, and its payload is correct); the interpretation is. No count and no
 * location are claimed, and no locator is disclosed — there is none to disclose.
 */
function blockingPathsMessage(validate: ApiValidateResult | undefined | null): AssistantMessage | null {
  if (!validate) return null; // data absent → chip disabled
  const errors = validate.errors;
  if (isValidationUnavailable(errors)) {
    return {
      text: VALIDATION_UNAVAILABLE_SUMMARY,
      answeredFrom: 'schema',
      action: OPEN_VALIDATOR_ACTION,
    };
  }
  if (errors.length === 0) {
    return {
      text: NO_BLOCKING_ISSUES,
      answeredFrom: 'schema',
      action: OPEN_VALIDATOR_ACTION,
    };
  }
  const paths = errors.map((e) => e.path);
  return {
    text: blockingSummary(paths),
    answeredFrom: 'schema',
    action: OPEN_VALIDATOR_ACTION,
    technicalPaths: technicalPaths(paths),
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
      const { record_filename, sidecar_filename } = state.bundle.artifacts;
      // isUsableStr uniformly handles null / undefined / empty-string, so a
      // filename is echoed ONLY when it is a present, non-empty string. These
      // are safe basenames (P30.6) — never an absolute server/mount path.
      const hasRecord = isUsableStr(record_filename);
      const hasSidecar = isUsableStr(sidecar_filename);
      if (hasRecord && hasSidecar) {
        return {
          text: `Exported: record ${record_filename} and its evidence sidecar ${sidecar_filename}.`,
          answeredFrom: 'workflow',
        };
      }
      if (hasRecord) {
        return {
          text: `Exported: record ${record_filename}. No evidence sidecar filename is recorded.`,
          answeredFrom: 'workflow',
        };
      }
      if (hasSidecar) {
        return {
          text: `Exported: evidence sidecar ${sidecar_filename}. No record filename is recorded.`,
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
    // P36V S-B — the retired trailing clause ("— open Validate to run the
    // deterministic schema check") was the SAME dead prose in its mid-sentence
    // lowercase form. It is now the real OPEN_VALIDATOR_ACTION control; the rest
    // of the approved copy is untouched, and the chip's condition (any
    // `complete` context) is unchanged.
    resolve(state): AssistantMessage | null {
      if (state.context !== 'complete') return null;
      return {
        text:
          'Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks ' +
          'export is a schema question.',
        answeredFrom: 'schema',
        action: OPEN_VALIDATOR_ACTION,
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

// --- Project Memory (context: 'memory'; state = graph status only) -----------
// P25.7. Grounds ENTIRELY in the already-fetched GET /api/graph/status response
// the screen holds (Q: NO new fetch, no graph/graphify import). The memory plane
// reports FOUR independent axes — availability (primary), integrity,
// memory_policy, indexed_sources — and the assistant NEVER collapses them into
// one universal freshness/valid/invalid word (§6). Every reply carries the
// leads-to-verify framing and answers from `graph` (→ "Project Memory"); none
// states a validation verdict, claims related records, similarity, audit,
// export-readiness, scientific truth, or that a file was directly inspected.
//
// The catalog is chosen by `availability`: available → three chips
// (provenance / freshness / scope); unavailable → a SINGLE replacement chip —
// never four chips at once (§5.5).

// The leads-to-verify tail shared by the provenance, freshness, and scope chips.
const MEMORY_LEADS_TAIL =
  'Project memory returns leads to verify — never a validation verdict.';

export const MEMORY_CATALOG: GroundedChip[] = [
  {
    id: 'memory_provenance',
    label: 'Where do these leads come from?',
    source: 'graph',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'memory') return null;
      const { provider } = state.graph;
      // Drop the parenthetical when the provider is absent, empty, or the
      // 'unavailable' sentinel — never render "(provider: unavailable)" or a
      // dangling "(provider: )".
      const providerClause =
        isUsableStr(provider) && provider !== 'unavailable' ? ` (provider: ${provider})` : '';
      return {
        text: `Leads come from indexed project files and concepts${providerClause}. ${MEMORY_LEADS_TAIL}`,
        answeredFrom: 'graph',
      };
    },
  },
  {
    id: 'memory_freshness',
    label: 'Is project memory current?',
    source: 'graph',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'memory') return null;
      const { integrity, memory_policy, indexed_sources } = state.graph;
      // Base line echoes each axis value verbatim; the per-axis caveats (§6) are
      // then appended as SEPARATE sentences (the single documented exception to
      // the ≤1-caveat density rule). Faithful separation wins over collapsing:
      // in the realistic available state at most policy + indexed contribute
      // caveats (integrity is verified when available), so the reply stays ≤3
      // sentences; a type-constructed all-degraded available state may add the
      // integrity caveat too — still each axis stated precisely, never merged.
      let text =
        `Snapshot integrity: ${integrity}; policy consistency: ${memory_policy}; ` +
        `indexed sources: ${indexed_sources}.`;

      if (integrity === 'malformed' || integrity === 'unsupported' || integrity === 'unknown') {
        text += ` Snapshot integrity is ${integrity} — the snapshot artifact itself could not be fully verified.`;
      }

      if (memory_policy === 'stale') {
        text +=
          ' The shipped sanitization/exclusion policy or its versions differ from what this snapshot was built under.';
      } else if (memory_policy === 'unknown') {
        text += ' Policy consistency: comparison could not be established.';
      }

      // `indexed_sources` is never `stale` at runtime — real content drift is
      // CI-only (§6). We deliberately emit NOTHING for a `stale` value from live
      // status; only `unknown` yields a caveat. (Documented-but-unreachable: a
      // future runtime surfacing `stale` would use its own wording — never here.)
      if (indexed_sources === 'unknown') {
        text += ' Indexed-source status: comparison could not be established.';
      }

      // Leads-to-verify framing is the FINAL sentence of every memory reply,
      // appended after all per-axis caveats (CQ-2).
      text += ` ${MEMORY_LEADS_TAIL}`;

      return { text, answeredFrom: 'graph' };
    },
  },
  {
    id: 'included_scope',
    label: 'What sources are included?',
    source: 'graph',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'memory') return null;
      // Grounds on `file_count` (the "Indexed files" figure the screen renders),
      // NOT served_file_count (withheld by the screen) and NOT any invented
      // count. Null → the honest unavailable-count string, never a fabrication.
      const { file_count } = state.graph;
      if (file_count == null) {
        return {
          text: `The indexed-file count is unavailable for this snapshot. ${MEMORY_LEADS_TAIL}`,
          answeredFrom: 'graph',
        };
      }
      return {
        text:
          `This snapshot indexes ${count(file_count, 'project file')}. That scope covers files ` +
          `already in the snapshot; newly added indexable files require a Graphify refresh. ${MEMORY_LEADS_TAIL}`,
        answeredFrom: 'graph',
      };
    },
  },
];

// The single replacement chip shown when `availability === 'unavailable'`. Uses
// the approved frontend string (NOT raw `graph.note`, NOT the retired "answered
// from source files directly"): the assistant performs no source lookup.
export const MEMORY_UNAVAILABLE_CATALOG: GroundedChip[] = [
  {
    id: 'memory_unavailable',
    label: 'Why is memory unavailable?',
    source: 'graph',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'memory') return null;
      return {
        text: 'Project Memory is unavailable, so no memory-based answer is available here.',
        answeredFrom: 'graph',
      };
    },
  },
];

// Neutral fallback when every memory chip resolves to null (defensive — memory
// chips always answer within the memory context).
const MEMORY_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'graph',
};

// Per-context chip catalog + neutral fallback. The memory catalog additionally
// depends on `availability`, so the picker reads the full state.
function pickCatalog(state: GroundingState): {
  catalog: GroundedChip[];
  fallback: AssistantMessage;
} {
  switch (state.context) {
    case 'review':
      return { catalog: REVIEW_CATALOG, fallback: REVIEW_FALLBACK };
    case 'export':
      return { catalog: EXPORT_CATALOG, fallback: EXPORT_FALLBACK };
    case 'evidence':
      return { catalog: EVIDENCE_CATALOG, fallback: EVIDENCE_FALLBACK };
    case 'complete':
      return { catalog: COMPLETE_CATALOG, fallback: COMPLETE_FALLBACK };
    case 'memory':
      // available → 3 chips; unavailable → the single replacement chip. Never
      // both at once.
      return state.graph.availability === 'available'
        ? { catalog: MEMORY_CATALOG, fallback: MEMORY_FALLBACK }
        : { catalog: MEMORY_UNAVAILABLE_CATALOG, fallback: MEMORY_FALLBACK };
    default: {
      // Exhaustiveness guard: every ScreenContext is handled above.
      const _exhaustive: never = state;
      throw new Error(`compose: unhandled context ${(_exhaustive as { context: string }).context}`);
    }
  }
}

/**
 * Compose the reply + guided prompts for a screen from its already-fetched
 * state. `review` (P25.1), `export` (P25.4), `evidence` (P25.5), `complete`
 * (P25.6) and `memory` (P25.7) are wired.
 */
export function compose(state: GroundingState): ComposerOutput {
  const { catalog, fallback } = pickCatalog(state);

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
