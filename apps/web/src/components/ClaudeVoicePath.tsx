import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy } from './icons';
import { Disclosure } from './Disclosure';
import { SemanticStatus } from './SemanticStatus';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { MCP_ENDPOINT } from '../lib/mcpConnectContent';
import { ROUTES } from '../lib/routes';
import { useHealthState } from '../lib/useHealth';
import type { ApiHealth } from '../lib/types';

/**
 * VOICE CAPTURE THROUGH CLAUDE — the primary path of "Record at the Instrument"
 * (owner QA 2026-09-22, C3).
 *
 * The intended path is Scientist → Claude app → ISAAC's agent interface (MCP) →
 * notes and proposals → this record. Speech becomes text in the Claude app, and
 * only text crosses into ISAAC (`isaac_capture_transcript`). Audio recorded in this
 * browser can only be played back and typed from — every transcription provider
 * answers 501 — which is why the local recorder is the secondary path.
 *
 * ── THE STATE IS READ, NEVER ASSUMED, FROM TWO SOURCES THAT ALREADY EXIST ────
 *
 *  1. `/api/health` → `mcp.posture`, the server's own derivation from the three
 *     flags the application actually consults (`mcp/deployment.py::posture`).
 *  2. `MCP_ENDPOINT`, the published address Settings → Connect Your Agent renders
 *     from — so this view and that tab cannot disagree about whether there is an
 *     address to add in Claude.
 *
 * The "ready for a connector" state needs BOTH: a posture a remote caller could
 * reach (`oauth-mounted`, or `remote-ready`, which no configuration of this build
 * reports) AND a published address, because the steps begin with adding one.
 * Everything else is "not enabled", with the specific reason the server gave.
 *
 * ── THERE IS NO "CONNECTED" STATE, AND THERE CANNOT BE ONE ──────────────────
 *
 * Nothing in this application can observe a Claude app. A connected state would
 * need a signal the browser does not have, and `ai-integration-decision-packet.md`
 * §6 forbids a fake one. The type below has no such member, so the claim has
 * nowhere to live; the ready state says so in words instead.
 */
export type ClaudeVoiceState =
  | { kind: 'checking' }
  | { kind: 'unavailable'; reason: 'unmounted' | 'local-only' | 'no-address' | 'unreported' }
  | { kind: 'ready'; endpoint: string };

export function claudeVoiceState(
  settled: boolean,
  health: ApiHealth | undefined,
  endpoint: string | null,
): ClaudeVoiceState {
  if (!settled) return { kind: 'checking' };
  const posture = health?.mcp?.posture ?? null;
  if (posture === 'unmounted') return { kind: 'unavailable', reason: 'unmounted' };
  if (posture === 'local-only') return { kind: 'unavailable', reason: 'local-only' };
  if (posture === 'oauth-mounted' || posture === 'remote-ready') {
    return endpoint === null
      ? { kind: 'unavailable', reason: 'no-address' }
      : { kind: 'ready', endpoint };
  }
  // Absent block, a failed read, `null` ("could not determine") or a posture this
  // client does not recognise: none of them is evidence a connector would work.
  return { kind: 'unavailable', reason: 'unreported' };
}

const UNAVAILABLE_COPY: Record<
  Extract<ClaudeVoiceState, { kind: 'unavailable' }>['reason'],
  string
> = {
  unmounted: CAPTURE_COPY.claudeUnmounted,
  'local-only': CAPTURE_COPY.claudeLocalOnly,
  'no-address': CAPTURE_COPY.claudeNoAddress,
  unreported: CAPTURE_COPY.claudeUnreported,
};

