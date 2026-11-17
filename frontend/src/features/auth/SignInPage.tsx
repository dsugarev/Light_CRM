import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// Phase 0 placeholder: the form is shown but disabled. Phase 1 wires it to
// POST /api/v1/auth/login (FR-AUTH-01).
export function SignInPage() {
  const { t } = useTranslation('auth')
  const emailId = useId()
  const passwordId = useId()

  return (
    <section className="mx-auto mt-16 w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
      <h1 className="mb-6 text-xl font-semibold">{t('signIn.title')}</h1>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
        }}
      >
        <fieldset disabled className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={emailId}>{t('signIn.email')}</Label>
            <Input id={emailId} name="email" type="email" autoComplete="username" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={passwordId}>{t('signIn.password')}</Label>
            <Input
              id={passwordId}
              name="password"
              type="password"
              autoComplete="current-password"
            />
          </div>
          <Button type="submit">{t('signIn.submit')}</Button>
        </fieldset>
        <p role="status" className="text-sm text-muted-foreground">
          {t('signIn.notAvailable')}
        </p>
      </form>
    </section>
  )
}
