import './evidence.css';
import { sourceIcon } from './icons';
import { OriginChip } from './ProvenanceChips';
import { SOURCE_TYPE_ORIGIN } from '../lib/provenance';
import type { FieldEvidence, SourceType } from '../lib/types';

const SRC_CLASS: Record<SourceType, string> = {
  spreadsheet: 'src-spreadsheet',
  file_listing: 'src-filelisting',
  derivation: 'src-derivation',
  user_confirmation: 'src-userconf',
  document: 'src-filelisting',
  screenshot: 'src-filelisting',
  web_form: 'src-filelisting',
};

/**
 * A neutral chip + colored source-type icon + the source type IN WORDS (QA A-15).
 *
 * Tolerates a source type this build does not know: the glyph falls back (see
 * `sourceIcon`) and the label still prints the stored string verbatim, so an
 * unrecognised kind is shown as itself rather than crashing the surface it is on.
 * This token is mounted on the record workbench field rows AND in the Evidence
 * sidecar detail, so the crash it used to cause had two blast radii, not one.
 */
/**
 * A source type in words (QA A-15): `user_confirmation` → "User Confirmation".
 *
 * CASING AND SEPARATORS ONLY — the `enumOptionLabel` contract: every output word is
 * an input word, so nothing is glossed or invented. The stored token is kept, exactly,
 * in the chip's `title` and `data-source-type` for a curator who maps by it.
 */
export function evidenceSourceLabel(sourceType: string): string {
  return sourceType
    .split('_')
    .filter((word) => word !== '')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * A source type in words when THIS BUILD KNOWS it, verbatim otherwise — the one rule
 * every surface shows a source type by (review minor: the asset evidence list put an
 * unrecognised type in words while this token printed it as stored).
 */
export function sourceTypeWords(sourceType: string): string {
  return Object.prototype.hasOwnProperty.call(SRC_CLASS, sourceType)
    ? evidenceSourceLabel(sourceType)
    : sourceType;
}

export function SourceTypeToken({ sourceType }: { sourceType: SourceType }) {
  const Icon = sourceIcon(sourceType);
  const cls = SRC_CLASS[sourceType] ?? 'src-unknown';
  const stored = typeof sourceType === 'string' && (sourceType as string) !== '';
  /* Only a type THIS BUILD KNOWS is put in words; an unrecognised one is still printed
     verbatim, as this token always has (see the note above). */
  const known = stored && Object.prototype.hasOwnProperty.call(SRC_CLASS, sourceType);
  return (
    <span
      className={`src-token ${cls}`}
      title={stored ? sourceType : undefined}
      data-source-type={stored ? sourceType : undefined}
    >
      <Icon size={12} strokeWidth={2} aria-hidden="true" />
      {!stored
        ? 'source type not recorded'
        : known
          ? evidenceSourceLabel(sourceType)
          : sourceType}
    </span>
  );
}

/**
 * One evidence entry — the compact citation on S3 field rows. Source type is
 * icon + mono label; user_confirmation carries the human motif, distinct from
 * machine-extracted evidence. Never hidden behind a hover-only tooltip.
 */
export function EvidenceRow({ evidence }: { evidence: FieldEvidence }) {
  return (
    <div className="ev-row">
      <SourceTypeToken sourceType={evidence.source_type} />
      {/* THE ORIGIN DIMENSION, ADDED BESIDE the existing detail rather than
          instead of it — the exact source type, the rule, the confirmation, the
          file, the locator and the quote all still render below. A citation has
          an ORIGIN; it has no review state of its own, because what establishes a
          value is a property of the field, not of one of its citations. That
          asymmetry is why only one chip appears here and the pair appears on the
          trail entry. An unrecognised source type falls back to `evidence` —
          "a citation exists, its channel is not one this build can name" — never
          to `unknown`, which would claim nothing is recorded. */}
      <OriginChip origin={SOURCE_TYPE_ORIGIN[evidence.source_type] ?? 'evidence'} />
      {evidence.source_type === 'derivation' && evidence.rule && (
        <span className="ev-rule">rule: {evidence.rule}</span>
      )}
      {evidence.source_type === 'user_confirmation' && (
        <span className="ev-userconf">confirmed by you{evidence.answer ? ` · ${evidence.answer}` : ''}</span>
      )}
      {evidence.source_file && <span className="ev-file">{evidence.source_file}</span>}
      {evidence.locator && evidence.source_type !== 'derivation' && (
        <span className="ev-locator">{evidence.locator}</span>
      )}
      {evidence.quote && <span className="ev-quote">"{evidence.quote}"</span>}
    </div>
  );
}
