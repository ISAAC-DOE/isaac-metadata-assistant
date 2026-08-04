import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tokens.css';
import './styles/base.css';
import App from './App';
import { resumeTutorialSession } from './lib/tutorialController';

/*
 * Bounded recovery for a walkthrough interrupted by a reload.
 *
 * Deliberately NOT awaited, and deliberately here rather than inside `App`:
 *
 * - not awaited, because `api.ts` has already entered the persisted scope at
 *   module load, so record fetches resolve correctly from the first paint. This
 *   call only decides whether to re-open the overlay and whether the session is
 *   still real; blocking the first render on a network round-trip to learn that
 *   would trade a correct paint for a slower one.
 * - not in `App`, because tests mount `AppRoutes` directly and must not each
 *   acquire a background session probe as a side effect of rendering a screen.
 *   `main.tsx` is the real entry point and never runs under vitest.
 */
void resumeTutorialSession();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
