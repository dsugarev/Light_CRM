import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { EmptyState } from '@/components/EmptyState'
import { Button, buttonVariants } from '@/components/ui/button'

/**
 * An empty list that says what to do next (CRM best practice): when filters hide every
 * record, offer to clear them; when there is nothing yet, offer to create the first one.
 */
export function ListEmptyState({
  filtered,
  onClear,
  create,
}: {
  filtered: boolean
  onClear: () => void
  /** The create action, when the user may create (omit otherwise). */
  create?: { to: string; label: string } | undefined
}) {
  const { t } = useTranslation()
  if (filtered) {
    return (
      <EmptyState
        message={t('states.noMatches')}
        action={
          <Button type="button" variant="outline" size="sm" onClick={onClear}>
            {t('states.clearFilters')}
          </Button>
        }
      />
    )
  }
  return (
    <EmptyState
      message={t('states.noRecords')}
      action={
        create ? (
          <Link to={create.to} className={buttonVariants({ size: 'sm' })}>
            {create.label}
          </Link>
        ) : undefined
      }
    />
  )
}
