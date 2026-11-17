import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** Read-only value with a copy button (one-time links). */
export function CopyField({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex gap-2">
      <Input
        readOnly
        value={value}
        aria-label={label}
        onFocus={(e) => {
          e.target.select()
        }}
      />
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          void navigator.clipboard.writeText(value).then(() => {
            setCopied(true)
          })
        }}
      >
        {copied ? t('actions.copied') : t('actions.copy')}
      </Button>
    </div>
  )
}
