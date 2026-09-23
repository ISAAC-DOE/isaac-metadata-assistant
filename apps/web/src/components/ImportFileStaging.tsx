import { useCallback, useId, useRef, useState } from 'react';

import { Disclosure } from './Disclosure';
import { FileText, Plus, X } from './icons';
import './import-file-staging.css';

/**
 * CHOOSING FILES FOR AN IMPORT, WITHOUT SENDING ONE.
 *
 * ── THIS REVERSES A RECORDED, REASONED DECLINE ──────────────────────────────
 *
 * `screens/HistoricalImport.tsx` carries a comment saying a previous session
 * BUILT a multi-file picker and REVERTED it. Its argument, which is a good one
 * and is quoted rather than paraphrased:
 *
 *   "A `Choose Files…` button is an upload affordance whatever it does
 *    underneath — a scientist who picked twelve files would reasonably believe
 *    twelve files had been uploaded. Recording their names while they believe
 *    that is worse than asking them to type, because it is a false impression
 *    the product created on purpose."
 *
 * The project owner overturned that on 2026-09-15 (`DEC-33`) — and, crucially,
 * he answered its OBJECTION rather than overruling it: every staged row must
 * say `Local only — not sent to ISAAC`, and his instruction is explicitly *"Do
 * not merely delete the guards. Reconcile them."* So the decline stands in the
 * source beside its reversal, because it was right about the risk, and this
 * component exists to carry the mitigation it asked for.
 *
 * ── WHY THIS NEEDS NO NEW CAPABILITY, WHICH IS WHAT MAKES IT HONEST ─────────
 *
 * `POST /api/imports/{id}/sources` ALREADY accepts `kind: "reference"` with
 * `filename`, `reference`, `media_type`, `size_bytes` and `sha256`; it stores
 * them verbatim, FETCHES NOTHING, and records the entry as
 * `parse_state: "no_content_path"`. A browser hands over `File.name`,
 * `File.size` and `File.type` AS PART OF THE SELECTION — no read is involved —
 * so a picker can fill every one of those fields without opening the file.
 *
 * Measured over HTTP against a local backend, 2026-09-15: an entry sent with a
 * real filename, a real size and a genuine SHA-256 lands with exactly those
 * values and `parse_state: "no_content_path"`. So this changes no route, adds
 * no capability, and moves no governance boundary. `POST /api/uploads` is still
 * an unconditional 403 and this component never calls it.
 *
 * ── THE ONE THING THAT DOES READ BYTES, AND WHY IT IS OPT-IN ────────────────
 *
 * A checksum cannot be computed without reading the file. So it is NOT
 * automatic: the row offers `Compute checksum`, per file, and says what it will
 * do before it does it. Two reasons, and the second is not the obvious one:
 *
 *   1. HONESTY. The default state of a staged row is then literally true —
 *      nothing has opened this file. Computing on selection would have made the
 *      panel's own summary claim false for every row, which is this
 *      application's signature defect class.
 *   2. MEMORY. `file.arrayBuffer()` reads the WHOLE file. A raw beamline
 *      dataset is exactly the kind of thing a scientist would drop here, and
 *      silently pulling a multi-gigabyte file into the tab to compute a digest
 *      nobody asked for is a performance defect dressed as provenance.
 *
 * AND THE DIGEST IS NEVER DESCRIBED AS VERIFIED. The route's own description
 * says `sha256` is checked for SHAPE only and is "never computed" server-side,
 * and that no surface may call it verified, checked or matched. A digest
 * computed here is computed by the CLIENT, over bytes the server never sees, and
 * remains the caller's claim about the file. The copy says "computed in your
 * browser" and never "verified".
 */

/** How far one chosen file has got. Nothing here describes a transfer. */
export type StagedFileState = 'local' | 'recording' | 'recorded' | 'failed';

export interface StagedFile {
  /** Stable across re-renders; a filename is not unique and a File is not a key. */
  key: string;
  name: string;
  /** Bytes, from the browser's own file metadata. Never measured by reading. */
  size: number;
  /** The browser's guess. Often `''`, and an empty string is not a defect. */
  mediaType: string;
  file: File;
  state: StagedFileState;
  /** Present only after the reader explicitly asks for one. */
  sha256: string | null;
  digestBusy: boolean;
  /** The reason a record attempt or a digest failed, in the server's words. */
  error: string | null;
}

