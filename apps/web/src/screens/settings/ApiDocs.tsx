/**
 * The OpenAPI-derived Settings surfaces (P36V PR3 slice C; split across two tabs
 * by P36V-1 slice 12). ONE source of truth — the document `GET /api/openapi`
 * returns. There is no hand-maintained endpoint catalog anywhere in the client,
 * no CDN, no embedded API-explorer library, and no second description of any
 * operation.
 *
 * Two exported panels, one per Settings tab:
 *
 *   · {@link ApiQuickStartPanel} (API Access) — Quick Start, the handful of
 *     facts a caller needs first, every one derived from that document, plus the
 *     collapsed Connect an Agent guide.
 *   · {@link ApiExplorerPanel} (Endpoint Explorer) — the master-detail browser,
 *     grouped by the document's real `tags` (see `lib/apiDocsModel.ts` for why
 *     the old path-segment inference had to go), with Purpose, whether the
 *     contract declares a 401, parameters, request body, responses, error
 *     states, generated code examples, and raw JSON only behind a
 *     `Technical Schema` disclosure. Nothing here reports whether a DEPLOYMENT
 *     enables authentication — the app cannot see that.
 *
 * Because those are now separate tabs, nothing here may call the Explorer
 * "above": the prose names the TAB and offers a control that goes there.
 *
 * The base URL is always the RELATIVE path the contract itself declares; no
 * origin or host literal is ever displayed or assumed, and the generated samples
 * read the origin from an environment variable instead.
 */
