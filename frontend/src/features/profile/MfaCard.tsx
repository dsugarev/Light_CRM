import { useMutation, useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ME_QUERY_KEY, type Me } from '@/features/auth/useMe'

function errorCode(error: unknown): string | null {
  if (!error) return null
  if (error instanceof ApiError) return error.errors[0]?.code ?? error.code
  return 'unknown'
}

/** FR-AUTH-07: optional two-factor sign-in with an authenticator app. */
export function MfaCard({ me }: { me: Me }) {
  const { t } = useTranslation('profile')
  const queryClient = useQueryClient()
  const [setup, setSetup] = useState<Schemas['MfaSetup'] | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const refreshMe = () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })

  const start = useMutation({
    mutationFn: () => call(api.POST('/api/v1/auth/mfa/setup')),
    onSuccess: (result) => {
      setSetup(result)
      setCode('')
    },
  })
  const confirm = useMutation({
    mutationFn: () => call(api.POST('/api/v1/auth/mfa/confirm', { body: { code: code.trim() } })),
    onSuccess: async (result) => {
      setSetup(null)
      setCodes(result.recovery_codes)
      await refreshMe()
    },
  })
  const disable = useMutation({
    mutationFn: () => call(api.POST('/api/v1/auth/mfa/disable', { body: { password } })),
    onSuccess: async () => {
      setPassword('')
      await refreshMe()
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('mfa.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="flex items-center gap-2 text-sm">
          {t('mfa.status')}
          <Badge variant={me.mfa_enabled ? 'default' : 'outline'}>
            {me.mfa_enabled ? t('mfa.on') : t('mfa.off')}
          </Badge>
        </p>

        {codes ? (
          <div className="flex flex-col gap-2" role="region" aria-label={t('mfa.recoveryTitle')}>
            <FormMessage success={t('mfa.enabled')} />
            <p className="text-sm font-medium">{t('mfa.recoveryTitle')}</p>
            <p className="text-sm text-muted-foreground">{t('mfa.recoveryHint')}</p>
            <ul className="grid grid-cols-2 gap-1 font-mono text-sm">
              {codes.map((recovery) => (
                <li key={recovery}>{recovery}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard.writeText(codes.join('\n'))
                }}
              >
                {t('mfa.copyCodes')}
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setCodes(null)
                }}
              >
                {t('mfa.savedCodes')}
              </Button>
            </div>
          </div>
        ) : null}

        {!me.mfa_enabled && !setup && !codes ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">{t('mfa.intro')}</p>
            <FormMessage error={errorCode(start.error)} />
            <Button
              type="button"
              className="self-start"
              disabled={start.isPending}
              onClick={() => {
                start.mutate()
              }}
            >
              {t('mfa.enable')}
            </Button>
          </div>
        ) : null}

        {setup ? (
          <form
            aria-label={t('mfa.setupTitle')}
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (code.trim()) confirm.mutate()
            }}
          >
            <p className="text-sm">{t('mfa.scan')}</p>
            <div className="self-start rounded-lg bg-qr-surface p-3">
              <QRCodeSVG value={setup.provisioning_uri} size={176} title={t('mfa.qrTitle')} />
            </div>
            <p className="text-sm">
              {t('mfa.manual')}{' '}
              <code className="rounded bg-muted px-1 font-mono text-xs break-all">
                {setup.secret}
              </code>
            </p>
            <FormMessage error={errorCode(confirm.error)} />
            <FormField label={t('mfa.code')} required>
              {(control) => (
                <Input
                  {...control}
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value)
                  }}
                />
              )}
            </FormField>
            <div className="flex gap-2">
              <Button type="submit" disabled={confirm.isPending || code.trim().length !== 6}>
                {t('mfa.confirm')}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSetup(null)
                }}
              >
                {t('mfa.cancel')}
              </Button>
            </div>
          </form>
        ) : null}

        {me.mfa_enabled && !codes ? (
          <form
            aria-label={t('mfa.disableTitle')}
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (password) disable.mutate()
            }}
          >
            <p className="text-sm text-muted-foreground">{t('mfa.disableHint')}</p>
            <FormMessage error={errorCode(disable.error)} />
            <FormField label={t('mfa.password')} required>
              {(control) => (
                <Input
                  {...control}
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value)
                  }}
                />
              )}
            </FormField>
            <Button
              type="submit"
              variant="outline"
              className="self-start"
              disabled={disable.isPending || password === ''}
            >
              {t('mfa.disable')}
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  )
}
