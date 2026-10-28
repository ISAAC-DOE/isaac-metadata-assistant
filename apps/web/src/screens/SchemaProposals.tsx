import './screens.css';
import './schema-proposals.css';
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { Copy, Download } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { serverMessageOf } from '../lib/mutationErrors';
import {
  SCHEMA_PROPOSALS_COPY as COPY,
  STATUS_LABEL,
  portalBodyFilename,
  portalBodyText,
  proposalHeadline,
  schemaFieldErrors,
  type ApiSchemaCategory,
  type ApiSchemaProposal,
  type ApiSchemaProposalGate0,
  type ApiSchemaProposalResponse,
  type SchemaSourceId,
  type ApiSchemaSection,
  type ApiSchemaVocabulary,
  type SchemaFieldError,
  type SchemaProposalInput,
  type SchemaProposalType,
} from '../lib/schemaProposals';

/**
 * SCHEMA PROPOSALS — browse the vocabulary, draft a proposal to change it, and
 * track the drafts.
 *
 * WHAT THIS SCREEN WILL NOT DO, and each is a claim a test pins by behaviour:
 *
 *   1. IT NEVER APPROVES, APPLIES OR SENDS. There is no such control. A proposal is a
 *      draft on this server; the people who own the ISAAC standard review it in the
 *      ISAAC portal and record any decision there. The two states shown are the
 *      server's own — Pending and Withdrawn — and Pending is worded to claim nothing
 *      about whether anyone has seen it.
 *   2. IT NAMES NOBODY. Who is using this server is not verified, so a proposal records
 *      no author and the list says so rather than showing a blank or a guess.
 *   3. IT DOES NOT PRETEND TO KEEP WHAT THE SERVER MAY LOSE. Every response carries the
 *      server's own statement of how long a proposal lasts, and the screen shows it
 *      beside the proposals and again after saving one.
 *   4. IT NEVER LOSES WHAT YOU TYPED. The three panels stay mounted when you change tab,
 *      and a refused submit leaves every box as it was, with the server's own sentence
 *      beside the box it is about.
 */

type TabId = 'browse' | 'propose' | 'proposals';
const TAB_PARAM = 'tab';
const TABS: { id: TabId; label: string }[] = [
  { id: 'browse', label: COPY.tabBrowse },
  { id: 'propose', label: COPY.tabPropose },
  { id: 'proposals', label: COPY.tabProposals },
];
const isTab = (v: string | null): v is TabId => TABS.some((t) => t.id === v);
const tabDomId = (id: TabId) => `schema-proposals-tab-${id}`;
const panelDomId = (id: TabId) => `schema-proposals-panel-${id}`;

/** A request to open the form on a given section and category, with a counter so asking twice re-applies. */
interface Prefill {
  type: SchemaProposalType;
  section: string;
  category: string;
  nonce: number;
}

