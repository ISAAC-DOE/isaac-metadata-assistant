/*
 * ASSET REFERENCES — where a scientist records the files an experiment points at.
 *
 * WHAT THIS PANEL IS FOR. An ISAAC record does not carry data files; it carries
 * REFERENCES to them — where the file is, what role it plays, and the digest that
 * identifies it. Until now the only place a human touched an asset was a text box in
 * the guided-completion flow that asked for the sha256 of a file the EXTRACTOR had
 * already found; there was no way to record one yourself. This is that surface.
 *
 * THE ONE SENTENCE THIS PANEL MUST NEVER SAY. It must never describe a digest as
 * verified, checked, matched or confirmed against the file. ISAAC does not read,
 * fetch or open the file at the URI — not once, anywhere — so the only thing it can
 * say about a digest is whether the STRING is well formed: 64 lowercase hexadecimal
 * characters. Every piece of copy below is written to that limit, and
 * `assets.test.tsx` asserts the limit rather than trusting it.
 *
 * THREE THINGS THIS PANEL WILL NOT DO, each of which would be easy:
 *
 *   1. IT NEVER FILLS IN A FIELD. No suggested `asset_id` from the role, no
 *      `content_role` guessed from a file extension, no media type inferred from a
 *      suffix, and no run pre-selected — not even when the record has exactly one
 *      run. Every one of those is a scientific or identifying statement, and a
 *      plausible default is still a guess.
 *   2. IT NEVER HIDES AN ASSET THAT WILL NOT BE EXPORTED. An experiment with runs
 *      exports one record per run, composed from that run's own content, and assets
 *      are run-level — so a reference associated with no run reaches no exported
 *      record. The card says so, in words, on the card.
 *   3. IT NEVER REPAIRS A DIGEST. What is typed is what is sent. The server refuses
 *      a digest with a stray space or a trailing newline; trimming it here would
 *      make that refusal invisible and store something the scientist did not enter.
 *
 * ONE VALIDATOR, THE RECORD'S, re-read from each write's own response — the rule
 * `UnmappedNotesPanel` and `RunsSection` both follow, and for the reason they record:
 * between a write and the refetch, every other control on screen is still live, so a
 * held token that is one revision stale manufactures a 412 out of this component's
 * own bookkeeping.
 *
 * NO MODAL. Every form here is an inline disclosure with focus returned to the
 * control that opened it, which is this project's established pattern (see
 * `UnmappedNotesPanel`, `NewExperimentForm`). A dialog was considered and rejected:
 * it would add a focus trap and a scroll lock to a form a reader wants to compare
 * against the card underneath it.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { mutationFailureCopy, staleWriteCurrentVersion } from '../lib/mutationErrors';
import type {
  ApiAsset,
  ApiAssetExportReach,
  ApiAssetsResponse,
} from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import './assets.css';

/** Same narrowing the other panels use — a non-`ApiError` throw still renders a panel. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/**
 * The twelve official roles in product words.
 *
 * A LABEL MAP, NOT A VOCABULARY. The values come from the SERVER, which reads them
 * out of the vendored official schema; this only decides how each reads to a
 * scientist, and an unknown value is shown VERBATIM rather than dropped or renamed.
 * That fallback is what makes it safe for the schema to gain a thirteenth role
 * without this file being the reason it disappears from the control.
 */
const ROLE_LABELS: Readonly<Record<string, string>> = {
  raw_data: 'Raw data',
  raw_data_pointer: 'Raw data — pointer to a location',
  reduction_product: 'Reduction product',
  input_structure: 'Input structure',
  workflow_recipe: 'Workflow recipe',
  processing_script: 'Processing script',
  calibration_reference: 'Calibration reference',
  auxiliary_reference: 'Auxiliary reference',
  documentation: 'Documentation',
  metadata_snapshot: 'Metadata snapshot',
  supplementary_image: 'Supplementary image',
  other: 'Other',
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

/**
 * What `export_reach` means, said in full rather than as a badge word.
 *
 * `none` is the one that earns this map's existence. A one-word chip reading "None"
 * next to an asset a scientist has just recorded communicates nothing; the sentence
 * has to name the consequence, because the consequence — this file will not appear
 * in any exported record — is the whole reason the state is worth showing.
 */
const REACH_TEXT: Readonly<Record<ApiAssetExportReach, string>> = {
  record: 'This record has no runs, so it exports one record and this file is part of it.',
  // "named here", NOT "below": the run labels are rendered immediately before this
  // sentence, in the same line. A direction that points at nothing is a small lie in
  // a panel whose whole argument is that its sentences are literally true.
  runs: 'Part of the export of each run named here.',
  none: 'Not in any export yet — this record exports one record per run, and no run cites this file.',
};

/** The optional official fields this panel offers, in the order they are asked for. */
const OPTIONAL_TEXT_FIELDS: readonly { key: string; label: string; hint?: string }[] = [
  { key: 'media_type', label: 'Media type', hint: 'For example application/x-hdf5. Never inferred from the file name.' },
  { key: 'notes', label: 'Notes' },
  { key: 'figure_label', label: 'Figure label', hint: 'For a figure taken from a publication, e.g. Figure 2b.' },
  { key: 'page', label: 'Page' },
  { key: 'caption_verbatim', label: 'Caption, word for word' },
];

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: ApiAssetsResponse };

