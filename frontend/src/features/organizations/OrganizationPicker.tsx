import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, asPage, call } from '@/api/client'
import { SearchInput } from '@/components/SearchInput'
import { Button } from '@/components/ui/button'

interface OrganizationPickerProps {
  id: string
  value: { id: string; name: string } | null
  onChange: (value: { id: string; name: string } | null) => void
  invalid?: boolean
}

/** Search-as-you-type picker: lists can hold thousands of organizations. */
export function OrganizationPicker({
  id,
  value,
  onChange,
  invalid = false,
}: OrganizationPickerProps) {
  const { t } = useTranslation('party')
  const [q, setQ] = useState('')
  const results = useQuery({
    queryKey: ['organizations', 'picker', q],
    queryFn: async () =>
      asPage(
        await call(api.GET('/api/v1/organizations', { params: { query: { q, page_size: 8 } } })),
      ),
    enabled: q.length >= 2,
  })

  if (value) {
    return (
      <div id={id} className="flex items-center gap-2">
        <span className="text-sm font-medium">{value.name}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            onChange(null)
          }}
        >
          {t('contact.noOrganization')}
        </Button>
      </div>
    )
  }
  return (
    <div id={id} className="flex flex-col gap-2" aria-invalid={invalid}>
      <SearchInput label={t('organizations.search')} value={q} onChange={setQ} />
      {results.data && results.data.items.length > 0 ? (
        <ul className="rounded-lg border" aria-label={t('organizations.title')}>
          {results.data.items.map((org) => (
            <li key={org.id}>
              <button
                type="button"
                className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted focus-visible:bg-muted"
                onClick={() => {
                  onChange({ id: org.id, name: org.name })
                  setQ('')
                }}
              >
                {org.name}
                {org.city ? <span className="text-muted-foreground"> · {org.city}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
