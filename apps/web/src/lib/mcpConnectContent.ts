/**
 * Settings → Connect Your Agent — every sentence the tab renders, authored once.
 *
 * WHAT THIS SURFACE IS FOR, AND THE ONE THING IT MUST NEVER DO
 * ============================================================
 * It describes ISAAC's agent interface — the machine-callable tool surface a
 * scientist's own Claude would connect to — to a human. It must never claim a
 * connection exists. There is no published endpoint, no configured way to
 * authenticate a caller, and nothing this screen could revoke, so the honest
 * state is `Requires organization configuration` and every part of the page is
 * built from that one fact rather than around it.
 *
 * Concretely, and each of these is a defect this repository has shipped before
 * in some other form:
 *
 *   · no `Connected` state, and no "(demo)" variant of one;
 *   · no status conveyed by colour alone — the state is a sentence;
 *   · no endpoint URL, because none exists and this module will not invent one;
 *   · no last-activity value, because nothing here measures activity. Absent is
 *     the honest value and a plausible timestamp would be a lie;
 *   · no Revoke control. A control whose only possible outcome is nothing is the
 *     same defect as an Override offered at an address where override was
 *     impossible — so the page states why there is nothing to revoke instead;
 *   · nothing shaped like a credential input. This repository removed
 *     `VITE_API_KEY` outright; no field, no paste box, no "enter your …" prompt.
 *
 * PROVENANCE — WHAT IS TRUE OF *THIS BUILD* VERSUS WHAT IS DEFINED ELSEWHERE
 * ==========================================================================
 * This distinction is the whole honesty of the page and must not be collapsed.
 *
 *   · TRUE OF THIS BUILD, and checkable from the repository as it stands:
 *     there is no agent interface here, no endpoint, and no activity record.
 *     The Endpoint Explorer tab lists every operation this build exposes and
 *     none of them is one.
 *   · DEFINED, NOT DEPLOYED: the capability boundary and the "never submit"
 *     rule are settled in the committed audit `docs/mcp-capability-audit.md`
 *     (§1 one-way, §4 annotations are hints not enforcement, §5 never build a
 *     submit/delete/migration/governance tool, §6 D1 and D2 deferred). The tool
 *     set and the two permissions below are what the interface is being built
 *     to; they are not running here. `MCP_CONNECT_COPY.provenanceNote` says so
 *     on the page, next to the material it qualifies — not in a footnote a
 *     reader can miss.
 *
 * The tab therefore speaks in the future tense about capability ("will be able
 * to") and the present tense about state ("there is no endpoint"). Instructions
 * for a future state are fine; a status claim about a present state is not.
 *
 * VOCABULARY CONSTRAINTS THAT SHAPED THE WORDING
 * ==============================================
 * `settings-page.test.tsx` forbids a list of substrings on every Settings
 * surface — the same list the backend withholds from `GET /api/about` — because
 * naming a provider or a host discloses infrastructure topology. Two of them
 * bite here: the word for a bearer credential, and the name of the identity
 * layer in front of a deployment. So the copy says "credential" and "the
 * organization's existing authentication" throughout, and names neither. That
 * is a real constraint on this file, not a stylistic preference.
 */

/**
 * The agent interface's endpoint address, or `null` when the deployment
 * publishes none.
 *
 * It is `null`, and that is not a placeholder waiting to be filled in with
 * something plausible: **D1 — may the agent path be reachable from a
 * scientist's own machine over the public internet? — is an outstanding
 * infrastructure decision, deferred 2026-08-12** (`docs/mcp-capability-audit.md`
 * §6). Until it is answered there is no address to publish, and a screen that
 * showed one would be describing a deployment that does not exist.
 *
 * The type is `string | null` rather than `null` so that the component's
 * "an endpoint exists" branch is real code with a real test, instead of
 * something a future author has to invent under time pressure on the day the
 * decision lands. That branch still does not say "Connected": an address being
 * published is not evidence that anything reached it, and this screen contacts
 * nothing.
 */
