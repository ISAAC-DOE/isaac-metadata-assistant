import './help.css';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CircleHelp, X } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { CANONICAL_STEPS } from '../lib/workflowSteps';

/*
 * ONE WORKFLOW VOCABULARY, AND IT IS THE SERVER'S.
 *
 * This list used to be authored here from five now-deleted `LABELS` entries —
 * Draft · Complete · Export · Validate · Audit — while every per-record surface
 * in the same product showed the server-derived spine: Record Created · Complete
 * Metadata · Review Evidence · Review Export Readiness · Export. A first-timer
 * opening Help was taught the five words that appear nowhere else in the app.
 *
 * The retired five were not a worse wording of these five. They were the
 * AGENT-SIDE AUTHORING TOOLCHAIN — two Claude Code skills (`isaac-draft`,
 * `isaac-complete`) and three `isaac` subcommands (`cli.py` declares exactly
 * `validate`, `export`, `audit`, `new-id`) — none of which the deployed web
 * application can invoke. `lib/labels.ts` records the full reasoning for
 * deleting them rather than renaming them.
 *
 * The labels and the order now come from `lib/workflowSteps.ts`, the committed
 * mirror of `apps/api/isaac_api/workflow.py:17,26`, so a rename on the server
 * moves this copy too. Using the mirror rather than a live `ordered_steps` is
 * deliberate and is the same justification the mirror already carries for the
 * cross-record histogram: what is needed here is the fixed AXIS — the wording
 * and the order — and Help has no record to read state from. Nothing here
 * carries per-step STATE: no tick, no lock, no current marker. Those are
 * per-record truth, they are derived by `derive_workflow` on the server, and a
 * static popover must not appear to report them.
 */