import {
  useCallback,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { ChevronRight, Search } from '../../components/icons';
import {
  codeSamples,
  collectExamples,
  flattenOpenApi,
  groupEndpoints,
  isErrorCode,
  quickStartFacts,
  resolveSchema,
  stringify,
  tagDescriptions,
  SAMPLE_BASE_ENV,
  type ApiEndpoint,
  type QuickStartFacts,
  type SampleId,
} from '../../lib/apiDocsModel';
import { API_ACCESS_COPY } from '../../lib/settingsContent';
import type { ApiOpenApiResponse, OpenApiMediaType } from '../../lib/types';
import { ConnectAnAgent } from './ConnectAnAgent';
import { CopyAnnouncer, CopyButton, MethodBadge, RovingTabs } from './apiShared';

const API_DETAIL_ID = 'settings-api-detail';
const API_DETAIL_NAME_ID = 'settings-api-detail-name';
const API_LIST_HEADING_ID = 'settings-api-endpoints-heading';
const CONNECT_SUMMARY_ID = 'settings-api-connect-summary';
/** The tab-level Auth legend, referenced by every detail pane's Auth flag. */
const AUTH_LEGEND_ID = 'settings-api-auth-legend';
/**
 * Names the endpoint-filter `role="search"` landmark — FINDING A11Y-06 below.
 * It must differ from the TopBar region's "Site search"
 * (`components/SearchDialog.tsx`), which is the whole point of naming either.
 */
const API_SEARCH_LANDMARK = 'Endpoint search';

const slug = (value: string) => value.replace(/[^a-zA-Z0-9]+/g, '-');
const endpointRowId = (key: string) => `settings-api-row-${slug(key)}`;
const groupHeadingId = (key: string) => `settings-api-group-${slug(key)}`;

/** The API Access tab's contract-derived half: Quick Start + Connect an Agent. */
export function ApiQuickStartPanel({
  schema,
  onOpenExplorer,
}: {
  schema: ApiOpenApiResponse;
  onOpenExplorer: () => void;
}) {
  const rows = useMemo(() => flattenOpenApi(schema), [schema]);
  const facts = useMemo(() => quickStartFacts(schema, rows), [schema, rows]);

  // ONE polite region for every copy affordance on this panel, so adding a copy
  // button never adds a live region.
  const [copyMessage, setCopyMessage] = useState('');
  const onCopied = useCallback((what: string) => setCopyMessage(`Copied ${what}.`), []);

  const [connectOpen, setConnectOpen] = useState(false);
  const openConnect = useCallback(() => {
    setConnectOpen(true);
    (document.getElementById(CONNECT_SUMMARY_ID) as HTMLElement | null)?.focus();
  }, []);

  return (
    <>
      <CopyAnnouncer message={copyMessage} />
      <QuickStart
        facts={facts}
        onCopied={onCopied}
        onOpenExplorer={onOpenExplorer}
        onOpenConnect={openConnect}
      />
      <ConnectAnAgent
        open={connectOpen}
        onOpenChange={setConnectOpen}
        summaryId={CONNECT_SUMMARY_ID}
        facts={{
          requestMediaTypes: facts.requestMediaTypes,
          errorCodes: facts.errorCodes,
        }}
        onOpenExplorer={onOpenExplorer}
      />
    </>
  );
}

/** The Endpoint Explorer tab: the master-detail browser and nothing else. */
export function ApiExplorerPanel({ schema }: { schema: ApiOpenApiResponse }) {
  const rows = useMemo(() => flattenOpenApi(schema), [schema]);
  const descriptions = useMemo(() => tagDescriptions(schema), [schema]);

  const [copyMessage, setCopyMessage] = useState('');
  const onCopied = useCallback((what: string) => setCopyMessage(`Copied ${what}.`), []);

  return (
    <>
      <CopyAnnouncer message={copyMessage} />
      <ApiBrowser schema={schema} rows={rows} descriptions={descriptions} onCopied={onCopied} />
    </>
  );
}

// --- Quick Start -------------------------------------------------------------

/**
 * Only values this running app can actually report. In particular the base URL
 * is the relative path the contract's own paths share — `/api` locally, or
 * `/<base>/api` where a deployment sets a base path — and NOT an origin, which
 * would be both wrong for any other caller and a disclosure of deployment
 * topology. When the paths share no single base, that is said rather than
 * papered over with a plausible default.
 */
function QuickStart({
  facts,
  onCopied,
  onOpenExplorer,
  onOpenConnect,
}: {
  facts: QuickStartFacts;
  onCopied: (what: string) => void;
  onOpenExplorer: () => void;
  onOpenConnect: () => void;
}) {
  const first = facts.firstRequest;
  const firstSample = first ? codeSamples(first)[0] : null;
  return (
    <section className="api-quickstart" aria-labelledby="settings-api-quickstart-heading">
      <h3 id="settings-api-quickstart-heading" className="api-section-title">
        Quick Start
      </h3>
      <p className="settings-source-line mono">{facts.contractLine}</p>

      <dl className="api-quickstart-rows">
        <QuickStartRow label="Base URL">
          {facts.basePath ? (
            <>
              <code className="mono api-quickstart-value">{facts.basePath}</code>
              <span className="api-quickstart-note">
                Relative to the origin serving this page. Every path on the Endpoint Explorer tab
                already begins with it, so a request needs the origin and nothing else.
              </span>
            </>
          ) : (
            <span className="api-quickstart-note">
              The contract's paths share no single base, so there is no one base URL to
              report. Use each path exactly as the Endpoint Explorer tab lists it.
            </span>
          )}
        </QuickStartRow>

        <QuickStartRow label="API Version">
          <code className="mono api-quickstart-value">
            {facts.apiVersion ? `v${facts.apiVersion}` : 'not declared'}
          </code>
          <span className="api-quickstart-note">
            The app version this contract was generated from, described as OpenAPI{' '}
            {facts.openApiVersion}.
          </span>
        </QuickStartRow>

        <QuickStartRow label="Authentication">
          <code className="mono api-quickstart-value">Authorization: Bearer</code>
          {/* The HEADER and the contract-derived COUNT, and nothing else: the
              key-unavailable status is the banner's (stated once, above this),
              and the hosted-session boundary is one of the access rows'. */}
          {/* FINDING D — the count was already honest ("the contract DOCUMENTS a
              401"), but the sentence in front of it was not conditional, and a
              deployment that sets no credential returns a 401 from the
              application on no operation at all. The Explorer's own legend for
              the same marker already hedges this way ("where a deployment
              enables authentication…"); this row now matches it rather than
              contradicting it one tab away. */}
          <span className="api-quickstart-note">
            One credential belonging to the deployment, sent on every call that needs it — where a
            deployment sets one. Where none is set, no operation refuses a call for want of it.{' '}
            {facts.authRequiredCount} of {facts.operationCount} operations document a 401, and the
            Endpoint Explorer tab marks which.
          </span>
        </QuickStartRow>

        <QuickStartRow label="Content Type">
          {facts.requestMediaTypes.length > 0 ? (
            <>
              {facts.requestMediaTypes.map((mediaType) => (
                <code className="mono api-quickstart-value" key={mediaType}>
                  {mediaType}
                </code>
              ))}
              <span className="api-quickstart-note">
                The only request media types this contract declares. Read operations send no body.
              </span>
            </>
          ) : (
            <span className="api-quickstart-note">
              No operation in this contract declares a request body.
            </span>
          )}
        </QuickStartRow>
      </dl>

      {first && firstSample && (
        <div className="api-quickstart-first">
          <div className="api-samples-head">
            <span className="api-samples-lang">
              A First Request &middot; <MethodBadge method={first.method} />{' '}
              <code className="mono">{first.path}</code>
            </span>
            <CopyButton
              what="the first-request sample"
              value={firstSample.code}
              onCopied={onCopied}
            />
          </div>
          {/*
            FINDING A11Y-04 fix. `.api-samples-code` is `overflow: auto` with
            `white-space: pre` and a 280px `max-height`, so a long curl line
            scrolls sideways and a long sample scrolls down. Without a tab stop
            a keyboard-only reader can see the first ~227px of a 2000px command
            and reach no more of it (`e2e/helpers/layout.ts:116` measured
            exactly that). `role="group"` rather than `region`, because a
            landmark here would collide with the two `role="search"` landmarks
            this slice is naming for A11Y-06.
          */}
          <pre
            className="mono api-samples-code"
            tabIndex={0}
            role="group"
            aria-label={`First request sample, ${first.method} ${first.path}`}
          >{firstSample.code}</pre>
          <p className="api-quickstart-note">
            {first.authRequired
              ? 'Every read operation in this contract documents a 401, so this one needs a credential too.'
              : 'Chosen because the contract documents no 401 for it: it answers before any credential exists.'}{' '}
            <code className="mono">${SAMPLE_BASE_ENV}</code> stands for the origin serving this
            page; the sample never hard-codes one.
          </p>
        </div>
      )}

      {/* Where a reader goes next. The old first entry pointed at an "API Keys"
          sub-tab that no longer exists — that content is now the status banner
          at the top of THIS tab, so a jump to it would be a link to the page
          you are on. The Endpoint Explorer is a different tab, and Connect an
          Agent is the disclosure immediately below. */}
      <nav className="api-quickstart-jump" aria-label="More API detail">
        <button type="button" className="settings-jump-btn" onClick={onOpenExplorer}>
          Browse Every Endpoint
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <button type="button" className="settings-jump-btn" onClick={onOpenConnect}>
          Connect an Agent
        </button>
      </nav>
    </section>
  );
}

function QuickStartRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="api-quickstart-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

// --- Endpoint Explorer -------------------------------------------------------

function ApiBrowser({
  schema,
  rows,
  descriptions,
  onCopied,
}: {
  schema: ApiOpenApiResponse;
  rows: ApiEndpoint[];
  descriptions: Record<string, string>;
  onCopied: (what: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.path.toLowerCase().includes(q) ||
        (r.summary ?? '').toLowerCase().includes(q) ||
        r.group.toLowerCase().includes(q) ||
        r.method.includes(q),
    );
  }, [rows, query]);

  const groups = useMemo(() => groupEndpoints(filtered, descriptions), [filtered, descriptions]);

  // Selection follows the filter without an effect: the explicitly selected
  // endpoint when it is still visible, otherwise the first visible one,
  // otherwise nothing. Never an endpoint the user cannot see in the list.
  const selected =
    filtered.find((r) => r.key === selectedKey) ?? (filtered.length > 0 ? filtered[0] : null);

  const cursor = filtered.length === 0 ? 0 : Math.min(focusIndex, filtered.length - 1);

  /** Roving tabindex: exactly ONE row is in the tab order; Arrow/Home/End move
   *  that cursor without selecting. Same contract as the Schema Reference
   *  Fields list and the Concepts master list — one interaction model. */
  const onListKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
      let next: number | null = null;
      if (e.key === 'ArrowDown') next = Math.min(index + 1, filtered.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(index - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = filtered.length - 1;
      if (next === null || filtered.length === 0) return;
      e.preventDefault();
      setFocusIndex(next);
      (document.getElementById(endpointRowId(filtered[next].key)) as HTMLButtonElement | null)?.focus();
    },
    [filtered],
  );

  return (
    <section className="api-explorer" aria-labelledby="settings-api-explorer-heading">
      <h3 id="settings-api-explorer-heading" className="api-section-title">
        Endpoint Explorer
      </h3>

      {/*
        FINDING A11Y-06 fix. This is the second of the two `role="search"`
        landmarks that coexist on the Endpoint Explorer tab; the other is the
        TopBar trigger in `components/SearchDialog.tsx`. Two same-role landmarks
        with no names are indistinguishable in a screen reader's landmark list.

        `aria-label`, NOT `aria-labelledby` pointing at the visible label below.
        That was the first attempt and it is recorded because it looked like the
        tidier choice: reusing the visible string means one copy to keep true.
        But it makes ONE string the accessible name of TWO different things —
        the landmark and the text box inside it — and any name-based lookup then
        resolves to both. Three existing tests broke on exactly that
        (`Found multiple elements with the text of: Search endpoints`), and they
        were right to: a reader searching by name would have found the region
        where they meant the input. The landmark gets its own name.
      */}
      <div className="settings-search" role="search" aria-label={API_SEARCH_LANDMARK}>
        <label className="settings-search-label" htmlFor="api-docs-search">
          Search endpoints
        </label>
        <div className="settings-search-input-wrap">
          <Search size={14} strokeWidth={2.2} aria-hidden="true" className="settings-search-icon" />
          <input
            id="api-docs-search"
            type="search"
            className="settings-search-input"
            placeholder="Filter by group, path, method, or summary…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedKey(null);
              setFocusIndex(0);
            }}
          />
        </div>
      </div>

      {/* The only EXPLICIT `aria-live` region here. Note the copy announcer's
          `role="status"` carries an implicit `aria-live="polite"`, so this surface
          has TWO polite regions with distinct purposes: this one reports the search
          result count, that one confirms a copy. Both are asserted (exactly one of
          each kind) rather than claimed to be a single region. */}
      <p className="settings-doc-count" aria-live="polite">
        {filtered.length} of {rows.length} endpoint{rows.length === 1 ? '' : 's'}
      </p>

      {/* The authentication explanation, ONCE for the whole tab. It used to be a
          two-sentence paragraph re-rendered inside every endpoint's detail pane —
          the same warning up to seven times per visit — while the per-operation
          fact is a single flag. The flag is now compact metadata on the detail
          pane and this legend says what it means, in one place. */}
      <p className="api-browser-legend" id={AUTH_LEGEND_ID}>
        {API_ACCESS_COPY.authMarkerLegend}
      </p>

      {filtered.length === 0 && (
        <p className="settings-doc-empty">No endpoints match &ldquo;{query}&rdquo;.</p>
      )}

      {filtered.length > 0 && (
        <div className="api-browser-split">
          {/* Named the same way the detail pane is, so both halves of the
              master-detail pair announce what they are. */}
          <section className="api-browser-master" aria-labelledby={API_LIST_HEADING_ID}>
            <h4 id={API_LIST_HEADING_ID} className="api-browser-pane-heading">
              Endpoints
              <span className="api-browser-pane-count mono">
                {groups.length} group{groups.length === 1 ? '' : 's'}
              </span>
            </h4>
            <div className="api-browser-list">
              {groups.map((group) => (
                <section
                  className="api-browser-group"
                  key={group.key}
                  aria-labelledby={groupHeadingId(group.key)}
                >
                  <h5 id={groupHeadingId(group.key)} className="api-browser-group-heading">
                    {group.key}
                    <span className="api-browser-group-count">{group.rows.length}</span>
                  </h5>
                  <ul className="api-browser-rows">
                    {group.rows.map(({ row, index }) => (
                      <ApiEndpointRow
                        key={row.key}
                        row={row}
                        selected={selected?.key === row.key}
                        tabIndex={index === cursor ? 0 : -1}
                        onSelect={() => {
                          setSelectedKey(row.key);
                          setFocusIndex(index);
                        }}
                        onKeyDown={(e) => onListKeyDown(e, index)}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </section>

          {/* `tabIndex={-1}`: a programmatic focus target that adds no tab stop;
              its accessible name is the selected endpoint's own heading. */}
          <div
            className="api-browser-detail"
            id={API_DETAIL_ID}
            role="region"
            tabIndex={-1}
            aria-labelledby={API_DETAIL_NAME_ID}
          >
            {selected && (
              <ApiEndpointDetail
                row={selected}
                schema={schema}
                groupDescription={descriptions[selected.group]}
                onCopied={onCopied}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ApiEndpointRow({
  row,
  selected,
  tabIndex,
  onSelect,
  onKeyDown,
}: {
  row: ApiEndpoint;
  selected: boolean;
  tabIndex: number;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  // Selection comes from the native <button> (browsers synthesize a click from
  // Enter and Space); `onKeyDown` only moves the roving cursor.
  return (
    <li className="api-browser-row">
      <button
        id={endpointRowId(row.key)}
        type="button"
        className={`api-browser-rowbtn${selected ? ' selected' : ''}`}
        aria-current={selected ? 'true' : undefined}
        aria-controls={API_DETAIL_ID}
        tabIndex={tabIndex}
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        <MethodBadge method={row.method} />
        <span className="api-browser-rowtext">
          <code className="mono api-docs-path">{row.path}</code>
          {row.summary && <span className="api-docs-summary-text">{row.summary}</span>}
        </span>
      </button>
    </li>
  );
}

/**
 * Above this many characters of REMAINDER (every paragraph after the lead, joined)
 * a description is long enough that collapsing the tail is worth the chrome.
 *
 * 400 characters is ~60–70 words, five or six lines at the detail pane's measure:
 * a remainder that long materially doubles the Purpose section, while one below it
 * costs more in `<details>` chrome — a summary row, a disclosure triangle and a
 * count chip — than the text it would conceal. Measured against the real
 * generated contract (36 operations, `GET /api/openapi`): lead paragraphs run
 * 78–594 characters and remainders 0–1,740, so this threshold separates the five
 * genuine docstrings from the 28 one-extra-sentence tails.
 *
 * The first version of this surface had NO threshold — any blank line produced a
 * disclosure. That collapsed 31 of the then-35 operations and hid 8,568 of that
 * contract's 18,314 description characters (47%), including boundary copy this
 * project requires to stay visible. See {@link BOUNDARY_CAVEAT_MARKERS}.
 */
export const PURPOSE_DISCLOSURE_MIN_CHARS = 400;

/**
 * The project's boundary/honesty vocabulary, lowercased. A remainder containing
 * ANY of these is never collapsed, however long it is.
 *
 * This exists because length alone is the wrong instrument. Three of this API's
 * descriptions exceed the threshold above, and every one of them carries its
 * boundary claim AFTER the lead paragraph:
 *
 *   · `POST /api/experiments/{id}/assistant/query` ¶2 — "There is no language
 *     model. A question outside the catalog … is refused honestly rather than
 *     answered";
 *   · `GET /api/memory/graph/detail` ¶2 — the structural-staleness disclosure
 *     ("a point-in-time index, not a map of today's code");
 *   · `GET /api/graph/status` ¶3 — "leads and provenance … never a correctness
 *     ruling. Read-only."
 *
 * Hiding any of those would let the visible lead overstate what the code does —
 * the exact inversion of the rule the sibling Data & Privacy surface enforces
 * (progressive disclosure is for EDGE CASES, never for a caveat). The test is
 * ALL-OR-NOTHING over the whole remainder, deliberately: rendering ¶2 and ¶4
 * inline while hiding ¶3 would scramble the contract's own reading order.
 *
 * The list errs toward showing text: a false positive costs a slightly longer
 * section, a false negative would hide a caveat.
 */
export const BOUNDARY_CAVEAT_MARKERS: readonly string[] = [
  'never',
  'cannot',
  'no language model',
  'refus', // refuse / refuses / refused / refusal
  'honest',
  'fabricat',
  'guess',
  'advisory',
  'verdict',
  'read-only',
  'deliberately',
  'point-in-time',
  'approval-gated',
  'synthetic-only',
  'immutable',
  'not enabled',
  /*
   * ── ADDED FOR `GET /api/runtime/verification`, AND THE MISS IS THE LESSON ──
   *
   * That operation shipped three post-lead paragraphs — 629 characters, over the
   * threshold — carrying the aggregate-only guarantee ("No record id, title,
   * field value, evidence entry or per-record outcome appears… withheld rather
   * than named") and the corpus boundary ("this operation does not connect to
   * any database"). It is boundary copy by any reading, and it contained NOT ONE
   * token from the list above, so length alone collapsed all three behind the
   * disclosure. Exactly the inversion this list exists to prevent, on the
   * newest endpoint, caught by review rather than by CI.
   *
   * The general lesson is that this list is a RATCHET over vocabulary that has
   * actually shipped, not a detector for the claim class — the same limit
   * `db-recon-truthfulness.test.tsx` states about its own sweep. A boundary
   * paragraph written in words nobody has used before will still slip through,
   * and a human reviewing new contract copy remains the backstop.
   *
   * EACH OF THESE WAS MEASURED AGAINST THE REAL STRING, not eyeballed. A
   * candidate that reads plausibly and never fires is worse than no marker at
   * all, because it looks like coverage: `'not the production'` was proposed and
   * REJECTED here, because the served description writes `It is **not** the
   * production-derived corpus` and the markdown emphasis breaks the substring.
   */
  'aggregate only',
  'withheld',
  'does not connect',
  /*
   * ── ADDED FOR `GET .../revisions/{revision_no}/diff`, THE SAME MISS AGAIN ──
   *
   * That operation shipped four post-lead paragraphs — 1,320 characters, well over
   * the threshold — and every one of them is scope copy: which content the
   * comparison covers ("Evidence entries, run overrides, answer logs, assets and
   * implicit claims are NOT compared"), what an empty result does and does not
   * mean, and that an unreadable snapshot yields no comparison rather than an empty
   * one. Hiding that behind the disclosure would leave the visible lead — "reports
   * every draft field address whose value differs" — reading as a complete
   * comparison, which is precisely the overstatement this list exists to prevent.
   *
   * It contained NOT ONE token from the list above, and CI caught it this time
   * (`settings-api.test.tsx`, "hides ZERO characters of the real contract"), which
   * is the difference from the `runtime/verification` miss recorded above.
   *
   * EACH WAS MEASURED AGAINST THE REAL SERVED STRING, per the rule stated above,
   * and each fires on its own paragraph: `not compared` on ¶2, `did not look` on
   * ¶3, `could not` on ¶5. ¶4 carries none, which is correct and is why the rule is
   * ALL-OR-NOTHING over the remainder rather than per-paragraph.
   */
  'not compared',
  'did not look',
  'could not',
];

/** Does this paragraph carry a boundary/honesty claim that must stay visible? */
export function isBoundaryCaveat(paragraph: string): boolean {
  const lower = paragraph.toLowerCase();
  return BOUNDARY_CAVEAT_MARKERS.some((marker) => lower.includes(marker));
}

/**
 * Split a contract description into its LEAD paragraph, the paragraphs rendered
 * INLINE after it, and the paragraphs behind the disclosure — all verbatim.
 *
 * FastAPI publishes the route docstring as the operation description, and this
 * API's longest runs to ~1,400 characters across four blank-line-separated
 * paragraphs — a docstring, not a purpose. Only the blank-line boundaries are
 * honoured (a single newline inside a paragraph is soft-wrapping from the source
 * and collapses to a space); no sentence is shortened, truncated, re-worded or
 * discarded, so every word of the contract's text is rendered either way.
 *
 * A remainder is collapsed only when it is BOTH long enough to be a wall
 * ({@link PURPOSE_DISCLOSURE_MIN_CHARS}) AND free of boundary copy
 * ({@link BOUNDARY_CAVEAT_MARKERS}). Against the real contract that is currently
 * zero of 39 operations, which is the honest outcome: this API's descriptions are
 * short-to-medium and boundary-laden, so nothing about them needs hiding. The
 * disclosure remains for a future docstring that is genuinely long and carries no
 * caveat.
 *
 * "Currently zero" IS A MEASUREMENT THAT HAS ALREADY BEEN WRONG ONCE, so it is
 * not a property of the rule. `GET /api/runtime/verification` arrived with a
 * 629-character, three-paragraph, entirely boundary-bearing remainder that
 * matched no marker, and it collapsed. The count is re-measured every run by
 * `settings-api.test.tsx`; treat a change in it as a defect to investigate
 * rather than a number to update.
 */
export function splitPurpose(description?: string): {
  lead: string;
  inline: string[];
  collapsed: string[];
} {
  const paragraphs = (description ?? '')
    .split(/\n[ \t]*\n/)
    .map((p) => p.replace(/\s*\n\s*/g, ' ').trim())
    .filter((p) => p.length > 0);
  const lead = paragraphs[0] ?? '';
  const rest = paragraphs.slice(1);
  const collapse =
    rest.join('').length > PURPOSE_DISCLOSURE_MIN_CHARS && !rest.some(isBoundaryCaveat);
  return { lead, inline: collapse ? [] : rest, collapsed: collapse ? rest : [] };
}

function ApiEndpointDetail({
  row,
  schema,
  groupDescription,
  onCopied,
}: {
  row: ApiEndpoint;
  schema: ApiOpenApiResponse;
  groupDescription?: string;
  onCopied: (what: string) => void;
}) {
  const ok = row.responses.filter((r) => !isErrorCode(r.code));
  const errors = row.responses.filter((r) => isErrorCode(r.code));
  const purpose = splitPurpose(row.description);
  return (
    <>
      <h4 id={API_DETAIL_NAME_ID} className="api-browser-detail-name">
        <MethodBadge method={row.method} />
        <code className="mono api-browser-detail-path">{row.path}</code>
      </h4>

      {/* The group is the operation's REAL tag, and the sentence beside it is
          that tag's own registered description — not a label invented here. */}
      <p className="api-browser-detail-group">
        <span className="api-browser-detail-grouptag">{row.group}</span>
        {groupDescription && (
          <span className="api-browser-detail-groupdesc">{groupDescription}</span>
        )}
      </p>

      {row.summary && <p className="api-browser-detail-summary">{row.summary}</p>}

      {/* Compact metadata, scannable in one pass. `Auth` is the per-operation
          FLAG only — what it means is stated once for the whole tab, above the
          list, rather than as a paragraph repeated on every endpoint. Each
          value is the contract's own declaration, and the text carries the
          meaning: no colour-only marker.

          The flag reads `401 documented`, not `Credential required`. The app
          CANNOT know whether a given deployment enables authentication — the
          shared key is configured outside the browser, which is why Settings'
          own Authentication Boundary says "this screen cannot report whether
          access is restricted". What the app genuinely knows is what the
          generated contract declares: whether this operation documents a 401.
          The flag now states exactly that, so the marker no longer asserts
          something the page elsewhere admits it cannot see.

          `aria-describedby` additionally points at the tab-level legend, which
          supplies the conditional ("where a deployment enables authentication
          those operations need the deployment's credential") for a reader in the
          detail pane who never scrolled past the list. Support for
          `aria-describedby` on a non-interactive element varies by AT, so it is
          a supplement — the label above is truthful on its own. */}
      <dl className="api-browser-meta">
        <div className="api-browser-meta-item">
          <dt>Auth</dt>
          <dd
            className={row.authRequired ? 'api-browser-meta-flag required' : 'api-browser-meta-flag'}
            aria-describedby={AUTH_LEGEND_ID}
          >
            {row.authRequired ? '401 documented' : 'No 401 documented'}
          </dd>
        </div>
        <div className="api-browser-meta-item">
          <dt>Parameters</dt>
          <dd>{row.parameters.length === 0 ? 'None' : String(row.parameters.length)}</dd>
        </div>
        <div className="api-browser-meta-item">
          <dt>Request Body</dt>
          <dd>
            {row.requestBody
              ? row.requestBody.required
                ? 'Required'
                : 'Optional'
              : 'None declared'}
          </dd>
        </div>
      </dl>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Purpose</h5>
        {purpose.lead ? (
          <>
            <p className="api-docs-description">{purpose.lead}</p>
            {/* Short and medium remainders — and ANY remainder carrying a
                boundary caveat, at any length — render in full, right here. See
                `splitPurpose`: the disclosure below is reserved for a genuinely
                long, caveat-free docstring tail.

                THIS COMMENT USED TO END "which no operation in the current
                contract has", and that became false the moment
                `GET /api/runtime/verification` was added: its three-paragraph
                aggregate-only guarantee matched no marker and was collapsed.
                A standing claim about the CONTENT of a contract this file does
                not own goes stale silently, so the claim is gone; the measured
                one lives in `settings-api.test.tsx`, which re-counts every run.

                Keyed by index, not by text: two identical paragraphs in one
                description are legal and must not collide. */}
            {purpose.inline.map((paragraph, i) => (
              <p className="api-docs-description" key={`purpose-inline-${i}`}>
                {paragraph}
              </p>
            ))}
            {purpose.collapsed.length > 0 && (
              <details className="api-browser-disclosure">
                <summary>
                  Full Description
                  <span className="api-browser-morecount mono">
                    {purpose.collapsed.length} more paragraph
                    {purpose.collapsed.length === 1 ? '' : 's'}
                  </span>
                </summary>
                {purpose.collapsed.map((paragraph, i) => (
                  <p className="api-docs-description" key={`purpose-collapsed-${i}`}>
                    {paragraph}
                  </p>
                ))}
              </details>
            )}
          </>
        ) : (
          <p className="api-docs-no-params">The contract states no purpose for this operation.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Parameters</h5>
        {row.parameters.length > 0 ? (
          <div className="api-docs-params-wrap">
            <table className="api-docs-params">
              <caption className="sr-only">Parameters for {row.path}</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">In</th>
                  <th scope="col">Required</th>
                  <th scope="col">Description</th>
                </tr>
              </thead>
              <tbody>
                {row.parameters.map((p) => (
                  <tr key={`${p.in}:${p.name}`}>
                    <td className="mono">{p.name}</td>
                    <td>{p.in}</td>
                    <td>{p.required ? 'Yes' : 'No'}</td>
                    <td className="api-docs-param-desc">{p.description ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="api-docs-no-params">No parameters.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Request Body</h5>
        {row.requestBody ? (
          <>
            {row.requestBody.description && (
              <p className="api-browser-section-note">{row.requestBody.description}</p>
            )}
            <p className="api-browser-section-note">
              {row.requestBody.required ? 'Required.' : 'Optional.'}
            </p>
            <ContentBlocks content={row.requestBody.content} schema={schema} idBase="reqbody" />
          </>
        ) : row.method === 'get' ? (
          <p className="api-docs-no-params">No request body.</p>
        ) : (
          // Seven of this API's write operations declare no `requestBody`: two
          // read the RAW request and describe it in prose, and five take no body
          // at all. The document carries no signal that separates those two
          // cases, so the wording below covers both without picking one —
          // inventing a schema, or asserting "no body", would each be a guess.
          <p className="api-docs-no-params">
            The contract declares no request body for this operation. Where one is expected, it is
            described under Purpose rather than as a schema; nothing is inferred either way.
          </p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Responses</h5>
        {ok.length > 0 ? (
          <ResponseList entries={ok} schema={schema} />
        ) : (
          <p className="api-docs-no-params">The contract documents no non-error response.</p>
        )}
      </section>

      <section className="api-browser-section">
        <h5 className="api-browser-section-heading">Error States</h5>
        {errors.length > 0 ? (
          <ResponseList entries={errors} schema={schema} />
        ) : (
          <p className="api-docs-no-params">The contract documents no error response.</p>
        )}
      </section>

      <CodeSamples row={row} onCopied={onCopied} />

      <p className="api-browser-detail-source">
        Rendered verbatim from <code className="mono">GET /api/openapi</code> — this app's own
        generated contract. Every status, description and example above is the contract's own
        wording, including where it says an outcome never occurs.
      </p>
    </>
  );
}

function ResponseList({
  entries,
  schema,
}: {
  entries: ApiEndpoint['responses'];
  schema: ApiOpenApiResponse;
}) {
  return (
    <ul className="api-browser-responses">
      {entries.map((res) => (
        <li key={res.code} className="api-browser-response">
          <span className="api-browser-status mono">{res.code}</span>
          <div className="api-browser-response-body">
            {res.description ? (
              <p className="api-browser-section-note">{res.description}</p>
            ) : (
              <p className="api-browser-section-note">The contract gives this status no wording.</p>
            )}
            <ContentBlocks content={res.content} schema={schema} idBase={`res-${res.code}`} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Per-media-type schema + example disclosures. Collapsed by default, and the
 *  raw JSON is explicitly labelled `Technical Schema` so it never leads. */
function ContentBlocks({
  content,
  schema,
  idBase,
}: {
  content?: Record<string, OpenApiMediaType>;
  schema: ApiOpenApiResponse;
  idBase: string;
}) {
  const entries = Object.entries(content ?? {});
  if (entries.length === 0) return null;
  return (
    <>
      {entries.map(([mediaType, media]) => {
        const resolved = resolveSchema(media?.schema, schema);
        const examples = collectExamples(media);
        return (
          <div className="api-browser-media" key={`${idBase}:${mediaType}`}>
            <p className="api-browser-mediatype mono">{mediaType}</p>
            {resolved.value !== undefined && (
              <details className="api-browser-disclosure">
                <summary>
                  Technical Schema
                  {resolved.resolvedFrom && (
                    <span className="api-browser-reftag mono">{resolved.resolvedFrom}</span>
                  )}
                </summary>
                {/* A11Y-04: `.api-browser-json` is `overflow: auto` + `white-space: pre`
                    with a 260px cap, i.e. the same scroll container as the code samples.
                    It sits inside a collapsed `<details>`, so no axe scan has ever
                    measured it — that is a coverage fact, not evidence it is reachable. */}
                <pre
                  className="mono api-browser-json"
                  tabIndex={0}
                  role="group"
                  aria-label={`Technical schema for ${mediaType}`}
                >{stringify(resolved.value)}</pre>
              </details>
            )}
            {examples.map((ex) => (
              <details className="api-browser-disclosure" key={ex.name}>
                <summary>
                  Example
                  <span className="api-browser-reftag mono">{ex.name}</span>
                </summary>
                <pre
                  className="mono api-browser-json"
                  tabIndex={0}
                  role="group"
                  aria-label={`Example ${ex.name} for ${mediaType}`}
                >{stringify(ex.value)}</pre>
              </details>
            ))}
          </div>
        );
      })}
    </>
  );
}

// --- generated code examples -------------------------------------------------

const SAMPLE_TABS: { id: SampleId; label: string }[] = [
  { id: 'curl', label: 'cURL' },
  { id: 'python', label: 'Python' },
  { id: 'javascript', label: 'JavaScript' },
];

/**
 * Three runnable-shaped samples per operation, generated from that operation's
 * own contract (see `codeSamples`). Collapsed by default, and compact: one
 * language at a time behind a roving tablist, never three code walls at once.
 * No SDK and no dependency is referenced, because none exists.
 */
function CodeSamples({ row, onCopied }: { row: ApiEndpoint; onCopied: (what: string) => void }) {
  const samples = useMemo(() => codeSamples(row), [row]);
  const [active, setActive] = useState<SampleId>('curl');
  const current = samples.find((s) => s.id === active) ?? samples[0];
  const base = `settings-api-sample-${slug(row.key)}`;
  const tabId = (id: SampleId) => `${base}-tab-${id}`;
  const panelId = (id: SampleId) => `${base}-panel-${id}`;
  return (
    <details className="api-samples">
      <summary className="api-samples-summary">Code Examples</summary>
      <p className="api-browser-section-note">
        Generated from this operation's method, path, required parameters and declared media
        type. Standard library only — no client library exists for this API.
      </p>
      <RovingTabs
        className="api-samples-tabs"
        label="Code example language"
        tabs={SAMPLE_TABS}
        active={active}
        onSelect={setActive}
        tabId={tabId}
        panelId={panelId}
      />
      <div
        className="api-samples-panel"
        id={panelId(current.id)}
        role="tabpanel"
        aria-labelledby={tabId(current.id)}
      >
        <div className="api-samples-head">
          <span className="api-samples-lang">{current.label}</span>
          <CopyButton
            what={`the ${current.label} sample`}
            value={current.code}
            onCopied={onCopied}
          />
        </div>
        {/* A11Y-04: the same scroll container as the Quick Start sample above. */}
        <pre
          className="mono api-samples-code"
          tabIndex={0}
          role="group"
          aria-label={`${current.label} sample`}
        >{current.code}</pre>
      </div>
    </details>
  );
}
