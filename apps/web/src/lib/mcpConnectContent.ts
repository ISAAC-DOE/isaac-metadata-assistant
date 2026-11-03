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
 *     set and the permissions below are what the interface is being built
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
import { CAPTURE_COPY } from './transcriptCaptureContent';

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

/**
 * Connect Your Agent copy. ONE plain state line per state, then the reference
 * sections in sequence inside one disclosure (2026-11-02, owner's direction: no
 * standing disclaimers). ~~`statusLabel` "Requires Organization Configuration",
 * `statusDetail`, `statusOwner`, `endpointNone`, `endpointVerify`, `restApiPointer`,
 * `activityNone`, `revocationNone`, `revocationFuture`, `provenanceNote`,
 * `oneWayDetail`, `neverSubmitEnforcement`, `setupPrerequisite`, `setupBilling`~~ —
 * retired. Nothing here may show a connected state the app has not verified
 * (`connect-your-agent.test.tsx`).
 */
export const MCP_CONNECT_COPY = {
  stateLine:
    'Not set up on this server. An administrator connects it in the deployment settings.',
  /* While `/api/health` has not answered: says what is happening, claims nothing. */
  stateLineChecking: 'Checking how this server accepts agent connections…',
  /* Absent block, a failed read, `null` or a posture this client does not know:
     the server has not said, so neither does this line. */
  stateLineUnreported: 'This server has not reported whether its agent interface is set up.',
  stateLinePublished: 'This deployment publishes an address for its agent interface:',
  neverSubmitHeading: 'No Agent Can Submit a Record',
  neverSubmitDetail:
    'Submitting is the step that mints an official ISAAC record, and no agent can take it — with your permission or an administrator’s. An agent can read and draft; you submit.',
  canDoHeading: 'What an Agent Can Do',
  permissionsHeading: 'Permissions an Agent Holds',
  permissionsDetail:
    'Three permissions, each granted explicitly. Read is the base; both write permissions are granted on top of it.',
  setupHeading: 'Setting It Up',
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
     *
     * M7 — AND THE WITHHELD SET WAS UNDER-STATED BY ITS OWN NAME. The copy called it
     * "the instrument and detector settings", which reads as one coherent category a
     * scientist can picture. Measured against `extract/structured.FIELD_MAP`, the
     * unclassified `system.configuration.*` namespace has SIX members, and the last
     * two are not settings of anything:
     *
     *     detector_model · monochromator_crystal · spectrometer_geometry · n_scans
     *     proposal_id · session_id                     ← ADMINISTRATIVE identifiers
     *
     * `workspace.field_level`'s own docstring records the same undercount being found
     * and corrected there ("SIX fields, not the five this list used to name"), by
     * enumerating the map rather than reading the prose — and the prose here was the
     * next copy of it. A reader who accepted "instrument and detector settings" would
     * not expect the proposal a record belongs to, or the beamtime session it was
     * taken in, to be dropped from a record exported per run; those are exactly the
     * fields somebody looks for when reconciling a run against a beamtime schedule.
     * The reason for withholding is unchanged and still honest — the contract assigns
     * the whole namespace to neither level, and guessing would be the unevidenced
     * inference `CLAUDE.md` §5 forbids — so what changes is the naming, not the rule.
     */
    id: 'add-run',
    action: 'Add a run',
    detail:
      'Add one measurement condition to a record. The first run carries across most of what the record already holds — its spectrum, QC verdict, descriptors, asset hashes, conditions and acquisition times move onto the run, because that is where an exported record reads them from. Six fields do NOT move — the detector model, monochromator crystal, spectrometer geometry and scan count, and also the proposal and session identifiers, which are administrative rather than instrument settings. Whether two runs of one experiment may legitimately differ in any of them is an open question this application has no answer to, and copying them would answer it by accident; the cost is that all six are dropped from a record exported per run. Every run after the first starts empty: nothing is copied from one run to another, because that would assert two runs measured the same thing. No value is ever invented.',
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
      'Fill in a run’s own five context and timing fields, or correct a value already answered on the record. An invented or misspelt key is refused with nothing written, and correcting something still unanswered is refused too. The confirmation each write records, though, is the agent’s assertion that you gave it — ISAAC cannot check whether you were ever asked, so grant this permission only to an agent you trust to ask you first.',
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
      'Give a record, or one of its runs, the answers it is blocked on — a reduced spectrum, a QC verdict, a descriptor, an asset hash — or overwrite one already answered. The agent must name the run a question belongs to: ISAAC will not guess which run measured something, and an answer sent to the record when a run owns it is refused with nothing written. Overwriting keeps the earlier confirmation beside the new one for a QC verdict and an asset hash, and REPLACES it for a spectrum or a descriptor — so after a corrected spectrum the record holds no trace that a different one was ever confirmed. As above, the confirmation recorded is the agent’s assertion that you gave it, and here it stands behind scientific judgement rather than a setting.',
    tools: ['isaac_answer_questions'],
  },
  {
    /*
     * I2 — TWO SOURCES NAMED WHERE THERE ARE THREE, which is the same conflation four
     * product screens carried and this row inherited. `isaac_check_run` reaches
     * `post_run_check`, whose dry-run branch returns `export_draft`'s result — and
     * `export.py` runs `check_exactness` on the assembled record BETWEEN the
     * no-guessing report and `validate_official` (`:339`), folding a refusal into
     * `draft_report` and returning `official_report=None` (`:339-343`). So a finding
     * this tool surfaces may come from a gate neither of the two named validators
     * owns, and the response carries no discriminator.
     *
     * The correction here is deliberately smaller than the screens': this row
     * describes what the tool ASKS, not what it reports, so naming the third gate is
     * enough — an agent reading the row must not conclude by elimination that an
     * unfamiliar finding is the official schema's. `CLAUDE.md` §12: the exactness gate
     * is ISAAC's, not upstream's, and §1 makes the schema not ours to speak for.
     */
    id: 'check-run',
    action: 'Check a run',
    detail:
      'Ask what the no-guessing draft check, ISAAC’s own anchored-pattern exactness gate and the official ISAAC schema say about the record a run would produce. On a candidate record the reply does not label which of the three a finding came from, so none is claimed. It writes nothing and changes nothing.',
    tools: ['isaac_check_run'],
  },
  {
    /*
     * TWO OVERCLAIMS, CORRECTED 2026-08-27 AGAINST A MEASURED WALK — and the
     * shape of the failure is the one worth remembering, not the wording.
     *
     * This row read: *"Read the field-by-field trail for a record: each value,
     * the kind of support behind it, and the source cited."* The BACKEND tool it
     * describes already said neither half was true, in `mcp/tools.py`'s own
     * `isaac_inspect_evidence` description — *"A BLOCK-LEVEL entry … carries its
     * support with `value: null`"* and *"on a record with RUNS this returns the
     * record's own trail only — each run's evidence is not in it"*. So the
     * machine-readable contract was corrected and the SCIENTIST-FACING copy was
     * not, which is the wrong way round: an agent's operator reads this tab, and
     * the tool description is read by the model.
     *
     * Measured through the registry (`isaac_answer_questions` → `isaac_create_run`
     * → `isaac_answer_questions` at the run level → `isaac_inspect_evidence`):
     *
     *     record with NO runs, all three questions answered   ->  3 entries,
     *                                                             every one `value: null`
     *     the SAME record once `isaac_create_run` has run,
     *     the science answered on the run as the API's own
     *     `409 belongs_to_a_run` REQUIRES                     ->  {"evidence": []}
     *
     * The second line is the one that matters. Once a record has runs, answering
     * at the record level is refused, so the run is the only place the science
     * can go — and the trail then shows the agent none of what it just wrote.
     * The run's draft demonstrably holds the confirmations (`block_evidence`
     * keys `qc:status`, `series:…`); no operation in the allowlist, and no route
     * in the HTTP API, serves them. `routes.py`'s own comment states this as
     * "STATED, NOT FIXED"; the gap is the API's, and this row's job is not to
     * paper over it.
     */
    id: 'inspect-evidence',
    action: 'Inspect the evidence',
    detail:
      'Read the evidence trail for a record: each entry’s official path or block key, the kind of support behind it, and the source cited. Two limits, because this row used to promise more than the tool returns. A block-level entry — a QC verdict, a spectrum, a descriptor set, an attribution or a link — carries no value of its own, so the value has to be read from the record itself. And on a record that has runs, the trail is the record’s own only: each run’s evidence is not in it, so a record whose spectrum, verdict and descriptors were answered on a run — which is where ISAAC requires them once runs exist — reads as an empty trail.',
    tools: ['isaac_inspect_evidence'],
  },
  {
    /*
     * THE ROW THAT IS EASIEST TO WRITE FALSELY, AND THE ONE A SCIENTIST DECIDES ON.
     *
     * `isaac_propose_field_value` is the channel the voice-and-chat workflow needs, and
     * the temptation is to describe it as "let your agent fill in a value". It is not
     * that, and the difference is the whole reason the tool was allowed to exist:
     * `apps/api/isaac_api/proposals.py` cannot even REPRESENT a confirmed value —
     * `status`, `verified`, `is_evidence` and `is_field_value` are read-only constants
     * on a frozen, slotted class and are serialised on the wire — and a proposal is
     * stored at `state["proposals"]`, OUTSIDE `draft`, so no exported record and no
     * submission signature reads it. Creating one leaves every field of the record and
     * of every run byte-for-byte unchanged (contract §5 I1/I2).
     *
     * So the row says what the agent CANNOT do first, in the scientist's own terms: it
     * cannot enter data, and the value stays a suggestion until the scientist accepts
     * it — which no agent tool at any permission can do. That refusal is structural in
     * the same way "no agent can submit" is: `accept` is a forbidden substring in any
     * tool name, checked at import, and the review route is in no operation allowlist.
     *
     * DELIBERATELY NOT MENTIONED: any suggestion that a connector exists. This tab is
     * future-tense throughout and this row keeps that register.
     */
    id: 'propose-a-value',
    action: 'Suggest a value for you to review',
    detail:
      'Record a suggestion against a record — a value, the field it is for, and the sentence explaining where it came from — for you to accept or refuse later. A suggestion is not an entry: it writes nothing into the record, counts as no evidence, changes nothing about what the record would export, and cannot make a blocked record exportable. It stays a suggestion until you accept it on the website, and no agent will be able to accept one — the tool that would is not built, and the same refusal that stops an agent submitting stops it. Every suggestion has to cite a note the record already holds, so the words behind it survive whatever you decide. Retrying is safe: a repeated suggestion returns the first one rather than making a second.',
    tools: ['isaac_propose_field_value'],
  },
  {
    /*
     * THE ROW THAT MAKES THE ONE ABOVE REACHABLE, and the sentence it had to correct.
     *
     * The `propose-a-value` row used to end *"no agent tool can create that note"*.
     * That was true when it was written and is FALSE now — `isaac_capture_note`
     * creates one — so the clause is DELETED from that row rather than softened, and
     * the correction is recorded here because a stale denial in scientist-facing copy
     * is the honesty-defect class this repository has shipped and fixed repeatedly.
     * The sentence's surviving half is the half that mattered: a suggestion must cite
     * a note, so the words behind it survive whatever the scientist decides.
     *
     * WHY THIS ROW IS SAFE TO OFFER AT ALL, in the scientist's terms rather than the
     * schema's. A note is not a value and cannot become one by itself:
     * `apps/api/isaac_api/notes.py` has no field on a note in which a value could sit,
     * its `status`/`verified`/`is_evidence`/`is_field_value` are read-only constants on
     * a frozen slotted class, and a note is stored at `state["notes"]`, OUTSIDE
     * `draft`, so no exported record and no submission signature reads it. So the row
     * leads with what the agent is doing — writing down what was said — and says
     * plainly that it changes nothing about the record itself.
     *
     * IT NAMES NO PERSON, DELIBERATELY. The server records that the content arrived
     * through the agent interface; that is a channel, not an identity, and this build
     * establishes no identity for an agent call at all. The copy must not imply the
     * note is attributed to the reader.
     *
     * DELIBERATELY NOT MENTIONED, as everywhere on this tab: any suggestion that a
     * connector exists. Future tense throughout.
     */
    id: 'capture-a-note',
    action: 'Write down what you said, word for word',
    detail:
      'Store what you told your agent against a record, exactly as you said it, as a note. This is how your own words reach ISAAC. A note is not an entry and not evidence: there is no value in it, it changes nothing about the record, it cannot make a blocked record exportable, and it will never appear in an exported record — which is exactly why writing your words down is safe when filling in a field from them would not be. The words are stored unedited and are refused rather than shortened if they are too long, so nothing is quietly trimmed. Deciding what a note means stays yours: no agent tool can map one to a field, edit it, set it aside or delete it. The note also survives your refusing any suggestion made from it. Retrying is safe: a repeated capture returns the first note rather than storing a second, and a record will not accept notes without limit — past its ceiling it refuses rather than dropping anything older.',
    tools: ['isaac_capture_note'],
  },
  {
    /*
     * HAND OVER A WHOLE DICTATION, AND LET ISAAC DO THE READING.
     *
     * The companion to `capture-a-note`, and the difference is WHO finds the
     * values. There, your agent stores your words and — if it believes a value is
     * stated in them — makes a separate, rule-stating suggestion. Here you hand
     * over one finished dictation and ISAAC's OWN reader looks for the handful of
     * things it knows how to read. No model reads the text on this path: the rules
     * are fixed, they are quoted back with every suggestion, and what they cannot
     * read they say they cannot read instead of guessing.
     *
     * WHY THIS IS THE HONEST ROUTE FOR A TRANSCRIPT. `docs/ai-integration-decision-packet.md`
     * §6 keeps model output out of the truth path; a suggestion this reader makes is
     * not model output at all. And every segment is kept as a note either way, so
     * refusing every suggestion still loses none of what you said.
     *
     * DELIBERATELY NOT MENTIONED, as everywhere on this tab: any suggestion that a
     * connector exists. Future tense throughout.
     */
    id: 'capture-a-transcript',
    action: 'Hand over a finished dictation and let ISAAC read it',
    detail:
      'Give a record one dictation you have finished — not text you are still typing — and ISAAC reads it with its own fixed rules rather than with a language model. Every segment of it is kept as a note, including the segments a rule recognised, so nothing you said is lost whatever you decide afterwards. Anything a rule does read becomes a suggestion that quotes the words it came from and the rule that read them, and it is still only a suggestion: no value moves, the record is unchanged, and an exported record will not contain it until you accept it. The reader deliberately knows only a few things; a sentence it cannot read is kept as a note and reported as unread rather than interpreted, and where one field is claimed two different ways it hands you both instead of preferring one. Saying which run the dictation describes is required for a record that has runs — "the only run" is a guess about the science, so it is never assumed.',
    tools: ['isaac_capture_transcript'],
  },
  {
    id: 'read-proposals',
    action: 'Read the suggestions and what you decided',
    detail:
      'List the suggestions stored against a record — including the ones you accepted, refused or withdrew, because those are outcomes rather than deletions — or read one in full with the note excerpt behind it and the history of what happened to it. The list arrives one window at a time and reports how many the record actually holds, so a short page is visibly a page. Reads only; deciding stays yours.',
    tools: ['isaac_list_proposals', 'isaac_get_proposal'],
  },
  {
    /*
     * THE FEED IS A STATE FEED AND NOT AN EVENT LOG, and the copy has to say so
     * because the name invites the other reading. `change_feed.py`'s own docstring is
     * explicit: this application keeps no event table, so ten edits between two reads
     * are ONE entry and nothing can say how many there were or in what order. A row
     * that promised "see what changed" would promise a history this build cannot
     * produce.
     */
    id: 'watch-for-changes',
    action: 'Notice that something moved',
    detail:
      'Ask what on a record is at a later version than the last time it looked, so an agent can notice you answered a suggestion instead of asking again. It reports where things stand NOW, not what happened: several edits between two checks appear as one entry, and nothing in it can say how many there were, in what order, or what the intermediate values were. Reads only.',
    tools: ['isaac_get_changes'],
  },
  {
    /*
     * `CTX-004`. THE ROW HAS TO SAY "NOT A FIELD VALUE" IN THE SCIENTIST'S OWN
     * SENTENCE, not only in the tool's description, because this tab is where a
     * person decides what to hand an agent — and the decision they are making is
     * about a list of literals that look exactly like field values and are not.
     * An agent relaying one as "the record says X" would be the failure, and the
     * person granting the permission should be able to see that it cannot happen
     * from the row rather than from a schema.
     */
    id: 'read-extended-context',
    action: 'Read the extra context an import kept',
    detail:
      'Read the scientifically useful statements an import found that the official ISAAC record has no field for — each with the source’s own words, which source they came from, and where in it. None of them is a field value, none was validated against the official schema, and none affects whether a record can be exported, so an agent can quote them as "a source said this" and never as "the record says this". The list arrives one window at a time and reports how many the record actually holds. Reads only.',
    tools: ['isaac_get_extended_context'],
  },
  {
    /*
     * 2026-09-22 (backend historical-semantics slice). ADDED BECAUSE THE BACKEND
     * PERMITS THE TOOL and `connect-your-agent.test.tsx` requires this list to cover
     * every permitted tool exactly. The row says "unattributed" in the scientist's
     * sentence for the reason the extended-context row says "not a field value": the
     * thing a person is deciding to hand an agent is a history that names nobody.
     */
    id: 'read-activity',
    action: 'Read what has been done to a record',
    detail:
      'Read a record’s append-only history of acts — what was changed, from what to what, when, and through which channel. Every entry names nobody: this deployment cannot establish who is calling, so each act reads as unattributed rather than guessing a person. An entry is not a field value and not evidence, and a few acts (creating, discarding and resetting a record) are never recorded, so an absence proves nothing. Reads only.',
    tools: ['isaac_list_activity'],
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
      'No agent tool sends a file, and none reaches the in-app tools that read one.',
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
      'Added to read, it lets an agent change draft content: add a run, answer or re-answer the questions a record or one of its runs is blocked on — including a run’s spectrum, QC verdict and descriptors — correct an answered field, and edit a run’s own five context and timing fields. It does not export, submit or finalise anything.',
    refuses:
      'On its own it permits nothing. Every tool this permission unlocks requires read as well, so an agent granted draft-write without read is refused every tool and is shown none of them. It also finalizes nothing: it unlocks a fixed, reviewed list of operations and none of them mints an official record. It does not let an agent record a suggestion either — that is a separate permission.',
  },
  {
    /*
     * WHY THIS IS NOT PART OF DRAFT-WRITE, which is the question a scientist reading
     * three permissions will ask. Draft-write changes draft content directly. This
     * changes nothing a draft, an export or a submission reads, and that inertness is
     * exactly what makes it the safe permission to give a model-derived channel — so
     * folding the two together would hand every suggesting agent the ability to write
     * values, and every drafting agent the suggestion channel. `mcp/policy.py`'s
     * `Scope.PROPOSALS_WRITE` records the same reasoning where it is enforced.
     *
     * ~~"alone, this permission is admitted by the permission check and then cannot
     * finish"~~ — **THAT WAS BUILT, MEASURED AND WITHDRAWN ON 2026-09-01, and it is
     * struck here rather than reworded because this is the copy a scientist reads
     * BEFORE granting the permission.** The tool briefly cost proposals-write alone.
     * Measured against the real server with that scope and nothing else: a fabricated
     * validator earns a `412` that reports the record's `current_version`, the next
     * request with it stores a proposal, and the success envelope's `etag` sustains the
     * session. So "cannot finish" was false, and withholding the disclosure would have
     * made the shape inert instead. The tool now costs read as well, and this row says
     * what every other write row says.
     */
    id: 'proposals-write',
    name: 'isaac:proposals.write',
    allows:
      'Record suggestions for you to review: a value, the field it is for, and the sentence explaining where it came from, cited to a note the record already holds. It writes nothing into the record, mints no evidence, and changes nothing about what the record would export.',
    refuses:
      'It cannot change a draft, answer a question, or add a run — those are the draft-write permission, and holding this one confers none of it. It cannot accept, refuse or withdraw a suggestion either: deciding is yours, on the website, and no agent tool at any permission does it. Like draft-write it permits nothing on its own — it is granted on top of read, never instead of it, and an agent holding it alone is refused every tool and shown none of them.',
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
      'Ask whoever runs this deployment for the agent interface’s address.',
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
      'Your client either signs you in through the deployment, or presents a credential your organization issues for this path. Whoever runs the deployment tells you which.',
  },
  {
    id: 'scope',
    title: 'Grant only what you need',
    detail:
      'Grant the read permission for an agent that should only look, and add the draft-write permission on top of read if you want it filling in drafts. Draft-write is never a substitute for read: granted by itself it permits nothing, so an agent holding it alone is refused every tool. Add the proposals-write permission instead if you want an agent that suggests values for you to review rather than entering them — it is the weaker of the two writes and does not include the other.',
  },
  {
    id: 'verify',
    title: 'Confirm it with a read, not a write',
    detail:
      'Ask your Claude to list your experiments. A read that returns what you expect is a real check; a write is not the thing to try first.',
  },
];

