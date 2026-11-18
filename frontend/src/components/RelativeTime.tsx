import { useState } from 'react'

import { formatDateTime, formatRelative } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

/** UX-08: "3 hours ago", with the exact Sofia time on hover and for assistive technology. */
export function RelativeTime({ iso }: { iso: string }) {
  const locale = useLocale()
  // Fixed when the component mounts: a list does not need to tick.
  const [now] = useState(() => Date.now())
  const exact = formatDateTime(iso, locale)
  return (
    <time dateTime={iso} title={exact}>
      {formatRelative(iso, now, locale)}
      <span className="sr-only"> ({exact})</span>
    </time>
  )
}
