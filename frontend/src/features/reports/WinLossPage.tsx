import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatMoney, formatNumber, formatPercent } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { ExportMenu } from './ExportMenu'
import { ScopeFilters } from './ScopeFilters'
import { useReportScope } from './useReportScope'

const GROUPS = ['loss_reason', 'owner', 'month'] as const
type Group = (typeof GROUPS)[number]
type Figures = Schemas['WinLossFigures']

/** FR-REP-03: won against lost by loss reason, owner or month, for a year. */
export function WinLossPage() {
  const { t } = useTranslation('reports')
  const locale = useLocale()
  const scope = useReportScope()
  const [params, setParams] = useSearchParams()
  const raw = params.get('group_by')
  const groupBy: Group = (GROUPS as readonly string[]).includes(raw ?? '')
    ? (raw as Group)
    : 'loss_reason'
  const query = { ...scope.query, group_by: groupBy }
  const report = useQuery({
    queryKey: ['reports', 'win-loss', query],
    placeholderData: keepPreviousData,
    queryFn: () => call(api.GET('/api/v1/reports/win-loss', { params: { query } })),
  })
  const rate = (share: number | null) => (share === null ? '' : formatPercent(share, locale))
  const cells = (f: Figures) => [
    formatNumber(f.won_count, locale),
    formatMoney(f.won_amount, locale),
    formatNumber(f.lost_count, locale),
    formatMoney(f.lost_amount, locale),
    rate(f.win_rate),
  ]
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-4">
      <PageHeader
        title={t('winLoss.title')}
        actions={<ExportMenu path="/api/v1/reports/win-loss/export" query={query} />}
      />
      <div className="flex flex-wrap items-center gap-2">
        <ScopeFilters scope={scope} />
        <NativeSelect
          aria-label={t('winLoss.groupBy')}
          value={groupBy}
          className="w-44"
          onChange={(e) => {
            const next = new URLSearchParams(params)
            next.set('group_by', e.target.value)
            setParams(next, { replace: true })
          }}
        >
          {GROUPS.map((group) => (
            <option key={group} value={group}>
              {t(`winLoss.groups.${group}`)}
            </option>
          ))}
        </NativeSelect>
      </div>
      {report.isError ? (
        <ErrorState
          error={report.error}
          onRetry={() => {
            void report.refetch()
          }}
        />
      ) : null}
      {report.data ? (
        <Table>
          <caption className="sr-only">{t('winLoss.title')}</caption>
          <TableHeader>
            <TableRow>
              <TableHead>{t(`winLoss.groups.${groupBy}`)}</TableHead>
              <TableHead className="text-right">{t('columns.won')}</TableHead>
              <TableHead className="text-right">{t('columns.wonAmount')}</TableHead>
              <TableHead className="text-right">{t('columns.lost')}</TableHead>
              <TableHead className="text-right">{t('columns.lostAmount')}</TableHead>
              <TableHead className="text-right">{t('columns.winRate')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.data.groups.map((g) => (
              <TableRow key={g.group.key}>
                <TableCell>
                  {(locale === 'bg' ? g.group.name_bg : g.group.name_en) ?? t('winLoss.none')}
                </TableCell>
                {cells(g).map((value, index) => (
                  <TableCell key={index} className="text-right">
                    {value}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            <TableRow className="font-semibold">
              <TableCell>{t('winLoss.total')}</TableCell>
              {cells(report.data.totals).map((value, index) => (
                <TableCell key={index} className="text-right">
                  {value}
                </TableCell>
              ))}
            </TableRow>
          </TableBody>
        </Table>
      ) : report.isPending ? (
        <Loading />
      ) : null}
    </section>
  )
}
