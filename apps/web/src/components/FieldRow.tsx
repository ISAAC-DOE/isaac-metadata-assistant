import './fields.css';
import { useId } from 'react';
import { HelpTip } from './HelpTip';
import { StatusChip } from './StatusChip';
import { EvidenceRow } from './EvidenceRow';
import { FieldCaptureControl, canEnterOnRecord, captureHint } from './FieldCaptureControl';
import { fieldChipKind } from '../lib/status';
import type { DraftField } from '../lib/types';

interface FieldRowProps {
  field: DraftField;
  /**
   * How a value may be entered on THIS record, when the screen can offer it.
   *
   * Absent means this row is read-only wherever it is mounted — which is what every
   * mount that is not the record workbench gets, deliberately: a control needs the
   * record's id and its current version token, and a screen that does not hold both
   * cannot write. It is a prop rather than a context for that reason; the capability
   * is the caller's to grant, not this row's to assume.
   */
  capture?: {
    experimentId: string;
    /** The RECORD's current version token — both write operations here are the record's. */
    version: string;
    /** MUST be the SILENT refetch. See `FieldCaptureControl`'s `onSaved`. */
    onSaved: () => void;
  };
}

/**
 * One field in the envelope shape {value, unit?, status, evidence[]}, with a
 * route to its evidence. Missing/needs-you read honest and expected — never a
 * red error. No value is shown without a path to its evidence.
 *
 * A ROW MAY NOW BE A FIELD THE RECORD DOES NOT HOLD. `GET /draft` returns the group
 * skeleton — a row for every field path this build can extract into or write at — so a
 * created record renders its fields instead of nothing. Such a row carries
 * `present: false` with a `missing` status, and it is rendered exactly as an honestly
 * missing value has always been rendered: no error, no red, no claim that the record
 * holds anything.
 *
 * WHAT IS NEW IS THE SENTENCE UNDER IT, and it is per path rather than true on average.
 * Either the row offers a control (only where a RECORD-level route accepts a value and
 * the schema's own closed set arrived with it) or it says where the value is entered —
 * or that this version records none. The decision is `FieldCaptureControl`'s, from facts
 * the server derives from the sets its write routes enforce; nothing about writability
 * is decided here.
 */
export function FieldRow({ field, capture }: FieldRowProps) {
  const kind = fieldChipKind(field.status, field.source_types);
  const needsYou = field.status === 'needs_confirmation';
  const missing = field.status === 'missing' || field.status === 'rejected';
  const offering = canEnterOnRecord(field.capture) && capture !== undefined;
  /* The PATH is passed because one of the sentences is true of exactly one path — see
     `captureHint`'s own note on the export stamp. Nothing else about the copy varies by
     path; the rest is composed from the served facts. */
  const hint = captureHint(field.capture, offering, field.path);
  const labelId = useId();

  return (
    <div className="field-row" data-present={field.present === false ? 'false' : undefined}>
      {/* The human label leads; the official path is one `?` away (owner QA F1,
          2026-09-22) — never removed, because it is how a curator maps a field
          (`UX-014`). The tip is named generically and DESCRIBED by the label, so
          a page of rows does not offer forty controls all called "About …". */}
      <div className="field-label-col">
        <div className="field-label-row">
          <div className="field-label" id={labelId}>
            {field.label}
          </div>
          <HelpTip subject={field.label} label="Official Field Details" describedBy={labelId}>
            <span>
              Official field: <code className="field-path">{field.path}</code>
            </span>
          </HelpTip>
        </div>
      </div>

      <div className="field-value-col">
        <div className="field-value-row">
          {needsYou || missing ? (
            /*
             * ONE ANNOUNCEMENT, IN ONE REGISTER — UX casing conformance,
             * 2026-09-14.
             *
             * ~~`{needsYou ? 'awaiting your confirmation' : 'honestly missing'}`~~ —
             * two hardcoded lowercase literals (never in `LABELS`), rendered at
             * 12px italic in the VALUE slot, 10px to the left of a `<StatusChip>`
             * reading `Needs You` / `Missing` in Title Case. So one state was
             * announced TWICE in one 22px row, in two different registers, and
             * `casing-and-copy.md:12` puts "status chips, badge labels" in
             * Register 1 — which is the chip, not this span.
             *
             * THE CHIP WINS, and the value slot stops speaking. Three reasons,
             * in order of weight:
             *   1. The chip is the registry-driven status system (`CHIP_META` in
             *      `lib/status.ts`, icon + label, never colour alone). Its words
             *      are the spec's own approved ones — `casing-and-copy.md:53`
             *      maps the `pending` status to **`Needs You`**, which is
             *      `LABELS.chipNeedsYou` and is exactly what renders here now.
             *      Keeping the TEXT instead would have meant dropping the chip,
             *      deleting the icon and the amber attention affordance for
             *      precisely the two states that need them, and desynchronising
             *      this row from every other chip surface in the app.
             *   2. This column's job is the VALUE. When there is none, a dash is
             *      the honest placeholder; a second sentence about the status is
             *      not a value.
             *   3. `aria-hidden` on the dash means the row announces its status
             *      exactly once to a screen reader, where before it announced it
             *      twice in two vocabularies.
             *
             * NOTHING IS LOST IN WORDS. `mapFieldStatus` maps
             * `needs_confirmation` -> `needsYou` and `missing`/`rejected` ->
             * `missing`, so the chip's condition is byte-for-byte this branch's
             * condition — the two states stay distinguishable. The row's own
             * prose (`.field-helper`, `.field-capture-hint`) still says in
             * Register 2 where the value is entered, and the styling that made
             * this slot read as "not a value" (`.field-value.awaiting`: sans,
             * italic, muted) is untouched and still does that work.
             *
             * THE APPROVED PROSE IS ELSEWHERE AND IS NOT THIS.
             * `casing-and-copy.md:67` approves "Leave honestly missing — a blank
             * stays blank until you confirm it" as Register 2 copy, and
             * `LABELS.actionDontKnow` ("I don't know — leave honestly missing")
             * renders it on /complete. That sentence is DELIBERATELY unchanged;
             * it is prose a reader acts on, not a label in a status slot.
             */
            <span className="field-value awaiting" aria-hidden="true">
              —
            </span>
          ) : (
            <span className="field-value">
              {String(field.value)}
              {field.unit ? ` ${field.unit}` : ''}
            </span>
          )}
          <StatusChip kind={kind} />
        </div>

        {field.helper && <p className="field-helper">{field.helper}</p>}

        {field.evidence && field.evidence.length > 0 && !needsYou && (
          <div className="field-evidence">
            {field.evidence.map((ev, i) => (
              <EvidenceRow evidence={ev} key={i} />
            ))}
          </div>
        )}

        {/*
          THE CONTROL, OR THE SENTENCE — never both, and never neither when the server
          said something. `capture` being absent is what makes every other mount of this
          row read-only; the hint is still shown there, because "this value is entered on
          a run" is true wherever it is read and costs nothing to say.
        */}
        {offering && capture ? (
          <FieldCaptureControl
            field={field}
            experimentId={capture.experimentId}
            version={capture.version}
            onSaved={capture.onSaved}
          />
        ) : (
          hint !== null && <p className="field-capture-hint">{hint}</p>
        )}
      </div>
    </div>
  );
}
