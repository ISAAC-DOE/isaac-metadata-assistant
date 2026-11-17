import './technical-details.css';
import type { ReactNode } from 'react';
import { Disclosure } from './Disclosure';
import { describeSchemaMessage } from '../lib/plainSchemaMessage';

/**
 * A QUIET "Details" ROW for technical text — a validator's exact message, a code, an
 * id, a timestamp in ISO form (2026-11-17, plain-language pass).
 *
 * It is the shared `Disclosure` (closed by default, content `hidden` but still in the
 * DOM, so every guard that reads the DOM still finds the exact text), styled small and
 * borderless so a list of findings does not turn into a list of boxes. Never put a
 * blocking error, a required action or anything a reader must see inside one (DEC-35):
 * the plain line it follows says what matters.
 */
export function TechnicalDetails({
  children,
  summary = 'Details',
}: {
  children: ReactNode;
  summary?: ReactNode;
}) {
  return (
    <Disclosure className="technical-details" summary={summary}>
      {children}
    </Disclosure>
  );
}

/**
 * A validator message, plain line first; the exact text behind Details when the plain
 * line is not the message itself.
 */
export function SchemaMessage({
  message,
  path,
  className,
}: {
  message: string;
  path?: string;
  className?: string;
}) {
  const view = describeSchemaMessage(message, path);
  return (
    <>
      <span className={className}>{view.plain}</span>
      {view.raw !== null && (
        <TechnicalDetails>
          <span className="technical-details-raw">
            The check&rsquo;s exact words: <code className="mono">{view.raw}</code>
          </span>
        </TechnicalDetails>
      )}
    </>
  );
}
