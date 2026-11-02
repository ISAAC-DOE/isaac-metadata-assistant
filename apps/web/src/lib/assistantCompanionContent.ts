/**
 * Settings → Connect Your Agent → "Open ISAAC Assistant in Claude" — every
 * sentence the section renders, authored once.
 *
 * WHAT THIS SURFACE IS, AND THE FOUR THINGS IT MUST NEVER DO
 * =========================================================
 * It reports one deployment-configuration fact read live from
 * `GET /api/runtime/assistant-companion`: whether an operator has supplied a
 * link to an ISAAC Assistant companion artifact, and — when they have — offers
 * that link. It is a READOUT plus one link. It is not a connection, not a
 * status, and not a feature that turns on.
 *
 * Each of the four prohibitions below is a defect this repository has shipped
 * before in some other form, and each is pinned by a behavioural test in
 * `__tests__/assistant-companion.test.tsx` rather than by a string check:
 *
 *   · NO CONNECTED CLAIM, IN ANY STATE. `configured` means an operator set a
 *     value and it passed a SHAPE check. The route publishes
 *     `checked_reachable: false` precisely so a screen cannot read `configured`
 *     as `working`, and this module never writes a sentence that does. The
 *     guard is a case-insensitive substring ratchet over the rendered DOM, so
 *     even an honest negation ("nothing is connected") is written another way
 *     here — a guard a future author can satisfy by adding the word "not" is
 *     not a guard.
 *   · NO INVENTED URL. There is no default, no fallback, and no placeholder
 *     shaped like a link anywhere in this module or its component. A published
 *     artifact URL is access-bearing in an organization; committing one would
 *     put it in a history that outlives the artifact. The only URL that can
 *     ever render is the one the server returned in `url`, and the server
 *     returns one only in `configured`.
 *   · NO ERROR FRAMING FOR `unconfigured`. That is the DEFAULT and a working
 *     state — not a fault, not a wait, not "coming soon", and not something to
 *     ask a scientist to fix. The website is complete without a companion.
 *   · NO ECHO OF A REFUSED VALUE. The route's refusal names a category and
 *     never repeats what was pasted; this surface relays that sentence and adds
 *     nothing that could reconstruct it.
 *
 * THE PREREQUISITE IS NOT A FOOTNOTE
 * ==================================
 * Each scientist enables the ISAAC connector in their own Claude settings, and
 * nothing in this application can do that for them or observe whether they
 * have. A link offered with nothing beside it implies an in-app feature that
 * will simply work, which is false for anyone who has not done it — so the
 * sentence renders next to the link, in the one state where a link exists.
 * It is deliberately NOT rendered in the other two states: it QUALIFIES a
 * link, and shown where there is no link it would describe how to reach a
 * companion this deployment does not have.
 *
 * DEEP LINK ONLY
 * ==============
 * The route publishes `link_kind: "deep_link"` as a constant, because
 * `artifact_link.embed_markup()` always raises: the vendor documents the embed
 * flow only for PUBLICLY published artifacts, and a Team-account artifact
 * cannot be published publicly at all. So this surface renders no inline frame,
 * no embed, and no allowed-domain control. There is nothing here for a future
 * author to "finish"; the absence is the decision.
 *
 * VOCABULARY CONSTRAINTS THAT SHAPED THE WORDING
 * ==============================================
 * `settings-page.test.tsx` forbids a list of substrings on every Settings
 * surface — the same list the backend withholds from `GET /api/about` — because
 * naming a provider or a host discloses infrastructure topology. The copy below
 * is written to it.
 */

/**
 * The three states the server can report, mirrored here as a type so the
 * component's branches are exhaustive at compile time.
 *
 * THREE VALUES RATHER THAN A BOOLEAN, and the reason is the same one the route
 * gives: "nobody set a link" and "somebody set one that was refused" are
 * different facts about a deployment, and a reader needs different words for
 * them. Collapsing them would tell an operator that nothing was configured when
 * something was.
 */
export type AssistantCompanionState = 'unconfigured' | 'configured' | 'refused';

export const ASSISTANT_COMPANION_STATES: readonly AssistantCompanionState[] = [
  'unconfigured',
  'configured',
  'refused',
];

export function isAssistantCompanionState(value: unknown): value is AssistantCompanionState {
  return (
    typeof value === 'string' &&
    (ASSISTANT_COMPANION_STATES as readonly string[]).includes(value)
  );
}

/**
 * The Claude companion section (inside Connect Your Agent). One plain state line
 * per state (2026-11-02, owner's direction: no standing disclaimers).
 * ~~`notSystemOfRecord`, `limits` ("What This Section Checked, and What It Did
 * Not"), `verifyNote`, `refusedScientistNote`, `unconfiguredOperator`~~ — retired.
 * It still never shows a link it was not given, and never the setting's value.
 */
export const ASSISTANT_COMPANION_COPY = {
  heading: 'Open ISAAC Assistant in Claude',

  lead: 'An optional companion page, opened in Claude, for asking about your ISAAC work. Some actions there write directly into this record’s draft once you confirm them; others leave a suggestion attached to the record for review. Exports happen here.',

  unconfiguredLabel: 'Not set up on this server',
  unconfiguredDetail: 'An administrator sets it up in the deployment settings.',

  configuredLabel: 'A companion link is set',
  configuredDetail: 'Open it to check that the page is still there and shared with you.',

  configuredPrerequisiteHeading: 'Before You Open It',

  openLinkText: 'Open the companion in Claude',

  leavesSiteNote: 'The link opens in a new tab, outside this website.',

  refusedLabel: 'The companion link set for this deployment was not accepted',
  refusedDetail: 'The reason below names the check it failed.',
  refusedReasonHeading: 'Why It Was Not Used',

  configurationHeading: 'Deployment Configuration',
  configurationNote: 'The setting an administrator changes, and where the steps are written down.',
  configuredByLabel: 'Setting',
  referenceLabel: 'Written down in',

  loadingLabel: 'Reading this deployment’s configuration…',

  unknownLabel: 'The companion setting could not be read',
  unknownDetail: 'Reload the page to read it again.',
} as const;