export function ClaudeVoicePath({
  experimentId,
  experimentTitle,
  runLabel,
  endpoint = MCP_ENDPOINT,
}: {
  experimentId: string;
  experimentTitle: string;
  /** The run chosen for capture on this record, or `null` — never guessed. */
  runLabel: string | null;
  /** Test seam; the product always passes the module constant. */
  endpoint?: string | null;
}) {
  const headingId = useId();
  const { settled, health } = useHealthState();
  const state = claudeVoiceState(settled, health, endpoint);
  const starter = CAPTURE_COPY.claudeStarter(experimentTitle, experimentId, runLabel);

  return (
    <section className="claude-voice" aria-labelledby={headingId}>
      <h3 className="claude-voice-heading" id={headingId}>
        {state.kind === 'ready' ? CAPTURE_COPY.claudeReadyHeading : CAPTURE_COPY.claudeHeading}
      </h3>

      {state.kind === 'checking' && (
        <p className="claude-voice-line" role="status">
          {CAPTURE_COPY.claudeChecking}
        </p>
      )}

      {state.kind === 'unavailable' && (
        <>
          <div className="claude-voice-state" role="status">
            <SemanticStatus state="unavailable" label="Not Enabled Here" size="sm" />
            <p className="claude-voice-line">{UNAVAILABLE_COPY[state.reason]}</p>
          </div>
          <div className="claude-voice-actions">
            <Link className="btn btn-secondary" to={ROUTES.settingsTab('mcp')}>
              {CAPTURE_COPY.claudeConnectAction}
            </Link>
          </div>
        </>
      )}

      {state.kind === 'ready' && (
        <>
          <ol className="claude-voice-steps">
            <li>
              {CAPTURE_COPY.claudeStepAdd}{' '}
              <code className="mono claude-voice-endpoint">{state.endpoint}</code>
            </li>
            <li>{CAPTURE_COPY.claudeStepSignIn}</li>
            <li>{CAPTURE_COPY.claudeStepSay}</li>
          </ol>
          <StarterInstruction text={starter} noRun={runLabel === null} />
          <p className="claude-voice-note">{CAPTURE_COPY.claudeNotObservable}</p>
        </>
      )}

      {/* THE OLD "Transcribe With Your Claude App Instead" CONTENT, RECONCILED
          RATHER THAN DUPLICATED: it lived inside the recorder, where the reader
          had just been told the recorder cannot produce text. It now explains the
          primary path, once, here — and the recorder no longer repeats it. */}
      {state.kind !== 'ready' && (
        <Disclosure summary={CAPTURE_COPY.claudeHowHeading} className="claude-voice-how">
          <p className="capture-note">{CAPTURE_COPY.mcpRouteLead}</p>
          <p className="capture-note">{CAPTURE_COPY.mcpRoutePrecondition}</p>
          <p className="capture-guidance-label">{CAPTURE_COPY.mcpRouteSayLabel}</p>
          <p className="capture-mcp-say">{starter}…</p>
          <p className="capture-note">{CAPTURE_COPY.mcpRouteOutcome}</p>
        </Disclosure>
      )}
    </section>
  );
}

/** The copyable starter. Copying is a courtesy; the text is selectable either way. */
function StarterInstruction({ text, noRun }: { text: string; noRun: boolean }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
  };
  return (
    <div className="claude-voice-starter">
      <p className="capture-label">{CAPTURE_COPY.claudeStarterLabel}</p>
      <div className="claude-voice-starter-row">
        <code className="mono claude-voice-starter-text">{text}</code>
        <button type="button" className="btn btn-secondary" onClick={() => void copy()}>
          <Copy size={14} strokeWidth={2} aria-hidden="true" />
          {CAPTURE_COPY.claudeCopy}
        </button>
      </div>
      {noRun && <p className="capture-hint">{CAPTURE_COPY.claudeStarterNoRun}</p>}
      <p className="sr-only" role="status" aria-live="polite">
        {copyState === 'copied'
          ? CAPTURE_COPY.claudeCopied
          : copyState === 'failed'
            ? CAPTURE_COPY.claudeCopyFailed
            : ''}
      </p>
      {copyState === 'failed' && <p className="capture-hint">{CAPTURE_COPY.claudeCopyFailed}</p>}
    </div>
  );
}
