import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, call, type Schemas } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { stageName } from '@/features/opportunities/opportunityValues'
import { formatMoney, formatNumber, formatPercent } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { ScopeFilters } from './ScopeFilters'
import { useReportScope } from './useReportScope'

type DashboardData = Schemas['Dashboard']
const CHART_HEIGHT = 260
const TOTAL_COLOR = 'var(--color-chart-2)'
const WEIGHTED_COLOR = 'var(--color-chart-1)'

/** FR-REP-01: pipeline, forecast, conversion and win rates, my open tasks. */
export function Dashboard() {
  const { t } = useTranslation('reports')
  const scope = useReportScope()
  const dashboard = useQuery({
    queryKey: ['reports', 'dashboard', scope.query],
    placeholderData: keepPreviousData,
    queryFn: () => call(api.GET('/api/v1/reports/dashboard', { params: { query: scope.query } })),
  })
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{t('dashboard.title')}</h2>
        <div className="flex items-center gap-2">
          <ScopeFilters scope={scope} />
          <Link
            to="/reports/win-loss"
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            {t('winLoss.title')}
          </Link>
        </div>
      </div>
      {dashboard.isError ? <ErrorState error={dashboard.error} /> : null}
      {dashboard.data ? (
        <Figures data={dashboard.data} />
      ) : dashboard.isPending ? (
        <Loading />
      ) : null}
    </div>
  )
}

function Kpi({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail?: string | undefined
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 pt-6">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-2xl font-semibold" data-testid={`kpi-${label}`}>
          {value}
        </span>
        {detail ? <span className="text-xs text-muted-foreground">{detail}</span> : null}
      </CardContent>
    </Card>
  )
}

function Figures({ data }: { data: DashboardData }) {
  const { t } = useTranslation('reports')
  const locale = useLocale()
  const money = (value: string) => formatMoney(value, locale)
  const rate = (share: number | null) =>
    share === null ? t('dashboard.noData') : formatPercent(share, locale)
  const stages = data.pipeline.stages.map((s) => ({
    name: stageName(s.stage, locale),
    total: Number(s.total_amount),
    weighted: Number(s.weighted_amount),
  }))
  const months = data.forecast.months.map((m) => ({
    name: new Intl.DateTimeFormat(locale === 'bg' ? 'bg-BG' : 'en-GB', {
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${m.month}-01T00:00:00Z`)),
    weighted: Number(m.weighted_amount),
  }))
  const conversion = data.lead_conversion
  const closed = data.win_loss
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label={t('dashboard.openPipeline')}
          value={money(data.pipeline.total_amount)}
          detail={t('dashboard.weighted', { value: money(data.pipeline.weighted_amount) })}
        />
        <Kpi
          label={t('dashboard.conversionRate')}
          value={rate(conversion.conversion_rate)}
          detail={t('dashboard.conversionDetail', {
            converted: formatNumber(conversion.converted, locale),
            created: formatNumber(conversion.created, locale),
          })}
        />
        <Kpi
          label={t('dashboard.winRate')}
          value={rate(closed.win_rate)}
          detail={t('dashboard.winDetail', {
            won: formatNumber(closed.won_count, locale),
            lost: formatNumber(closed.lost_count, locale),
          })}
        />
        <Card>
          <CardContent className="flex flex-col gap-1 pt-6">
            <span className="text-sm text-muted-foreground">{t('dashboard.myTasks')}</span>
            <Link to="/tasks" className="text-2xl font-semibold hover:underline">
              {formatNumber(data.my_tasks.open, locale)}
            </Link>
            <span className="text-xs text-muted-foreground">
              {t('dashboard.overdue', { count: data.my_tasks.overdue })}
            </span>
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t('dashboard.pipelineByStage')}</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Hidden from assistive technology and not focusable: the table below has the figures. */}
            <div aria-hidden="true" style={{ height: CHART_HEIGHT }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stages} accessibilityLayer={false}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis fontSize={12} />
                  <Tooltip formatter={(value) => money(String(value))} />
                  <Legend />
                  <Bar dataKey="total" name={t('dashboard.total')} fill={TOTAL_COLOR} />
                  <Bar
                    dataKey="weighted"
                    name={t('dashboard.weightedShort')}
                    fill={WEIGHTED_COLOR}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="sr-only">
              <caption>{t('dashboard.pipelineByStage')}</caption>
              <thead>
                <tr>
                  <th>{t('columns.stage')}</th>
                  <th>{t('columns.count')}</th>
                  <th>{t('dashboard.total')}</th>
                  <th>{t('dashboard.weightedShort')}</th>
                </tr>
              </thead>
              <tbody>
                {data.pipeline.stages.map((s) => (
                  <tr key={s.stage.id}>
                    <td>{stageName(s.stage, locale)}</td>
                    <td>{s.count}</td>
                    <td>{money(s.total_amount)}</td>
                    <td>{money(s.weighted_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('dashboard.forecast')}</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Hidden from assistive technology and not focusable: the table below has the figures. */}
            <div aria-hidden="true" style={{ height: CHART_HEIGHT }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={months} accessibilityLayer={false}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis fontSize={12} />
                  <Tooltip formatter={(value) => money(String(value))} />
                  <Bar
                    dataKey="weighted"
                    name={t('dashboard.weightedShort')}
                    fill={WEIGHTED_COLOR}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="sr-only">
              <caption>{t('dashboard.forecast')}</caption>
              <thead>
                <tr>
                  <th>{t('columns.month')}</th>
                  <th>{t('dashboard.weightedShort')}</th>
                </tr>
              </thead>
              <tbody>
                {data.forecast.months.map((m, index) => (
                  <tr key={m.month}>
                    <td>{months[index]?.name}</td>
                    <td>{money(m.weighted_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
