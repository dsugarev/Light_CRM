import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { Input } from '@/components/ui/input'

/** Header search box: Enter opens the search page (FR-PARTY-04). */
export function HeaderSearch() {
  const { t } = useTranslation('party')
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault()
        if (q.trim()) void navigate(`/search?q=${encodeURIComponent(q.trim())}`)
      }}
    >
      <Input
        type="search"
        className="w-48 lg:w-64"
        aria-label={t('search.label')}
        placeholder={t('search.label')}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
        }}
      />
    </form>
  )
}
