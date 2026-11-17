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

const stage = (
  n: number,
  name_en: string,
  name_bg: string,
  default_probability: number,
  stage_type: 'open' | 'won' | 'lost',
): Schemas['StageOut'] => ({
  id: `01930000-0000-7000-8000-0000000005${String(n).padStart(2, '0')}`,
  name_en,
  name_bg,
  position: n,
  default_probability,
  stage_type,
  is_active: true,
})

export const STAGES = [
  stage(1, 'Prospecting', 'Проучване', 10, 'open'),
  stage(2, 'Qualification', 'Квалификация', 25, 'open'),
  stage(3, 'Solution & Proposal', 'Решение и оферта', 50, 'open'),
  stage(4, 'Negotiation', 'Преговори', 75, 'open'),
  stage(5, 'Closed Won', 'Спечелена', 100, 'won'),
  stage(6, 'Closed Lost', 'Загубена', 0, 'lost'),
] as const

export const PIPELINE: Schemas['PipelineOut'] = {
  id: '01930000-0000-7000-8000-000000000500',
  name: 'Sales pipeline',
  is_default: true,
  stages: [...STAGES],
}

export const summary = (s: Schemas['StageOut']): Schemas['StageSummary'] => ({
  id: s.id,
  name_en: s.name_en,
  name_bg: s.name_bg,
  stage_type: s.stage_type,
  position: s.position,
  default_probability: s.default_probability,
})

export const OPPORTUNITY: Schemas['OpportunityOut'] = {
  id: '01930000-0000-7000-8000-0000000000e1',
  name: 'Branch connectivity',
  organization: { id: ORG.id, name: ORG.name },
  primary_contact: null,
  owner: { id: REP_ME.id, full_name: REP_ME.full_name },
  pipeline_id: PIPELINE.id,
  stage: summary(STAGES[1]),
  amount: '48000.00',
  currency: 'EUR',
  probability: 25,
  probability_overridden: false,
  weighted_amount: '12000.00',
  expected_close_date: '2027-02-28',
  actual_close_date: null,
  next_step: 'Send the offer',
  description: null,
  source_lead: null,
  loss_reason: null,
  competitor: null,
  is_stale: false,
  last_activity_at: null,
  created_at: '2026-11-17T08:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
  created_by: { id: REP_ME.id, full_name: REP_ME.full_name },
  archived_at: null,
  version: 2,
}

export const LOSS_REASON: Schemas['ReferenceItem'] = {
  id: '01930000-0000-7000-8000-0000000000f1',
  code: 'price',
  name_en: 'Price',
  name_bg: 'Цена',
  position: 1,
  is_active: true,
}

export function opportunityLists() {
  server.use(
    http.get('*/api/v1/pipelines', () => HttpResponse.json([PIPELINE])),
    http.get('*/api/v1/reference/loss-reasons', () => HttpResponse.json([LOSS_REASON])),
  )
}