/* ~~MCP_AUDIT_DOC~~ — removed 2026-11-02: no consumer since the Connect Your Agent copy was cut. */

// --- the Connect Your Agent WIDGET (2026-10-12) -------------------------------

export const MCP_WIDGET_COPY = {
  title: 'Connect Your Agent',
  refusedHeading: 'What an Agent Cannot Do',
  detailsSummary: 'Setup and Reference',
} as const;


/**
 * THE UNCONFIGURED STATE LINE, BY THE SERVER'S OWN POSTURE (`/api/health` →
 * `mcp.posture`, derived by `mcp/deployment.py::posture` from the flags the app
 * consults). Restored 2026-11-02 after review: a single "Not set up on this server"
 * line was FALSE in `local-only` and `oauth-mounted`, where an administrator HAS set
 * the interface up.
 *
 * `local-only` and `oauth-mounted`/`remote-ready` reuse the voice-capture view's two
 * sentences verbatim (`CAPTURE_COPY`, read by `ClaudeVoicePath`), so the two screens
 * cannot give two different reasons for one deployment. `unmounted` is the plain
 * "not set up" line. Anything else — no block, a failed read, `null`, an unknown
 * value — is "not reported": no line claims more than the server reported.
 */
export function mcpStateLine(settled: boolean, posture: string | null | undefined): string {
  if (!settled) return MCP_CONNECT_COPY.stateLineChecking;
  if (posture === 'unmounted') return MCP_CONNECT_COPY.stateLine;
  if (posture === 'local-only') return CAPTURE_COPY.claudeLocalOnly;
  if (posture === 'oauth-mounted' || posture === 'remote-ready') return CAPTURE_COPY.claudeNoAddress;
  return MCP_CONNECT_COPY.stateLineUnreported;
}
