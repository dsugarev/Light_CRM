import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const { t } = useTranslation()
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 text-sm"
      aria-label={t('pagination.summary', {
        page: String(page),
        pages: String(pages),
        total: String(total),
      })}
    >
      <span className="text-muted-foreground">
        {t('pagination.summary', {
          page: String(page),
          pages: String(pages),
          total: String(total),
        })}
      </span>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => {
            onPageChange(page - 1)
          }}
        >
          {t('actions.previous')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => {
            onPageChange(page + 1)
          }}
        >
          {t('actions.next')}
        </Button>
      </div>
    </nav>
  )
}
