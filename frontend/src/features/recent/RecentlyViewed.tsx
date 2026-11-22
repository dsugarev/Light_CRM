import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { RelativeTime } from '@/components/RelativeTime'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { RecordType } from './recentRecords'
import { useRecentRecords } from './useRecentRecords'

const PATHS: Record<RecordType, string> = {
  organization: '/organizations',
  contact: '/contacts',
  lead: '/leads',
  opportunity: '/opportunities',
}

/** Home page card: the records this user opened last, newest first. */
export function RecentlyViewed() {
  const { t } = useTranslation()
  const records = useRecentRecords()
  if (records.length === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-base font-semibold">{t('home.recent.title')}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          {records.map((record) => (
            <li key={`${record.type}-${record.id}`} className="flex min-w-0 flex-col">
              <Link
                to={`${PATHS[record.type]}/${record.id}`}
                className="truncate font-medium hover:underline"
                title={record.label}
              >
                {record.label}
              </Link>
              <span className="text-xs text-muted-foreground">
                {t(`home.recent.types.${record.type}`)} ·{' '}
                <RelativeTime iso={new Date(record.at).toISOString()} />
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
