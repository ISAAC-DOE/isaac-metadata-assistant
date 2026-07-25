import './schema-browser.css';
import { useMemo, useState } from 'react';
import { LoadingPanel, BackendDown } from './FetchStates';
import { LayoutList, Search } from './icons';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  buildSchemaFieldTree,
  extractRelationships,
  filterFieldTree,
  formatRelationship,
  type SchemaFieldNode,
  type SchemaRelationship,
} from '../lib/schemaBrowser';
import type { ApiSchemaResponse } from '../lib/types';

/**
 * P36.6 — the Schema & Vocabulary browser (Governance & Safety > "Schema &
 * Vocabulary" tab).
 *
 * A READ-ONLY reference view over the canonical official ISAAC schema and
 * controlled vocabulary, fetched from `GET /api/schema`. Every field, type,
 * required/optional flag, allowed value, description, and relationship shown
 * here is read verbatim from that response — nothing is computed, summarized,
 * or invented client-side beyond deterministic tree-building and substring
 * search (see `lib/schemaBrowser.ts`).
 *
 * This is explicitly NOT the portal Ontology system: there is no
 * propose/review/approve/edit/role/persistence affordance anywhere in this
 * component.
 */
export function SchemaBrowser() {
  const fetchState = useFetch(() => api.getSchema(), []);

  return (
    <section className="schema-browser card" aria-labelledby="schema-browser-heading">
      <header className="schema-browser-head">
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="schema-browser-icon" />
        <div>
          <h2 id="schema-browser-heading">Schema &amp; Vocabulary</h2>
          <p className="schema-browser-sub">
            A read-only browser of the canonical official ISAAC schema and controlled vocabulary —
            every field, type, requirement, allowed value, and relationship below is read verbatim
            from the vendored schema and vocabulary files. This is a reference view, not the portal
            Ontology system: there is nothing to propose, review, approve, or edit here.
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

function SchemaBrowserBody({ data }: { data: ApiSchemaResponse }) {
  const [query, setQuery] = useState('');
  const tree = useMemo(() => buildSchemaFieldTree(data.schema), [data.schema]);
  const relationships = useMemo(() => extractRelationships(data.schema), [data.schema]);
  const visibleFields = useMemo(() => filterFieldTree(tree, query), [tree, query]);
  const isFiltered = query.trim().length > 0;
  const vocabNames = Object.keys(data.vocabularies ?? {});

  return (
    <>
      <p className="schema-browser-source-line mono">
        {data.schema_title ?? 'ISAAC official schema'} — v{data.schema_version} — vendored official
        schema (read-only reference)
      </p>

      <div className="schema-browser-search-row">
        <label htmlFor="schema-browser-search" className="schema-browser-search-label">
          <Search size={14} strokeWidth={2} aria-hidden="true" />
          Search fields
        </label>
        <input
          id="schema-browser-search"
          type="search"
          className="schema-browser-search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by field name, path, or description…"
        />
      </div>

      <section aria-labelledby="schema-fields-heading" className="schema-browser-section">
        <h3 id="schema-fields-heading">Fields</h3>
        {visibleFields.length === 0 ? (
          <p className="schema-browser-empty">No fields match &ldquo;{query}&rdquo;.</p>
        ) : (
          <ul className="schema-field-tree">
            {visibleFields.map((node) => (
              <SchemaFieldRow key={node.path} node={node} flat={isFiltered} />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="schema-relationships-heading" className="schema-browser-section">
        <h3 id="schema-relationships-heading">Relationships</h3>
        <p className="schema-browser-section-note">
          Conditional requirements the schema itself encodes (JSON-Schema <code>allOf</code> if/then
          rules) — nothing here is inferred beyond what the schema states.
        </p>
        <SchemaRelationshipsList relationships={relationships} />
      </section>

      <section aria-labelledby="schema-vocab-heading" className="schema-browser-section">
        <h3 id="schema-vocab-heading">Vocabulary</h3>
        {vocabNames.length === 0 ? (
          <p className="schema-browser-empty">No vocabulary files are present.</p>
        ) : (
          <div className="schema-vocab-list">
            {vocabNames.map((name) => (
              <VocabularyCard key={name} name={name} data={data.vocabularies[name]} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

// --- field rows ------------------------------------------------------------

function SchemaFieldRow({ node, flat = false }: { node: SchemaFieldNode; flat?: boolean }) {
  const hasChildren = !flat && !!node.children && node.children.length > 0;
  const header = (
    <span className="schema-field-head">
      <span className="schema-field-name mono">{node.name}</span>
      <span className="schema-field-type mono">{node.typeLabel}</span>
      <span
        className={`schema-field-badge ${node.required ? 'schema-field-badge-required' : 'schema-field-badge-optional'}`}
      >
        {node.required ? 'Required' : 'Optional'}
      </span>
    </span>
  );

  if (!hasChildren) {
    return (
      <li className="schema-field-row">
        <div className="schema-field-leaf">
          {header}
          <SchemaFieldBody node={node} />
        </div>
      </li>
    );
  }

  return (
    <li className="schema-field-row">
      <details>
        <summary>{header}</summary>
        <SchemaFieldBody node={node} />
        <ul className="schema-field-children">
          {node.children!.map((child) => (
            <SchemaFieldRow key={child.path} node={child} />
          ))}
        </ul>
      </details>
    </li>
  );
}

function SchemaFieldBody({ node }: { node: SchemaFieldNode }) {
  return (
    <div className="schema-field-body">
      <p className="schema-field-path mono">{node.path}</p>
      {node.description && <p className="schema-field-desc">{node.description}</p>}
      {node.enumValues && node.enumValues.length > 0 && (
        <div className="schema-field-enum">
          <span className="schema-field-enum-label">Allowed values ({node.enumValues.length})</span>
          <ul className="schema-field-enum-list">
            {node.enumValues.map((value) => (
              <li key={String(value)} className="mono">
                {String(value)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --- relationships -----------------------------------------------------

function SchemaRelationshipsList({ relationships }: { relationships: SchemaRelationship[] }) {
  if (relationships.length === 0) {
    return <p className="schema-browser-empty">No conditional relationships are declared in this schema.</p>;
  }
  return (
    <ul className="schema-relationships-list">
      {relationships.map((r, i) => (
        // Relationships have no stable id of their own; the list is a fixed,
        // deterministic snapshot of one fetch, so a positional key is safe.
        // eslint-disable-next-line react/no-array-index-key
        <li key={i} className="schema-relationship-row">
          <p className="schema-relationship-scope mono">{r.scope}</p>
          <p className="schema-relationship-text">{formatRelationship(r)}</p>
        </li>
      ))}
    </ul>
  );
}

// --- vocabulary ----------------------------------------------------------

function VocabularyCard({ name, data }: { name: string; data: unknown }) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return (
      <div className="schema-vocab-card">
        <h4 className="schema-vocab-name mono">{name}</h4>
        <pre className="schema-vocab-raw mono">{JSON.stringify(data, null, 2)}</pre>
      </div>
    );
  }
  const obj = data as Record<string, unknown>;
  return (
    <div className="schema-vocab-card">
      <h4 className="schema-vocab-name mono">{name}</h4>
      {typeof obj.note === 'string' && <p className="schema-vocab-note">{obj.note}</p>}
      {typeof obj.source === 'string' && (
        <p className="schema-vocab-source">
          Source: <span className="mono">{obj.source}</span>
        </p>
      )}
      {Object.entries(obj).map(([key, value]) => {
        if (key === 'note' || key === 'source' || key === 'field') return null;
        return <VocabularyGroup key={key} label={key} value={value} />;
      })}
    </div>
  );
}

function VocabularyGroup({ label, value }: { label: string; value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <div className="schema-vocab-group">
        <h5 className="schema-vocab-group-label">{label}</h5>
        <ul className="schema-vocab-terms">
          {value.map((term) => (
            <li key={String(term)} className="schema-vocab-term mono">
              {String(term)}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (value && typeof value === 'object') {
    return (
      <div className="schema-vocab-group">
        <h5 className="schema-vocab-group-label">{label}</h5>
        {Object.entries(value as Record<string, unknown>).map(([subKey, subValue]) => (
          <VocabularyGroup key={subKey} label={subKey} value={subValue} />
        ))}
      </div>
    );
  }
  return (
    <p className="schema-vocab-scalar">
      <span className="schema-vocab-group-label">{label}:</span> <span className="mono">{String(value)}</span>
    </p>
  );
}