/** A draft of the form's text inputs. Everything is a string until it is sent. */
type FormValues = Record<string, string>;

/**
 * What a form was holding when it closed — the D4 fix.
 *
 * THE DEFECT. The control labelled `Record an Asset Reference` was a TOGGLE
 * (`setAdding((open) => !open)`), so the button that opened the create form was the
 * button that destroyed it: nine values in the form's own state, gone on a second
 * click, with no confirmation and nothing on screen to recover them from. The submit
 * inside the form reads `Record This Reference` — near enough to the toggle's label
 * that pressing the wrong one is an ordinary mistake, not carelessness. The peer
 * disclosures on a card did the same to an OPEN EDIT form: `Evidence (n)` and `Remove`
 * both call `setOpen`, and so does `Edit` itself.
 *
 * THE FIX IS THAT NOTHING IS DESTROYED, rather than a confirmation before destroying
 * it. What the form held is kept OUTSIDE the form — in a ref on the component that
 * decides whether the form is mounted — so closing and re-opening finds it as it was.
 * Two things clear it, and only two: the form's own `Cancel`, and a write the server
 * recorded.
 *
 * IT IS SEPARATE FROM `initial`, DELIBERATELY. `initial` is the DIFF BASELINE — an
 * edit sends only what changed, which is what stops an untouched `page` from being
 * rewritten as a string (see `submit`) — so restoring a draft into `initial` would
 * silently redefine "changed" as "different from what I typed last time".
 */
interface FormDraft {
  values: FormValues;
  runIds: string[];
}

const EMPTY_FORM: FormValues = {
  asset_id: '',
  content_role: '',
  uri: '',
  sha256: '',
  media_type: '',
  notes: '',
  figure_label: '',
  page: '',
  caption_verbatim: '',
};

function formFromAsset(asset: ApiAsset): FormValues {
  return {
    ...EMPTY_FORM,
    asset_id: asset.asset_id,
    content_role: asset.content_role,
    uri: asset.uri,
    sha256: asset.sha256,
    media_type: asset.media_type ?? '',
    notes: asset.notes ?? '',
    figure_label: asset.figure_label ?? '',
    page: asset.page === undefined ? '' : String(asset.page),
    caption_verbatim: asset.caption_verbatim ?? '',
  };
}

/**
 * THE CLIENT'S SHAPE CHECK, AND WHAT IT IS FOR.
 *
 * It is exactly the server's rule — 64 lowercase hexadecimal characters, anchored,
 * nothing before or after — restated here for ONE purpose: telling a scientist what
 * is wrong with what they typed before they submit it. It is not a gate. The server
 * refuses independently and its refusal is what decides; if these two ever disagree,
 * the server wins and the banner shows its message.
 *
 * `/^[0-9a-f]{64}$/` WOULD BE WRONG EVEN HERE, and that is not a JavaScript
 * pedantry — in JavaScript `$` does not match before a trailing newline, so the
 * pattern happens to be safe. It is written with an explicit length check anyway so
 * that a reader comparing this to `isaac_records.complete.is_sha256_shaped` sees the
 * same rule rather than a lookalike, and so pasting from a terminal (which is where
 * a trailing newline comes from) fails loudly here rather than only at the server.
 */
export function sha256Shape(value: string): 'empty' | 'ok' | 'malformed' {
  if (value === '') return 'empty';
  return value.length === 64 && /^[0-9a-f]+$/.test(value) ? 'ok' : 'malformed';
}

/**
 * Why a digest is not acceptable, said specifically.
 *
 * "Invalid" tells a scientist nothing. Whitespace is called out by name because a
 * digest is almost always pasted, and a trailing newline from a terminal is both the
 * commonest cause and the one that is invisible on screen.
 */
export function sha256Problem(value: string): string {
  if (value !== value.trim()) {
    return 'This has a space or a line break at the start or end. Paste the 64 characters on their own.';
  }
  if (/[A-F]/.test(value)) {
    return 'A sha256 is recorded in lower case here. Convert it before pasting — nothing is changed on your behalf.';
  }
  if (!/^[0-9a-f]*$/.test(value)) {
    return 'A sha256 contains only the characters 0–9 and a–f.';
  }
  return `A sha256 is exactly 64 characters. This one is ${value.length}.`;
}

