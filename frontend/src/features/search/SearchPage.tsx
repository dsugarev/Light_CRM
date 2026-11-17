import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { api, call } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'

/** Global quick search (API spec section 12) across organizations and contacts. */
export function SearchPage() {
  const { t } = useTranslation('party')
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()
  const results = useQuery({
    queryKey: ['search', q],
    queryFn: () => call(api.GET('/api/v1/search', { params: { query: { q } } })),
    enabled: q.length >= 2,
  })
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={q ? t('search.results', { q }) : t('search.title')} />
      {q.length < 2 ? <p className="text-muted-foreground">{t('search.tooShort')}</p> : null}
      {results.isError ? <ErrorState error={results.error} /> : null}
      {results.isFetching && !results.data ? <Loading /> : null}
      {results.data ? (
        results.data.items.length === 0 ? (
          <p className="text-muted-foreground">{t('search.none')}</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {results.data.items.map((hit) => (
              <li key={`${hit.type}-${hit.id}`} className="flex items-center gap-3 px-4 py-2">
                <Badge variant="secondary">{t(`search.${hit.type}`)}</Badge>
                <Link
                  to={
                    hit.type === 'organization' ? `/organizations/${hit.id}` : `/contacts/${hit.id}`
                  }
                  className="font-medium hover:underline"
                >
                  {hit.label}
                </Link>
                {hit.detail ? (
                  <span className="text-sm text-muted-foreground">{hit.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  )
}
