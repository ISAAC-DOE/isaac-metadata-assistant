import './schema-browser.css';
import {
  useCallback,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { LoadingPanel, BackendDown } from './FetchStates';
import { LayoutList, Search, ChevronRight } from './icons';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  buildSchemaFieldTree,
  buildVocabularyFile,
  citationsArePatternOnly,
  extractRelationships,
  fieldsCitingVocabulary,
  filterFields,
  filterRelationships,
  filterVocabularyNodes,
  findFieldByPath,
  flattenFieldTree,
  formatRelationship,
  parentPath,
  relationshipOutcomes,
  relationshipPaths,
  relationshipTriggers,
  rulesNamingField,
  rulesNestedUnderField,
  vocabularySourceSlug,
  type SchemaFieldNode,
  type SchemaRelationship,
  type VocabularyFile,
  type VocabularyNode,
} from '../lib/schemaBrowser';
import type { ApiSchemaResponse } from '../lib/types';

/**
 * P36.6 + P36R S8 — the Schema Reference browser (Governance & Safety >
 * "Schema Reference" tab).
 *
 * A READ-ONLY reference view over the canonical official ISAAC schema and
 * controlled vocabulary, fetched from `GET /api/schema`. Every field, type,
 * required/optional flag, allowed value, example, description, rule, and
 * vocabulary term shown here is read verbatim from that response — nothing is
 * computed, summarized, or invented client-side beyond deterministic
 * tree-building, path comparison, and substring search (`lib/schemaBrowser.ts`).
 *
 * P36R S8 replaces the three always-open sections with three subviews —
 * Fields (a master-detail browser, not an expanded tree), Conditional Rules
 * (the `allOf` if/then clauses restructured into trigger / consequence /
 * affected paths, raw form behind a disclosure), and Vocabulary (the real
 * controlled-vocabulary content, with an honest empty state as the FALLBACK
 * branch when no vocabulary file is bundled).
 *
 * This is explicitly NOT the portal Ontology system: there is no
 * propose/review/approve/edit/role/persistence affordance anywhere in this
 * component, and it computes no verdict of its own.
 */
export function SchemaBrowser() {
  const fetchState = useFetch(() => api.getSchema(), []);

  return (
    <section className="schema-browser card" aria-labelledby="schema-browser-heading">
      <header className="schema-browser-head">
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="schema-browser-icon" />
        <div>
          <h2 id="schema-browser-heading">Schema Reference</h2>
          <p className="schema-browser-sub">
            A read-only reference for the canonical official ISAAC schema and its controlled
            vocabulary — every field, type, requirement, allowed value, rule, and term below is read
            verbatim from the vendored schema and vocabulary files. This is a reference view, not
            the portal Ontology system: there is nothing to propose, review, approve, or edit here.
          </p>
        </div>
      </header>

      {fetchState.status === 'loading' && <LoadingPanel label="Loading schema…" />}
      {fetchState.status === 'error' && (
        <BackendDown error={fetchState.error} onRetry={fetchState.reload} />
      )}
      {fetchState.status === 'data' && <SchemaBrowserBody data={fetchState.data} />}
    </section>
  );
}

// --- subview navigation ----------------------------------------------------

type SchemaView = 'fields' | 'rules' | 'vocabulary';

const SCHEMA_VIEWS: { id: SchemaView; label: string }[] = [
  { id: 'fields', label: 'Fields' },
  { id: 'rules', label: 'Conditional Rules' },
  { id: 'vocabulary', label: 'Vocabulary' },
];

const viewTabId = (id: SchemaView) => `schema-view-tab-${id}`;
const viewPanelId = (id: SchemaView) => `schema-view-panel-${id}`;

/**
 * The inner tablist — Fields · Conditional Rules · Vocabulary. Same roving
 * tabindex + Arrow/Home/End contract as the outer Governance tablist, nested
 * one level down (its own `aria-label` keeps the two distinguishable).
 */