export const MCP_ENDPOINT: string | null = null;

/**
 * The deployment states this screen can describe.
 *
 * There is deliberately no `connected` member. A connected state would need a
 * signal this application does not have and cannot get from the browser, and an
 * enum member is exactly how an unverifiable claim acquires a place to live.
 */
export type McpDeploymentState = 'requires-configuration' | 'endpoint-published';

export function mcpDeploymentState(endpoint: string | null): McpDeploymentState {
  return endpoint === null ? 'requires-configuration' : 'endpoint-published';
}

export const MCP_CONNECT_COPY = {
  /** The card subtitle. Says what the tab is before it says anything else. */
  cardSub:
    "How a scientist's own Claude would call ISAAC's tools — what it will be allowed to do, and what this deployment has to settle first.",

  /** The status, stated as a sentence so it never depends on a colour. */
  statusLabel: 'Requires organization configuration',
  statusDetail:
    'No agent can connect to this deployment. There is no endpoint address to connect to and no configured way to authenticate a caller, so there is no live connection for this page to report, and nothing for it to revoke.',

  /*
   * THE SAME TWO LINES FOR THE DAY AN ADDRESS EXISTS, and they are here because
   * the two above would otherwise be rendered beside one.
   *
   * The published branch used to show the address and, in the same banner, the
   * sentence "There is no endpoint address to connect to" — a page contradicting
   * itself on the one fact it exists to report. The label had the same problem:
   * an address being published is not evidence that the deployment is still
   * unconfigured, so asserting it would be a status claim nothing had checked.
   *
   * What replaces it claims strictly less. It reports what this build can see —
   * that an address is published — and is explicit that the authentication
   * decision is a separate question this screen cannot observe. It deliberately
   * does not say the deployment is ready, and it deliberately does not say it is
   * unready. Note the wording avoids the bare word the ratchet forbids, for the
   * reason given at the top of `ConnectYourAgent.tsx`: an honest negation that
   * happens to contain it would still have to defeat the guard.
   */
  statusLabelPublished: 'An address is published; this screen has not verified it',
  statusDetailPublished:
    'This deployment publishes an address for its agent interface. This screen has not contacted it, and reports nothing about whether it answers, whether you are authorized to call it, or whether any agent has ever reached it. Whether a caller can authenticate is a separate decision, and this screen cannot observe it.',
  statusOwner:
    'Two decisions settle it, and both sit with whoever runs this deployment rather than with this application: whether the agent path may be reached from a scientist’s own machine over the public internet, and what authenticates that caller once it can be. Both were deferred on 2026-08-12 and neither has been narrowed since.',

  /** The endpoint, when there is not one. */
  endpointHeading: 'Endpoint',
  endpointNone:
    'None. This screen will not show a placeholder address, because a scientist who copied one would be pointing their Claude at something that does not answer. Ask whoever runs this deployment whether an address exists yet.',
  endpointVerify:
    'You can check the claim rather than take it: the Endpoint Explorer tab lists every operation this build exposes, generated from the app’s own contract, and no agent interface is among them.',
  /**
   * THE OTHER MECHANISM, named — because two tabs apart, one word apart, this
   * page and API Access make auth claims that do not reconcile on their own.
   *
   * API Access → Connect an Agent says every call carries a credential in a
   * header when a deployment enables authentication. This page says there is no
   * configured way to authenticate a caller. Both are true OF THEIR OWN PATH —
   * that one is REST over HTTP against the published contract, this one is the
   * machine-callable tool interface — and neither said which path it meant
   * relative to the other. A reader who met only this tab could conclude ISAAC
   * has no program access at all; a reader who met only that one could conclude
   * the agent story works. One sentence each way, rather than a restructure.
   *
   * Rendered in BOTH endpoint branches: the distinction does not stop being
   * worth drawing on the day an address is published.
   */
  restApiPointer:
    'This page is about the agent interface only. This build does serve an HTTP API, and the API Access tab’s “Connect an Agent” guide covers what a program you write has to get right to call it — a different mechanism, with its own separate answer about authentication.',

  /** The endpoint, when a deployment publishes one. Still not a connection. */
  endpointPublishedNote:
    'This is the address the deployment publishes. This screen has not contacted it and reports nothing about whether it is reachable, whether you are authorized to call it, or whether any agent has ever reached it.',

  /** Last activity — the honest absence, and why it is an absence. */
  activityHeading: 'Activity',
  activityNone:
    'Nothing is shown here because nothing is measured. No agent interface is running in this build, so no call has been made, and no record of one exists for this screen to read. A date in this space would be invented.',

  /** Revocation — the honest absence of a control, and where it will live. */
  revocationHeading: 'Access and Revocation',
  revocationNone:
    'There is no Revoke control on this page, because no access has been granted to anything. Offering a button whose only possible outcome is nothing would tell you an authorization exists.',
  revocationFuture:
    'Where revocation will live follows from the authentication decision. If ISAAC runs its own authorization server, access is granted and withdrawn here. If instead the organization issues each scientist a credential for this path, it is withdrawn wherever the organization issues it — and this page will link there rather than pretend to own it.',

  /** The provenance qualifier, rendered beside the capability and permission
   *  material rather than tucked away from it. */
  provenanceNote:
    'The capability boundary below is settled in this repository’s committed capability audit and is what the agent interface is being built to. None of it is running in this build: there is no agent interface here to grant a permission or refuse one.',

  /** The one-way fact, which is the most commonly misunderstood thing about
   *  this whole feature and is worth a scientist’s attention. */
  oneWayHeading: 'Which Direction This Runs',
  oneWayDetail:
    'Connecting is one-way: your Claude calls ISAAC. It does not give ISAAC an AI of its own, and nothing about it makes the assistant inside this app generative. The work your Claude does on your behalf is billed to your own Claude subscription or key, not to ISAAC.',

  /** The headline capability boundary, called out on its own. */
  neverSubmitHeading: 'No Agent Can Submit a Record',
  neverSubmitDetail:
    'Submitting is the step that mints an official ISAAC record, and no agent will be able to take it — not with your permission, not with an administrator’s. The tool that would do it is not built, and the audit that governs this interface forbids building one. An agent can bring a draft all the way to the point of submission and then has to hand it back to you.',
  neverSubmitEnforcement:
    'That is a structural refusal rather than a setting: the capability is absent, so there is no switch that turns it on. Advisory hints a tool can carry about its own behaviour are, by the protocol’s own specification, hints and not enforcement — so they are not what this rests on.',

  /** Setup — the precondition first, before any step. */
  setupHeading: 'Setting It Up',
  setupPrerequisite:
    'None of this can be done yet, and the reason is the first step: there is no address to enter. What follows describes what connecting will involve once this deployment publishes one — it is not a procedure you can complete today.',
  setupBilling:
    'Every step happens in your own Claude client, on your own machine. ISAAC does not install anything and cannot connect on your behalf.',

  /** Permissions. */
  permissionsHeading: 'Permissions an Agent Will Hold',
  permissionsDetail:
    'Two permissions, and they do not nest: an agent granted only the draft-write permission is refused every read tool, and one granted only read is refused every write. Neither of them means “may finalize”, and there is no third permission that does.',
} as const;

