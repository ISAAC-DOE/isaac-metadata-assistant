import './fields.css';
import { useId } from 'react';
import { ChevronDown, ChevronRight } from './icons';
import { HelpTip } from './HelpTip';
import { SemanticStatus } from './SemanticStatus';
import { FieldRow } from './FieldRow';
import { fieldGroupStatus } from '../lib/adapt';
import type { FieldGroupData } from '../lib/types';

interface FieldGroupProps {
  group: FieldGroupData;
  expanded: boolean;
  onToggle: () => void;
  /**
   * Passed straight to every `FieldRow`. Absent means every row in this group is
   * read-only — see `FieldRow`'s own prop note on why the capability is the caller's
   * to grant rather than the row's to assume.
   */
  capture?: {
    experimentId: string;
    version: string;
    onSaved: () => void;
  };
}

/**
 * A record block (system / sample / measurement / assets / descriptors) as a
 * card. Collapsed blocker groups show only the header + an amber "N Needs You"
 * chip, so the draft never turns into a wall of errors. No rail marks a blocker
 * group — the amber chip + summary carry it.
 *
 * THE COLLAPSED HEADER STILL CANNOT HIDE A BLOCKER, and the group skeleton did not
 * change that. `needsYouCount` counts `needs_confirmation` rows, and a skeleton row —
 * a field path the record has no value at — is `missing`, not a blocker: a record's
 * blocking questions are its series, QC verdict, descriptors and assets, none of which
 * is a field row. What DID have to move is the summary beside the chip, because
 * `adapt.summarize` computed `all verified` from a status set that a section of nothing
 * but `missing` rows satisfies vacuously — it now leads with how many of the section's
 * fields are recorded. See its header for the measurement.
 *
 * `data-draft-block` MARKS THIS AS A DRAFT SECTION AND NOT ONE OF THE RECORD SCREEN'S
 * OTHER `.field-group` CARDS. `RenameExperimentPanel`, `RecordInfoPanel` and
 * `RecordLinksPanel` deliberately reuse this component's shell down to the class names,
 * so `.fg-header` alone cannot address the four draft sections. `e2e/helpers/disclosures`
 * opens exactly these before axe scans, which is what stops the group bodies — and every
 * control this slice put inside them — from being silently exempt from every scan at
 * every viewport. It is the same reason the Statistics prose disclosures carry a class of
 * their own rather than borrowing `details.stats-technical`.
 */
export function FieldGroup({
  group,
  expanded,
  onToggle,
  capture,
}: FieldGroupProps) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  /* `aria-controls` completes `RunCard`'s accordion shape. It is set only WHILE
     EXPANDED, the discipline `RenameExperimentPanel` and `RecordInfoPanel`
     already follow here: this body is rendered conditionally, so pointing at its
     id while collapsed would name an element that does not exist. */
  const bodyId = useId();
  const titleId = useId();
  const status = fieldGroupStatus(group.fields, group.needsYouCount);
  const total = group.fields.length;
  return (
    <section
      className="field-group"
      data-draft-block={group.block}
      /* The human heading only (owner QA F1). The official block key used to be in
         the region's name too, so a screen reader announced "System & Instrument
         (system)"; it is one `?` away now, beside the header. */
      aria-label={group.humanLabel}
    >
      {/*
        A REAL HEADING LANDMARK, closing a MEASURED accessibility gap rather than a
        stylistic one. This toggle was a bare `button.fg-header` with no heading
        ancestor, so a screen-reader user navigating by heading (the "H" quick-nav
        key) walked straight past it — and past every one of the record's actual
        scientific field groups, which is half the page's content. Measured on the
        rendered DOM: 8 of the record screen's 22 content sections had no
        heading-level landmark while the other 14 did.

        `h2 > button[aria-expanded]` is `RunCard`'s own documented accordion shape,
        at the level its peers use: on the Record Fields workspace every section is
        a peer of these, so `h2` under the screen's single `h1` keeps the outline
        contiguous — an `h3` here would skip a level, because this workspace holds
        no `h2` above it.

        The `<h2>` is a transparent wrapper (`.fg-heading` resets margin and type),
        so nothing about the header's appearance changes.
      */}
      {/*
        THE HEADER ROW (owner QA F1/F2, 2026-09-22): the human heading, then a
        count and ONE status — `fieldGroupStatus`, computed from the rows below —
        where a lowercase block key and a prose tail used to be. The block key is
        in the `?` BESIDE the toggle, never inside it: a button inside a button is
        invalid, and inside the `h2` its name would join the heading's. The tip is
        named generically and described by the heading, so two sections never
        offer two controls with one name.
      */}
      <div className="fg-headrow">
        <h2 className="fg-heading">
          <button
            type="button"
            className="fg-header"
            aria-expanded={expanded}
            aria-controls={expanded ? bodyId : undefined}
            onClick={onToggle}
          >
            <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
            <span className="fg-block" id={titleId}>
              {group.humanLabel}
            </span>
            <span className="fg-summary fg-status-group">
              <span className="fg-count">
                {total} field{total === 1 ? '' : 's'}
              </span>
              <SemanticStatus state={status.state} label={status.label} size="sm" />
            </span>
          </button>
        </h2>
        <HelpTip subject={group.humanLabel} label="Official Block Details" describedBy={titleId}>
          <span>
            Official block: <code>{group.block}</code>
          </span>
          <span>Each field inside names its own official path in its own details.</span>
        </HelpTip>
      </div>

      {expanded && (
        <div className="fg-body" id={bodyId}>
          {group.fields.map((field) => (
            <FieldRow key={field.path} field={field} capture={capture} />
          ))}
        </div>
      )}
    </section>
  );
}