function SchemaViewTabs({
  active,
  onSelect,
}: {
  active: SchemaView;
  onSelect: (view: SchemaView) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % SCHEMA_VIEWS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + SCHEMA_VIEWS.length) % SCHEMA_VIEWS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = SCHEMA_VIEWS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = SCHEMA_VIEWS[nextIndex];
    onSelect(next.id);
    (document.getElementById(viewTabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="schema-subtabs" role="tablist" aria-label="Schema Reference views">
      {SCHEMA_VIEWS.map((view, i) => {
        const selected = active === view.id;
        return (
          <button
            key={view.id}
            id={viewTabId(view.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? viewPanelId(view.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`schema-subtab${selected ? ' active' : ''}`}
            onClick={() => onSelect(view.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {view.label}
          </button>
        );
      })}
    </div>
  );
}

// --- body ------------------------------------------------------------------

function SchemaBrowserBody({ data }: { data: ApiSchemaResponse }) {
  const [view, setView] = useState<SchemaView>('fields');
  const [fieldQuery, setFieldQuery] = useState('');
  const [ruleQuery, setRuleQuery] = useState('');
  const [vocabQuery, setVocabQuery] = useState('');
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  // Roving-tabindex cursor for the Fields master list — see `FieldsView`. Held
  // here, not inside `FieldsView`, so switching subviews and coming back does
  // not drop the reading position. Focus and SELECTION stay separate: an arrow
  // key moves this cursor, Enter/Space (native button activation) selects.
  const [focusIndex, setFocusIndex] = useState(0);

  const tree = useMemo(() => buildSchemaFieldTree(data.schema), [data.schema]);
  const allFields = useMemo(() => flattenFieldTree(tree), [tree]);
  const rules = useMemo(() => extractRelationships(data.schema), [data.schema]);
  const visibleFields = useMemo(() => filterFields(allFields, fieldQuery), [allFields, fieldQuery]);
  const visibleRules = useMemo(() => filterRelationships(rules, ruleQuery), [rules, ruleQuery]);
  // "Rule 3" must stay Rule 3 under a search — the ordinal is the rule's place
  // in the UNFILTERED list, never its index in whatever the filter left.
  const ruleOrdinals = useMemo(
    () => new Map(rules.map((r, i) => [r.id, i + 1])),
    [rules],
  );
  const vocabFiles = useMemo(
    () =>
      Object.entries(data.vocabularies ?? {}).map(([name, value]) =>
        buildVocabularyFile(name, value),
      ),
    [data.vocabularies],
  );

  // Selection follows the filter without an effect: the explicitly selected
  // field when it is still visible, otherwise the first visible field, otherwise
  // nothing. Never a field the user cannot see in the list.
  const selected =
    findFieldByPath(visibleFields, selectedPath) ?? (visibleFields.length > 0 ? visibleFields[0] : null);

  const sourceLine = `${data.schema_title ?? 'ISAAC official schema'} — v${data.schema_version} — vendored official schema (read-only reference)`;

  /** Cross-view navigation: show one exact field in the Fields master-detail. */
  function openField(path: string) {
    setFieldQuery(path);
    setSelectedPath(path);
    // Land the roving cursor on the row that is about to be selected, so the
    // next Tab into the list lands on the selection instead of a stale row.
    const index = filterFields(allFields, path).findIndex((f) => f.path === path);
    setFocusIndex(index >= 0 ? index : 0);
    setView('fields');
  }

  /** Cross-view navigation: show the rules that name one exact field path. */
  function openRulesFor(path: string) {
    setRuleQuery(path);
    setView('rules');
  }

  return (
    <>
      <p className="schema-browser-source-line mono">{sourceLine}</p>

      <SchemaViewTabs active={view} onSelect={setView} />

      {view === 'fields' && (
        <div
          id={viewPanelId('fields')}
          role="tabpanel"
          aria-labelledby={viewTabId('fields')}
          tabIndex={0}
          className="schema-view-panel"
        >
          <FieldsView
            fields={visibleFields}
            total={allFields.length}
            query={fieldQuery}
            onQuery={(q) => {
              setFieldQuery(q);
              setSelectedPath(null);
              setFocusIndex(0);
            }}
            selected={selected}
            onSelect={(path, index) => {
              setSelectedPath(path);
              setFocusIndex(index);
            }}
            focusIndex={focusIndex}
            onFocusIndex={setFocusIndex}
            rules={rules}
            sourceLine={sourceLine}
            onOpenField={openField}
            onOpenRules={openRulesFor}
          />
        </div>
      )}

      {view === 'rules' && (
        <div
          id={viewPanelId('rules')}
          role="tabpanel"
          aria-labelledby={viewTabId('rules')}
          tabIndex={0}
          className="schema-view-panel"
        >
          <RulesView
            rules={visibleRules}
            total={rules.length}
            ordinals={ruleOrdinals}
            query={ruleQuery}
            onQuery={setRuleQuery}
            allFields={allFields}
            onOpenField={openField}
          />
        </div>
      )}

      {view === 'vocabulary' && (
        <div
          id={viewPanelId('vocabulary')}
          role="tabpanel"
          aria-labelledby={viewTabId('vocabulary')}
          tabIndex={0}
          className="schema-view-panel"
        >
          <VocabularyView
            files={vocabFiles}
            query={vocabQuery}
            onQuery={setVocabQuery}
            allFields={allFields}
            onOpenField={openField}
          />
        </div>
      )}
    </>
  );
}

// --- shared search field ---------------------------------------------------

function SearchField({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="schema-browser-search-row">
      <label htmlFor={id} className="schema-browser-search-label">
        <Search size={14} strokeWidth={2} aria-hidden="true" />
        {label}
      </label>
      <input
        id={id}
        type="search"
        className="schema-browser-search-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

// --- Fields (master-detail) -------------------------------------------------

const FIELD_DETAIL_ID = 'schema-field-detail';
/** The detail pane's accessible name — the selected field's own heading. */
const FIELD_DETAIL_NAME_ID = 'schema-field-detail-name';

/** A DOM-id-safe token for one field row, so the roving cursor can focus it. */
const fieldRowId = (path: string) => `schema-field-row-${path.replace(/[^a-zA-Z0-9]+/g, '-')}`;

function FieldsView({
  fields,
  total,
  query,
  onQuery,
  selected,
  onSelect,
  focusIndex,
  onFocusIndex,
  rules,
  sourceLine,
  onOpenField,
  onOpenRules,
}: {
  fields: SchemaFieldNode[];
  total: number;
  query: string;
  onQuery: (next: string) => void;
  selected: SchemaFieldNode | null;
  onSelect: (path: string, index: number) => void;
  focusIndex: number;
  onFocusIndex: (next: number) => void;
  rules: SchemaRelationship[];
  sourceLine: string;
  onOpenField: (path: string) => void;
  onOpenRules: (path: string) => void;
}) {
  const listHeadingId = 'schema-fields-list-heading';
  // The cursor can outrun a shrinking list (type a query after arrowing down).
  const cursor = fields.length === 0 ? 0 : Math.min(focusIndex, fields.length - 1);

  /**
   * Roving tabindex: exactly one row is in the tab order, and Arrow/Home/End
   * move that cursor WITHOUT selecting. Same contract as the Concepts master
   * list in Project Memory — one interaction model, not two.
   */
  const onListKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
      let next: number | null = null;
      if (e.key === 'ArrowDown') next = Math.min(index + 1, fields.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(index - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = fields.length - 1;
      if (next === null || fields.length === 0) return;
      e.preventDefault();
      onFocusIndex(next);
      (document.getElementById(fieldRowId(fields[next].path)) as HTMLButtonElement | null)?.focus();
    },
    [fields, onFocusIndex],
  );

  return (
    <>
      <SearchField
        id="schema-browser-search"
        label="Search fields"
        placeholder="Search by field name, path, or description…"
        value={query}
        onChange={onQuery}
      />

      <div className="schema-fields-split">
        <div className="schema-fields-master">
          <h3 id={listHeadingId} className="schema-pane-heading">
            Fields
            <span className="schema-pane-count mono">
              {fields.length === total ? `${total}` : `${fields.length} of ${total}`}
            </span>
          </h3>
          {fields.length === 0 ? (
            <p className="schema-browser-empty">No fields match &ldquo;{query}&rdquo;.</p>
          ) : (
            <ul className="schema-field-rows" aria-labelledby={listHeadingId}>
              {fields.map((node, i) => (
                <SchemaFieldRow
                  key={node.path}
                  node={node}
                  selected={selected?.path === node.path}
                  tabIndex={i === cursor ? 0 : -1}
                  onSelect={() => onSelect(node.path, i)}
                  onKeyDown={(e) => onListKeyDown(e, i)}
                />
              ))}
            </ul>
          )}
        </div>

        {/* `tabIndex={-1}` makes the pane a programmatic focus target without
            adding a stop; its accessible name is whichever heading is showing. */}
        <div
          className="schema-fields-detailpane"
          id={FIELD_DETAIL_ID}
          role="region"
          tabIndex={-1}
          aria-labelledby={FIELD_DETAIL_NAME_ID}
        >
          {selected ? (
            <SchemaFieldDetail
              node={selected}
              rules={rules}
              sourceLine={sourceLine}
              onOpenField={onOpenField}
              onOpenRules={onOpenRules}
            />
          ) : (
            <div className="schema-detail-empty">
              <p id={FIELD_DETAIL_NAME_ID} className="schema-detail-empty-title">
                No field selected
              </p>
              <p className="schema-detail-empty-text">
                Nothing in the schema matches this search, so there is no field to describe. Clear
                the search to browse all {total} fields.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function SchemaFieldRow({
  node,
  selected,
  tabIndex,
  onSelect,
  onKeyDown,
}: {
  node: SchemaFieldNode;
  selected: boolean;
  tabIndex: number;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  // Selection comes from the native <button>: browsers synthesize a click from
  // Enter and Space, so no activation key is handled here. `onKeyDown` only
  // moves the roving cursor and never selects.
  return (
    <li className="schema-field-row">
      <button
        id={fieldRowId(node.path)}
        type="button"
        className={`schema-field-btn${selected ? ' selected' : ''}`}
        aria-current={selected ? 'true' : undefined}
        aria-controls={FIELD_DETAIL_ID}
        tabIndex={tabIndex}
        onClick={onSelect}
        onKeyDown={onKeyDown}
        style={{ paddingInlineStart: 8 + Math.min(node.depth, 5) * 12 }}
      >
        <ChevronRight className="schema-field-chevron" size={13} strokeWidth={2} aria-hidden="true" />
        <span className="schema-field-head">
          <span className="schema-field-name mono">{node.name}</span>
          <span className="schema-field-type mono">{node.typeLabel}</span>
          <RequirementBadge required={node.required} />
        </span>
      </button>
    </li>
  );
}

/** Required/Optional is carried by the TEXT itself — the tint is secondary only. */
function RequirementBadge({ required }: { required: boolean }) {
  return (
    <span
      className={`schema-field-badge ${required ? 'schema-field-badge-required' : 'schema-field-badge-optional'}`}
    >
      {required ? 'Required' : 'Optional'}
    </span>
  );
}

function SchemaFieldDetail({
  node,
  rules,
  sourceLine,
  onOpenField,
  onOpenRules,
}: {
  node: SchemaFieldNode;
  rules: SchemaRelationship[];
  sourceLine: string;
  onOpenField: (path: string) => void;
  onOpenRules: (path: string) => void;
}) {
  const parent = parentPath(node.path);
  // Two DISTINCT relations, never merged: rules whose clauses name this exact
  // path, and rules that name only something nested inside it. A rule on a
  // sibling subtree (or on an ancestor) is related to neither and is not shown.
  const naming = rulesNamingField(rules, node.path);
  const nested = rulesNestedUnderField(rules, node.path);
  const relatedCount = naming.length + nested.length;
  const children = node.children ?? [];

  return (
    <div className="schema-field-detail">
      <h3 id={FIELD_DETAIL_NAME_ID} className="schema-fielddetail-name mono">
        {node.name}
      </h3>
      <p className="schema-fielddetail-path mono">{node.path}</p>

      <p className="schema-fielddetail-meta">
        <span className="schema-field-type mono">{node.typeLabel}</span>
        <RequirementBadge required={node.required} />
        {node.format && <span className="schema-fielddetail-chip mono">format: {node.format}</span>}
      </p>

      {node.description ? (
        <p className="schema-field-desc">{node.description}</p>
      ) : (
        <p className="schema-fielddetail-nodesc">The schema declares no description for this field.</p>
      )}

      {parent && (
        <p className="schema-fielddetail-parent">
          <span className="schema-fielddetail-label">Nested in</span>
          <button type="button" className="schema-linkbtn mono" onClick={() => onOpenField(parent)}>
            {parent}
          </button>
        </p>
      )}

      {node.constValue !== undefined && (
        <div className="schema-fielddetail-section">
          <h4 className="schema-fielddetail-heading">Fixed value</h4>
          <p className="mono schema-fielddetail-value">{JSON.stringify(node.constValue)}</p>
        </div>
      )}

      {node.enumValues && node.enumValues.length > 0 && (
        <div className="schema-fielddetail-section">
          <h4 className="schema-fielddetail-heading">Allowed values ({node.enumValues.length})</h4>
          <ul className="schema-field-enum-list">
            {node.enumValues.map((value) => (
              <li key={String(value)} className="mono">
                {String(value)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {node.pattern && (
        <div className="schema-fielddetail-section">
          <h4 className="schema-fielddetail-heading">Pattern</h4>
          <p className="mono schema-fielddetail-pattern">{node.pattern}</p>
          <p className="schema-fielddetail-note">
            The schema constrains this field by regular expression and does not list its allowed
            values inline.
          </p>
        </div>
      )}

      {node.examples && node.examples.length > 0 && (
        <div className="schema-fielddetail-section">
          <h4 className="schema-fielddetail-heading">Examples ({node.examples.length})</h4>
          <ul className="schema-fielddetail-examples">
            {node.examples.map((example, i) => (
              // Examples are a fixed, ordered snapshot of one fetch and carry no
              // id of their own, so a positional key is stable here.
              // eslint-disable-next-line react/no-array-index-key
              <li key={i} className="mono">
                {typeof example === 'string' ? example : JSON.stringify(example)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {children.length > 0 && (
        <div className="schema-fielddetail-section">
          <h4 className="schema-fielddetail-heading">Nested fields ({children.length})</h4>
          <ul className="schema-fielddetail-children">
            {children.map((child) => (
              <li key={child.path}>
                <button
                  type="button"
                  className="schema-linkbtn mono"
                  onClick={() => onOpenField(child.path)}
                >
                  {child.name}
                </button>
                <span className="schema-field-type mono">{child.typeLabel}</span>
                <RequirementBadge required={child.required} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="schema-fielddetail-section">
        <h4 className="schema-fielddetail-heading">Related conditional rules ({relatedCount})</h4>
        {relatedCount === 0 ? (
          <p className="schema-fielddetail-note">
            No conditional rule in this schema names this field, or any field nested inside it.
          </p>
        ) : (
          <>
            {naming.length > 0 && (
              <>
                <h5 className="schema-fielddetail-subheading">
                  Rules that name this field ({naming.length})
                </h5>
                <ul className="schema-fielddetail-rules">
                  {naming.map((r) => (
                    <li key={r.id}>{formatRelationship(r)}</li>
                  ))}
                </ul>
              </>
            )}
            {nested.length > 0 && (
              <>
                <h5 className="schema-fielddetail-subheading">
                  Rules that constrain a field nested inside it ({nested.length})
                </h5>
                <ul className="schema-fielddetail-rules">
                  {nested.map((r) => (
                    <li key={r.id}>{formatRelationship(r)}</li>
                  ))}
                </ul>
              </>
            )}
            <button
              type="button"
              className="schema-linkbtn"
              onClick={() => onOpenRules(node.path)}
            >
              Open in Conditional Rules
            </button>
          </>
        )}
      </div>

      <p className="schema-fielddetail-source mono">{sourceLine}</p>
    </div>
  );
}

// --- Conditional Rules ------------------------------------------------------

function RulesView({
  rules,
  total,
  ordinals,
  query,
  onQuery,
  allFields,
  onOpenField,
}: {
  rules: SchemaRelationship[];
  total: number;
  /** Rule id → its 1-based place in the UNFILTERED list. */
  ordinals: Map<string, number>;
  query: string;
  onQuery: (next: string) => void;
  allFields: SchemaFieldNode[];
  onOpenField: (path: string) => void;
}) {
  const headingId = 'schema-rules-heading';
  return (
    <>
      <h3 id={headingId} className="schema-pane-heading">
        Conditional rules
        <span className="schema-pane-count mono">
          {rules.length === total ? `${total}` : `${rules.length} of ${total}`}
        </span>
      </h3>
      <p className="schema-browser-section-note">
        Requirements the schema itself encodes as JSON-Schema <code>allOf</code> if/then clauses —
        read here as a trigger condition and the consequence it forces. Nothing is inferred beyond
        what the schema states; each rule&rsquo;s exact source clause is available below it.
      </p>

      <SearchField
        id="schema-rules-search"
        label="Search rules"
        placeholder="Search by field path or value…"
        value={query}
        onChange={onQuery}
      />

      {total === 0 ? (
        <p className="schema-browser-empty">No conditional rules are declared in this schema.</p>
      ) : rules.length === 0 ? (
        <p className="schema-browser-empty">No rules match &ldquo;{query}&rdquo;.</p>
      ) : (
        <ul className="schema-rules-list" aria-labelledby={headingId}>
          {rules.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              index={ordinals.get(rule.id) ?? 0}
              allFields={allFields}
              onOpenField={onOpenField}
            />
          ))}
        </ul>
      )}
    </>
  );
}

function RuleCard({
  rule,
  index,
  allFields,
  onOpenField,
}: {
  rule: SchemaRelationship;
  index: number;
  allFields: SchemaFieldNode[];
  onOpenField: (path: string) => void;
}) {
  const triggers = relationshipTriggers(rule);
  const outcomes = relationshipOutcomes(rule);
  const paths = relationshipPaths(rule);

  return (
    <li className="schema-rule-card">
      <h4 className="schema-rule-heading">
        Rule {index}
        <span className="schema-rule-scope mono">{rule.scope}</span>
      </h4>
      <p className="schema-rule-sentence">{formatRelationship(rule)}</p>

      <div className="schema-rule-grid">
        <div className="schema-rule-cell">
          <h5 className="schema-rule-celltitle">Trigger condition</h5>
          <ul className="schema-rule-clauses">
            {triggers.map((t) => (
              <li key={t} className="mono">
                {t}
              </li>
            ))}
          </ul>
        </div>
        <div className="schema-rule-cell">
          <h5 className="schema-rule-celltitle">Required consequence</h5>
          <ul className="schema-rule-clauses">
            {outcomes.map((o) => (
              <li key={o} className="mono">
                {o}
              </li>
            ))}
          </ul>
        </div>
        <div className="schema-rule-cell">
          <h5 className="schema-rule-celltitle">Affected field paths</h5>
          <ul className="schema-rule-paths">
            {paths.map((p) => {
              const known = findFieldByPath(allFields, p);
              return (
                <li key={p}>
                  {known ? (
                    <button
                      type="button"
                      className="schema-linkbtn mono"
                      onClick={() => onOpenField(p)}
                    >
                      {p}
                    </button>
                  ) : (
                    <span className="mono">{p}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <details className="schema-rule-raw">
        <summary>Source rule (raw JSON Schema)</summary>
        <pre className="mono schema-rule-rawpre">{JSON.stringify(rule.raw, null, 2)}</pre>
      </details>
    </li>
  );
}

// --- Vocabulary -------------------------------------------------------------

function VocabularyView({
  files,
  query,
  onQuery,
  allFields,
  onOpenField,
}: {
  files: VocabularyFile[];
  query: string;
  onQuery: (next: string) => void;
  allFields: SchemaFieldNode[];
  onOpenField: (path: string) => void;
}) {
  const headingId = 'schema-vocab-heading';

  // FALLBACK branch — renders only when the deployment bundles no vocabulary
  // file. With the vendored `vocabulary/descriptor_class.json` present this is
  // never the observed state.
  if (files.length === 0) {
    return (
      <>
        <h3 id={headingId} className="schema-pane-heading">
          Controlled vocabulary
        </h3>
        <p className="schema-browser-empty">
          No controlled-vocabulary file is bundled with this deployment. The official schema remains
          the authority on allowed values — fields that enumerate their values inline show them under
          Fields &rarr; Allowed values.
        </p>
      </>
    );
  }

  return (
    <>
      <h3 id={headingId} className="schema-pane-heading">
        Controlled vocabulary
        <span className="schema-pane-count mono">
          {files.length === 1 ? '1 file' : `${files.length} files`}
        </span>
      </h3>
      <p className="schema-browser-section-note">
        Vocabulary files vendored alongside the schema, shown exactly as they are written — including
        each file&rsquo;s own provenance note. The official schema and the portal validator remain
        authoritative; a vocabulary file is an authoring aid, never a validation gate.
      </p>

      <SearchField
        id="schema-vocab-search"
        label="Search vocabulary"
        placeholder="Search by term or group…"
        value={query}
        onChange={onQuery}
      />

      <div className="schema-vocab-list">
        {files.map((file) => (
          <VocabularyFileCard
            key={file.name}
            file={file}
            query={query}
            allFields={allFields}
            onOpenField={onOpenField}
          />
        ))}
      </div>
    </>
  );
}

function VocabularyFileCard({
  file,
  query,
  allFields,
  onOpenField,
}: {
  file: VocabularyFile;
  query: string;
  allFields: SchemaFieldNode[];
  onOpenField: (path: string) => void;
}) {
  const slug = vocabularySourceSlug(file.source);
  const citing = fieldsCitingVocabulary(allFields, slug);
  const patternOnly = citationsArePatternOnly(citing);
  const visible = filterVocabularyNodes(file.nodes, query);

  return (
    <div className="schema-vocab-card">
      <h4 className="schema-vocab-name mono">
        {file.name}
        <span className="schema-pane-count mono">
          {file.entryCount === 1 ? '1 entry' : `${file.entryCount} entries`}
        </span>
      </h4>

      {file.field && (
        <p className="schema-vocab-field">
          <span className="schema-fielddetail-label">Vocabulary for</span>
          <span className="mono">{file.field}</span>
        </p>
      )}

      {file.raw !== undefined && (
        <pre className="schema-vocab-raw mono">{JSON.stringify(file.raw, null, 2)}</pre>
      )}

      {(file.note || file.source) && (
        <div className="schema-vocab-provenance">
          <h5 className="schema-vocab-group-label">Provenance</h5>
          {file.note && <p className="schema-vocab-note">{file.note}</p>}
          {file.source && (
            <p className="schema-vocab-source">
              Source: <span className="mono">{file.source}</span>
            </p>
          )}
        </div>
      )}

      {citing.length > 0 && (
        <div className="schema-vocab-link">
          <h5 className="schema-vocab-group-label">How the schema uses this</h5>
          <p className="schema-vocab-linktext">
            {citing.length === 1
              ? 'One schema field cites '
              : `${citing.length} schema fields cite `}
            <span className="mono">{slug}</span>
            {citing.length === 1 ? ' in its own description' : ' in their own descriptions'}
            {patternOnly
              ? ' and is constrained by a regular expression rather than an inline list of values — which is exactly the gap this file fills.'
              : '.'}
          </p>
          <ul className="schema-vocab-linklist">
            {citing.map((f) => (
              <li key={f.path}>
                <button
                  type="button"
                  className="schema-linkbtn mono"
                  onClick={() => onOpenField(f.path)}
                >
                  {f.path}
                </button>
                <span className="schema-vocab-linkchip">
                  {f.pattern && (!f.enumValues || f.enumValues.length === 0)
                    ? 'pattern-constrained, not enumerated inline'
                    : 'enumerated in the schema'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {file.nodes.length > 0 &&
        (visible.length === 0 ? (
          <p className="schema-browser-empty">No terms match &ldquo;{query}&rdquo;.</p>
        ) : (
          visible.map((node) => <VocabularyGroup key={node.path} node={node} level={5} />)
        ))}
    </div>
  );
}

/**
 * A group heading at the correct outline depth — a vocabulary file is an <h4>,
 * its top-level groups <h5>, and anything nested inside them <h6>. Written as
 * two explicit elements rather than a dynamic tag so the outline is greppable.
 */
function GroupHeading({
  level,
  children,
}: {
  level: 5 | 6;
  children: ReactNode;
}) {
  if (level === 5) return <h5 className="schema-vocab-group-label">{children}</h5>;
  return <h6 className="schema-vocab-group-label">{children}</h6>;
}

function VocabularyGroup({ node, level }: { node: VocabularyNode; level: 5 | 6 }) {
  if (node.kind === 'scalar') {
    return (
      <p className="schema-vocab-scalar">
        <span className="schema-vocab-group-label">{node.label}:</span>{' '}
        <span className="mono">{node.value}</span>
      </p>
    );
  }

  if (node.kind === 'terms') {
    return (
      <div className="schema-vocab-group">
        <GroupHeading level={level}>
          {node.label}
          <span className="schema-pane-count mono">{node.terms.length}</span>
        </GroupHeading>
        <ul className="schema-vocab-terms">
          {node.terms.map((term) => (
            <li key={term} className="schema-vocab-term mono">
              {term}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="schema-vocab-group">
      <GroupHeading level={level}>{node.label}</GroupHeading>
      {node.children.map((child) => (
        <VocabularyGroup key={child.path} node={child} level={6} />
      ))}
    </div>
  );
}