/** One capability row: what an agent will be able to do, in a scientist's terms. */
export interface McpCapability {
  id: string;
  action: string;
  detail: string;
  /**
   * The backend tool names this row describes, for the ALLOWED list only.
   *
   * It exists so the page cannot silently under-describe the interface. The
   * tool set is defined in `apps/api/isaac_api/mcp/policy.py`
   * (`PERMITTED_TOOL_NAMES`), and a slice that adds a tool there would
   * otherwise leave this tab quietly describing the set as it was — a scientist reading a
   * complete-looking list that has become incomplete. `connect-your-agent.test.tsx`
   * reads that file and requires these names to cover it exactly, so adding a
   * tool fails here until somebody writes down what it lets an agent do.
   *
   * The grouping is EDITORIAL and deliberately not one row per tool: "read your
   * experiments" is one thing a scientist does, and listing `isaac_list_experiments`
   * and `isaac_get_experiment` separately would describe the interface to a
   * machine on the one page whose job is to describe it to a person.
   */
  tools?: readonly string[];
}

/**
 * What an agent WILL be able to do. Future tense throughout, because none of it
 * is reachable in this build.
 *
 * Deliberately phrased as the scientist's own work rather than as operation
 * names: this tab is the place where a machine interface is described to a
 * person, and a bare list of operation identifiers would describe it to a machine.
 */
