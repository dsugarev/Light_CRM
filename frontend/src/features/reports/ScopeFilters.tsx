import { useTranslation } from 'react-i18next'

import { NativeSelect } from '@/components/NativeSelect'

import type { useReportScope } from './useReportScope'

/** Owner (mine / everyone) and year filters shared by the dashboard and reports. */
export function ScopeFilters({ scope }: { scope: ReturnType<typeof useReportScope> }) {
  const { t } = useTranslation('reports')
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect
        aria-label={t('filters.owner')}
        value={scope.mine ? 'me' : ''}
        className="w-40"
        onChange={(e) => {
          scope.update({ owner: e.target.value || null })
        }}
      >
        <option value="">{t('filters.everyone')}</option>
        <option value="me">{t('filters.mine')}</option>
      </NativeSelect>
      <NativeSelect
        aria-label={t('filters.year')}
        value={String(scope.year)}
        className="w-32"
        onChange={(e) => {
          scope.update({ year: e.target.value })
        }}
      >
        {scope.years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}
