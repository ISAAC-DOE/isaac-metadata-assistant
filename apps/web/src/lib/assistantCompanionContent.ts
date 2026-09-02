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

export const ASSISTANT_COMPANION_COPY = {
  /** The section heading. Names the thing, not a status. */
  heading: 'Open ISAAC Assistant in Claude',

  /**
   * What the section is, said before any state is reported. Present tense about
   * what the companion IS, and deliberately silent about whether it works —
   * that is the state's job, one paragraph down.
   */
  lead: 'An optional companion page, opened in Claude, that a scientist can ask about their ISAAC work. It is a separate place you open, never a part of this website, and nothing you do there changes a record here unless you come back and change it yourself.',

  /**
   * THE HEADLINE BOUNDARY, rendered in every state including the one with a
   * link. This website is the system of record; the companion is not, and
   * cannot become one by being configured.
   */
  notSystemOfRecordHeading: 'This Website Remains the System of Record',
  notSystemOfRecord:
    'Every record, every piece of evidence and every export lives here and only here. The companion holds none of it and decides none of it. This website works exactly the same whether or not a companion link is set, and no part of the record workflow needs one.',

  /* ---------------------------------------------------------------------- *
   * The three states. Each pair is a LABEL (what this deployment is) and a
   * DETAIL (what that means for the reader). Neither ever depends on a colour.
   * ---------------------------------------------------------------------- */

  /**
   * `unconfigured` — the DEFAULT, and the wording carries no fault at all.
   *
   * The label deliberately does not say "not set up", "unavailable", "disabled"
   * or "coming soon". The first three read as a broken deployment; the fourth
   * is a promise nobody has authorized. It says what is true and stops.
   */
  unconfiguredLabel: 'No companion link is set for this deployment',
  /*
   * NOT ONE WORD OF ERROR VOCABULARY, and this is enforced rather than intended:
   * `assistant-companion.test.tsx` ratchets the whole `unconfigured` render
   * against the words a reader reads as a fault. So this sentence says what is
   * true and what follows from it, and never reaches for "nothing is missing" or
   * "nothing is broken" — a denial still puts the word on the page, and a reader
   * skimming takes the word rather than the negation.
   */
  unconfiguredDetail:
    'That is the normal, documented default, and it is the state most deployments are in. Whether to publish a companion and share it is an organization decision; a deployment that never makes one behaves exactly as this one does now.',
  unconfiguredOperator:
    'An operator who has decided to publish one sets a single environment variable on this deployment. That decision, and the steps it takes, are written down in the repository — see the reference below.',

  /**
   * `configured` — and every sentence here is scoped to what was actually
   * checked. The route checked a SHAPE. It did not fetch the link, did not
   * confirm the artifact exists, and did not confirm anyone can see it.
   */
  configuredLabel: 'A companion link is set for this deployment',
  configuredDetail:
    'An operator supplied a link and it passed the checks this application makes on its shape. Those checks are all that has happened: this application has not opened the link, so it cannot tell you whether the page is still there, whether it has moved, or whether it has been shared with you. Opening it is how you find out.',

  /** Sits immediately beside the link, never in a footnote. */
  configuredPrerequisiteHeading: 'Before the link will be useful to you',

  /** The visible text of the one link this surface can render. */
  openLinkText: 'Open the companion in Claude',

  /**
   * Named for what it is. The link leaves this website, and a reader is told so
   * before they follow it rather than after.
   */
  leavesSiteNote:
    'The link opens in a new tab, outside this website. Nothing about your workspace is sent with it.',

  /**
   * `refused` — an operator mistake worth surfacing, addressed to the operator
   * and written so a scientist reading it is not alarmed about their data.
   */
  refusedLabel: 'A companion link was supplied and this application will not use it',
  refusedDetail:
    'Something was set, and it did not pass the checks this application makes before it will offer a link to anyone. The reason below names which check it failed. The value itself is deliberately not shown here or written to any log, because a value pasted into the wrong place must not be copied back out of it.',
  refusedReasonHeading: 'Why it was not used',
  refusedScientistNote:
    'No record, export or evidence is affected by this. Nothing that a scientist does on this website depends on a companion link, so the workflow is unchanged while this is sorted out.',

  /* ---------------------------------------------------------------------- *
   * Limits and provenance, rendered in every state.
   * ---------------------------------------------------------------------- */

  limitsHeading: 'What This Section Checked, and What It Did Not',

  /**
   * The three named limits, each mapped to the field of the response that
   * publishes it. They are rendered as a list because they are separable
   * claims, and a reader who stops after the first must not have skipped one.
   */
  limits: [
    {
      id: 'reachable',
      claim: 'It did not open the link.',
      detail:
        'This application makes no outbound request of any kind here. A link that is set may still point at a page that has moved, been removed, or was never shared with you.',
    },
    {
      id: 'embed',
      claim: 'It offers a link and nothing else.',
      detail:
        'The companion is never displayed inside this website, and there is no setting here that would let it be. Embedding is documented by the vendor only for pages published to the public, which this companion is not.',
    },
    {
      id: 'connector',
      claim: 'It cannot see your own Claude settings.',
      detail:
        'Whether you have enabled the ISAAC connector is yours to know. Nothing here can enable it for you and nothing here can check it, so this section never reports on it — it only tells you it is a step you take yourself.',
    },
  ],

  /**
   * How the reader can check every claim above against the contract. The same
   * affordance Connect Your Agent offers for its own claim, and for the same
   * reason: a boundary a reader cannot verify is a boundary they have to take
   * on faith.
   */
  verifyNote:
    'Every claim above comes from this build’s own published contract. The Endpoint Explorer lists the operation this section reads and its full description.',

  /** The label of the button that opens the Endpoint Explorer tab. */
  verifyAction: 'Endpoint Explorer',

  /** Introduces the machine-readable facts, above the two `code` values. */
  configurationHeading: 'Deployment Configuration',
  configurationNote:
    'The name of the setting an operator changes, and the document that records the steps and who owns them. The value of that setting is never shown here, in any state.',
  configuredByLabel: 'Setting',
  referenceLabel: 'Written down in',

  /* ---------------------------------------------------------------------- *
   * Fetch states. This section reads live configuration, so it has the two
   * states any live read has, and it says what each means rather than showing
   * a bare spinner or a bare failure.
   * ---------------------------------------------------------------------- */

  loadingLabel: 'Reading this deployment’s configuration…',

  /**
   * A FAILED READ IS NOT AN ABSENT LINK, and conflating them is the defect this
   * sentence exists to prevent. "We could not ask" must never render as "there
   * is none" — the first is unknown, the second is a fact about the deployment.
   */
  unknownLabel: 'This deployment’s companion configuration could not be read',
  unknownDetail:
    'This section asked the server and did not get an answer, so it does not know whether a companion link is set. That is different from knowing there is none, and it is reported as its own outcome rather than shown as an empty result. Nothing else on this website is affected.',
} as const;