export const MCP_CAPABILITIES_ALLOWED: readonly McpCapability[] = [
  {
    id: 'read-experiments',
    action: 'Read your experiments',
    detail:
      'List what is in your workspace and open one, with its status, how many blocking questions are open, and whether it has been exported.',
    tools: ['isaac_list_experiments', 'isaac_get_experiment'],
  },
  {
    id: 'read-runs',
    action: 'Read a record’s runs',
    detail:
      'Page through the runs on a record, or read one run in detail with the record-level values it inherits resolved for you.',
    tools: ['isaac_list_runs', 'isaac_get_run'],
  },
  {
    /*
     * "IT STARTS EMPTY" WAS TRUE AND STOPPED BEING TRUE, and the correction is
     * the interesting part. `routes._seed_for_new_run` now gives the FIRST run of
     * a record the run-level values the record already holds, because a run's
     * spectrum, verdict, descriptors, asset hashes, conditions and acquisition
     * times are read OFF THE RUN — so a first run that started empty silently
     * deleted every evidenced value from the record it exports, and the export
     * still said `ok: true`.
     *
     * A LATER run does start empty, and that asymmetry is the no-guessing rule
     * rather than an inconsistency: copying one run's spectrum onto a second
     * asserts they measured the same thing, which is a scientific claim this
     * application has no evidence for. Both halves are stated, because "it starts
     * empty" and "it inherits everything" are each half-false and a scientist
     * reading either one alone would be misled about what Add Run just did.
     */
    id: 'add-run',
    action: 'Add a run',
    detail:
      'Add one measurement condition to a record. The first run carries across what the record already holds — its spectrum, conditions and times move onto the run, because that is where an exported record reads them from. Every run after that starts empty: nothing is copied from one run to another, because that would assert two runs measured the same thing. No value is ever invented.',
    tools: ['isaac_create_run'],
  },
  {
    /*
     * THE CONFIRMATION IS THE AGENT'S ASSERTION, AND THIS ROW HAS TO SAY SO.
     *
     * It used to read "Each write carries your confirmation as its support",
     * which a scientist reads as a gate — as though ISAAC had asked them and
     * recorded the answer. It has not. `confirmed_by_user` is a boolean the
     * CALLER sends, and the backend is explicit that it is deliberately not
     * this layer's to set: `apps/api/isaac_api/mcp/tools.py` — "a layer that
     * sets it on the caller's behalf manufactures a confirmation nobody gave"
     * and "it is the caller's assertion that the scientist confirmed it, not
     * this server's". Nothing checks that the scientist was asked, and the
     * value is stored as `user_confirmation` evidence — which under CLAUDE.md
     * §5 is the support for a value with no other evidence. So an agent that
     * asked nothing can write a field whose evidence trail is indistinguishable
     * from one the scientist really confirmed.
     *
     * The register is `neverSubmitEnforcement`'s: name what is structural and
     * name what is only asserted, rather than letting the second borrow the
     * first's authority. The refusal of an unknown field path IS structural and
     * is kept; the confirmation is not, and now says whose claim it is and what
     * the reader has to do about it (trust the agent, because ISAAC cannot).
     */
    id: 'write-draft',
    action: 'Write draft values',
    detail:
      'Correct an answered record-level field, or fill in a run’s own five context and timing fields. Field paths only — the spectrum, the QC verdict and the descriptors are answers to questions rather than field paths, and are written through “Answer the open questions” below. An invented or misspelt field path is refused with nothing written. The confirmation each write records, though, is the agent’s assertion that you gave it — ISAAC cannot check whether you were ever asked, so grant this permission only to an agent you trust to ask you first.',
    tools: ['isaac_update_draft'],
  },
  {
    id: 'list-questions',
    action: 'See what a record is waiting for',
    detail:
      'Read the open questions blocking a record — what each one asks, the key an answer goes under, and which run owns it. Reads only; writes nothing.',
    tools: ['isaac_list_questions'],
  },
  {
    /*
     * THE SAME CONFIRMATION CAVEAT AS `write-draft`, RESTATED RATHER THAN
     * CROSS-REFERENCED. This row authorises writing a spectrum and a QC verdict —
     * scientific judgement, not a temperature — on the strength of a
     * `confirmed_by_user` boolean the CALLER sends and nothing verifies. A reader
     * who skims one row must not be able to grant this one while having read the
     * caveat only on the other.
     *
     * AND THE LEVEL IS NOT INFERRED, which the copy says because it is the
     * scientist's protection: ISAAC does not decide which run measured something.
     * An answer sent to the record when a run owns it is refused, not redirected.
     */
    id: 'answer-questions',
    action: 'Answer the open questions',
    detail:
      'Give a record, or one of its runs, the answers it is blocked on — a reduced spectrum, a QC verdict, a descriptor, an asset hash — or overwrite one already answered, keeping the earlier confirmation beside the new one. The agent must name the run a question belongs to: ISAAC will not guess which run measured something, and an answer sent to the record when a run owns it is refused with nothing written. As above, the confirmation recorded is the agent’s assertion that you gave it, and here it stands behind scientific judgement rather than a setting.',
    tools: ['isaac_answer_questions'],
  },
  {
    id: 'check-run',
    action: 'Check a run',
    detail:
      'Ask what the no-guessing draft check and the official ISAAC schema say about the record a run would produce. It writes nothing and changes nothing.',
    tools: ['isaac_check_run'],
  },
  {
    id: 'inspect-evidence',
    action: 'Inspect the evidence',
    detail:
      'Read the field-by-field trail for a record: each value, the kind of support behind it, and the source cited.',
    tools: ['isaac_inspect_evidence'],
  },
];

