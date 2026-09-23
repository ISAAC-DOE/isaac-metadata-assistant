import './blocker-items.css';
import { useId } from 'react';
import { Link, useInRouterContext } from 'react-router-dom';
import { CornerDownRight } from './icons';
import { HelpTip } from './HelpTip';
import { fieldLabel, isRunFieldPath, officialPathOf } from '../lib/fieldLabels';
import { RUN_FIELDS } from '../lib/runFields';
import { RECORD_ADDRESS_PARAM, ROUTES } from '../lib/routes';

/**
 * ONE VALIDATOR FINDING PER ROW, IN THE SCIENTIST'S WORDS FIRST (owner QA V1,
 * DEC-30; 2026-09-22).
 *
 * Each row names the FIELD in human words where the finding's own `path` names
 * one, shows the validator's sentence VERBATIM (paraphrasing a schema error would
 * change what the validator said), keeps the official path one `?` away (never
 * removed — `UX-014`), and offers `Go to Field` ONLY where a real destination
 * exists: one of the five run-level fields the Runs editor renders an input for,
 * on a run the finding is addressed to. Everything else gets no control at all —
 * a disabled one would still read as an offer.
 *
 * WHAT IT NEVER DOES: infer a subject from the message text. The whole-document
 * sentinel `$` (an error with an empty path, `official.py`'s convention) names no
 * field, so its row says nothing about a subject — DEC-30's rule for an absent
 * `kind`, applied to the path.
 *
 * Renders `<li>` items only; each caller keeps its own `<ul>` and class, because
 * three surfaces style and test their lists independently.
 */
/** Moved to `lib/fieldLabels.ts`; kept exported under its old name for callers. */
export const findingFieldLabel = fieldLabel;

/** The Runs editor address for a run-level field, or `null` when there is none. */
export function goToFieldHref(
  experimentId: string | undefined,
  runId: string | null | undefined,
  path: string,
): string | null {
  return goToDestination(experimentId, runId, path)?.href ?? null;
}

/**
 * The record blocks the Record Fields view renders as a section of their own — the
 * four draft blocks (`data-draft-block`). A finding under one of these can link to
 * that section, and the view expands it on arrival (`?at=block:<name>`).
 */
const RECORD_FIELD_SECTIONS = new Set(['system', 'sample', 'timestamps', 'context']);
/** Blocks answered on Complete Metadata (the spectrum, QC verdict, descriptors). */
const COMPLETE_METADATA_BLOCKS = new Set(['measurement', 'descriptors']);

export interface FindingDestination {
  href: string;
  /** The words on the control — it names where it goes, not a generic "go". */
  label: string;
}

/**
 * WHERE A FINDING CAN SEND THE READER, OR `null` WHEN NOWHERE REAL EXISTS
 * (review #277, I-9; DEC-30 — a non-action must not look clickable).
 *
 * jsonschema reports a missing `required` property at its PARENT's path, and the
 * structured detail that would name the missing child (`validator_value`) is dropped
 * inside the truth plane (`OfficialError` keeps only path and message), which this
 * slice does not touch. So the destination is derived from the PATH alone, most
 * specific first — and the message text is never parsed:
 *
 *   1. a run-level field, on a run → that field's input on the run form;
 *   2. a parent of run-level fields (`context`, `timestamps`, …), on a run → the
 *      run form's Conditions section;
 *   3. under the spectrum / QC / descriptors → Complete Metadata, where they are
 *      answered;
 *   4. under a block the Record Fields view renders as a section → that section,
 *      expanded on arrival.
 *
 * `$` (the whole document) and every other path get no control.
 */
export function goToDestination(
  experimentId: string | undefined,
  runId: string | null | undefined,
  path: string,
): FindingDestination | null {
  const trimmed = officialPathOf(path);
  if (!experimentId || trimmed === '' || trimmed === '$') return null;
  if (runId && isRunFieldPath(trimmed)) {
    return {
      href: `${ROUTES.recordRun(experimentId, runId)}&${RECORD_ADDRESS_PARAM}=${encodeURIComponent(
        `field:${trimmed}`,
      )}`,
      label: 'Go to Field',
    };
  }
  if (runId && RUN_FIELDS.some((spec) => spec.path.startsWith(`${trimmed}.`))) {
    return {
      href: `${ROUTES.recordRun(experimentId, runId)}&${RECORD_ADDRESS_PARAM}=${encodeURIComponent(
        'section:run-conditions',
      )}`,
      label: 'Go to Run Conditions',
    };
  }
  const block = trimmed.split('.')[0];
  if (COMPLETE_METADATA_BLOCKS.has(block)) {
    return { href: ROUTES.complete(experimentId), label: 'Go to Complete Metadata' };
  }
  if (RECORD_FIELD_SECTIONS.has(block)) {
    return {
      href: `${ROUTES.record(experimentId)}?view=fields&${RECORD_ADDRESS_PARAM}=${encodeURIComponent(
        `block:${block}`,
      )}`,
      label: 'Go to Section',
    };
  }
  return null;
}

export function BlockerItems({
  errors,
  experimentId,
  runId,
}: {
  errors: readonly { path: string; message: string }[];
  /** With `runId`, enables `Go to Field` for the five run-level fields. */
  experimentId?: string;
  runId?: string | null;
}) {
  return (
    <>
      {errors.map((err, j) => (
        <BlockerItem
          // `err.path` is NOT unique — several missing required properties all
          // report at `$` — so the index is part of the key.
          key={`${j}:${err.path}`}
          path={err.path}
          message={err.message}
          destination={goToDestination(experimentId, runId, err.path)}
        />
      ))}
    </>
  );
}

function BlockerItem({
  path,
  message,
  destination,
}: {
  path: string;
  message: string;
  destination: FindingDestination | null;
}) {
  const subjectId = useId();
  const subject = findingFieldLabel(path);
  /* A plain anchor outside a router (a component rendered on its own); a client-side
     `Link` everywhere the app actually mounts it. */
  const inRouter = useInRouterContext();
  return (
    <li className="blocker-item">
      <span className="blocker-head">
        {subject !== null && (
          <span className="blocker-subject" id={subjectId}>
            {subject}
          </span>
        )}
        {subject !== null && (
          <HelpTip subject={subject} label="Official Field Details" describedBy={subjectId}>
            <span>
              Official field: <code className="blocker-path">{path}</code>
            </span>
          </HelpTip>
        )}
        {destination !== null &&
          (() => {
            const body = (
              <>
                <CornerDownRight size={13} strokeWidth={2} aria-hidden="true" />
                {destination.label}
                {subject !== null && <span className="sr-only"> — {subject}</span>}
              </>
            );
            return inRouter ? (
              <Link className="blocker-go" to={destination.href}>
                {body}
              </Link>
            ) : (
              <a className="blocker-go" href={destination.href}>
                {body}
              </a>
            );
          })()}
      </span>
      <span className="blocker-message">{message}</span>
    </li>
  );
}
