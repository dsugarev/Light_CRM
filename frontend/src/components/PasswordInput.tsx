import { useId, useState, type ComponentProps, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/**
 * UX-06: a password field with a show/hide toggle and a Caps Lock warning.
 * Takes the same props as Input (FormField control props and react-hook-form register).
 */
export function PasswordInput({
  onKeyDown,
  onKeyUp,
  onBlur,
  'aria-describedby': describedBy,
  ...props
}: Omit<ComponentProps<'input'>, 'type'>) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const warningId = useId()
  const track = (event: KeyboardEvent<HTMLInputElement>) => {
    setCapsLock(event.getModifierState('CapsLock'))
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2">
        <Input
          {...props}
          type={visible ? 'text' : 'password'}
          aria-describedby={
            [describedBy, capsLock ? warningId : undefined].filter(Boolean).join(' ') || undefined
          }
          onKeyDown={(event) => {
            track(event)
            onKeyDown?.(event)
          }}
          onKeyUp={(event) => {
            track(event)
            onKeyUp?.(event)
          }}
          onBlur={(event) => {
            setCapsLock(false)
            onBlur?.(event)
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 shrink-0 pointer-coarse:h-11"
          aria-pressed={visible}
          aria-controls={props.id}
          onClick={() => {
            setVisible(!visible)
          }}
        >
          {visible ? t('password.hide') : t('password.show')}
        </Button>
      </div>
      {capsLock ? (
        <p id={warningId} role="status" className="text-xs text-destructive">
          {t('password.capsLock')}
        </p>
      ) : null}
    </div>
  )
}
