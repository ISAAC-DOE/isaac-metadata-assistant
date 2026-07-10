/*
 * Route constants. Record sub-surfaces (S4/S5/S6) are nested under /record/:id
 * and are reachable only when the WorkflowSpine gate allows.
 */

export const ROUTES = {
  experiments: '/experiments',
  load: '/load',
  memory: '/memory',
  governance: '/governance',
  settings: '/settings',
  record: (id: string) => `/record/${id}`,
  complete: (id: string) => `/record/${id}/complete`,
  evidence: (id: string) => `/record/${id}/evidence`,
  export: (id: string) => `/record/${id}/export`,
} as const;

// Path patterns for the router definitions.
export const ROUTE_PATTERNS = {
  experiments: '/experiments',
  load: '/load',
  memory: '/memory',
  governance: '/governance',
  settings: '/settings',
  record: '/record/:id',
  complete: '/record/:id/complete',
  evidence: '/record/:id/evidence',
  export: '/record/:id/export',
} as const;
