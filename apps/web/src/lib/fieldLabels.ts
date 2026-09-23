/**
 * ONE NAME FOR A FIELD PATH, EVERYWHERE A SCIENTIST SEES IT (review #277, I-5/I-9).
 *
 * The run-level fields use their own labels (`RUN_FIELDS`, "Temperature (K)"); every
 * other path uses `fieldPathLabel`'s presentation. Moved out of `BlockerItems` so the
 * proposal cards, their accessible names, the live announcements, the unmapped
 * notes and the e2e helpers all resolve a path through ONE function — a card named
 * one way on screen and another way to a screen reader was the defect.
 *
 * `null` for the whole-document sentinel (`$`, or an empty path): it names no field,
 * so nothing is said about one (DEC-30).
 */
import { fieldPathLabel } from './recordMap';
import { RUN_FIELDS } from './runFields';

const RUN_FIELD_LABEL = new Map(RUN_FIELDS.map((spec) => [spec.path, spec.label]));

/**
 * The OFFICIAL path a finding's `path` names. Two prefixes are namespaces, not part of
 * the path: `$.` (a JSON-path root some reports keep) and `fields.` (the draft
 * envelope map, whose keys ARE official paths — `draft_validator` files a finding at
 * `fields.<path>`). Anything else is returned as given.
 */
export function officialPathOf(path: string): string {
  return path.trim().replace(/^\$\./, '').replace(/^fields\./, '');
}

export function fieldLabel(path: string): string | null {
  const trimmed = officialPathOf(path);
  if (trimmed === '' || trimmed === '$') return null;
  return RUN_FIELD_LABEL.get(trimmed) ?? fieldPathLabel(trimmed);
}

/** Whether `path` is one of the five run-level fields the Runs editor has an input for. */
export function isRunFieldPath(path: string): boolean {
  return RUN_FIELD_LABEL.has(officialPathOf(path));
}