/** `1.4 KB`, `812 bytes`. Display only — the exact byte count is what is sent. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return 'unknown size';
  if (bytes < 1024) return `${bytes} byte${bytes === 1 ? '' : 's'}`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

let staggerCounter = 0;
function nextKey(): string {
  staggerCounter += 1;
  return `staged-${staggerCounter}`;
}

/**
 * SHA-256 of the file, computed in this tab.
 *
 * `crypto.subtle` is unavailable on an insecure origin that is not localhost,
 * so this can legitimately be absent. It returns `null` rather than throwing,
 * and the row then says the checksum could not be computed here — it never
 * invents one, and a missing digest is simply a source entry without one, which
 * the route already accepts.
 */
async function digestInBrowser(file: File): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (subtle === undefined) return null;
  try {
    const buffer = await file.arrayBuffer();
    const hashed = await subtle.digest('SHA-256', buffer);
    return Array.from(new Uint8Array(hashed))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    return null;
  }
}

export interface ImportFileStagingProps {
  /**
   * Record ONE staged file as a source entry. The caller owns the API call, so
   * this component never imports `api` and cannot be the thing that sends a
   * byte — a structural guarantee rather than a promise in a comment.
   */
  onRecord: (input: {
    filename: string;
    reference: string;
    mediaType: string;
    sizeBytes: number;
    sha256: string | null;
  }) => Promise<void>;
  /** Disables the controls while the session is busy with another act. */
  busy?: boolean;
}