/**
 * What an agent will NOT be able to do. The first row is the one that matters
 * most to a scientist and is repeated as its own section above; the rest bound
 * the surface so the list is a boundary rather than a highlight.
 */
export const MCP_CAPABILITIES_REFUSED: readonly McpCapability[] = [
  {
    id: 'no-submit',
    action: 'Submit, finalize, or export a record',
    detail:
      'The step that produces an official ISAAC record stays yours. No agent will be able to take it.',
  },
  {
    id: 'no-delete',
    action: 'Delete anything',
    detail: 'No agent will be able to remove an experiment, a run, or a piece of evidence.',
  },
  {
    /*
     * SCOPED TO THE UPLOAD ROUTE, and this is the FOURTH site to make the claim.
     *
     * It used to read "File ingestion is refused for this whole deployment,
     * agent or not" — deployment-wide, and false in the same way three other
     * surfaces were false before (CLAUDE.md §11; the correction is pinned by
     * `__tests__/upload-claim-parity.test.tsx`). `POST /api/uploads` really is
     * refused unconditionally, but the standalone record validator calls
     * `file.text()` on a file you pick, and the campaign-sheet CSV
     * reconciliation panel reads one and POSTs it. A reader who took the old
     * sentence literally would believe this build never opens a file at all.
     *
     * It survived the parity guard only on WORDING: that guard bans "no file is
     * read/parsed/inspected", and "ingestion" is not one of the banned shapes.
     * A claim that escapes a ratchet by synonym is not held by it, so this row
     * is now IN `SITES` there and states the whole shared claim — the refusal,
     * both readers by name, the in-memory bound and the outcome-only bound —
     * exactly as the other three do.
     */
    id: 'no-upload',
    action: 'Upload or ingest a file',
    detail:
      'File upload is refused outright for this whole deployment, agent or not, and no agent tool sends a file. That refusal is the upload route: inside the app the record validator and campaign-sheet CSV reconciliation do read a file you paste or pick — in memory, never stored, recording only the outcome and never the content — and an agent has no tool that reaches either of them.',
  },
  {
    id: 'no-governance',
    action: 'Change governance or validation',
    detail:
      'Policy, the official schema, and the deterministic validators are outside the interface entirely. An agent can read a verdict; it cannot change what produces one.',
  },
  {
    id: 'no-corpus',
    action: 'Reach the production-derived records',
    detail:
      'The routes that touch that corpus are excluded from what an agent may call, independently of any permission it holds.',
  },
];