export function SchemaProposals() {
  const [params, setParams] = useSearchParams();
  const requested = params.get(TAB_PARAM);
  const tab: TabId = isTab(requested) ? requested : 'browse';

  const vocabulary = useFetch(() => api.getSchemaVocabulary(), []);
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  /** Bumped whenever a proposal is saved, so the list refetches. */
  const [listVersion, setListVersion] = useState(0);

  const selectTab = useCallback(
    (next: TabId) => {
      const nextParams = new URLSearchParams(params);
      nextParams.set(TAB_PARAM, next);
      setParams(nextParams, { replace: true });
    },
    [params, setParams],
  );

  const startProposal = useCallback(
    (type: SchemaProposalType, section: string, category: string) => {
      setPrefill((previous) => ({ type, section, category, nonce: (previous?.nonce ?? 0) + 1 }));
      selectTab('propose');
    },
    [selectTab],
  );

  function onTabKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextIndex = (index + 1) % TABS.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') nextIndex = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') nextIndex = 0;
    else if (e.key === 'End') nextIndex = TABS.length - 1;
    if (nextIndex === null) return;
    e.preventDefault();
    const next = TABS[nextIndex];
    selectTab(next.id);
    (document.getElementById(tabDomId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="schemaProposals" />}
      mainPad="pad"
      width="wide"
    >
      <div className="sp-screen">
        <header className="sp-head">
          <h1 className="page-title">{LABELS.navSchemaProposals}</h1>
          <p className="sp-lead">{COPY.lead}</p>
          <p className="sp-boundary">{COPY.boundary}</p>
        </header>

        <div className="section-tabs" role="tablist" aria-label="Schema Proposals sections">
          {TABS.map((t, i) => {
            const selected = t.id === tab;
            return (
              <button
                key={t.id}
                id={tabDomId(t.id)}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={panelDomId(t.id)}
                tabIndex={selected ? 0 : -1}
                className={`section-tab${selected ? ' active' : ''}`}
                onClick={() => selectTab(t.id)}
                onKeyDown={(e) => onTabKeyDown(e, i)}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {/* All three panels stay mounted and are hidden rather than unmounted, so a half-written
            proposal survives a trip to Browse. */}
        <div
          id={panelDomId('browse')}
          role="tabpanel"
          aria-labelledby={tabDomId('browse')}
          hidden={tab !== 'browse'}
        >
          {vocabulary.status === 'loading' && <LoadingPanel label="Reading the vocabulary…" />}
          {vocabulary.status === 'error' && <BackendDown error={vocabulary.error} onRetry={vocabulary.reload} />}
          {vocabulary.status === 'data' && (
            <BrowsePanel vocabulary={vocabulary.data} onPropose={startProposal} />
          )}
        </div>

        <div
          id={panelDomId('propose')}
          role="tabpanel"
          aria-labelledby={tabDomId('propose')}
          hidden={tab !== 'propose'}
        >
          {vocabulary.status === 'loading' && <LoadingPanel label="Reading the vocabulary…" />}
          {vocabulary.status === 'error' && <BackendDown error={vocabulary.error} onRetry={vocabulary.reload} />}
          {vocabulary.status === 'data' && (
            <ProposePanel
              vocabulary={vocabulary.data}
              prefill={prefill}
              onSaved={() => setListVersion((v) => v + 1)}
              onViewProposals={() => selectTab('proposals')}
            />
          )}
        </div>

        <div
          id={panelDomId('proposals')}
          role="tabpanel"
          aria-labelledby={tabDomId('proposals')}
          hidden={tab !== 'proposals'}
        >
          <ProposalsPanel version={listVersion} />
        </div>
      </div>
    </AppShell>
  );
}

// --- Browse ---------------------------------------------------------------------

function BrowsePanel({
  vocabulary,
  onPropose,
}: {
  vocabulary: ApiSchemaVocabulary;
  onPropose: (type: SchemaProposalType, section: string, category: string) => void;
}) {
  const sectionSelectId = useId();
  const sourceName = useId();
  const [sourceId, setSourceId] = useState<SchemaSourceId>(vocabulary.default_source);
  const source = vocabulary.sources[sourceId];
  const sections = source.sections;
  const [sectionId, setSectionId] = useState(sections[0]?.id ?? '');
  const section: ApiSchemaSection | undefined = sections.find((s) => s.id === sectionId) ?? sections[0];
  const [categoryKey, setCategoryKey] = useState<string | null>(null);
  const category: ApiSchemaCategory | undefined =
    section?.categories.find((c) => c.key === categoryKey) ?? section?.categories[0];
  // A new term can join only a list the PORTAL has, because the portal is what checks it.
  const termListsHere = new Set(
    vocabulary.proposal_sections.find((s) => s.id === section?.id)?.term_lists ?? [],
  );
  const canAddTerm = category !== undefined && termListsHere.has(category.key);

  return (
    <section className="sp-panel sp-panel-wide" aria-label={COPY.tabBrowse}>
      <p className="sp-note">{COPY.browseLead}</p>

      <fieldset className="sp-fieldset">
        <legend>Which list?</legend>
        {(['portal', 'schema'] as const).map((id) => (
          <label className="sp-radio" key={id}>
            <input
              type="radio"
              name={sourceName}
              checked={sourceId === id}
              onChange={() => {
                setSourceId(id);
                setSectionId(vocabulary.sources[id].sections[0]?.id ?? '');
                setCategoryKey(null);
              }}
            />
            <span>{vocabulary.sources[id].label}</span>
          </label>
        ))}
      </fieldset>
      <p className="sp-note">{source.detail}</p>
      <p className="sp-meta">
        {source.section_count} sections, {source.term_list_count} term lists, {source.term_count} terms.
      </p>

      <div className="sp-field">
        <label htmlFor={sectionSelectId}>Section</label>
        <select
          id={sectionSelectId}
          className="input sp-select"
          value={section?.id ?? ''}
          onChange={(e) => {
            setSectionId(e.target.value);
            setCategoryKey(null);
          }}
        >
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label} ({s.categories.length} {s.categories.length === 1 ? 'entry' : 'entries'})
            </option>
          ))}
        </select>
      </div>

      {section && section.categories.length === 0 && (
        <p className="sp-note" role="status">
          This section has no fixed lists of allowed terms in this source. You can still propose a new list for it.
        </p>
      )}

      {section && section.categories.length > 0 && (
        <div className="sp-browse-grid">
          <div>
            <h2 className="sp-h2" id="sp-categories-heading">
              Categories
            </h2>
            <ul className="sp-cat-list" aria-labelledby="sp-categories-heading">
              {section.categories.map((c) => {
                const current = c.key === category?.key;
                return (
                  <li key={c.key}>
                    <button
                      type="button"
                      className={`sp-cat${current ? ' is-current' : ''}`}
                      aria-pressed={current}
                      onClick={() => setCategoryKey(c.key)}
                    >
                      <span className="sp-cat-key">{c.key}</span>
                      <span className="sp-cat-count">{c.kind === 'other' ? 'no list' : c.terms.length}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {category && (
            <div>
              <h2 className="sp-h2">{category.key}</h2>
              {category.description && <p className="sp-note">{category.description}</p>}
              {category.kind === 'other' ? (
                <p className="sp-note">
                  This entry is a mapping or a unit grammar, not a list of allowed terms, so it has no terms to show.
                </p>
              ) : (
                <table className="sp-table">
                  <caption className="sr-only">Allowed terms for {category.key}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Allowed term</th>
                    </tr>
                  </thead>
                  <tbody>
                    {category.terms.map((term) => (
                      <tr key={term}>
                        <td className="sp-term">{term}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {canAddTerm ? (
                <div className="sp-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => onPropose('add_term', section.id, category.key)}
                  >
                    Propose a New Term for This List
                  </button>
                </div>
              ) : (
                category.kind !== 'other' && (
                  <p className="sp-hint">
                    The portal vocabulary snapshot has no list for this entry in this section, so the portal would
                    refuse a new term for it. Switch to the portal list to propose a term.
                  </p>
                )
              )}
            </div>
          )}
        </div>
      )}

      {section && (
        <div className="sp-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onPropose('add_category', section.id, '')}
          >
            Propose a New List in {section.label}
          </button>
        </div>
      )}
    </section>
  );
}

// --- Propose --------------------------------------------------------------------

const GATE0_FIELDS: { key: keyof ApiSchemaProposalGate0; label: string; rows: number; hint: string }[] = [
  {
    key: 'problem',
    label: 'The problem, with counts and examples',
    rows: 3,
    hint: 'What goes wrong today? How many records, and which?',
  },
  {
    key: 'examples',
    label: 'Examples',
    rows: 2,
    hint: 'Record ids or a sentence from a record that shows it.',
  },
  {
    key: 'affected_records_estimate',
    label: 'Records affected (estimate)',
    rows: 1,
    hint: 'A rough number is fine, for example "about 40".',
  },
  {
    key: 'flip_list',
    label: 'What would change',
    rows: 2,
    hint: 'Which stored records or checks would behave differently once this is added?',
  },
];

function ProposePanel({
  vocabulary,
  prefill,
  onSaved,
  onViewProposals,
}: {
  vocabulary: ApiSchemaVocabulary;
  prefill: Prefill | null;
  onSaved: () => void;
  onViewProposals: () => void;
}) {
  const ids = {
    type: useId(),
    section: useId(),
    category: useId(),
    term: useId(),
    description: useId(),
  };
  const limits = vocabulary.limits;
  const sections = vocabulary.proposal_sections;

  const [type, setType] = useState<SchemaProposalType>('add_term');
  const [sectionId, setSectionId] = useState(sections.find((s) => s.term_lists.length > 0)?.id ?? sections[0]?.id ?? '');
  const [category, setCategory] = useState('');
  const [term, setTerm] = useState('');
  const [description, setDescription] = useState('');
  const [gate0, setGate0] = useState<Record<string, string>>({});

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<SchemaFieldError[]>([]);
  const [topMessage, setTopMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState<ApiSchemaProposalResponse | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const savedRef = useRef<HTMLDivElement>(null);

  const section = sections.find((s) => s.id === sectionId);
  const listsInSection = useMemo(() => section?.term_lists ?? [], [section]);

  // An "open the form on this list" request from Browse.
  useEffect(() => {
    if (!prefill) return;
    setType(prefill.type);
    setSectionId(prefill.section);
    setCategory(prefill.category);
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
  }, [prefill]);

  // The category for "add a term" must be one of the section's lists. Keep it valid when the
  // section changes; an explicit empty choice is kept so the reader sees it is not chosen yet.
  useEffect(() => {
    if (type !== 'add_term') return;
    if (category !== '' && !listsInSection.includes(category)) setCategory('');
  }, [type, listsInSection, category]);

  useEffect(() => {
    if (errors.length > 0 || topMessage) summaryRef.current?.focus();
  }, [errors, topMessage]);

  useEffect(() => {
    if (saved) savedRef.current?.focus();
  }, [saved]);

  const errorFor = (field: string) => errors.find((e) => e.field === field)?.message;
  const shown = new Set(['proposal_type', 'section', 'category', 'term', 'description', ...GATE0_FIELDS.map((g) => `gate0.${g.key}`)]);
  const elsewhere = errors.filter((e) => e.field === null || !shown.has(e.field));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setErrors([]);
    setTopMessage(null);
    setSaved(null);
    const note: ApiSchemaProposalGate0 = {};
    for (const g of GATE0_FIELDS) {
      const text = (gate0[g.key] ?? '').trim();
      if (text) note[g.key] = text;
    }
    const input: SchemaProposalInput = {
      proposal_type: type,
      section: sectionId,
      category: category.trim(),
      description: description.trim(),
      ...(type === 'add_term' ? { term: term.trim() } : {}),
      ...(Object.keys(note).length > 0 ? { gate0: note } : {}),
    };
    try {
      const response = await api.createSchemaProposal(input);
      setSaved(response);
      setTerm('');
      setDescription('');
      setGate0({});
      onSaved();
    } catch (err) {
      const fieldErrors = schemaFieldErrors(err);
      setErrors(fieldErrors);
      setTopMessage(
        serverMessageOf(err) ??
          'The proposal could not be saved, and nothing was written. Check your connection and try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  const descriptionCount = description.trim().length;

  return (
    <section className="sp-panel" aria-label={COPY.tabPropose}>
      <p className="sp-note">{COPY.proposeLead}</p>

      {saved && (
        <div className="sp-saved" role="status" tabIndex={-1} ref={savedRef}>
          <p className="sp-saved-title">{COPY.savedNotice}</p>
          {saved.withdrawn_removed ? (
            <p>
              To stay within the server&apos;s limit, {saved.withdrawn_removed} of the oldest withdrawn proposals{' '}
              {saved.withdrawn_removed === 1 ? 'was' : 'were'} removed.
            </p>
          ) : null}
          {saved.ignored_fields && saved.ignored_fields.length > 0 && (
            <p>Ignored, because the server sets them: {saved.ignored_fields.join(', ')}.</p>
          )}
          <div className="sp-actions">
            <PortalActions proposalId={saved.proposal.id} />
            <button type="button" className="btn btn-secondary" onClick={onViewProposals}>
              View Proposals
            </button>
          </div>
        </div>
      )}

      {(topMessage || elsewhere.length > 0) && (
        <div className="sp-error-summary" role="alert" tabIndex={-1} ref={summaryRef}>
          <p className="sp-error-title">{topMessage}</p>
          {elsewhere.length > 0 && (
            <ul>
              {elsewhere.map((er, i) => (
                <li key={`${er.code}-${i}`}>{er.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <form className="sp-form" onSubmit={onSubmit} noValidate>
        <fieldset className="sp-fieldset">
          <legend id={ids.type}>What do you want to propose?</legend>
          <label className="sp-radio">
            <input
              type="radio"
              name="schema-proposal-type"
              checked={type === 'add_term'}
              onChange={() => setType('add_term')}
            />
            <span>Add a term to an existing list</span>
          </label>
          <label className="sp-radio">
            <input
              type="radio"
              name="schema-proposal-type"
              checked={type === 'add_category'}
              onChange={() => setType('add_category')}
            />
            <span>Add a new list of allowed terms</span>
          </label>
          <FieldError id={`${ids.type}-err`} message={errorFor('proposal_type')} />
        </fieldset>

        <div className="sp-field">
          <label htmlFor={ids.section}>Section</label>
          <select
            id={ids.section}
            className="input sp-select"
            value={sectionId}
            onChange={(e) => setSectionId(e.target.value)}
            aria-invalid={errorFor('section') ? true : undefined}
            aria-describedby={errorFor('section') ? `${ids.section}-err` : undefined}
          >
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <FieldError id={`${ids.section}-err`} message={errorFor('section')} />
        </div>

        {type === 'add_term' ? (
          <>
            <div className="sp-field">
              <label htmlFor={ids.category}>Category</label>
              <select
                id={ids.category}
                className="input sp-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-invalid={errorFor('category') ? true : undefined}
                aria-describedby={errorFor('category') ? `${ids.category}-err` : `${ids.category}-hint`}
              >
                <option value="">Choose a list…</option>
                {listsInSection.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
              {listsInSection.length === 0 ? (
                <p className="sp-hint" id={`${ids.category}-hint`}>
                  The portal vocabulary snapshot has no term lists in this section. Choose another section, or propose a
                  new list.
                </p>
              ) : (
                <span id={`${ids.category}-hint`} className="sr-only">
                  The list the new term belongs to.
                </span>
              )}
              <FieldError id={`${ids.category}-err`} message={errorFor('category')} />
            </div>

            <div className="sp-field">
              <label htmlFor={ids.term}>New term</label>
              <input
                id={ids.term}
                className="input input-mono"
                value={term}
                maxLength={limits.term_max}
                placeholder="for example rotating_cylinder"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setTerm(e.target.value)}
                aria-invalid={errorFor('term') ? true : undefined}
                aria-describedby={`${ids.term}-hint${errorFor('term') ? ` ${ids.term}-err` : ''}`}
              />
              <p className="sp-hint" id={`${ids.term}-hint`}>
                {vocabulary.term_rule}
              </p>
              <FieldError id={`${ids.term}-err`} message={errorFor('term')} />
            </div>
          </>
        ) : (
          <div className="sp-field">
            <label htmlFor={ids.category}>New list key</label>
            <input
              id={ids.category}
              className="input input-mono"
              value={category}
              maxLength={limits.category_max}
              placeholder="for example context.transport.viscosity"
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setCategory(e.target.value)}
              aria-invalid={errorFor('category') ? true : undefined}
              aria-describedby={`${ids.category}-hint${errorFor('category') ? ` ${ids.category}-err` : ''}`}
            />
            <p className="sp-hint" id={`${ids.category}-hint`}>
              A dotted path of field names. It starts with the section&apos;s own block name
              {section?.block ? ` (${section.block}.)` : ''}.
            </p>
            <FieldError id={`${ids.category}-err`} message={errorFor('category')} />
          </div>
        )}

        <div className="sp-field">
          <label htmlFor={ids.description}>Description (required)</label>
          <textarea
            id={ids.description}
            className="input sp-textarea"
            rows={4}
            value={description}
            maxLength={limits.description_max}
            placeholder="Say what this means and where it is used. A reviewer writes the definition from it."
            onChange={(e) => setDescription(e.target.value)}
            aria-invalid={errorFor('description') ? true : undefined}
            aria-describedby={`${ids.description}-hint${errorFor('description') ? ` ${ids.description}-err` : ''}`}
          />
          <p className="sp-hint" id={`${ids.description}-hint`}>
            At least {limits.description_min} characters, at most {limits.description_max}. {descriptionCount}{' '}
            so far.
          </p>
          <FieldError id={`${ids.description}-err`} message={errorFor('description')} />
        </div>

        <details className="sp-why">
          <summary>Why (for reviewers), optional</summary>
          <p className="sp-hint">
            Reviewers of changes to the standard look for the problem, who it affects and what would change.
            These answers travel with your description.
          </p>
          {GATE0_FIELDS.map((g) => {
            const fieldId = `${ids.description}-gate0-${g.key}`;
            const err = errorFor(`gate0.${g.key}`);
            return (
              <div className="sp-field" key={g.key}>
                <label htmlFor={fieldId}>{g.label}</label>
                <textarea
                  id={fieldId}
                  className="input sp-textarea"
                  rows={g.rows}
                  value={gate0[g.key] ?? ''}
                  onChange={(e) => setGate0((prev) => ({ ...prev, [g.key]: e.target.value }))}
                  aria-invalid={err ? true : undefined}
                  aria-describedby={`${fieldId}-hint${err ? ` ${fieldId}-err` : ''}`}
                />
                <p className="sp-hint" id={`${fieldId}-hint`}>
                  {g.hint}
                </p>
                <FieldError id={`${fieldId}-err`} message={err} />
              </div>
            );
          })}
        </details>

        <div className="sp-actions">
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save Proposal'}
          </button>
          <span className="sp-hint">Saving keeps a draft here. It does not send it to anyone.</span>
        </div>
      </form>
    </section>
  );
}

function FieldError({ id, message }: { id: string; message: string | undefined }) {
  if (!message) return null;
  return (
    <p className="sp-field-error" id={id}>
      {message}
    </p>
  );
}

// --- Proposals ------------------------------------------------------------------

const PAGE_SIZE = 25;

function ProposalsPanel({ version }: { version: number }) {
  const first = useFetch(() => api.listSchemaProposals({ limit: PAGE_SIZE, offset: 0 }), [version]);
  const [more, setMore] = useState<ApiSchemaProposal[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  /** A proposal changed in place by a withdraw, keyed by id, so the list needs no refetch. */
  const [changed, setChanged] = useState<Record<string, ApiSchemaProposal>>({});

  const firstData = first.status === 'data' ? first.data : null;
  useEffect(() => {
    // A fresh first page replaces everything that was appended after the previous one.
    setMore([]);
    setChanged({});
    setMoreFailed(false);
    setNextOffset(firstData ? firstData.next_offset : null);
  }, [firstData]);

  async function showMore() {
    if (nextOffset === null || loadingMore) return;
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const page = await api.listSchemaProposals({ limit: PAGE_SIZE, offset: nextOffset });
      setMore((prev) => [...prev, ...page.proposals]);
      setNextOffset(page.next_offset);
    } catch {
      setMoreFailed(true);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="sp-panel" aria-label={COPY.tabProposals}>
      {first.status === 'loading' && <LoadingPanel label="Loading proposals…" />}
      {first.status === 'error' && <BackendDown error={first.error} onRetry={first.reload} />}
      {firstData && (
        <>
          <div className="sp-notice">
            <p>{firstData.persistence.message}</p>
            <p>
              {firstData.capacity.pending} of {firstData.capacity.max_pending} pending places used. {firstData.capacity.scope}
            </p>
            <p>{COPY.unverifiedAuthor}</p>
          </div>

          {firstData.total === 0 ? (
            <p className="sp-note">No proposals on this server yet. Use Propose a Change to draft one.</p>
          ) : (
            <>
              <p className="sp-meta" role="status">
                {firstData.total} {firstData.total === 1 ? 'proposal' : 'proposals'}, newest first.
              </p>
              <ul className="sp-list">
                {[...firstData.proposals, ...more].map((p) => (
                  <ProposalRow
                    key={p.id}
                    proposal={changed[p.id] ?? p}
                    onChanged={(next) => setChanged((prev) => ({ ...prev, [p.id]: next }))}
                  />
                ))}
              </ul>
              {moreFailed && (
                <p className="sp-field-error" role="alert">
                  The next proposals could not be loaded. Try again.
                </p>
              )}
              {nextOffset !== null && (
                <div className="sp-actions">
                  <button type="button" className="btn btn-secondary" onClick={showMore} disabled={loadingMore}>
                    {loadingMore ? 'Loading…' : 'Show More'}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

function ProposalRow({
  proposal,
  onChanged,
}: {
  proposal: ApiSchemaProposal;
  onChanged: (next: ApiSchemaProposal) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const withdrawRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  async function withdraw() {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.withdrawSchemaProposal(proposal.id);
      setConfirming(false);
      onChanged(response.proposal);
    } catch (err) {
      setConfirming(false);
      setFailure(serverMessageOf(err) ?? 'The proposal could not be withdrawn. Nothing was changed.');
      // Hand focus back to a control that still exists.
      requestAnimationFrame(() => withdrawRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  const gate0 = proposal.gate0;
  return (
    <li className="sp-item">
      <div className="sp-item-head">
        <h2 className="sp-item-title">{proposalHeadline(proposal)}</h2>
        <span className={`sp-status sp-status-${proposal.status}`}>{STATUS_LABEL[proposal.status]}</span>
      </div>
      <p className="sp-item-meta">
        {proposal.section}
        {proposal.proposal_type === 'add_term' ? ' · new term' : ' · new list'}
        {proposal.proposed_at ? ` · drafted ${proposal.proposed_at}` : ''}
        {proposal.withdrawn_at ? ` · withdrawn ${proposal.withdrawn_at}` : ''}
      </p>
      <p className="sp-item-text">{proposal.description}</p>
      {gate0 && (
        <dl className="sp-why-list">
          {gate0.problem && (
            <>
              <dt>The problem</dt>
              <dd>{gate0.problem}</dd>
            </>
          )}
          {gate0.examples && (
            <>
              <dt>Examples</dt>
              <dd>{gate0.examples}</dd>
            </>
          )}
          {gate0.affected_records_estimate && (
            <>
              <dt>Records affected</dt>
              <dd>{gate0.affected_records_estimate}</dd>
            </>
          )}
          {gate0.flip_list && (
            <>
              <dt>What would change</dt>
              <dd>{gate0.flip_list}</dd>
            </>
          )}
        </dl>
      )}
      <p className="sp-item-meta">
        {proposal.attribution === 'verified' && proposal.proposed_by
          ? `Proposed by ${proposal.proposed_by}`
          : 'Author not recorded (not verified).'}
      </p>

      <div className="sp-actions">
        <PortalActions proposalId={proposal.id} />
        {proposal.status === 'pending' && !confirming && (
          <button
            type="button"
            className="btn btn-secondary"
            ref={withdrawRef}
            onClick={() => setConfirming(true)}
          >
            Withdraw
          </button>
        )}
        {proposal.status === 'pending' && confirming && (
          <span className="sp-confirm" role="group" aria-label="Confirm withdrawing this proposal">
            <span>Withdraw this proposal? This cannot be undone.</span>
            <button type="button" className="btn btn-danger" ref={confirmRef} onClick={withdraw} disabled={busy}>
              {busy ? 'Withdrawing…' : 'Confirm Withdraw'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Keep It
            </button>
          </span>
        )}
      </div>
      {failure && (
        <p className="sp-field-error" role="alert">
          {failure}
        </p>
      )}
    </li>
  );
}

// --- Copy / download ------------------------------------------------------------

/**
 * Copy the portal body, or download it as JSON. The body is fetched when asked for — it is
 * the server's exact answer, never rebuilt here — and is the ONLY thing either control hands
 * out. Neither sends anything anywhere: copying puts text on the reader's clipboard, and the
 * person who pastes it into the portal is the person who sends it.
 */
function PortalActions({ proposalId }: { proposalId: string }) {
  /** What the server said about where this payload goes. Shown with every outcome. */
  type Where = { restSupported: boolean; notes: string[] };
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'busy' }
    | { kind: 'copied'; where: Where }
    | { kind: 'downloaded'; where: Where }
    | { kind: 'manual'; text: string; where: Where }
    | { kind: 'failed' }
  >({ kind: 'idle' });

  async function load() {
    const payload = await api.getSchemaProposalPortalPayload(proposalId);
    return {
      text: portalBodyText(payload),
      where: { restSupported: payload.portal.rest_supported, notes: payload.notes },
    };
  }

  async function copy() {
    setState({ kind: 'busy' });
    let loaded: Awaited<ReturnType<typeof load>>;
    try {
      loaded = await load();
    } catch {
      setState({ kind: 'failed' });
      return;
    }
    try {
      await navigator.clipboard.writeText(loaded.text);
      setState({ kind: 'copied', where: loaded.where });
    } catch {
      // No clipboard permission: show the text for the reader to select and copy by hand,
      // rather than saying it was copied.
      setState({ kind: 'manual', text: loaded.text, where: loaded.where });
    }
  }

  async function download() {
    setState({ kind: 'busy' });
    try {
      const { text, where } = await load();
      const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = portalBodyFilename(proposalId);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState({ kind: 'downloaded', where });
    } catch {
      setState({ kind: 'failed' });
    }
  }

  const busy = state.kind === 'busy';
  const where = state.kind === 'copied' || state.kind === 'downloaded' || state.kind === 'manual' ? state.where : null;
  /** The destination, from the server's own flag: new terms go to the portal's web endpoint; a new list does not. */
  const destination = where
    ? where.restSupported
      ? 'Paste it into the ISAAC portal.'
      : "The portal's web endpoint takes new terms only: enter this in the portal's Ontology Editor (its Propose a Change form), using these fields."
    : null;
  return (
    <span className="sp-portal">
      <button type="button" className="btn btn-secondary" onClick={copy} disabled={busy}>
        <Copy size={14} strokeWidth={2} aria-hidden="true" /> Copy Portal Payload
      </button>
      <button type="button" className="btn btn-secondary" onClick={download} disabled={busy}>
        <Download size={14} strokeWidth={2} aria-hidden="true" /> Download JSON
      </button>
      <span className="sp-portal-status" role="status">
        {state.kind === 'copied' && `Copied. ISAAC has not sent it. ${destination}`}
        {state.kind === 'downloaded' && `Downloaded. ISAAC has not sent it anywhere. ${destination}`}
        {state.kind === 'failed' && 'The portal payload could not be prepared. Nothing was copied.'}
        {state.kind === 'manual' && 'Your browser did not allow copying. Select the text below and copy it.'}
      </span>
      {where && where.notes.length > 0 && (
        <ul className="sp-portal-notes">
          {where.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {state.kind === 'manual' && (
        <textarea
          className="input input-mono sp-textarea"
          readOnly
          rows={8}
          aria-label="Portal payload"
          value={state.text}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </span>
  );
}