export function AssetReferencesPanel({ experimentId }: { experimentId: string }) {
  return (
    <section className="assets-section" aria-labelledby="asset-references-heading">
      <div className="assets-head">
        <h2 className="assets-title" id="asset-references-heading">
          Asset References
        </h2>
        <p className="assets-sub">
          The files this record points at — where each one is, what it is for, and the
          sha256 you record for it. ISAAC stores the reference only: it does not
          upload, open, download or hash the file, so a digest here is the one you
          entered and has not been checked against anything.
        </p>
      </div>
      {/* Keyed on the record so switching records rebuilds this panel's state
          rather than showing one record's assets under another's heading. */}
      <AssetsBrowser key={experimentId} experimentId={experimentId} />
    </section>
  );
}

/**
 * The same dead end `UnmappedNotesPanel` had, and the same two-part fix — read that
 * file's `STALE_REVIEW_COPY` note for the measurement.
 *
 * In short: create, update and remove all adopted the new version token on SUCCESS and
 * did nothing with it on a 412, so one refusal stranded the panel on a stale validator
 * for good; and the only remedy offered (`Reload This Section`) blanked the list, which
 * unmounted every open edit form and every one of the nine values inside it.
 */
const STALE_ASSET_COPY =
  'The record changed since this section was loaded, so that was not recorded — it can ' +
  'be your own edit elsewhere on this screen. Nothing was lost: this section has picked ' +
  'up the current version and what you typed is still here, so try again.';

