import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router'

import { useCan } from '@/lib/permissions'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-1.5 text-sm ${
    isActive ? 'bg-secondary font-medium text-secondary-foreground' : 'hover:bg-muted'
  }`

interface Item {
  to: string
  label: string
  end?: boolean
  badge?: number
  badgeLabel?: string
}

/** UX-02: navigation grouped by area; only routes the user may open are listed. */
export function AppNav({
  webhookProblems,
  onNavigate,
}: {
  webhookProblems: number
  onNavigate?: (() => void) | undefined
}) {
  const { t } = useTranslation()
  const can = useCan()
  const idPrefix = useId()
  const sales: Item[] = [
    { to: '/', label: t('nav.home'), end: true },
    { to: '/organizations', label: t('nav.organizations') },
    { to: '/contacts', label: t('nav.contacts') },
    { to: '/leads', label: t('nav.leads') },
    { to: '/opportunities', label: t('nav.opportunities'), end: true },
    { to: '/opportunities/board', label: t('nav.board') },
    { to: '/tasks', label: t('nav.tasks') },
    { to: '/reports/win-loss', label: t('nav.reports') },
  ]
  const admin: Item[] = [
    ...(can('users.manage') ? [{ to: '/admin/users', label: t('nav.users') }] : []),
    ...(can('data.import') ? [{ to: '/admin/imports', label: t('nav.imports') }] : []),
    ...(can('users.manage')
      ? [
          {
            to: '/admin/integrations',
            label: t('nav.integrations'),
            badge: webhookProblems,
            badgeLabel: t('nav.failingDeliveries', { count: webhookProblems }),
          },
        ]
      : []),
    ...(can('audit.read') ? [{ to: '/admin/audit-log', label: t('nav.auditLog') }] : []),
    ...(can('settings.manage')
      ? [
          { to: '/admin/settings', label: t('nav.settings') },
          { to: '/admin/reference/industries', label: t('nav.reference') },
          { to: '/admin/stages', label: t('nav.stages') },
        ]
      : []),
  ]
  const groups = [
    { key: 'sales', title: t('nav.groupSales'), items: sales },
    { key: 'admin', title: t('nav.groupAdmin'), items: admin },
  ].filter((group) => group.items.length > 0)

  return (
    <nav aria-label={t('nav.label')} className="flex flex-col gap-4">
      {groups.map((group) => (
        <div key={group.key}>
          <p
            id={`${idPrefix}-${group.key}`}
            className="px-3 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase"
          >
            {group.title}
          </p>
          <ul aria-labelledby={`${idPrefix}-${group.key}`} className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end ?? false}
                  className={linkClass}
                  onClick={onNavigate}
                >
                  {item.label}
                  {item.badge ? (
                    <span
                      className="ml-1 rounded-full bg-destructive px-1.5 text-xs text-destructive-foreground"
                      aria-label={item.badgeLabel}
                    >
                      {item.badge}
                    </span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}
