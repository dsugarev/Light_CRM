import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

import { AssistantPanel } from './AssistantPanel'
import { useAssistantStatus } from './useAssistant'

/** The header button and the drawer it opens; absent while AI_ENABLED is off (FR-AI-07). */
export function AssistantLauncher() {
  const { t } = useTranslation('assistant')
  const status = useAssistantStatus(true)
  const [open, setOpen] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  if (!status.data?.enabled) return null
  return (
    <>
      <Button
        ref={button}
        type="button"
        variant={open ? 'secondary' : 'outline'}
        size="sm"
        aria-expanded={open}
        aria-controls="assistant-panel"
        onClick={() => {
          setOpen(!open)
        }}
      >
        {t('open')}
      </Button>
      {open ? (
        <AssistantPanel
          remaining={status.data.remaining_budget}
          onClose={() => {
            setOpen(false)
            button.current?.focus() // focus goes back where the user opened the drawer
          }}
        />
      ) : null}
    </>
  )
}