const STEP_TEXT: Record<string, string> = {
  // `satisfied['load_record']` is unconditionally `True` (`workflow.py:63`), and
  // the module's own header states the rest: per-step state is "computed on read
  // from the current signals only — never persisted".
  // TRIMMED (I-2 slice). The tail read "— your position in the sequence is never
  // stored", which restates "re-derived ... each time it is read" in different
  // words: `workflow.py`'s header states both halves of one fact, and this copy
  // had imported both. Nine words of the Help budget for no claim a reader did
  // not already have. Removed deliberately, not accidentally — the Impeccable
  // critique measured this surface 89% longer than it should be (`UX-021`), and
  // the room for the three-gate correction below is taken from wording.
  load_record:
    'opens a record. Every step below is re-derived from that record’s current state each time it is read.',
  // `satisfied['complete_metadata'] = pending_count == 0` (`workflow.py:65`), and
  // `workspace.run_questions` is documented as "The open blocking questions ONE
  // run carries" — so the questions asked ARE the blocking ones.
  complete_metadata:
    'asks only the questions still blocking export, and is satisfied when none are left.',
  // `satisfied['review_evidence'] = pending_count == 0 and draft_ok`
  // (`workflow.py:66`); `Experiment.draft_ok` is "Whether EVERY unit's draft
  // passes the no-guessing checks".
  review_evidence:
    'is satisfied only once every question is answered AND the no-guessing checks pass on every unit of the record.',
  // `satisfied['review_export_readiness'] = ready`, where `ready` is
  // `Experiment.export_ready` — "True iff a dry-run export of EVERY unit passes".
  // The dry run is `export.export_draft`, which returns a result object and
  // writes no file and no record.
  review_export_readiness:
    'dry-runs the export over every unit of the record and reports what would still refuse. Nothing is written.',
  // CORRECTED (I-2). "both export gates" was a COUNT CLAIM, and it was wrong by
  // one. RE-DERIVED HERE rather than taken from the comment it replaces:
  // `export.export_draft` has THREE refusal returns — the no-guessing draft
  // report (`export.py:305`), `check_exactness` on the assembled record (`:343`)
  // and `validate_official` (`:347`) — against exactly one success return at
  // `:350`.
  //
  // The repository already said so in two committed places while this said
  // "both": `screens/ExportReadiness.tsx:789-791` ("it clears THREE gates, not
  // two"), and `lib/officialAttribution.ts` calls them
  // "ISAAC's two gates" at `:164` — ISAAC's OWN — beside the upstream schema.
  //
  // THAT CITATION WAS WRONG IN TWO WAYS AND IS CORRECTED HERE, because a comment
  // citing the wrong line is how this branch has already lost time. It read
  // ``lib/officialAttribution.ts:11,164`, which counts the FIRST TWO as "ISAAC's
  // two gates"'. (i) `:11` does NOT make that count: it is item **3** of that
  // module's own three-item numbering of finding PRODUCERS (`:9` the vendored
  // official schema, `:10` the no-guessing draft validator, `:11` the
  // anchored-pattern exactness gate). Only `:164` states the count. (ii) The
  // pair is the LAST two, not the first two — `:13` is the line that pairs them
  // ("`export.py` folds (2) and (3) together"), and (1) is the upstream schema,
  // which is precisely the one that is NOT ISAAC's. The substantive point the
  // citation was making survives intact and is unchanged: this product shipped
  // two different counts of its own export gates on two screens. So the
  // product shipped two different counts of its own export gates on two screens,
  // and this was the wrong one.
  //
  // ~~DO NOT "HARMONISE" THIS WITH `components/ValidateReview.tsx:420`, which
  // says ISAAC applies ONE gate of its own beyond the official schema. That
  // surface validates a PASTED record through `POST /api/validate/record`, where
  // `ok = schema_ok AND exactness_ok` and the no-guessing draft check is not in
  // the path at all. TWO gates there, THREE here; both are correct about
  // different operations, and a sweep that averaged them would replace one false
  // claim with another.~~
  //
  // WITHDRAWN 2026-09-12, AND KEPT STRUCK RATHER THAN DELETED, because a
  // "DO NOT HARMONISE" instruction is exactly the kind of sentence a future
  // session obeys — this one told three sessions not to fix a real defect.
  // ATTRIBUTION, stated plainly: the premise came from an ORCHESTRATOR ADDENDUM
  // that has since been retracted in writing. The implementer who transcribed it
  // was following its brief; the error is the premise's, not the transcription's.
  //
  // Every load-bearing part of it is false. RE-MEASURED HERE rather than taken
  // on trust, which is how it should have arrived the first time:
  //
  //   - `ValidateReview` does NOT call `POST /api/validate/record`. It calls
  //     `api.validate(experimentId)` (`ValidateReview.tsx:305`), which is
  //     `POST /api/experiments/{id}/validate` (`lib/api.ts:2081-2083`). The
  //     retired sentence's own last clause sent the reader AWAY to the Standalone
  //     Validator, so it was never that route's copy — and the comment nine lines
  //     above this one already named `export_draft`.
  //   - So that surface describes THIS path, where the gates number THREE
  //     (`export.py:305`, `:343`, `:347`, against one success return at `:350`)
  //     and TWO of them are ISAAC's own. Same operation, same count.
  //   - "TWO gates there, THREE here; both are correct about different
  //     operations" is therefore wrong twice over, and the `ValidateReview` copy
  //     it forbade touching was a genuine defect.
  //
  // IT IS ALSO STALE. That copy HAS been corrected; the sentence quoted above no
  // longer exists there, and `ValidateReview.tsx:423-430` now keeps it struck
  // with a third falsehood nobody had named — its trailing clause predated the
  // `official_validator_ran` discriminator (`routes.py:19036`), so a CANDIDATE
  // record's findings CAN be headed "Official ISAAC schema findings"
  // (`lib/officialAttribution.ts:188`).
  //
  // WHAT IS ACTUALLY FORBIDDEN, and the citation to point at:
  // `lib/officialAttribution.ts:163-169` — copy attributing a REFUSAL may not
  // name ONE of ISAAC's two gates as its source, because `export.py:342` folds
  // the exactness findings into `draft_report` and the response cannot say which
  // of the two refused. That is a rule about ATTRIBUTING A FINDING, not about
  // listing which gates run: the rendered copy below names all three, claims no
  // finding for any of them, and is inside the rule.
  export:
    'writes the official ISAAC record plus an evidence sidecar — and only when all three export gates pass.',
};

/**
 * The five canonical steps with their explanatory text.
 *
 * Throws on a step the server's mirror declares and this file has no text for,
 * matching `canonicalStepLabel`'s posture: a missing entry means the mirror has
 * moved and this copy has not, and a popover must not paper over that with a
 * blank line. Silent omission is the failure mode that lets a workflow step go
 * undocumented while every test still passes.
 */
const WORKFLOW_STEPS: { id: string; label: string; text: string }[] = CANONICAL_STEPS.map(
  (step) => {
    const text = STEP_TEXT[step.id];
    if (text === undefined) {
      throw new Error(`HelpPanel has no text for canonical workflow step: ${step.id}`);
    }
    return { id: step.id, label: step.label, text };
  },
);

/**
 * Static, honest Help popover — explains only what this prototype actually
 * does (no chat, no fabricated features). Search IS real and lives in its own
 * ⌘K command palette (SearchDialog), separate from this panel. Anchored to the
 * Help button; hand-rolled (no dialog library) per project dependency discipline.
 */