function AssetsBrowser({ experimentId }: { experimentId: string }) {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [version, setVersion] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [busyAssetId, setBusyAssetId] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [adding, setAdding] = useState(false);

  const generationRef = useRef(0);
  const silentRef = useRef(false);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const wasAddingRef = useRef(false);
  /** What the create form held when it last closed — see `FormDraft`. */
  const createDraft = useRef<FormDraft | null>(null);

  useEffect(() => {
    let alive = true;
    const generation = ++generationRef.current;
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;

    api
      .listAssets(experimentId)
      .then((loaded) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'data', loaded });
        setVersion(loaded.experiment_version);
      })
      .catch((err: unknown) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'error', error: asApiError(err) });
      });

    return () => {
      alive = false;
    };
  }, [experimentId, reloadNonce]);

  /*
   * FOCUS RETURNS TO "Record an Asset Reference" WHEN THE CREATE FORM CLOSES, and it
   * has to be an effect for the reason `UnmappedNotesPanel` records: the form unmounts
   * while focus is inside it, so a `.focus()` in the handler would run before the
   * trigger exists again and silently do nothing.
   */
  useEffect(() => {
    if (adding) {
      wasAddingRef.current = true;
      return;
    }
    if (!wasAddingRef.current) return;
    wasAddingRef.current = false;
    addButtonRef.current?.focus();
  }, [adding]);

  const reload = useCallback((silent: boolean) => {
    silentRef.current = silent;
    setReloadNonce((n) => n + 1);
  }, []);

  /**
   * Turn a refused write into a state a reader can act from — see `STALE_ASSET_COPY`.
   * On a 412 it adopts the token the server reported and refreshes SILENTLY, so every
   * open form and everything typed into one stays put. On any other failure it changes
   * nothing and returns the caller's own sentence: it must never claim a recovery it
   * did not make.
   */
  const recoverFromStale = useCallback(
    (err: unknown, fallback: string): string => {
      const current = staleWriteCurrentVersion(err);
      if (current === null) return mutationFailureCopy(asApiError(err), fallback);
      setVersion(current);
      reload(true);
      return STALE_ASSET_COPY;
    },
    [reload],
  );

  const create = useCallback(
    async (fields: Record<string, unknown>, runIds: string[]) => {
      if (!version) return;
      setMutationError(null);
      try {
        const written = await api.createAsset(experimentId, {
          experimentVersion: version,
          fields,
          runIds,
        });
        // Adopted from this write's own response, not left to arrive with the refetch.
        setVersion(written.experiment_version);
        setAnnouncement(
          `Recorded the asset reference ${written.asset.asset_id}. The digest was stored as entered; no file was read.`,
        );
        reload(true);
      } catch (err: unknown) {
        setMutationError(recoverFromStale(err, 'That asset reference could not be recorded. Nothing was written.'));
        setAnnouncement('');
        // Rethrown so the form knows to stay open and keep what was typed.
        throw err;
      }
    },
    [experimentId, version, reload, recoverFromStale],
  );

  const update = useCallback(
    async (
      asset: ApiAsset,
      fields: Record<string, unknown>,
      runIds: string[] | undefined,
      announce: string,
    ) => {
      if (!version) return;
      setBusyAssetId(asset.asset_id);
      setMutationError(null);
      try {
        const written = await api.updateAsset(experimentId, asset.asset_id, {
          experimentVersion: version,
          fields,
          runIds,
        });
        setVersion(written.experiment_version);
        setAnnouncement(announce);
        reload(true);
      } catch (err: unknown) {
        setMutationError(recoverFromStale(err, 'That change could not be saved. The asset reference is unchanged.'));
        setAnnouncement('');
        throw err;
      } finally {
        setBusyAssetId(null);
      }
    },
    [experimentId, version, reload, recoverFromStale],
  );

  const remove = useCallback(
    async (asset: ApiAsset) => {
      if (!version) return;
      setBusyAssetId(asset.asset_id);
      setMutationError(null);
      try {
        const written = await api.removeAsset(experimentId, asset.asset_id, {
          experimentVersion: version,
        });
        setVersion(written.experiment_version);
        setAnnouncement(
          written.detached_from_runs.length > 0
            ? `Removed the reference ${written.removed_asset_id} and detached it from ${written.detached_from_runs.length} run${written.detached_from_runs.length === 1 ? '' : 's'}. The file itself was not touched.`
            : `Removed the reference ${written.removed_asset_id}. The file itself was not touched.`,
        );
        reload(true);
      } catch (err: unknown) {
        setMutationError(recoverFromStale(err, 'That asset reference could not be removed. Nothing was changed.'));
        setAnnouncement('');
        throw err;
      } finally {
        setBusyAssetId(null);
      }
    },
    [experimentId, version, reload, recoverFromStale],
  );

  /**
   * The last successfully loaded page, kept across a reload, so the live regions stay
   * MOUNTED — a region that is unmounted and remounted with new content is not read
   * out. Same rule as the notes panel's toolbar.
   */
  const lastLoadedRef = useRef<ApiAssetsResponse | null>(null);
  if (list.status === 'data') lastLoadedRef.current = list.loaded;
  const loaded = list.status === 'data' ? list.loaded : lastLoadedRef.current;

  const countLine = useMemo(() => {
    if (!loaded) return '';
    const total = `${loaded.total} asset ${loaded.total === 1 ? 'reference' : 'references'} on this record`;
    if (loaded.unreadable_entries <= 0) return total;
    const n = loaded.unreadable_entries;
    return (
      `${total} · ${n} stored ${n === 1 ? 'entry' : 'entries'} this version cannot show` +
      ' — kept unchanged on the record'
    );
  }, [loaded]);

  return (
    <div className="assets-browser">
      <div className="assets-toolbar">
        {/*
          THE LABEL CHANGES WHEN THE FORM IS OPEN, and that is part of the D4 fix rather
          than polish. Closed, this control opens the form; open, it CLOSES it — and
          while it was labelled `Record an Asset Reference` in both states it was one
          word away from the submit control inside the form (`Record This Reference`),
          so the two readings of one label were "start recording" and "throw away what I
          have recorded". Saying which act this is removes the ambiguity, and the form
          now keeps its content either way, so neither reading loses anything.
        */}
        <button
          ref={addButtonRef}
          type="button"
          className="btn btn-primary"
          disabled={version === null}
          aria-expanded={adding}
          onClick={() => setAdding((open) => !open)}
        >
          {adding ? 'Close This Form' : 'Record an Asset Reference'}
        </button>
        <p className="assets-count" aria-live="polite" aria-atomic="true">
          {list.status === 'loading' ? '' : countLine}
        </p>
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {mutationError && (
        <div className="assets-error" role="alert">
          {mutationError}
          {/*
            SILENT — `reload(true)`, not `reload(false)`. The loud reload sets
            `{status:'loading'}`, which unmounts the `<ul>` and every open edit form
            inside it, so the one control offered as a remedy destroyed the nine values
            the reader had typed. The refresh is unchanged; it just no longer blanks the
            list to perform it.
          */}
          <button type="button" className="btn btn-secondary" onClick={() => reload(true)}>
            Reload This Section
          </button>
        </div>
      )}

      {adding && loaded && (
        <AssetForm
          mode="create"
          runs={loaded.runs}
          contentRoles={loaded.content_roles}
          initial={EMPTY_FORM}
          initialRunIds={[]}
          restored={createDraft.current}
          onDraft={(draft) => {
            createDraft.current = draft;
          }}
          takenIds={loaded.assets.map((a) => a.asset_id)}
          headingLevel={3}
          onCancel={() => {
            // Cancel is a reader saying discard it. The toggle above is not.
            createDraft.current = null;
            setAdding(false);
          }}
          onSubmit={async (fields, runIds) => {
            await create(fields, runIds);
            // Recorded, so the draft is consumed and the next create starts empty.
            createDraft.current = null;
            setAdding(false);
          }}
        />
      )}

      {list.status === 'loading' && (
        <LoadingPanel label="Loading this record's asset references…" />
      )}
      {list.status === 'error' && (
        <BackendDown error={list.error} onRetry={() => reload(false)} />
      )}
      {list.status === 'data' &&
        (list.loaded.assets.length === 0 ? (
          <EmptyAssets unreadable={list.loaded.unreadable_entries} />
        ) : (
          <ul className="assets-list">
            {list.loaded.assets.map((asset) => (
              <li key={asset.asset_id}>
                <AssetCard
                  asset={asset}
                  runs={list.loaded.runs}
                  contentRoles={list.loaded.content_roles}
                  busy={busyAssetId === asset.asset_id || version === null}
                  onUpdate={update}
                  onRemove={remove}
                />
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function EmptyAssets({ unreadable }: { unreadable: number }) {
  return (
    <div className="assets-empty">
      <p>
        No asset references on this record
        {unreadable > 0
          ? `, and ${unreadable} stored ${unreadable === 1 ? 'entry' : 'entries'} this version cannot show — kept unchanged on the record`
          : ''}
        . An asset reference records where a file is and the sha256 you have for it.
        Nothing is created automatically, and no file is read to produce one.
      </p>
    </div>
  );
}

function AssetCard({
  asset,
  runs,
  contentRoles,
  busy,
  onUpdate,
  onRemove,
}: {
  asset: ApiAsset;
  runs: { id: string; label: string; ordinal: number }[];
  contentRoles: string[];
  busy: boolean;
  onUpdate: (
    asset: ApiAsset,
    fields: Record<string, unknown>,
    runIds: string[] | undefined,
    announce: string,
  ) => Promise<void>;
  onRemove: (asset: ApiAsset) => Promise<void>;
}) {
  const [open, setOpen] = useState<'edit' | 'remove' | 'provenance' | null>(null);
  /*
   * What the edit form held when it last closed — see `FormDraft`. `Edit`, `Evidence`
   * and `Remove` all call `setOpen`, so any of the three could unmount an open edit
   * form and take its nine values with it; the draft outlives all three.
   */
  const editDraft = useRef<FormDraft | null>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);
  const provenanceRef = useRef<HTMLButtonElement>(null);
  const returningTo = useRef<'edit' | 'remove' | 'provenance' | null>(null);
  const editId = useId();
  const removeId = useId();
  const provenanceId = useId();

  useEffect(() => {
    if (open !== null) return;
    const returning = returningTo.current;
    if (returning === null) return;
    returningTo.current = null;
    const trigger =
      returning === 'edit'
        ? editRef.current
        : returning === 'remove'
          ? removeRef.current
          : provenanceRef.current;
    trigger?.focus();
  }, [open]);

  const close = () => {
    if (open !== null) returningTo.current = open;
    setOpen(null);
  };

  return (
    <article className="asset-card" data-reach={asset.export_reach} data-asset-id={asset.asset_id}>
      <div className="asset-card-head">
        <h3 className="asset-name">{asset.asset_id}</h3>
        <span className="asset-role">{roleLabel(asset.content_role)}</span>
      </div>

      <dl className="asset-facts">
        <div className="asset-fact">
          <dt>Location</dt>
          <dd className="mono asset-uri">{asset.uri}</dd>
        </div>
        <div className="asset-fact">
          <dt>sha256, as recorded</dt>
          <dd className="mono asset-digest">
            {asset.sha256}
            {/*
              THE STATE IS NEVER CARRIED BY COLOUR ALONE. A malformed digest says so
              in words; a well-formed one says what "well formed" means, so the
              absence of a warning is not read as a verification result.
            */}
            <span
              className="asset-digest-note"
              data-wellformed={asset.sha256_wellformed ? 'yes' : 'no'}
            >
              {asset.sha256_wellformed
                ? ' — 64 lowercase hexadecimal characters. Not checked against the file; ISAAC has not read it.'
                : ' — this is not 64 lowercase hexadecimal characters, so it will block export.'}
            </span>
          </dd>
        </div>
        {asset.media_type && (
          <div className="asset-fact">
            <dt>Media type</dt>
            <dd className="mono">{asset.media_type}</dd>
          </div>
        )}
        {asset.notes && (
          <div className="asset-fact">
            <dt>Notes</dt>
            <dd>{asset.notes}</dd>
          </div>
        )}
        {asset.figure_label && (
          <div className="asset-fact">
            <dt>Figure</dt>
            <dd>
              {asset.figure_label}
              {asset.page !== undefined ? `, page ${asset.page}` : ''}
            </dd>
          </div>
        )}
        {asset.caption_verbatim && (
          <div className="asset-fact">
            <dt>Caption, word for word</dt>
            <dd className="asset-caption">{asset.caption_verbatim}</dd>
          </div>
        )}
        <div className="asset-fact">
          <dt>Used by</dt>
          <dd>
            {asset.used_by_runs.length === 0
              ? 'No run cites this file.'
              : asset.used_by_runs.map((use) => use.label).join(', ')}
            <span className="asset-reach"> {REACH_TEXT[asset.export_reach]}</span>
          </dd>
        </div>
      </dl>

      <div className="asset-actions">
        <button
          ref={editRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'edit'}
          aria-controls={open === 'edit' ? editId : undefined}
          onClick={() => setOpen(open === 'edit' ? null : 'edit')}
        >
          Edit
        </button>
        <button
          ref={provenanceRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'provenance'}
          aria-controls={open === 'provenance' ? provenanceId : undefined}
          onClick={() => setOpen(open === 'provenance' ? null : 'provenance')}
        >
          Evidence ({asset.evidence_count})
        </button>
        <button
          ref={removeRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'remove'}
          aria-controls={open === 'remove' ? removeId : undefined}
          onClick={() => setOpen(open === 'remove' ? null : 'remove')}
        >
          Remove
        </button>
      </div>

      {open === 'edit' && (
        <div className="asset-form-wrap" id={editId}>
          <AssetForm
            mode="edit"
            runs={runs}
            contentRoles={contentRoles}
            initial={formFromAsset(asset)}
            initialRunIds={asset.used_by_runs.map((use) => use.run_id)}
            restored={editDraft.current}
            onDraft={(draft) => {
              editDraft.current = draft;
            }}
            takenIds={[]}
            headingLevel={4}
            onCancel={() => {
              // Cancel discards; the three disclosure toggles above do not.
              editDraft.current = null;
              close();
            }}
            onSubmit={async (fields, runIds) => {
              await onUpdate(
                asset,
                fields,
                runIds,
                `Saved ${asset.asset_id}. Any digest you changed was stored as entered; no file was read.`,
              );
              // Recorded, so the draft is consumed; the card now reads from the server.
              editDraft.current = null;
              close();
            }}
          />
        </div>
      )}

      {open === 'provenance' && (
        <div className="asset-form" id={provenanceId}>
          {/*
            "and where it came from", NOT "and by whom". ISAAC records no actor
            identity on an evidence entry — there is no authenticated identity to
            stamp — so a heading promising WHO would be a claim the data cannot
            answer, in the one panel a reader opens to check provenance.
          */}
          <h4 className="asset-form-title">What was recorded, and where it came from</h4>
          {asset.evidence.length === 0 ? (
            <p className="asset-form-hint">
              This reference carries no evidence. Every asset must cite a source before
              the record can be exported.
            </p>
          ) : (
            <ol className="asset-evidence-list">
              {asset.evidence.map((entry, index) => (
                <li key={index}>
                  <span className="asset-evidence-kind">{entry.source_type}</span>
                  {entry.question ? <span> · {entry.question}</span> : null}
                  {entry.source_file ? (
                    <span className="mono"> · {entry.source_file}</span>
                  ) : null}
                  {entry.timestamp ? (
                    <span className="mono asset-evidence-when"> · {entry.timestamp}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
          <p className="asset-form-hint">
            Evidence records what a person entered or what a source file stated. None of
            it is a check of the file at the location above.
          </p>
          <div className="asset-form-actions">
            <button type="button" className="btn btn-secondary" onClick={close}>
              Close
            </button>
          </div>
        </div>
      )}

      {open === 'remove' && (
        <div className="asset-form" id={removeId}>
          <p className="asset-form-hint">
            This removes the REFERENCE from this record’s draft and from every run that
            cites it. It does not touch the file at{' '}
            <span className="mono">{asset.uri}</span> — ISAAC has never opened it — and
            it does not change any record already exported.
          </p>
          <div className="asset-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={async () => {
                try {
                  await onRemove(asset);
                } catch {
                  /* Refused. The banner above the list reports it; this form stays put. */
                }
              }}
            >
              Remove This Reference
            </button>
            <button type="button" className="btn btn-secondary" onClick={close}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

/**
 * The create/edit form.
 *
 * ONE COMPONENT FOR BOTH, because they differ in exactly two ways — whether
 * `asset_id` can be changed, and what the submit button says — and two forms would
 * be two places for the digest rule and the no-preselection rule to drift.
 *
 * NOTHING IS PRE-SELECTED ON CREATE. The role control opens on "Choose a role…" with
 * no value; the run checkboxes start unchecked even when the record has one run.
 */
function AssetForm({
  mode,
  runs,
  contentRoles,
  initial,
  initialRunIds,
  restored,
  onDraft,
  takenIds,
  headingLevel,
  onCancel,
  onSubmit,
}: {
  mode: 'create' | 'edit';
  runs: { id: string; label: string; ordinal: number }[];
  contentRoles: string[];
  initial: FormValues;
  initialRunIds: string[];
  /** What this form held last time it closed, if it is being re-opened — see
   *  `FormDraft`. It seeds the state and NOTHING else; `initial` remains the diff
   *  baseline, so what an edit sends is still measured against what was loaded. */
  restored?: FormDraft | null;
  /** Reports every change so the owner can re-seed this form after it unmounts. */
  onDraft?: (draft: FormDraft) => void;
  takenIds: string[];
  /*
   * THE HEADING LEVEL IS PASSED IN, NOT FIXED, AND THAT IS NOT FUSSINESS. The create
   * form sits directly under this panel's `h2`, so its title is an `h3`; the edit
   * form sits inside an asset card whose name is already an `h3`, so its title is an
   * `h4`. A single fixed level makes one of the two a SKIPPED heading level, which
   * `e2e/specs/structure.spec.ts` fails on every surface it checks — and which is a
   * real navigation defect for anyone moving through the page by headings.
   */
  headingLevel: 3 | 4;
  onCancel: () => void;
  onSubmit: (fields: Record<string, unknown>, runIds: string[]) => Promise<void>;
}) {
  const Heading = (headingLevel === 3 ? 'h3' : 'h4') as 'h3' | 'h4';
  const [values, setValues] = useState<FormValues>(restored?.values ?? initial);
  const [runIds, setRunIds] = useState<string[]>(restored?.runIds ?? initialRunIds);
  const [saving, setSaving] = useState(false);
  const [showProblems, setShowProblems] = useState(false);
  const base = useId();

  /*
   * REPORTED UPWARD ON EVERY CHANGE, so this form's owner can put it back after it
   * unmounts (see `FormDraft`). Held in a ref by the owner, so a keystroke here costs
   * no render there. The callback identity is captured in a ref for the reason every
   * other callback in this file is: an owner that re-creates it would otherwise
   * re-fire this effect on each of its own renders.
   */
  const onDraftRef = useRef(onDraft);
  onDraftRef.current = onDraft;
  useEffect(() => {
    onDraftRef.current?.({ values, runIds });
  }, [values, runIds]);

  const set = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const idProblem =
    values.asset_id.trim() === ''
      ? 'A name is required. It identifies this reference on the record and in the evidence sidecar; nothing is generated for you.'
      : takenIds.includes(values.asset_id.trim())
        ? 'This record already has a reference with that name. Names must be unique.'
        : null;
  const roleProblem =
    values.content_role === ''
      ? 'Choose the role this file plays. It is not inferred from the location or the file name.'
      : null;
  const uriProblem =
    values.uri.trim() === '' ? 'A location is required. It is never guessed.' : null;
  const shape = sha256Shape(values.sha256);
  const digestProblem =
    shape === 'empty'
      ? 'A sha256 is required. ISAAC does not read the file, so it cannot compute one — paste the digest you have.'
      : shape === 'malformed'
        ? sha256Problem(values.sha256)
        : null;

  const problems = [idProblem, roleProblem, uriProblem, digestProblem];
  const blocked = problems.some((p) => p !== null);

  const submit = async () => {
    if (saving) return;
    if (blocked) {
      setShowProblems(true);
      return;
    }
    setSaving(true);
    try {
      /*
       * EVERY VALUE GOES AS TYPED. `sha256` in particular is NOT trimmed: the server
       * refuses a digest with stray whitespace, and repairing it here would store
       * something the scientist did not enter and hide the refusal that says so.
       *
       * An optional field that is blank travels as `null` on EDIT (clear it) and is
       * omitted on CREATE (there is nothing to clear).
       */
      const fields: Record<string, unknown> = {};
      /*
       * AN EDIT SENDS ONLY WHAT CHANGED, AND THAT IS NOT AN OPTIMISATION.
       *
       * `page` is declared `number | string` by the schema, so a value an API client
       * stored as the NUMBER 12 is rendered here as the string "12"; re-sending every
       * field on every save would silently rewrite it as a string the scientist never
       * typed. Comparing against `initial` — which is exactly what was loaded — means
       * an untouched field is not sent at all, so its stored type survives.
       *
       * `run_ids` is always sent on an edit, so skipping unchanged fields can never
       * produce the empty body the server refuses with `empty_update`.
       */
      const unchanged = (key: string) => mode === 'edit' && values[key] === initial[key];
      for (const key of ['content_role', 'uri', 'sha256']) {
        if (!unchanged(key)) fields[key] = values[key];
      }
      if (mode === 'create') fields.asset_id = values.asset_id.trim();
      for (const { key } of OPTIONAL_TEXT_FIELDS) {
        if (unchanged(key)) continue;
        const raw = values[key] ?? '';
        if (raw === '') {
          if (mode === 'edit') fields[key] = null;
        } else {
          fields[key] = raw;
        }
      }
      await onSubmit(fields, runIds);
    } catch {
      /* The banner above the list reports it; what was typed stays on screen. */
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="asset-form">
      <Heading className="asset-form-title">
        {mode === 'create' ? 'Record an asset reference' : `Edit ${initial.asset_id}`}
      </Heading>

      <Field
        id={`${base}-id`}
        label="Name"
        hint="Identifies this reference on the record. It cannot be changed later."
        value={values.asset_id}
        onChange={(v) => set('asset_id', v)}
        problem={showProblems ? idProblem : null}
        readOnly={mode === 'edit'}
        required
      />

      <div className="asset-field">
        <label className="assets-control-label" htmlFor={`${base}-role`}>
          Role <span aria-hidden="true">*</span>
        </label>
        <select
          id={`${base}-role`}
          className="asset-input"
          value={values.content_role}
          required
          aria-invalid={showProblems && roleProblem !== null ? true : undefined}
          aria-describedby={
            showProblems && roleProblem !== null ? `${base}-role-problem` : undefined
          }
          onChange={(e) => set('content_role', e.target.value)}
        >
          {/* No pre-selection. A person chooses; nothing is proposed for them. */}
          <option value="">Choose a role…</option>
          {contentRoles.map((role) => (
            <option key={role} value={role}>
              {roleLabel(role)}
            </option>
          ))}
        </select>
        {showProblems && roleProblem !== null && (
          <p className="asset-problem" id={`${base}-role-problem`}>
            {roleProblem}
          </p>
        )}
      </div>

      <Field
        id={`${base}-uri`}
        label="Location"
        hint="Where the file is — a path, an archive URI, a DOI. ISAAC does not visit it."
        value={values.uri}
        onChange={(v) => set('uri', v)}
        problem={showProblems ? uriProblem : null}
        mono
        required
      />

      <Field
        id={`${base}-sha`}
        label="sha256"
        hint="64 lowercase hexadecimal characters, as you have them. ISAAC does not read the file, so it cannot compute or check this — and it will not tidy what you paste."
        value={values.sha256}
        onChange={(v) => set('sha256', v)}
        problem={showProblems ? digestProblem : null}
        mono
        required
      />

      {OPTIONAL_TEXT_FIELDS.map(({ key, label, hint }) => (
        <Field
          key={key}
          id={`${base}-${key}`}
          label={label}
          hint={hint}
          value={values[key] ?? ''}
          onChange={(v) => set(key, v)}
          problem={null}
          multiline={key === 'caption_verbatim' || key === 'notes'}
        />
      ))}

      <fieldset className="asset-runs">
        <legend className="assets-control-label">Runs that use this file</legend>
        {runs.length === 0 ? (
          <p className="asset-form-hint">
            This record has no runs, so it exports one record from the record itself and
            this file is part of it.
          </p>
        ) : (
          <>
            {runs.map((run) => (
              <label className="asset-run-choice" key={run.id}>
                <input
                  type="checkbox"
                  checked={runIds.includes(run.id)}
                  onChange={(e) =>
                    setRunIds((prev) =>
                      e.target.checked
                        ? [...prev, run.id]
                        : prev.filter((id) => id !== run.id),
                    )
                  }
                />
                <span>{run.label}</span>
              </label>
            ))}
            <p className="asset-form-hint">
              Nothing is ticked for you. A record with runs exports one record per run,
              built from that run’s own content — so a file no run cites will not appear
              in any exported record.
            </p>
          </>
        )}
      </fieldset>

      {/* SAID ON SCREEN, because the behaviour changed and a reader cannot see it (D4).
          Closing this form used to discard every value in it, silently. */}
      <p className="asset-form-hint">
        Closing this form keeps what you have typed here, and so does opening another
        panel on the same reference. Only Cancel discards it.
      </p>

      <div className="asset-form-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={saving}
          onClick={submit}
        >
          {saving
            ? 'Saving…'
            : mode === 'create'
              ? 'Record This Reference'
              : 'Save Changes'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/**
 * One labelled input, with its hint and its problem WIRED TO IT.
 *
 * `aria-describedby` names the hint and, when there is one, the problem — so a
 * screen-reader user hears why the field is refused at the field, not from a banner
 * somewhere else on the screen. `aria-invalid` is set only when a problem is being
 * shown, because marking a field invalid before anyone has submitted anything is a
 * false statement about what they typed.
 */
function Field({
  id,
  label,
  hint,
  value,
  onChange,
  problem,
  mono,
  multiline,
  readOnly,
  required,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  problem: string | null;
  mono?: boolean;
  multiline?: boolean;
  readOnly?: boolean;
  required?: boolean;
}) {
  const hintId = `${id}-hint`;
  const problemId = `${id}-problem`;
  const describedBy = [hint ? hintId : null, problem ? problemId : null]
    .filter(Boolean)
    .join(' ');
  const shared = {
    id,
    className: `asset-input${mono ? ' mono' : ''}`,
    value,
    readOnly,
    required,
    'aria-invalid': problem ? (true as const) : undefined,
    'aria-describedby': describedBy === '' ? undefined : describedBy,
    onChange: (e: { target: { value: string } }) => onChange(e.target.value),
  };
  return (
    <div className="asset-field">
      <label className="assets-control-label" htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
        {readOnly ? <span className="asset-readonly-note"> — cannot be changed</span> : null}
      </label>
      {multiline ? (
        <textarea {...shared} rows={2} />
      ) : (
        <input {...shared} type="text" />
      )}
      {hint && (
        <p className="asset-form-hint" id={hintId}>
          {hint}
        </p>
      )}
      {problem && (
        <p className="asset-problem" id={problemId} role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
