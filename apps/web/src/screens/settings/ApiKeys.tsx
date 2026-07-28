/**
 * Settings → API Access → the key/access surface (P36V PR3 slice C; restructured
 * by P36V-1 slices 11 & 13).
 *
 * This surface exists to tell the truth about a capability this build does NOT
 * have. The backend audit that decided its content:
 *
 *   `apps/api/isaac_api/auth.py` is a single process-wide shared credential read
 *   from one environment variable at construction time and compared with
 *   `secrets.compare_digest` on every request except `GET {base}/api/health` and
 *   `OPTIONS`. There is no per-key identity, no hashed storage, no expiry, no
 *   scopes, and — confirmed by grepping the whole of `apps/api` — no operation
 *   anywhere that creates, lists, revokes or rotates a credential. The generated
 *   contract the Endpoint Explorer renders is the proof: it lists every
 *   operation this API has, and none of them is key management.
 *
 * So the classification is UNAVAILABLE, and the screen is built as a complete,
 * deliberate unavailable state rather than a broken one:
 *
 *   · no key is ever generated, displayed, or partially displayed;
 *   · nothing is read from or written to `localStorage`, `sessionStorage`, or a
 *     cookie — this module contains no storage or cookie access at all;
 *   · there is no input, no field, and no control that cannot function;
 *   · the Create control is a really-`disabled` native button with a
 *     programmatically associated reason (`aria-describedby`), not an enabled
 *     control that silently does nothing;
 *   · there is no error banner and no simulated loading failure: nothing failed.
 *
 * Real key management is deliberately NOT stubbed. It would need durable
 * credential storage, per-key identity, revocation and scopes — a later,
 * separately authorized phase.
 *
 * LAYOUT (slice 11). The old version was one 74ch column inside a 1200px card,
 * so half the page was empty (plan §2.7). The arrangement is now:
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ status banner: icon · heading + one paragraph · → Explorer    │  full width
 *   ├───────────────────────────────────┬──────────────────────────┤
 *   │ How Access Works Today (rows)     │ Create API Key           │  2 columns
 *   │                                   │ + Technical Requirements │
 *   ├───────────────────────────────────┴──────────────────────────┤
 *   │ Your API Keys — the intentional empty state                   │  full width
 *   └──────────────────────────────────────────────────────────────┘
 *
 * The banner spends its width on a real second element (the Explorer action,
 * pushed to the trailing edge) instead of trailing whitespace, and the grid
 * splits the 1200px measure into two columns that each hold prose at a readable
 * measure — the `.settings-provenance-note { max-width: 80ch }` precedent
 * applied to a box rather than only to the text inside it. Below 900px the grid
 * is one column in the same source order; below 720px the disabled control goes
 * full width. Nothing scrolls sideways: this surface has no table and no `pre`.
 *
 * CONCISION (slice 13). Every string here comes from `lib/settingsContent.ts`,
 * which holds each claim exactly once, and each is rendered in exactly one
 * place: status → the banner · access model, external agents and the hosted
 * boundary → one access row each · why the button is disabled → the button's own
 * reason · the backend contract that would be needed → the Technical
 * Requirements disclosure · the empty list → the empty state. Nothing restates
 * anything above it, and the bearer-header / 401-count facts belong to Quick
 * Start, which derives them from the contract instead of asserting them.
 *
 * ON THE BANNER'S RETIRED AUTHENTICATION SUMMARY — the record, corrected. The
 * slice-13 report said the banner's authentication summary and the left column's
 * access model were merged because the two were "judged identical". They are not
 * identical, and that was never the reason: the banner carries the key-management
 * STATUS (`statusHeading` / `statusBody` — no operation exists to issue a key),
 * while `API_ACCESS_ROWS[0] 'Current Access Model'` describes the one
 * deployment-wide credential that does exist. Two different claims. What actually
 * happened is that a banner-level authentication SUMMARY — a third paraphrase of
 * material Quick Start derives from the contract and the access rows state
 * canonically — was consciously dropped, so each claim is stated exactly once.
 * That is the right call under slice 13; the stated rationale was wrong.
 *
 * LANDMARKS. This surface has FOUR headed regions and it is nested inside the
 * tab's own `settings-card` region, which was five `region` landmarks on one tab —
 * landmark inflation that makes a landmark list useless for navigation. The four
 * `<section>` elements are kept for document sectioning but carry no accessible
 * name, so they are not landmarks; their `<h3>`s still structure the outline,
 * which is how a screen-reader user navigates within a panel. The single landmark
 * on the tab is the card, named by the tab's own heading.
 */
import { Lock, ChevronRight } from '../../components/icons';
import {
  API_ACCESS_COPY,
  API_ACCESS_ROWS,
  API_KEY_REQUIREMENTS,
} from '../../lib/settingsContent';

/** The `aria-describedby` target for the disabled Create control. */
const CREATE_REASON_ID = 'settings-api-create-reason';

export function ApiKeysPanel({ onOpenExplorer }: { onOpenExplorer: () => void }) {
  return (
    <div className="api-access">
      {/* THE status, said once. Everything below answers a different question. */}
      <section className="api-access-banner">
        <Lock size={16} strokeWidth={2} aria-hidden="true" className="api-access-banner-icon" />
        <div className="api-access-banner-body">
          <h3 className="api-keys-heading">{API_ACCESS_COPY.statusHeading}</h3>
          <p className="api-keys-lead">{API_ACCESS_COPY.statusBody}</p>
        </div>
        {/* The banner's trailing edge carries the one action the status implies,
            so the full measure holds content rather than empty space. */}
        <div className="api-access-banner-action">
          <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
            Endpoint Explorer
            <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </div>
      </section>

      <div className="api-access-grid">
        <section className="api-access-col">
          <h3 className="api-keys-heading">How Access Works Today</h3>
          <dl className="api-keys-rows">
            {API_ACCESS_ROWS.map((row) => (
              <div className="api-keys-row" key={row.term}>
                <dt>{row.term}</dt>
                <dd>{row.detail}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="api-access-col">
          <h3 className="api-keys-heading">Create API Key</h3>
          {/* A real `disabled` button — not an enabled control that quietly does
              nothing — with its reason both programmatically associated
              (aria-describedby) and always visible, so `disabled` is never the
              only signal. The reason is deliberately SHORT: the full explanation
              is the banner's, and repeating it here is exactly the duplication
              slice 13 removed. */}
          <div className="api-keys-create">
            <button
              type="button"
              className="api-keys-create-btn"
              disabled
              aria-describedby={CREATE_REASON_ID}
            >
              <Lock size={13} strokeWidth={2} aria-hidden="true" />
              Create API Key
            </button>
            <p className="api-keys-create-reason" id={CREATE_REASON_ID}>
              {API_ACCESS_COPY.createDisabledReason}
            </p>
          </div>

          <details className="api-keys-technical">
            <summary>Technical Requirements</summary>
            <p className="api-keys-note">{API_ACCESS_COPY.requirementsNote}</p>
            <ul className="api-keys-requirements">
              {API_KEY_REQUIREMENTS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </section>
      </div>

      <section className="api-access-full">
        <h3 className="api-keys-heading">Your API Keys</h3>
        {/* Left-aligned row rather than a centred column: see the
            `.api-keys-empty` note in `screens.css`. */}
        <div className="api-keys-empty">
          <Lock size={16} strokeWidth={1.8} aria-hidden="true" className="api-keys-empty-icon" />
          <div className="api-keys-empty-text">
            <p className="api-keys-empty-title">{API_ACCESS_COPY.emptyTitle}</p>
            <p className="api-keys-empty-body">{API_ACCESS_COPY.emptyBody}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
