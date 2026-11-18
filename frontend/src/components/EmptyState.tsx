import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/** UX-04: what a list or section shows when it has nothing: an icon, a message, an optional action. */
export function EmptyState({
  message,
  action,
}: {
  message?: string | undefined
  action?: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center text-muted-foreground">
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M22 12h-6l-2 3h-4l-2-3H2" />
        <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      </svg>
      <p className="text-sm">{message ?? t('states.empty')}</p>
      {action}
    </div>
  )
}
