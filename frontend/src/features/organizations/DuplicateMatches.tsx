import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Schemas } from '@/api/client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

type Match = Schemas['Match']

/** FR-PARTY-01 AC1: possible duplicates, each linking to the existing record. */
export function DuplicateMatches({
  matches,
  kind,
  children,
}: {
  matches: Match[]
  kind: 'organization' | 'contact'
  children?: React.ReactNode
}) {
  const { t } = useTranslation('party')
  if (matches.length === 0) return null
  const base = kind === 'organization' ? '/organizations' : '/contacts'
  return (
    <Alert role="status" data-testid="duplicate-matches">
      <AlertTitle>{t('duplicates.title')}</AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
        <span>
          {kind === 'organization' ? t('duplicates.explain') : t('duplicates.contactExplain')}
        </span>
        <ul className="list-disc pl-5">
          {matches.map((match) => (
            <li key={match.id}>
              <Link
                to={`${base}/${match.id}`}
                className="font-medium text-primary underline underline-offset-4"
              >
                {match.name}
              </Link>{' '}
              <span className="text-muted-foreground">
                ({t(`duplicates.reason.${match.reason}`)}
                {match.registration_number ? `, ${match.registration_number}` : ''}
                {match.city ? `, ${match.city}` : ''}
                {match.archived ? `, ${t('duplicates.archived')}` : ''})
              </span>
            </li>
          ))}
        </ul>
        {children}
      </AlertDescription>
    </Alert>
  )
}
