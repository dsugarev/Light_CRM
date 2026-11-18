import { useTranslation } from 'react-i18next'

import { Skeleton } from '@/components/ui/skeleton'

type Variant = 'page' | 'table' | 'form'

const ROWS = [0, 1, 2, 3, 4]

/**
 * UX-04: placeholder shapes while data loads, announced to screen readers once.
 * `table` for lists, `form` for editors, `page` for record pages and sections.
 */
export function Loading({ variant = 'page' }: { variant?: Variant }) {
  const { t } = useTranslation()
  return (
    <div role="status" aria-label={t('states.loading')} className="flex flex-col gap-3 py-2">
      {variant === 'table' ? (
        <>
          <Skeleton className="h-8 w-full" />
          {ROWS.map((row) => (
            <Skeleton key={row} className="h-6 w-full opacity-70" />
          ))}
        </>
      ) : null}
      {variant === 'form' ? (
        <>
          {ROWS.slice(0, 4).map((row) => (
            <div key={row} className="flex flex-col gap-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-9 w-full" />
            </div>
          ))}
          <Skeleton className="h-9 w-24" />
        </>
      ) : null}
      {variant === 'page' ? (
        <>
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-24 w-full" />
        </>
      ) : null}
    </div>
  )
}
