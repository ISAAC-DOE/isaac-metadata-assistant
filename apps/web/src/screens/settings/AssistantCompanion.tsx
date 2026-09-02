/**
 * Settings → Connect Your Agent → "Open ISAAC Assistant in Claude".
 *
 * All copy comes from `lib/assistantCompanionContent.ts`, which carries the
 * reasoning for every claim. This file is layout, semantics, the live read, and
 * the branch that matters: which of the three states this deployment is in.
 *
 * WHY IT LIVES ON THIS TAB. Connect Your Agent is the one Settings surface about
 * reaching this build from a scientist's own Claude. The companion's stated
 * prerequisite — that each scientist enables the ISAAC connector in their own
 * Claude settings — is the very connector that tab describes, so the two claims
 * are read together or not at all. Putting it anywhere else would leave a reader
 * meeting one half.
 *
 * WHY IT FETCHES HERE RATHER THAN AT PAGE LEVEL. `SettingsPage` deliberately
 * issues its three fetches once, at page level, because each feeds SEVERAL tabs
 * and switching tabs should not re-hit the backend. This read is different in
 * the one way that matters: the route re-reads the environment per request and
 * never caches, precisely so that an operator who changes the variable is not
 * reported from a value the process happened to read once.
 *
 * WHAT THAT BUYS ON THE CLIENT IS NARROWER THAN "NOT STALE", and saying so is
 * the point of this paragraph. `useFetch(…, [])` pins the answer for the life of
 * this component's MOUNT — on this tab, the page load, unless the reader
 * switches tabs and comes back, which unmounts and remounts it. So the honest
 * claim is: page-level placement would re-read once per page load however often
 * the reader returned to the tab; section-level placement re-reads on every
 * return. Not live, just less pinned. The route's non-caching is the guarantee
 * that matters and is verified against the route; the remount is asserted in
 * `assistant-companion.test.tsx` rather than left as prose. It also feeds ONE
 * tab, so hoisting buys nothing to weigh against that.
 *
 * WHAT THIS COMPONENT DELIBERATELY DOES NOT RENDER, and each absence is pinned
 * behaviourally by `__tests__/assistant-companion.test.tsx`:
 *
 *   · any claim that something is connected, reachable, working, live, active,
 *     enabled or online — in any state, in any casing. The guard is a flat
 *     substring ratchet, not a negation-aware one, which is why even the honest
 *     negations are written another way in the copy module. A guard a future
 *     author can satisfy by adding the word "not" is not a guard;
 *   · any URL that did not come from the server's `url` field in the
 *     `configured` state. There is no default, no fallback, no example, and no
 *     placeholder shaped like a link — not in this file and not in the copy;
 *   · an `iframe`, an `embed`, an `object`, or any allowed-domain control. The
 *     route publishes `link_kind: "deep_link"` as a constant because
 *     `artifact_link.embed_markup()` always raises; the absence is the decision,
 *     not an unfinished branch;
 *   · error framing for `unconfigured`. It renders through the same neutral
 *     banner every state uses, with no warning icon and no alert role;
 *   · anything the server refused. `reason` is relayed verbatim and nothing on
 *     this surface could reconstruct the value behind it;
 *   · any status conveyed by colour. The state is a sentence inside a
 *     `role="status"` region, so a screen reader and a monochrome display get
 *     the same information as a sighted one;
 *   · any `input`, `textarea`, `select` or other field. Nothing here accepts
 *     typing, so nothing here can be shaped like a credential prompt.
 *
 * LAYOUT reuses the API Access tab's existing chrome (`.api-access*`,
 * `.api-keys*`) exactly as `ConnectYourAgent.tsx` does, rather than introducing
 * another arrangement of the same boxes. NO NEW CSS is added by this slice, and
 * no custom property is referenced that `styles/tokens.css` does not declare.
 *
 * HEADINGS start at `h3`. The tab's card supplies the `h2`, and this section
 * sits inside that card beside the other `h3` sections, so `h3` here and `h4`
 * within keeps the outline from skipping a level — a property
 * `settings-page.test.tsx` asserts across every Settings surface.
 *
 * LANDMARKS: the `<section>` elements carry no accessible name, on purpose, so
 * they are sectioning containers rather than landmarks — the same rule the
 * sibling panel follows, for the same reason.
 */
import { Compass, ChevronRight, ExternalLink } from '../../components/icons';
import { api } from '../../lib/api';
import { useFetch } from '../../lib/useFetch';
import type { ApiAssistantCompanion } from '../../lib/types';
import {
  ASSISTANT_COMPANION_COPY as COPY,
  isAssistantCompanionState,
  type AssistantCompanionState,
} from '../../lib/assistantCompanionContent';