export function HelpPanel() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const headingId = useId();
  const wasOpen = useRef(false);

  /*
   * A11Y-02 — Escape, click-outside, AND Tab containment.
   *
   * THE TRAP IS WHAT MAKES `role="dialog"` HONEST HERE. This panel has
   * announced itself as a dialog (and the trigger as `aria-haspopup="dialog"`)
   * since it shipped, and focus moved INTO it on open and back to the trigger
   * on close — but Tab from the last control inside walked straight out into
   * the page behind, which the dialog is visually covering. A screen-reader or
   * keyboard user therefore landed in content they could not see, with no way
   * to tell they had left. `aria-modal="true"` is added in the SAME change and
   * deliberately not before it: that attribute tells assistive technology the
   * rest of the page is inert, which was FALSE while Tab could reach it. Trap
   * and attribute are one decision, so neither ships without the other.
   *
   * The shape is copied deliberately from `SearchDialog` and `ResetDemoDialog`,
   * which hand-roll the identical containment — capture-phase listener, a
   * freshly-queried focusable list on every keystroke (the panel's content is
   * conditional, so a list captured once goes stale), `preventDefault` so focus
   * can never leave, and wraparound in both directions. Reading like the
   * surrounding code was preferred over extracting a shared hook: the two
   * existing copies are in dialogs whose behaviour is pinned by their own
   * suites, and one of them is the DESTRUCTIVE reset path. Extracting the hook
   * is real and is named as residue rather than smuggled into an accessibility
   * fix.
   */
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusable = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        return;
      }
      if (e.key !== 'Tab') return;
      e.preventDefault();
      const items = focusable();
      if (items.length === 0) {
        // The panel itself is `tabIndex={-1}` and focusable programmatically,
        // so there is always somewhere for focus to rest. Without this branch a
        // content-less panel would swallow Tab and leave focus nowhere.
        panel!.focus();
        return;
      }
      const active = document.activeElement as HTMLElement | null;
      const idx = active ? items.indexOf(active) : -1;
      const delta = e.shiftKey ? -1 : 1;
      const next = items[(idx + delta + items.length) % items.length] ?? items[0];
      next.focus();
    }
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [open]);

  // Move focus into the panel on open; return it to the Help button on close.
  useEffect(() => {
    if (open) {
      panelRef.current?.focus();
    } else if (wasOpen.current) {
      buttonRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  return (
    <div className="help-anchor">
      <button
        ref={buttonRef}
        type="button"
        className="icon-btn"
        aria-label="Help"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <CircleHelp size={16} strokeWidth={2} aria-hidden="true" />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="help-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby={headingId}
          tabIndex={-1}
        >
          <div className="help-panel-head">
            <h2 id={headingId} className="help-panel-title">
              Help
            </h2>
            <button
              type="button"
              className="help-panel-close"
              aria-label="Close help"
              onClick={() => setOpen(false)}
            >
              <X size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>

          <div className="help-panel-body">
            <section className="help-section">
              <h3>How it works</h3>
              <ol className="help-steps">
                {WORKFLOW_STEPS.map((step) => (
                  <li key={step.id}>
                    <strong>{step.label}</strong> {step.text}
                  </li>
                ))}
              </ol>
              {/*
                UX-021 — THE WALKTHROUGH POINTER. The Impeccable critique named
                "no link to the guided walkthrough one route away" as part of
                this surface's P1 regression: Help explained the workflow in
                prose while the product's one interactive teaching path was
                reachable only by knowing where to look.

                THE DESTINATION IS SETTINGS, NOT MY EXPERIMENTS, AND THAT IS A
                CORRECTNESS POINT RATHER THAN A PREFERENCE. The obvious pointer
                — "press Launch Guided Demo on My Experiments" — is FALSE for
                any reader who has already finished the walkthrough: that
                control is gated on the queue and, per
                `ExperimentsHome.tsx`'s own note, "disappears for good once the
                walkthrough is finished", with the replay control living in
                Settings & API -> Help & Tutorial. `lib/routes.ts:19` already
                calls that tab "the one permanent home of the guided
                walkthrough". So the only pointer that is true for every reader
                is the permanent one, and a Help surface is exactly where a
                first-time-only claim would do the most damage.

                ZERO NEW VOCABULARY: `LABELS.actionGoToHelpAndTutorial` and
                `ROUTES.settingsTab('help')` both already exist and are already
                used for this destination elsewhere. A real `<Link>` rather than
                a button, so it is middle-clickable, bookmarkable and reachable
                by the keyboard walk — and it is now the first focusable item
                inside the trapped dialog, which is why the trap above had to
                land in the same change.
              */}
              <p className="help-walkthrough-pointer">
                Prefer to be shown? The guided walkthrough opens a worked example and
                steps through this in the product.{' '}
                <Link to={ROUTES.settingsTab('help')}>
                  {LABELS.actionGoToHelpAndTutorial}
                </Link>
              </p>
            </section>

            <section className="help-section">
              <h3>No guessing</h3>
              <p>
                Fields are filled only from evidence or your explicit confirmation.
                &quot;I don&apos;t know&quot; is always a safe answer — a field with no support stays
                empty rather than being guessed.
              </p>
            </section>

            <section className="help-section">
              {/* Was "This prototype runs on synthetic demo data only — no real
                  experiment data." — a flat guarantee the app cannot make: it
                  enforces the runtime MODE, and there is no real-vs-synthetic
                  detector anywhere in the backend (`isaac_api/runtime_mode.py`).
                  That correction stands: the first paragraph still says the app
                  gates on mode, not on contents.

                  Slice 2A (I5) added the second paragraph and retitled the
                  section "Synthetic mode" → "Synthetic workspace". The mode
                  claim was true but was being read as a claim about the whole
                  deployment, which stopped being accurate once a protected,
                  read-only diagnostic could run against an isolated test
                  database of production-derived records. The heading now names
                  what is actually synthetic — the workspace — matching the top-
                  bar chip and components/GovernanceBanner.tsx, and the two
                  paragraphs keep the claims apart.

                  Same load-bearing wording constraints as GovernanceBanner.tsx
                  and screens/GovernancePage.tsx: "may run", never "is running"
                  (configuration is not reachability); an isolated SLAC test
                  database, never the production database; and no claim that the
                  app verified that isolation — the guarantee is an external
                  pg_hba grant, not something this app can check. */}
              <h3>Synthetic workspace</h3>
              <p>
                The records shown here are synthetic and uploads are disabled: this deployment is
                configured for synthetic-only operation, and real mode intentionally refuses to
                start because the required ingestion and governance guardrails do not exist yet.
                What the app enforces is that mode, not the contents of what it is handed.
              </p>
              <p style={{ marginTop: 8 }}>
                Separately, this deployment may run a protected, read-only diagnostic against an
                isolated SLAC test database containing production-derived records: those records are
                processed transiently in pod memory, only sanitized aggregate results are returned,
                no record is modified, no per-record content is displayed, and nothing is sent to
                any model. Database-backed record display remains disabled pending an explicit
                visibility decision.
              </p>
            </section>

            {/* ── UX-021b — SEVEN TOP-LEVEL SECTIONS BECOME FOUR, BY DISCLOSURE
                AND NOT BY DELETION ──────────────────────────────────────────
                The ledger entry that asked for this said so in as many words:
                "the 7->4 reduction wants progressive disclosure, not deletion".
                The reason it has to be disclosure is that four of these seven
                sections carry claims that are PINNED BY TESTS as honesty
                guarantees -- `upload-claim-parity.test.tsx` §6 requires the
                "Where values come from" section to name BOTH file-reading
                controls and never to state the upload refusal unscoped, and
                `help-claim-parity.test.tsx` pins the gate and signal wording
                against three separately-retired false versions. Shortening this
                surface by removing any of that would be a disclosure
                regression dressed as polish.

                So NOTHING here is rewritten and nothing is dropped: every
                `.help-section` still exists with its own `<h3>`, which is also
                why every existing guard keeps matching (they query
                `.help-section h3` by text, and `querySelectorAll` reaches
                inside a collapsed `<details>`).

                WHAT A FIRST-TIME READER MEETS IS WHAT CHANGED. Open, in order:
                how the workflow runs, the no-guessing promise, and the scope of
                this deployment. The mechanism -- where a value comes from,
                which three signals exist, which three gates refuse an export,
                and where evidence is stored -- is one keystroke away instead of
                four screens down. `UX-021` measured this surface as 89% longer
                than it should be; this is that finding addressed without
                touching a single claim.

                A NATIVE `<details>`, which is the repo idiom (`FetchStates`,
                `SchemaBrowser`, `AssistantPanel`): keyboard-operable with no
                ARIA, announced as a disclosure, and -- the part that matters
                for this repository -- OPENED BY THE ACCESSIBILITY SWEEP, so
                every sentence behind it is still scanned at every viewport. */}
            <details className="help-more">
              <summary className="help-more-summary">How values, signals and gates work</summary>
              <section className="help-section">
                {/* CORRECTED. The first workflow step used to read:
                    "Draft extracts candidate field values FROM YOUR FILES, each tagged
                    with cited evidence." That described a capability this build does not
                    have, on the screen a first-time scientist opens to learn what the
                    product does.

                    MEASURED, not inferred. `POST /api/uploads` is an unconditional 403
                    and declares no multipart form at all (`routes.py:20946-20982`: "no
                    multipart is declared or parsed; no file is read or stored"); a sweep
                    for `UploadFile`/`multipart`/`File(` across `apps/api/isaac_api/*.py`
                    finds no parser anywhere, only comments saying there is none. The one
                    route that reads scientific content out of a file,
                    `POST /api/experiments/{id}/ingestion/csv/preview`, is read-only —
                    "no draft change, no revision bump, no export, no indexing, and no
                    retained upload" — and has NO apply route, which `CLAUDE.md` §15
                    records as a committed human decision rather than missing work. So no
                    path in this build turns a file into draft content.

                    Where the false sentence came from is worth keeping: it is an accurate
                    description of the `/isaac-draft` CLAUDE CODE SKILL, which reads files
                    under `examples/` and writes `drafts/*.draft.json`. That is an
                    agent-side tool a scientist using the hosted app cannot reach, and
                    importing its description into the product's Help is the same category
                    error as the retired five-step vocabulary above.

                    THIS REPLACEMENT STATES BEHAVIOUR, NOT A CAPABILITY, because a
                    softened version of the old sentence would still have been false —
                    §11 records that exact failure mode shipping twice. It deliberately
                    does NOT claim that acceptance of a dictated candidate writes a value:
                    the review route answers `409 human_actor_required` in every
                    default-configured deployment (`routes.py:13672`), so "dictate and it
                    becomes a field" would be the next false claim.

                    CORRECTED AGAIN (I-2), AND THE PARAGRAPH ABOVE IS WHY. Its last
                    clause used to end "...and it names no file READER, because naming one
                    without the in-memory and outcome-only bounds is the exact
                    half-disclosure `__tests__/upload-claim-parity` §2 exists to prevent".
                    The sentence it was defending NAMED ONE READER (the campaign-sheet
                    CSV comparison) AND OMITTED THE OTHER — so the comment asserted the
                    property the copy beside it did not have, which is the shape §11
                    records over and over. The omitted reader is a button labelled
                    "Upload JSON File" (`components/RecordValidator.tsx:241`) over a
                    file-typed `<input>` (`:245`) whose handler calls `file.text()`
                    (`:40`) and POSTs the contents — mounted one tab away from this
                    popover's own Governance page.

                    AND "file upload is refused" WAS UNSCOPED. §11 records that claim as
                    true of `POST /api/uploads` ONLY, and records the same claim class
                    shipping false three times before, each time repaired by SCOPING it
                    rather than deleting it. Unscoped, on a build with a visible "Upload
                    JSON File" control, it is the reader's own eyes against the copy.

                    BOTH READERS ARE NAMED NOW AND THE REFUSAL IS SCOPED TO THE ROUTE.
                    Measured rather than assumed: exactly two components under
                    `apps/web/src` declare a file-typed `<input>` —
                    `components/RecordValidator.tsx` and `components/CsvReconcilePanel.tsx`.

                    THE REPRODUCTION COMMAND WAS INVALIDATED BY THE COMMIT THAT WROTE
                    IT, and is corrected here rather than dropped. It read: `rg -al
                    'type="file"' apps/web/src` returns five files, three of them tests.
                    Five was right at `97c44c84`. At HEAD the same command returns SEVEN
                    — a test file was added, and, the part worth remembering, THIS
                    COMMENT BECAME ONE OF ITS OWN HITS by quoting the attribute it was
                    counting. A comment cannot quote the pattern it counts and stay
                    outside the count, so the corrected command excludes this file BY
                    NAME and says why rather than pretending the self-hit away. Note the
                    globs are BASENAME globs: a path glob would have to contain the two
                    characters that end this very comment block, so it cannot be written
                    here at all — which is the self-reference problem twice over.

                      rg -al -g '!*test*' -g '!HelpPanel*' 'type="file"' apps/web/src

                    returns exactly those TWO components (measured 2026-09-12). `-a` and
                    plain `rg` agree — 7 and 7 unfiltered, 2 and 2 filtered — and no file
                    under `apps/web/src` holds a NUL byte, which matters because a plain
                    `rg` silently drops every hit in a file that has one and still exits
                    0.

                    THE EXCLUSION IS THE WEAK PART OF THAT COMMAND, so the count does not
                    rest on it: `__tests__/upload-claim-parity.test.tsx` §1 pins the same
                    claim mechanically, by reading the tree and asserting that the set of
                    NON-TEST files whose JSX declares that attribute is exactly these two
                    — comments stripped, so no prose about the attribute can join the set
                    and no exclusion-by-name is needed. If a third control ever accepts a
                    file, that test fails; this comment going stale is the failure mode it
                    exists to replace.

                    WHY THIS IS STILL NOT A FIFTH SITE OF THE FOUR-PART CLAIM
                    `__tests__/upload-claim-parity` §2 pins. That claim adds two RETENTION
                    bounds — read in memory and never stored; only the outcome logged,
                    never the content. Those belong to a data-governance disclosure, not
                    to a section answering "where does a value come from": they answer a
                    question this section does not raise, and adding them would put ~25
                    more words on the surface the Impeccable critique measured as 89%
                    longer than it should be (`UX-021`). The half-disclosure risk is
                    closed from the other direction instead — `upload-claim-parity` §6
                    pins, with its own polarity proof on the sentence that shipped, that
                    this section names BOTH readers and never states the refusal
                    unscoped. That is the same remedy §5 of that file already applies to
                    the capture site: a fifth site with a DIFFERENT claim shape gets its
                    own narrow ban, not forced membership of §§2-4. */}
                <h3>Where values come from</h3>
                <p>
                  A value gets into a record because a person put it there — typed into a
                  record or run field, or given as an answer to a question above.
                  No control here reads one of your files and fills a field from it. The
                  upload route refuses every request. Three controls read a file you pick:
                  the Validator and the campaign-sheet CSV comparison, which report what
                  they found and apply nothing to a record, and Historical Import&rsquo;s
                  file staging, which opens one only to work out a checksum you asked for
                  and sends nothing anywhere.
                </p>
                <p style={{ marginTop: 8 }}>
                  Dictating into Capture does not write a field either. It stores every
                  segment you dictate as a note, and anything it recognises becomes a
                  proposal for a person to review — so your words survive whether or not
                  a proposal is ever accepted.
                </p>
              </section>
              <section className="help-section">
                {/* CORRECTED: this read "<strong>{LABELS.signalAdvisory} review</strong> is AI
                    consistency notes". That was FALSE, and it was the one sentence on a shipped
                    product screen that implied a model is involved in reviewing a record — which
                    `ai-integration-decision-packet.md` §9 forbids in as many words: "build nothing
                    that implies any of it exists".

                    What the Advisory signal actually is: `GET /api/experiments/{id}/warnings` ->
                    `src/isaac_records/portal_warnings.py`, whose own header calls it "local
                    heuristics" and places it at stage 3 of the validation stack, ADVISORY ONLY and
                    non-gating. It is `tuple(check(record) for check in _CHECKS)` — deterministic,
                    content-derived, no model.

                    The module that IS the AI tier is `src/isaac_records/review.py`, stage 4, an
                    "advisory placeholder" — and it has ZERO production importers (measured: `rg`
                    for `isaac_records.review` / `from .review import` across `src` and `apps/api`,
                    excluding the module itself, returns nothing). Nothing in this build runs it.

                    The sibling copy in `lib/tutorialSteps.ts:195-196` already said this correctly
                    ("advisory notes ... never blocks or authorises anything"), so the two screens
                    disagreed and the wrong one was the one that named a technology. */}
                <h3>Three separate signals</h3>
                {/* CORRECTED (second claim, same defect class as the first). This read
                    "Official Validation is the ISAAC v1.05 schema verdict — THE ONLY
                    SIGNAL THAT GATES EXPORT", and the retired step 4 read "Validate
                    checks the exported record against the official ISAAC v1.05 schema".
                    Both attributed the whole verdict to the upstream schema.

                    MEASURED: `ok = schema_ok AND exactness_ok`. `export.export_draft`
                    runs `check_exactness` on the assembled record at `export.py:339` and
                    refuses BEFORE `validate_official` is called at `:345`, and
                    `cli.py:81` returns `0 if (report.ok and exactness.ok) else 1` with
                    its own comment calling exactness "the ONLY non-schema input to this
                    exit code". So the schema verdict is not the only gate.

                    WHY THE DISTINCTION IS LOAD-BEARING AND NOT PEDANTRY. The schema is
                    upstream-owned (`CLAUDE.md` §1) and the exactness rule is ISAAC's own
                    — `exactness.py`'s header explains at length why it is deliberately
                    NOT in `official.py` — so `CLAUDE.md` §11 forbids any surface from
                    reporting an exactness refusal as an official-schema error. The
                    Validator already draws exactly this line on the wire
                    (`VerdictCard.tsx:62-75` branches on `schemaOk` and renders the
                    exactness findings under their own heading, pinned by
                    `__tests__/validator-exactness.test.tsx`); this popover is now
                    consistent with it instead of teaching the conflation the Validator
                    was fixed to stop making. The advisory tier is unchanged and still
                    gates nothing. */}
                <p>
                  <strong>{LABELS.evidenceAudit}</strong> is a deterministic evidence-coverage count.{' '}
                  <strong>Official {LABELS.signalValidation}</strong> is the ISAAC v1.05 schema
                  verdict.{' '}
                  <strong>{LABELS.signalAdvisory} review</strong> is a set of deterministic
                  local checks over the record's own content; it never blocks or authorizes
                  anything.
                </p>
              </section>
              <section className="help-section">
                {/* CORRECTED (I-2): THE HEADING WAS A COUNT CLAIM AND THE COUNT WAS
                    WRONG. "Two gates on export" named the official schema and the
                    exactness check. RE-DERIVED FROM `src/isaac_records/export.py`, not
                    from any comment about it: `export_draft` has THREE refusal returns —
                    the no-guessing draft report at `:305` (which also carries the
                    record-id check appended at `:298`), `check_exactness` on the
                    assembled record at `:343`, and `validate_official` at `:347` — and
                    exactly ONE success return, at `:350`.

                    THE PRODUCT ALREADY DISAGREED WITH ITSELF ABOUT THIS, in committed
                    prose, on two screens. `screens/ExportReadiness.tsx:789-791` says "it
                    clears THREE gates, not two — `export.py` runs `check_exactness` on
                    the assembled record between the no-guessing report and the official
                    validator", with its own comment explaining that a reader who saw only
                    two had no way to learn a third exists. And
                    `lib/officialAttribution.ts:164` calls them "ISAAC's two gates" —
                    ISAAC's OWN, beside the upstream schema — which is the same arithmetic
                    from the other end. This heading was the outlier.

                    THE CITATION HERE USED TO READ `:11,164` AND "the first two", and both
                    halves were wrong; see the block comment at the top of this file for
                    the full correction. In short: `:11` is item 3 of that module's own
                    three-item list of finding producers, not a statement of any count,
                    and the pair is the LAST two (`:10` and `:11`, paired at `:13`) — item
                    1 is the upstream schema, the one that is precisely NOT ISAAC's.

                    THE OWNERSHIP DISTINCTION IS THE PART THAT MUST SURVIVE ANY REWORDING,
                    and it is not pedantry. The schema is upstream-owned (`CLAUDE.md` §1)
                    and the other two gates are ISAAC's own — `exactness.py`'s header
                    explains at length why it is deliberately NOT in `official.py` — so
                    `CLAUDE.md` §11 forbids any surface from reporting an ISAAC-gate
                    refusal as an official-schema error. `VerdictCard.tsx:62-75` already
                    draws that line on the wire (it branches on `schemaOk` and renders the
                    exactness findings under their own heading, pinned by
                    `__tests__/validator-exactness.test.tsx`). The advisory tier is
                    unchanged and still gates nothing.

                    THE REGEX EXPLANATION IS GONE FROM THE RENDERED COPY, deliberately,
                    and this is the only claim that got SMALLER rather than more precise.
                    It read "...which refuses a value the schema's `^…$` patterns accept
                    only because Python's `$` also matches before a trailing newline" —
                    22 words of regex-flavour trivia on the screen a first-time SCIENTIST
                    opens, named as developer jargon by the Impeccable critique
                    (`UX-021`, P1). Nothing true was dropped: the claim this section has
                    to make is WHICH gates run and WHOSE they are, not why one of them
                    exists. The mechanism is recorded where it belongs — in
                    `exactness.py`'s own header, in `export.py:309-338`, and in the
                    `POST /api/validate/record` description an API reader meets.

                    ~~DO NOT "HARMONISE" THIS WITH `components/ValidateReview.tsx:420`,
                    which says ISAAC applies ONE gate of its own beyond the official
                    schema. That surface validates a PASTED record through
                    `POST /api/validate/record`, where `ok = schema_ok AND exactness_ok`
                    and the no-guessing draft check is not in the path at all. TWO gates
                    there, THREE here. Both are correct about different operations, and a
                    sweep that averaged them would replace one false claim with another.~~

                    WITHDRAWN 2026-09-12, AND KEPT STRUCK RATHER THAN DELETED, because a
                    "DO NOT HARMONISE" instruction is exactly the kind of sentence a
                    future session obeys — this one told three sessions not to fix a real
                    defect, and it said so TWICE in this file, verbatim, which is why one
                    strike was not enough. ATTRIBUTION, stated plainly: the premise came
                    from an ORCHESTRATOR ADDENDUM since retracted in writing; the
                    implementer who transcribed it was following its brief, and the error
                    is the premise's rather than the transcription's.

                    Every load-bearing part of it is false, RE-MEASURED here rather than
                    taken on trust. `ValidateReview` does NOT call
                    `POST /api/validate/record` — it calls `api.validate(experimentId)`
                    (`ValidateReview.tsx:305`), i.e. `POST /api/experiments/{id}/validate`
                    (`lib/api.ts:2081-2083`) — and the retired sentence's own last clause
                    sent the reader AWAY to the Standalone Validator, so it was never that
                    route's copy. It therefore describes THIS path, where the gates number
                    THREE (`export.py:305`, `:343`, `:347`, against one success return at
                    `:350`) and TWO of them are ISAAC's own. Same operation, same count —
                    so "TWO gates there, THREE here" is wrong twice, and the
                    `ValidateReview` copy it forbade touching was a genuine defect.

                    IT IS ALSO STALE. That copy HAS been corrected; the sentence quoted
                    above no longer exists there, and `ValidateReview.tsx:423-430` keeps it
                    struck with a third falsehood nobody had named — its trailing clause
                    predated the `official_validator_ran` discriminator
                    (`routes.py:19036`), so a CANDIDATE record's findings CAN be headed
                    "Official ISAAC schema findings" (`lib/officialAttribution.ts:188`).

                    WHAT IS ACTUALLY FORBIDDEN is narrower, and
                    `lib/officialAttribution.ts:163-169` already states it as a rule: copy
                    attributing a REFUSAL may not name ONE of ISAAC's two gates as its
                    source, because `export.py:342` folds the exactness findings into
                    `draft_report` and the response cannot say which of the two refused.
                    That governs ATTRIBUTING A FINDING, not listing which gates run — the
                    paragraph below names all three, claims no finding for any of them,
                    and is inside the rule.

                    MARKUP NOTE, because it is load-bearing for the guards rather than
                    cosmetic: `__tests__/help-and-honesty.test.tsx:108-109` asserts
                    `/anchored-pattern exactness check/i` and `/Neither the evidence audit
                    nor advisory review gates anything/i` through RTL's `getByText`, which
                    reads `getNodeText` — only an element's DIRECT text children. Both
                    strings therefore have to sit in the `<p>`'s own text runs and not
                    inside the `<strong>`. They do; the two `.mono` spans that used to
                    split this paragraph are gone with the jargon. */}
                <h3>Three gates on export</h3>
                <p>
                  Export runs three checks, in order: the no-guessing draft checks,
                  ISAAC&apos;s own anchored-pattern exactness check, and the official ISAAC
                  v1.05 schema. The first two are{' '}
                  <strong>ISAAC&apos;s, not the schema&apos;s</strong> — a record can be valid
                  against that schema and still be refused here, and no screen reports such
                  a refusal as a schema error. Neither the evidence audit nor advisory
                  review gates anything.
                </p>
              </section>
              <section className="help-section">
                {/* CORRECTED (QA-013). The first sentence read "Every field links to its
                    evidence trail in the record." The ledger's `QA-013` row recorded it
                    as UNMEASURED and warned in terms: "Do not read UX-003/004 as having
                    validated it." Measured, it was false three independent ways — all
                    three inside that one sentence.

                    1. NOTHING LINKS. `components/EvidenceRow.tsx` renders a
                       `div.ev-row` containing `span`s only (`:44-67`). A sweep of that
                       whole file for `<a `, `href`, `Link`, `button`, `onClick` and
                       `role=` returns ZERO hits on each, plain and with `-a`; the same
                       sweep over `components/FieldRow.tsx` (for `<a `, `href`, `<Link`,
                       `navigate`, `onClick`) also returns zero. The citation is rendered
                       INLINE, in place — its own docstring says it is "never hidden
                       behind a hover-only tooltip" — so there is nothing to click and
                       nowhere a click would go.

                    2. NOT EVERY FIELD, AND THAT IS BY DESIGN. `FieldRow.tsx:81` gates the
                       evidence block on `field.evidence && field.evidence.length > 0`, and
                       `CLAUDE.md` §5 guarantees fields with no evidence exist on purpose —
                       ~~`FieldRow.tsx:68` renders the literal `'honestly missing'` for
                       exactly that case~~ — **corrected 2026-09-14, casing conformance.**
                       That literal is GONE: it was one of two hardcoded lowercase strings
                       rendered in the value slot beside a Title Case `<StatusChip>`, so the
                       row announced one state twice in two registers. The row now renders an
                       `aria-hidden` dash there and lets the chip carry the words, which for
                       the evidence-free case reads `Missing` (`LABELS.chipMissing`). The
                       claim this footnote supports is UNCHANGED and is still true — the
                       state is still rendered, and still carries no citation — only the
                       mechanism that renders it moved. So the product deliberately ships fields with no
                       citation while Help told the scientist every field had one. This is
                       the worst of the three: it contradicts the policy the product is
                       FOR.

                    3. AWAITING CONFIRMATION SUPPRESSES IT EVEN WHEN EVIDENCE EXISTS. The
                       same condition carries `&& !needsYou`, so a field whose value is
                       still to be confirmed shows no citation whatever is recorded
                       against it.

                    SCOPED, NOT DELETED — §11's established remedy for this claim class,
                    and the right one here for a product reason as well as a procedural
                    one: evidence provenance is one of this prototype's two pillars, and a
                    scientist who is not told where citations appear will look for a trail
                    that does not exist. The true positive claim is worth more than the
                    false universal one, and it is shorter.

                    THE SECOND SENTENCE IS KEPT BECAUSE IT WAS RE-DERIVED, NOT INHERITED.
                    `export.build_sidecar` (`src/isaac_records/export.py:200`) builds the
                    path-keyed evidence map, and `cli.py:100` writes it to
                    `records_dir / f"{rid}.evidence.json"` beside `{rid}.json` — the exact
                    layout `CLAUDE.md` §4 documents. The `.mono` span stays here: no guard
                    matches across it, and a filename is the one thing on this surface that
                    earns a monospace face. */}
                <h3>Where evidence lives</h3>
                <p>
                  Citations show inline beside the value where evidence was recorded; a
                  field honestly missing or awaiting your confirmation shows none. Exports
                  write an evidence sidecar
                  (<span className="mono">&lt;record&gt;.evidence.json</span>) beside the
                  official record.
                </p>
              </section>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}
