import './chrome.css';
import { Link } from 'react-router-dom';
import { LayoutList, Network, ShieldCheck, Settings } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import type { LucideIcon } from './icons';

export type NavKey = 'experiments' | 'memory' | 'governance' | 'settings';

const ITEMS: { key: NavKey; label: string; icon: LucideIcon; to: string }[] = [
  { key: 'experiments', label: LABELS.navExperiments, icon: LayoutList, to: ROUTES.experiments },
  { key: 'memory', label: LABELS.navMemory, icon: Network, to: ROUTES.memory },
  { key: 'governance', label: LABELS.navGovernance, icon: ShieldCheck, to: ROUTES.governance },
  { key: 'settings', label: LABELS.navSettings, icon: Settings, to: ROUTES.settings },
];

interface LeftNavProps {
  active: NavKey;
}

/**
 * Top-level destinations. Project Memory is a deliberately separate destination
 * — never blended into the experiment queue. Active item = tint + weight + label
 * color (no colored rail).
 */
export function LeftNav({ active }: LeftNavProps) {
  return (
    <nav className="leftnav" aria-label="Primary">
      {ITEMS.map(({ key, label, icon: Icon, to }) => {
        const isActive = key === active;
        return (
          <Link
            key={key}
            to={to}
            className={`nav-item${isActive ? ' active' : ''}`}
            aria-current={isActive ? 'page' : undefined}
          >
            <Icon size={16} strokeWidth={2} aria-hidden="true" />
            {label}
          </Link>
        );
      })}

      <div className="nav-footer">
        <span className="nav-version">{LABELS.version}</span>
      </div>
    </nav>
  );
}
