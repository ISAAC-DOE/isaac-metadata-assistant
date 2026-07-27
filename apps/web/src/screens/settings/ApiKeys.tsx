/**
 * Settings → API → API Keys (P36V PR3 slice C).
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
 *   contract the Documentation sub-tab renders is the proof: it lists every
 *   operation this API has, and none of them is key management.
 *
 * So the classification is UNAVAILABLE, and the screen is built as a complete,
 * deliberate unavailable state rather than a broken one:
 *
 *   · no key is ever generated, displayed, or partially displayed;
 *   · nothing is read from or written to `localStorage`, `sessionStorage`, or a
 *     cookie — this module contains no storage or cookie access at all;
 *   · the Create control is a really-`disabled` native button with a
 *     programmatically associated reason (`aria-describedby`), not an enabled
 *     control that silently does nothing;
 *   · there is no error banner and no simulated loading failure: nothing failed.
 *
 * Real key management is deliberately NOT stubbed. It would need durable
 * credential storage, per-key identity, revocation and scopes — a later,
 * separately authorized phase.
 */
import { Lock, ChevronRight } from '../../components/icons';

/** The `aria-describedby` target for the disabled Create control. */
const CREATE_REASON_ID = 'settings-api-create-reason';

/** What a working key would enable, and what actually applies today. Four rows,
 *  one question each — the four the authorizing brief requires answered. */
const ACCESS_ROWS: { term: string; detail: string }[] = [
  {
    term: 'What an API Key Would Enable',
    detail:
      'A program running outside this browser — a script, a notebook, or an agent — could call the operations listed under Documentation directly, without a person driving the interface.',
  },
  {
    term: 'Authentication That Applies Today',
    detail:
      'One credential belonging to the whole deployment, set on the server before the app starts and required on every operation except the liveness check. It identifies the deployment, not a person, and this screen cannot see whether it is switched on.',
  },
  {
    term: 'Key Management',
    detail:
      'Unavailable. This API has no operation that creates, lists, revokes, or rotates a credential, so there is nothing for this screen to manage. Documentation lists every operation the app has — none of them is key management.',
  },
  {
    term: 'External Agent Access',
    detail:
      'Not through anything you can obtain here. Whoever operates this deployment holds the single credential; the app cannot issue a second one, and browsing this page does not give a program a way in.',
  },
];

/** The contract that would have to exist first. Stated as requirements, never as
 *  a roadmap promise. */
const REQUIREMENTS: string[] = [
  'Durable storage for credentials, holding a hash rather than the value, so a stored credential cannot be read back.',
  'Per-key identity, so a key names who or what holds it instead of standing for the whole deployment.',
  'Revocation and expiry, so a key can be withdrawn without restarting the service.',
  'Scopes, so a key issued for reading cannot be used to write or export.',
  'A record of use, so a key that leaks can be traced and cut off.',
];

export function ApiKeysPanel({ onOpenDocumentation }: { onOpenDocumentation: () => void }) {
  return (
    <>
      <section className="api-keys-section" aria-labelledby="settings-api-access-heading">
        <h3 id="settings-api-access-heading" className="api-keys-heading">
          API Access
        </h3>
        <p className="api-keys-lead">
          Programmatic access to this build is limited to what the deployment itself is configured
          with. There is no way to issue a key from this screen, and this screen will not pretend
          otherwise.
        </p>
        <dl className="api-keys-rows">
          {ACCESS_ROWS.map((row) => (
            <div className="api-keys-row" key={row.term}>
              <dt>{row.term}</dt>
              <dd>{row.detail}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="api-keys-section" aria-labelledby="settings-api-create-heading">
        <h3 id="settings-api-create-heading" className="api-keys-heading">
          Create API Key
        </h3>
        {/* A real `disabled` button — not an enabled control that quietly does
            nothing — with its reason both programmatically associated
            (aria-describedby) and always visible, so the explanation is
            available whether or not the control can take focus. */}
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
            Unavailable in this build: the API has no operation that issues a credential, so there
            is nothing this button could call. Enabling it would require server-side credential
            storage, per-key identity, and revocation — none of which exists here.
          </p>
        </div>
      </section>

      <section className="api-keys-section" aria-labelledby="settings-api-list-heading">
        <h3 id="settings-api-list-heading" className="api-keys-heading">
          Your API Keys
        </h3>
        <div className="api-keys-empty">
          <Lock size={16} strokeWidth={1.8} aria-hidden="true" className="api-keys-empty-icon" />
          <p className="api-keys-empty-title">No keys to show.</p>
          <p className="api-keys-empty-body">
            This list is empty by design, not by circumstance — nothing failed to load. There is no
            place in this build where a key could be created or kept, so there is never anything
            here to display, reveal, or copy.
          </p>
        </div>
      </section>

      <section className="api-keys-section" aria-labelledby="settings-api-required-heading">
        <h3 id="settings-api-required-heading" className="api-keys-heading">
          What Would Be Required
        </h3>
        <ul className="api-keys-requirements">
          {REQUIREMENTS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="api-keys-note">
          Each of those is a backend and security contract this prototype does not have. They belong
          to a later, separately authorized phase, and none of them is stubbed out behind this
          screen.
        </p>
      </section>

      <nav className="api-keys-jump" aria-label="More API detail">
        <button type="button" className="settings-jump-btn" onClick={onOpenDocumentation}>
          Read the API Documentation
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
      </nav>
    </>
  );
}