export function ImportFileStaging({ onRecord, busy = false }: ImportFileStagingProps) {
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inputId = useId();
  const noteId = useId();

  const add = useCallback((files: FileList | File[] | null) => {
    if (files === null) return;
    const incoming = Array.from(files).map<StagedFile>((file) => ({
      key: nextKey(),
      name: file.name,
      size: file.size,
      mediaType: file.type,
      file,
      state: 'local',
      sha256: null,
      digestBusy: false,
      error: null,
    }));
    if (incoming.length === 0) return;
    setStaged((prev) => [...prev, ...incoming]);
  }, []);

  const patch = useCallback((key: string, next: Partial<StagedFile>) => {
    setStaged((prev) => prev.map((row) => (row.key === key ? { ...row, ...next } : row)));
  }, []);

  const remove = useCallback((key: string) => {
    setStaged((prev) => prev.filter((row) => row.key !== key));
  }, []);

  const computeDigest = useCallback(
    async (row: StagedFile) => {
      patch(row.key, { digestBusy: true, error: null });
      const digest = await digestInBrowser(row.file);
      patch(row.key, {
        digestBusy: false,
        sha256: digest,
        error:
          digest === null
            ? 'The checksum could not be computed in this browser. The file can still be recorded without one.'
            : null,
      });
    },
    [patch],
  );

  const record = useCallback(
    async (row: StagedFile) => {
      patch(row.key, { state: 'recording', error: null });
      try {
        await onRecord({
          filename: row.name,
          /*
           * THE REFERENCE IS A STATEMENT ABOUT WHERE THE FILE IS, and for a
           * browser-chosen file the honest statement is that ISAAC does not
           * know. A browser deliberately does not disclose a local path, and
           * inventing one — or writing the bare filename into a field whose
           * whole meaning is "where to find this" — would be a pointer that
           * points nowhere while looking like one that does.
           */
          reference: 'Chosen in the browser; its location was not disclosed to ISAAC',
          mediaType: row.mediaType,
          sizeBytes: row.size,
          sha256: row.sha256,
        });
        patch(row.key, { state: 'recorded', error: null });
      } catch (error) {
        patch(row.key, {
          state: 'failed',
          error: error instanceof Error ? error.message : 'The source could not be recorded.',
        });
      }
    },
    [onRecord, patch],
  );

  return (
    <div className="ifs">
      {/*
        THE DROP TARGET IS NOT THE CONTROL. A `<div>` with an `onDrop` is
        unreachable by keyboard, so the real control is the `<label>`-bound
        `<input type="file">` inside it; the drop handling is an enhancement
        layered on top and nothing depends on it.
      */}
      <div
        className={`ifs-drop${dragging ? ' dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          add(event.dataTransfer?.files ?? null);
        }}
      >
        <FileText size={18} strokeWidth={1.8} aria-hidden="true" className="ifs-drop-icon" />
        <p className="ifs-drop-lead">Drop experiment files here, or choose them.</p>
        <label className="btn btn-secondary ifs-choose" htmlFor={inputId}>
          <Plus size={14} strokeWidth={2.2} aria-hidden="true" />
          Choose Files
        </label>
        <input
          ref={inputRef}
          id={inputId}
          className="ifs-input"
          type="file"
          multiple
          aria-describedby={noteId}
          disabled={busy}
          onChange={(event) => {
            add(event.target.files);
            // Re-selecting the same file must fire `change` again.
            event.target.value = '';
          }}
        />
        {/*
          THE CLAIM THIS WHOLE COMPONENT RESTS ON, and it is deliberately NOT in
          a tooltip. It is a privacy state, and the copy rule is that a
          security/privacy state stays visible.

          It is also worded to be EXACTLY true rather than reassuringly true:
          "not sent" is the claim, and it does not say "not read", because
          `Compute checksum` below does read — in this tab. A blanket "no file
          is read" here would be the same defect this repository has already
          shipped once and pinned a test against.
        */}
        <p className="ifs-claim" id={noteId}>
          {/*
            "lets you record", NOT "records". Choosing a file records NOTHING — it
            stages it in this browser, and recording is the separate per-row
            button. The first wording said otherwise two lines above a row
            reading "Local only — not sent to ISAAC", so the panel contradicted
            itself about the same act, and a reader could reasonably skip
            `Record as source` believing it had already happened. Found by
            independent review.
          */}
          Choosing a file lets you record its name, size and type in this import.{' '}
          <strong>The file itself is not sent to ISAAC</strong>, and no upload route is called.
        </p>
      </div>

      {staged.length === 0 ? null : (
        <ul className="ifs-list" aria-label="Files chosen in this browser">
          {staged.map((row) => (
            <li className={`ifs-row ifs-${row.state}`} key={row.key}>
              <FileText size={15} strokeWidth={1.9} aria-hidden="true" className="ifs-row-icon" />
              <div className="ifs-row-main">
                <span className="ifs-row-name mono">{row.name}</span>
                <span className="ifs-row-meta">
                  {formatBytes(row.size)}
                  {row.mediaType === '' ? '' : ` · ${row.mediaType}`}
                  {row.sha256 === null ? '' : ' · checksum computed in your browser'}
                </span>
                {row.sha256 !== null && (
                  <span className="ifs-row-digest mono" title={row.sha256}>
                    sha256 {row.sha256.slice(0, 16)}…
                  </span>
                )}
                {row.error !== null && <span className="ifs-row-error">{row.error}</span>}
              </div>

              {/* STATE IS A WORD, NOT A COLOUR. Each row says where it stands in
                  text; the class only tints what the text already said. */}
              <span className="ifs-row-state">
                {row.state === 'local' && 'Local only — not sent to ISAAC'}
                {row.state === 'recording' && 'Recording…'}
                {row.state === 'recorded' && 'Recorded as a source'}
                {row.state === 'failed' && 'Not recorded'}
              </span>

              <div className="ifs-row-actions">
                {row.state !== 'recorded' && (
                  <button
                    type="button"
                    className="btn btn-quiet ifs-row-btn"
                    disabled={busy || row.digestBusy}
                    onClick={() => void computeDigest(row)}
                  >
                    {row.digestBusy ? 'Reading…' : row.sha256 === null ? 'Compute checksum' : 'Recompute'}
                  </button>
                )}
                {row.state !== 'recorded' && (
                  <button
                    type="button"
                    className="btn btn-secondary ifs-row-btn"
                    disabled={busy || row.state === 'recording'}
                    onClick={() => void record(row)}
                  >
                    Record as source
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-quiet ifs-row-remove"
                  aria-label={`Remove ${row.name} from this list`}
                  disabled={busy}
                  onClick={() => remove(row.key)}
                >
                  <X size={14} strokeWidth={2.2} aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {staged.length > 0 && (
        /*
          WHAT `Record as source` ACTUALLY DOES, stated where the reader is about
          to press it rather than in a help panel. It is the difference between
          this panel and an uploader, and a reader who does not understand it
          would misread every row above.
        */
        /* The shared `Disclosure`, not a native `<details>` with an 11px triangle
           (independent review, 2026-09-23) — same words, same place. */
        <Disclosure className="ifs-explain" summary="What recording a file does">
          <p>
            It adds the file&rsquo;s name, size, type and — if you computed one — its checksum to
            this import&rsquo;s source list. <strong>The ISAAC server never receives the
            file</strong>, so that entry cannot contribute a parsed statement and is listed as
            having no readable content. A checksum, if you asked for one, was computed here in
            your browser by reading the file you chose — the server does not recompute it and
            does not confirm it.
          </p>
        </Disclosure>
      )}
    </div>
  );
}