/**
 * What this section can be showing. FOUR values, not three: the server's three
 * states plus `unknown`.
 *
 * `unknown` IS NOT A FOURTH SERVER STATE AND MUST NOT BE COLLAPSED INTO
 * `unconfigured`. "We could not ask" and "there is none" are different claims —
 * the first is an absence of knowledge, the second is a fact about the
 * deployment — and rendering the first as the second would have this section
 * assert something it never established. It is also what an unrecognised
 * `state` string resolves to, so a server that grows a fourth state cannot make
 * this component silently describe it as one of the three it knows.
 */
type SectionState = AssistantCompanionState | 'unknown';

function sectionState(data: ApiAssistantCompanion | undefined): SectionState {
  if (!data) return 'unknown';
  return isAssistantCompanionState(data.state) ? data.state : 'unknown';
}

/**
 * The link, and the ONE place in this component that can produce an `href`.
 *
 * It is deliberately a function of BOTH the state and the url, and it returns
 * `null` unless the state is `configured` AND the server actually sent a
 * non-empty string. The route's invariant already guarantees that pairing, so
 * this is belt-and-braces — but the cost is one line and the failure it prevents
 * is a link rendered from a stale or partially-parsed body.
 */
function companionHref(state: SectionState, url: string | null | undefined): string | null {
  if (state !== 'configured') return null;
  return typeof url === 'string' && url.length > 0 ? url : null;
}

/**
 * A server-supplied string, or a fixed sentence saying it could not be read.
 *
 * WHY THIS EXISTS, AND WHY IT IS NOT BELT-AND-BRACES. `companionHref` already
 * type-guards `url`, and its comment calls that "belt-and-braces — but the cost
 * is one line". The four fields below were rendered RAW, and their failure mode
 * is strictly worse than the one that was guarded: this application has no
 * `ErrorBoundary` anywhere, so a non-string reaching JSX throws "Objects are not
 * valid as a React child" during render, React unmounts the tree, and THE ENTIRE
 * SETTINGS PAGE GOES BLANK — not this section, the page. Measured on this
 * branch before the fix, with `reason: {nested: 'object'}`.
 *
 * IT DEGRADES ONE LINE, NEVER THE SECTION, and that is the §11 precedent rather
 * than a preference: a malformed value that is already PERSISTED (or, here,
 * already served) must be READ rather than refused, because the reader did
 * nothing wrong and their surface must not vanish. So a malformed `reference`
 * costs the reference line and leaves a configured link working, exactly as one
 * unreadable pending entry leaves the rest of a record readable.
 *
 * It invents nothing: the fallback says the value was not readable, which is
 * what happened, and never substitutes a plausible-looking value.
 */