/** One permission and what holding it allows. */
export interface McpPermission {
  id: string;
  name: string;
  allows: string;
  refuses: string;
}

export const MCP_PERMISSIONS: readonly McpPermission[] = [
  {
    id: 'read',
    name: 'isaac:read',
    allows:
      'See experiments, runs, evidence, and validation findings, and ask what a run would validate as.',
    refuses: 'Writes nothing. An agent holding only this permission cannot change a draft at all.',
  },
  {
    id: 'draft-write',
    name: 'isaac:draft.write',
    allows:
      'Change draft content: add a run, answer or re-answer the questions a record or one of its runs is blocked on — including a run’s spectrum, QC verdict and descriptors — correct an answered field, and edit a run’s own five context and timing fields. It does not export, submit or finalise anything.',
    refuses:
      'Finalizes nothing. It unlocks a fixed, reviewed list of operations and none of them mints an official record.',
  },
];

/** One numbered setup step. `command` is shown as inert text, never a link. */
export interface McpSetupStep {
  id: string;
  title: string;
  detail: string;
  command?: string;
}

/**
 * What connecting will involve, once there is something to connect to.
 *
 * Step 1 is the blocker on purpose. A procedure whose first instruction cannot
 * be carried out reads as blocked, which is the truth; burying the blocker at
 * step 4 would read as a working procedure with a caveat.
 *
 * The command in step 2 is the documented form for adding a remote server to
 * the command-line client, with the address written as a placeholder in angle
 * brackets — unmistakably not a URL, so it cannot be pasted and cannot be
 * mistaken for one this deployment published.
 */
export const MCP_SETUP_STEPS: readonly McpSetupStep[] = [
  {
    id: 'address',
    title: 'Get the address',
    detail:
      'Ask whoever runs this deployment for the agent interface’s address. There is none today, so this is where the procedure stops. Nothing below can be done until it changes.',
  },
  {
    id: 'add',
    title: 'Add it to your Claude client',
    detail:
      'In the command-line client, register it as a remote server over streamable HTTP. In the desktop and web apps, add it under Settings → Connectors as a custom connector. Either way your client connects out from your own machine to the address you supplied.',
    command: 'claude mcp add --transport http isaac <address>',
  },
  {
    id: 'authenticate',
    title: 'Sign in as yourself',
    detail:
      'What this looks like is the second undecided question. Either ISAAC runs its own authorization server and your client is sent to it to sign in, or the organization issues you a credential for this path and your client presents it. Which of the two has not been decided, so this page cannot tell you what you will see.',
  },
  {
    id: 'scope',
    title: 'Grant only what you need',
    detail:
      'Grant the read permission for an agent that should only look, and add the draft-write permission only if you want it filling in drafts. They are granted separately and one never implies the other.',
  },
  {
    id: 'verify',
    title: 'Confirm it with a read, not a write',
    detail:
      'Ask your Claude to list your experiments. A read that returns what you expect is a real check; a write is not the thing to try first.',
  },
];

/**
 * A pointer to the committed document that settles the capability boundary, so
 * a reader can go and check rather than take the page's word. Rendered as inert
 * text — it is a repository path, not a link, and this build serves no
 * documentation route.
 */
export const MCP_AUDIT_DOC = 'docs/mcp-capability-audit.md';
