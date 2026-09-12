import './help.css';
import { useEffect, useId, useRef, useState } from 'react';
import { CircleHelp, X } from './icons';
import { LABELS } from '../lib/labels';
import { CANONICAL_STEPS } from '../lib/workflowSteps';

/*
 * ONE WORKFLOW VOCABULARY, AND IT IS THE SERVER'S.
 *
 * This list used to be authored here from five now-deleted `LABELS` entries —
 * Draft · Complete · Export · Validate · Audit — while every per-record surface
 * in the same product showed the server-derived spine: Load Record · Complete
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
  load_record:
    'opens a record. Every step below is re-derived from that record’s current state each time it is read — your position in the sequence is never stored.',
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
  // `export.export_draft` applies BOTH gates, in this order: `check_exactness`
  // on the assembled record (`export.py:339`) and then `validate_official`
  // (`export.py:345`). Naming only the schema attributed an ISAAC policy to an
  // upstream document — see the "Two gates" section below.
  export:
    'writes the official ISAAC record plus an evidence sidecar — and only when both export gates pass.',
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

  // Escape + click-outside close while open.
  useEffect(() => {
    if (!open) return;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
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
                  becomes a field" would be the next false claim. And it names no file
                  READER, because naming one without the in-memory and outcome-only
                  bounds is the exact half-disclosure `__tests__/upload-claim-parity`
                  §2 exists to prevent — that claim has four sites already and this
                  popover is not a fifth. */}
              <h3>Where values come from</h3>
              <p>
                A value gets into a record because a person put it there — typed into a
                record or run field, or given as an answer to one of the questions above.
                No control here reads one of your files and fills a field from it: file
                upload is refused, and the campaign-sheet CSV comparison is read-only
                with no route that applies what it found.
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
              <h3>Two gates on export</h3>
              <p>
                Export is gated on the official ISAAC v1.05 schema <em>and</em> on ISAAC&apos;s own
                anchored-pattern exactness check, which refuses a value the schema&apos;s{' '}
                <span className="mono">^…$</span> patterns accept only because Python&apos;s{' '}
                <span className="mono">$</span> also matches before a trailing newline. A
                refusal by that check is <strong>ISAAC&apos;s, not the schema&apos;s</strong>: the
                record can be valid against official ISAAC v1.05 and still be refused here,
                and no screen reports such a refusal as a schema error. Neither the evidence
                audit nor advisory review gates anything.
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

            <section className="help-section">
              <h3>Where evidence lives</h3>
              <p>
                Every field links to its evidence trail in the record. Exports write an evidence
                sidecar (<span className="mono">&lt;record&gt;.evidence.json</span>) beside the
                official record.
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