function readableText(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

/** Said in place of a field the server sent in a shape this client cannot show.
 *  One sentence, reused, naming no field value and promising no retry. */
const UNREADABLE_FIELD = 'This deployment sent a value here that could not be displayed.';

export function AssistantCompanionSection({
  /** Selects the Endpoint Explorer tab, so a reader can check every claim here
   *  against the operation's own published description. */
  onOpenExplorer,
}: {
  onOpenExplorer: () => void;
}) {
  const companion = useFetch(() => api.getAssistantCompanion(), []);
  const data = companion.status === 'data' ? companion.data : undefined;
  const state = sectionState(data);
  const href = companionHref(state, data?.url);

  /* The banner reports the state it is IN. Every branch is derived from the same
     `state`, so no two of them can be on screen together and the section cannot
     contradict itself about its one subject — the defect the sibling panel's
     published branch shipped and had to be corrected for. */
  const label =
    state === 'configured'
      ? COPY.configuredLabel
      : state === 'refused'
        ? COPY.refusedLabel
        : state === 'unconfigured'
          ? COPY.unconfiguredLabel
          : COPY.unknownLabel;
  const detail =
    state === 'configured'
      ? COPY.configuredDetail
      : state === 'refused'
        ? COPY.refusedDetail
        : state === 'unconfigured'
          ? COPY.unconfiguredDetail
          : COPY.unknownDetail;

  return (
    <section className="api-access-full">
      <h3 className="api-keys-heading">{COPY.heading}</h3>
      <p className="api-keys-lead">{COPY.lead}</p>

      {/* THE STATE, said once, as a sentence.
          `role="status"` makes it a polite live region: the state arrives from a
          fetch, so when it replaces the loading line it is announced rather than
          silently swapped. Polite rather than assertive on purpose — nothing
          here is urgent and nothing here interrupts what a reader is doing.
          It is not decorated with a dot, a pill, or a colour, and the SAME
          neutral banner carries all four outcomes, so `unconfigured` cannot read
          as a failure by borrowing an error's chrome. */}
      <div className="api-access-banner" role="status">
        <Compass
          size={16}
          strokeWidth={2}
          aria-hidden="true"
          className="api-access-banner-icon"
        />
        <div className="api-access-banner-body">
          {companion.status === 'loading' ? (
            <p className="api-keys-lead">{COPY.loadingLabel}</p>
          ) : (
            <>
              <h4 className="api-connect-heading">{label}</h4>
              <p className="api-keys-lead">{detail}</p>

              {/* The operator's next step, rendered ONLY where nothing is set.
                  It is not an instruction to the scientist reading it, and it
                  names no value. */}
              {state === 'unconfigured' && (
                <p className="api-keys-note">{COPY.unconfiguredOperator}</p>
              )}

              {/* THE RELAYED REFUSAL. The server's own sentence, which names a
                  category and never repeats what was pasted. It is rendered
                  verbatim rather than re-worded, so a category added on the
                  server cannot leave a stale sentence here. */}
              {state === 'refused' && data && (
                <>
                  <h4 className="api-connect-heading">{COPY.refusedReasonHeading}</h4>
                  <p className="api-keys-note">{readableText(data.reason, UNREADABLE_FIELD)}</p>
                  <p className="api-keys-note">{COPY.refusedScientistNote}</p>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* THE LINK. The only branch that can render an `href`, and it renders the
          server's string and nothing else.

          `rel="noreferrer"` accompanies `target="_blank"` so the companion is
          not told which page sent the reader; `noopener` is implied by
          `noreferrer` and is spelled out anyway, because the two are separable
          in older engines and the pairing is the one a reviewer looks for.

          The prerequisite sits IMMEDIATELY ABOVE the link rather than below it
          or in a footnote: a reader who follows the link without knowing they
          must enable the connector themselves will conclude the companion is
          broken. */}
      {href && data && (
        <>
          <h4 className="api-connect-heading">{COPY.configuredPrerequisiteHeading}</h4>
          <p className="api-connect-prerequisite">{readableText(data.prerequisite, UNREADABLE_FIELD)}</p>
          <p>
            <a
              className="settings-jump-btn"
              href={href}
              target="_blank"
              rel="noopener noreferrer"
            >
              {COPY.openLinkText}
              <ExternalLink size={13} strokeWidth={2.2} aria-hidden="true" />
            </a>
          </p>
          <p className="api-keys-note">{COPY.leavesSiteNote}</p>
        </>
      )}

      <h4 className="api-connect-heading">{COPY.notSystemOfRecordHeading}</h4>
      <p className="api-keys-note">{COPY.notSystemOfRecord}</p>

      {/* THE LIMITS, in every state including the failed read. They are
          properties of what this section CAN establish, not of what it happened
          to find, so they do not belong inside a branch. */}
      <h4 className="api-connect-heading">{COPY.limitsHeading}</h4>
      <dl className="api-keys-rows">
        {COPY.limits.map((limit) => (
          <div className="api-keys-row" key={limit.id}>
            <dt>{limit.claim}</dt>
            <dd>{limit.detail}</dd>
          </div>
        ))}
      </dl>

      {/* The two machine-readable facts — the NAME of the setting and the
          document — rendered only once the server has told us what they are.
          Neither is hard-coded here, so a rename on the server cannot leave a
          wrong name published on this page, and neither is ever the setting's
          VALUE. */}
      {data && (
        <>
          <h4 className="api-connect-heading">{COPY.configurationHeading}</h4>
          <p className="api-keys-note">{COPY.configurationNote}</p>
          <dl className="api-keys-rows">
            <div className="api-keys-row">
              <dt>{COPY.configuredByLabel}</dt>
              <dd>
                <code className="mono">{readableText(data.configured_by, UNREADABLE_FIELD)}</code>
              </dd>
            </div>
            <div className="api-keys-row">
              <dt>{COPY.referenceLabel}</dt>
              <dd>
                <code className="mono">{readableText(data.reference, UNREADABLE_FIELD)}</code>
              </dd>
            </div>
          </dl>
        </>
      )}

      <p className="api-keys-note">{COPY.verifyNote}</p>
      <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
        {COPY.verifyAction}
        <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
      </button>
    </section>
  );
}
