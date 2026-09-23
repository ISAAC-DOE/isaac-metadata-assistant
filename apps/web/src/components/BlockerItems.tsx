import './blocker-items.css';
import { useId } from 'react';
import { Link } from 'react-router-dom';
import { CornerDownRight } from './icons';
import { HelpTip } from './HelpTip';
import { fieldPathLabel } from '../lib/recordMap';
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
const RUN_FIELD_LABEL = new Map(RUN_FIELDS.map((spec) => [spec.path, spec.label]));

export function findingFieldLabel(path: string): string | null {
  const trimmed = path.trim();
  if (trimmed === '' || trimmed === '$') return null;
  return RUN_FIELD_LABEL.get(trimmed) ?? fieldPathLabel(trimmed);
}

/** The Runs editor address for a run-level field, or `null` when there is none. */
export function goToFieldHref(
  experimentId: string | undefined,
  runId: string | null | undefined,
  path: string,
): string | null {
  if (!experimentId || !runId) return null;
  if (!RUN_FIELD_LABEL.has(path.trim())) return null;
  return `${ROUTES.recordRun(experimentId, runId)}&${RECORD_ADDRESS_PARAM}=${encodeURIComponent(
    `field:${path.trim()}`,
  )}`;
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
          href={goToFieldHref(experimentId, runId, err.path)}
        />
      ))}
    </>
  );
}

function BlockerItem({
  path,
  message,
  href,
}: {
  path: string;
  message: string;
  href: string | null;
}) {
  const subjectId = useId();
  const subject = findingFieldLabel(path);
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
        {href !== null && (
          <Link className="blocker-go" to={href}>
            <CornerDownRight size={13} strokeWidth={2} aria-hidden="true" />
            Go to Field
            <span className="sr-only"> {subject}</span>
          </Link>
        )}
      </span>
      <span className="blocker-message">{message}</span>
    </li>
  );
}
