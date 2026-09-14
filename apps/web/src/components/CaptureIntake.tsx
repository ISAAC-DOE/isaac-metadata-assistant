import { useId } from 'react';
import { Link } from 'react-router-dom';
import { FileText, AudioWaveform, ExternalLink } from './icons';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { ROUTES } from '../lib/routes';

/**
 * THE FIRST THING ON THE CAPTURE WORKSPACE: how do you want to get this
 * experiment in?
 *
 * ── WHY IT EXISTS (project owner, 2026-09-13) ──────────────────────────────
 *
 * Capture moved to the top of the record rail, and the owner's reason was that
 * this is where a scientist's own work starts — they arrive from the instrument
 * with something to write down, something to say, or files. Before this, the
 * capture workspace opened on a single collapsed button ("Capture Experiment
 * Notes") and a reader had to open it to discover what was inside, while the
 * file route lived on a different top-level destination entirely and the
 * recorder was three controls deep.
 *
 * ── THE HONEST PART, WHICH IS ALSO THE DESIGN ──────────────────────────────
 *
 * The owner named two routes: files, and voice with transcription. Measured over
 * HTTP, BOTH are externally blocked in this build and the unnamed third is not:
 *
 *     POST .../transcript       -> 200   (typed/pasted text -> note -> proposals)
 *     POST /api/transcription   -> 501   no_provider_configured
 *     POST /api/uploads         -> 403   unconditional
 *
 * A chooser offering only the two named would put a scientist in front of two
 * doors that do not open. So `Write it down` is listed FIRST and is the only
 * primary-styled action, because it is the one route that reaches a proposal
 * today; the other two are offered with what they actually do.
 *
 * NOTHING HERE IMPLIES TRANSCRIPTION WORKS — `CLAUDE.md` §15 and
 * `ai-integration-decision-packet.md` §6 (no fake `Connected` state; "build
 * nothing that implies any of it exists"). Dean deferred D1–D9, so there is no
 * approved provider and no application change can create one. The limit is
 * stated ON the card, names whose decision it is, and says what the control
 * still does — a reader can tell a deferred decision from a broken feature.
 *
 * ── WHAT THIS IS NOT ───────────────────────────────────────────────────────
 *
 * NOT a workflow step. It has no completion state, no tick, no lock and no
 * `aria-current="step"`, for the reason `workflow.py:128-149` keeps submission
 * out of `CANONICAL_ORDER`: a step needs a criterion the record's own signals
 * can decide, and "the scientist has finished capturing" is not one. Being
 * FIRST and being a STEP are different claims, and only the first was asked for.
 *
 * NOT a second way to do any of these things. Each card routes to the ONE
 * existing surface that owns that intake — the capture panel below, or
 * Historical Import — so there is no duplicate implementation to drift.
 */
export interface CaptureIntakeProps {
  /** Opens the capture panel below. */
  onOpenCapture: () => void;
  /**
   * Opens the capture panel below for the VOICE route.
   *
   * TODAY THIS DOES THE SAME THING AS {@link onOpenCapture}, and saying so is
   * the point — an earlier version of this comment claimed it "focuses the
   * recorder", which it does not: `RecordWorkbench` passes the same handler to
   * both, and nothing here moves focus. The recorder controls are visible as
   * soon as the panel opens, so the label is not false, but landing focus on
   * them is NAMED RESIDUE rather than something this prop already does.
   *
   * It stays a separate prop because the two routes are genuinely different
   * intents, and a caller that wants to distinguish them should not have to
   * change this component's signature to do it.
   */
  onOpenRecorder: () => void;
}

export function CaptureIntake({
  onOpenCapture,
  onOpenRecorder,
}: CaptureIntakeProps) {
  /* `useId`, not a literal — the same hazard `RecordWorkspaceNav` records: a
     fixed `id` works while exactly one of these is mounted and becomes a silent
     duplicate the moment a second is (a split view, a test rendering two).
     A `<section>` whose `aria-labelledby` resolves to the wrong heading is
     precisely the class of defect this slice already shipped once. */
  const headingId = useId();
  return (
    <section className="capture-intake" aria-labelledby={headingId}>
      <h2 className="capture-intake-heading" id={headingId}>
        {CAPTURE_COPY.intakeHeading}
      </h2>
      <p className="capture-intake-intro">{CAPTURE_COPY.intakeIntro}</p>

      <ul className="capture-intake-grid">
        <li className="capture-intake-card" data-route="write">
          <span className="capture-intake-icon" aria-hidden="true">
            <FileText size={18} strokeWidth={2} />
          </span>
          <h3 className="capture-intake-title">
            {CAPTURE_COPY.intakeWriteTitle}
          </h3>
          {/* The one route that reaches a proposal today, so it is the one
              labelled available. Text, not a colour — `interaction-states`
              forbids a reserved hue carrying a verdict, and this is a fact
              about the build rather than a status. */}
          <p className="capture-intake-available">
            {CAPTURE_COPY.intakeWriteAvailable}
          </p>
          <p className="capture-intake-body">{CAPTURE_COPY.intakeWriteBody}</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onOpenCapture}
          >
            {CAPTURE_COPY.intakeWriteAction}
          </button>
        </li>

        <li className="capture-intake-card" data-route="voice">
          <span className="capture-intake-icon" aria-hidden="true">
            <AudioWaveform size={18} strokeWidth={2} />
          </span>
          <h3 className="capture-intake-title">
            {CAPTURE_COPY.intakeVoiceTitle}
          </h3>
          <p className="capture-intake-body">{CAPTURE_COPY.intakeVoiceBody}</p>
          {/*
            THE LIMIT IS NOT A DISABLED BUTTON. The recorder genuinely works —
            it records, pauses and plays back — so disabling the control would
            be false in the other direction, and a disabled control with no
            reason is the pattern this repository bans. The button opens the
            recorder; the note says which half is missing and why.
          */}
          <p className="capture-intake-limit" role="note">
            {CAPTURE_COPY.intakeVoiceLimit}
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onOpenRecorder}
          >
            {CAPTURE_COPY.intakeVoiceAction}
          </button>
        </li>

        <li className="capture-intake-card" data-route="files">
          <span className="capture-intake-icon" aria-hidden="true">
            <ExternalLink size={18} strokeWidth={2} />
          </span>
          <h3 className="capture-intake-title">
            {CAPTURE_COPY.intakeFilesTitle}
          </h3>
          <p className="capture-intake-body">{CAPTURE_COPY.intakeFilesBody}</p>
          {/* A real <Link>: it leaves this record for a separately-routed
              destination, so it must be middle-clickable and bookmarkable
              rather than a button that only works on left-click. */}
          <Link className="btn btn-secondary" to={ROUTES.imports}>
            {CAPTURE_COPY.intakeFilesAction}
          </Link>
        </li>
      </ul>
    </section>
  );
}
