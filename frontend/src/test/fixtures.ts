import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'

import { server } from './server'

// Fictional people only (no real customer data).
export const ADMIN_ME: Schemas['Me'] = {
  principal_type: 'user',
  id: '01930000-0000-7000-8000-000000000001',
  email: 'ada.admin@example.test',
  full_name: 'Ada Admin',
  role: 'admin',
  locale: 'en',
  permissions: ['audit.read', 'records.read', 'settings.manage', 'users.manage'],
}

export const REP_ME: Schemas['Me'] = {
  ...ADMIN_ME,
  id: '01930000-0000-7000-8000-000000000002',
  email: 'boris.rep@example.test',
  full_name: 'Boris Rep',
  role: 'sales_rep',
  permissions: ['records.create', 'records.edit_own', 'records.read'],
}

export const USER: Schemas['UserOut'] = {
  id: '01930000-0000-7000-8000-000000000003',
  email: 'vera.viewer@example.test',
  full_name: 'Vera Viewer',
  role: 'viewer',
  locale: 'bg',
  user_type: 'human',
  is_active: true,
  is_locked: false,
  locked_until: null,
  last_login_at: '2026-11-17T07:30:00Z',
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

export function signedInAs(me: Schemas['Me']) {
  server.use(http.get('*/api/v1/me', () => HttpResponse.json(me)))
}
