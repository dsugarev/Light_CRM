import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export interface Crumb {
  label: string
  to: string
}

interface PageHeaderProps {
  title: string
  /** One line under the title saying what the page is for. */
  description?: string | undefined
  /** The pages above this one, outermost first; the current page is added from the title. */
  breadcrumbs?: Crumb[] | undefined
  /** Buttons, badges or links shown at the end of the title row. */
  actions?: ReactNode
}

/** UX-03: the one header every page uses: breadcrumbs, title, description and actions. */
export function PageHeader({ title, description, breadcrumbs, actions }: PageHeaderProps) {
  const { t } = useTranslation()
  return (
    <header className="mb-6 flex flex-col gap-2">
      {breadcrumbs?.length ? (
        <nav aria-label={t('breadcrumbs.label')}>
          <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
            {breadcrumbs.map((crumb) => (
              <li key={crumb.to} className="flex items-center gap-1.5">
                <Link to={crumb.to} className="hover:text-foreground hover:underline">
                  {crumb.label}
                </Link>
                <span aria-hidden="true">/</span>
              </li>
            ))}
            <li aria-current="page" className="min-w-0 truncate text-foreground">
              {title}
            </li>
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-semibold break-words">{title}</h1>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions}
      </div>
    </header>
  )
}
