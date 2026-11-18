import { useTranslation } from 'react-i18next'

import type { Crumb } from './PageHeader'

const SECTIONS = {
  organizations: '/organizations',
  contacts: '/contacts',
  leads: '/leads',
  opportunities: '/opportunities',
  users: '/admin/users',
  imports: '/admin/imports',
  integrations: '/admin/integrations',
  auditLog: '/admin/audit-log',
} as const

/** UX-03: breadcrumbs for the list pages in the navigation, labelled as the menu labels them. */
export function useSectionCrumbs(): Record<keyof typeof SECTIONS, Crumb> {
  const { t } = useTranslation()
  const entries = Object.entries(SECTIONS) as [keyof typeof SECTIONS, string][]
  return Object.fromEntries(
    entries.map(([key, to]) => [key, { label: t(`nav.${key}`), to }]),
  ) as Record<keyof typeof SECTIONS, Crumb>
}
