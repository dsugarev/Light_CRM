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
  permissions: [
    'audit.read',
    'data.export',
    'data.import',
    'records.create',
    'records.edit_any',
    'records.edit_own',
    'records.reassign',
    'records.read',
    'records.restore',
    'settings.manage',
    'users.manage',
  ],
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

export const TELECOM: Schemas['ReferenceItem'] = {
  id: '01930000-0000-7000-8000-0000000000a1',
  code: 'telecommunications',
  name_en: 'Telecommunications',
  name_bg: 'Телекомуникации',
  position: 1,
  is_active: true,
}

export const ORG: Schemas['OrganizationOut'] = {
  id: '01930000-0000-7000-8000-0000000000b1',
  name: 'Акме ЕООД',
  registration_number: '123456786',
  vat_number: 'BG123456786',
  industry: {
    id: TELECOM.id,
    code: TELECOM.code,
    name_en: TELECOM.name_en,
    name_bg: TELECOM.name_bg,
  },
  size_band: '10-49',
  website: 'https://acme.example',
  address_line: 'бул. Витоша 1',
  postal_code: '1000',
  city: 'София',
  country: 'BG',
  owner: { id: REP_ME.id, full_name: REP_ME.full_name },
  notes: null,
  created_at: '2026-11-17T08:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
  created_by: { id: REP_ME.id, full_name: REP_ME.full_name },
  archived_at: null,
  warnings: [],
}

export const CONTACT: Schemas['ContactOut'] = {
  id: '01930000-0000-7000-8000-0000000000c1',
  first_name: 'Мария',
  last_name: 'Иванова',
  full_name: 'Мария Иванова',
  job_title: 'CTO',
  email: 'maria@example.test',
  phone: '+359 2 000 0000',
  preferred_locale: 'bg',
  organization: { id: ORG.id, name: ORG.name },
  owner: { id: REP_ME.id, full_name: REP_ME.full_name },
  notes: null,
  created_at: '2026-11-17T08:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
  created_by: { id: REP_ME.id, full_name: REP_ME.full_name },
  archived_at: null,
  anonymized_at: null,
}

export const page = <T>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25 })

export function referenceLists() {
  server.use(http.get('*/api/v1/reference/industries', () => HttpResponse.json([TELECOM])))
}

export const LEAD: Schemas['LeadOut'] = {
  id: '01930000-0000-7000-8000-0000000000d1',
  title: 'Fibre for 3 branches',
  company_name: 'Акме ЕООД',
  contact_name: 'Мария Иванова',
  email: 'maria@example.test',
  phone: null,
  source: {
    id: 'src-1',
    code: 'inbound',
    name_en: 'Inbound inquiry',
    name_bg: 'Входящо запитване',
  },
  status: 'contacted',
  description: null,
  estimated_value: '48000.00',
  currency: 'EUR',
  owner: { id: REP_ME.id, full_name: REP_ME.full_name },
  qualification: {
    budget: { status: 'yes', note: 'Approved' },
    authority: { status: 'partial', note: '' },
    need: { status: 'yes', note: '' },
    timeline: { status: 'unknown', note: '' },
    fits_target_profile: true,
    score: 63,
  },
  organization: null,
  contact: null,
  converted_opportunity: null,
  converted_at: null,
  disqualification: null,
  created_at: '2026-11-17T08:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
  created_by: { id: REP_ME.id, full_name: REP_ME.full_name },
  archived_at: null,
  version: 3,
}

export function leadLists() {
  server.use(
    http.get('*/api/v1/reference/lead-sources', () =>
      HttpResponse.json([
        {
          id: 'src-1',
          code: 'inbound',
          name_en: 'Inbound inquiry',
          name_bg: 'Входящо запитване',
          position: 1,
          is_active: true,
        },
      ]),
    ),
    http.get('*/api/v1/reference/disqualification-reasons', () =>
      HttpResponse.json([
        {
          id: 'r-1',
          code: 'no_budget',
          name_en: 'No budget',
          name_bg: 'Няма бюджет',
          position: 1,
          is_active: true,
        },
      ]),
    ),
  )
}
