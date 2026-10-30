import './propose-term-link.css';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from './icons';
import { api } from '../lib/api';
import { ROUTES } from '../lib/routes';
import {
  canProposeTerm,
  categoryKeyOf,
  proposeTermHref,
  type ApiSchemaVocabulary,
  type ProposeSource,
} from '../lib/schemaProposals';

/**
 * "PROPOSE THIS TERM" — a link from a screen that shows a value outside a fixed list to the
 * Schema Proposals form, with the list and the value filled in.
 *
 * IT IS RENDERED ONLY WHEN THE LIST IS A REAL PORTAL TERM LIST, the value is not already on it
 * (not even as a near-spelling), and it has the shape the server accepts — all read from the
 * server's own vocabulary (`GET /api/schema-proposals/vocabulary`, including its `term_shape`
 * rules), via `canProposeTerm`. A schema enum the portal has no list for, a free-text field, a
 * phrase with a space, an empty value or a vocabulary that could not be read all render
 * NOTHING. The server remains the judge on save (e.g. a pending duplicate), which a link cannot see.
 *
 * It is navigation and nothing more: nothing is saved, nothing is sent, and the value is not
 * changed on the way (the form shows it as it was, and the server checks it).
 *
 * IT OPENS IN A NEW TAB. The screens it sits on hold work in progress — a record pasted into the
 * Validator, a half-typed run override — that a same-tab navigation discarded. The house pattern
 * for a link that leaves the page (`settings/AssistantCompanion.tsx`): `target="_blank"` with
 * `rel="noopener noreferrer"`, an icon, and the accessible name saying it opens a new tab.
 */
export function ProposeTermLink({
  fieldPath,
  term,
  from,
  className,
  vocabulary: given,
}: {
  /** The field's path as the surface knows it; array indices and `[]` are dropped. */
  fieldPath: string;
  /** The value the surface showed. Anything but a non-empty string renders nothing. */
  term: unknown;
  from: ProposeSource;
  className?: string;
  /** A vocabulary the caller already read; when given, none is fetched here. */
  vocabulary?: ApiSchemaVocabulary;
}) {
  const fetched = useSchemaVocabulary(given === undefined && typeof term === 'string' && term.trim() !== '');
  const vocabulary = given ?? fetched;
  if (vocabulary === null) return null;
  const category = categoryKeyOf(fieldPath);
  if (!canProposeTerm(vocabulary, category, term)) return null;
  return (
    <Link
      className={className ?? 'propose-term-link'}
      to={proposeTermHref(ROUTES.schemaProposals, { category, term, from })}
      target="_blank"
      rel="noopener noreferrer"
      /* The accessible name STARTS with the visible text (WCAG 2.5.3), then says which, and that it
         opens a new tab (the icon says so visually). */
      aria-label={`Propose this term: ${term}, for ${category} (opens in a new tab)`}
      title="Opens in a new tab"
    >
      Propose this term
      <ExternalLink size={12} strokeWidth={2.2} aria-hidden="true" className="propose-term-link-icon" />
    </Link>
  );
}

/** The vocabulary, read once per mount and only when `enabled`; `null` until (or unless) it arrives. */
export function useSchemaVocabulary(enabled: boolean): ApiSchemaVocabulary | null {
  const [vocabulary, setVocabulary] = useState<ApiSchemaVocabulary | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    api
      .getSchemaVocabulary()
      .then((v) => {
        if (live) setVocabulary(v);
      })
      .catch(() => {
        // Unreadable vocabulary: no link. The surface's own refusal still stands on its own.
      });
    return () => {
      live = false;
    };
  }, [enabled]);
  return vocabulary;
}
