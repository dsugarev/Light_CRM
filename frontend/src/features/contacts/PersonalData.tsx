import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useNotify } from '@/lib/notify'

const CONFIRM_WORD = 'ANONYMIZE'

/** FR-ADM-04: an Admin exports a contact's personal data or anonymizes the contact. */
export function PersonalData({ contact }: { contact: Schemas['ContactOut'] }) {
  const notify = useNotify()
  const { t } = useTranslation('party')
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState('')
  const path = { params: { path: { contact_id: contact.id } } }
  const download = useMutation({
    mutationFn: () => call(api.GET('/api/v1/contacts/{contact_id}/personal-data', path)),
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `contact-${contact.id}-personal-data.json`
      link.click()
      URL.revokeObjectURL(url)
    },
  })
  const anonymize = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/contacts/{contact_id}/anonymize', {
          ...path,
          body: { confirm: CONFIRM_WORD },
        }),
      ),
    onSuccess: async () => {
      setTyped('')
      await queryClient.invalidateQueries({ queryKey: ['contacts'] })
      await queryClient.invalidateQueries({ queryKey: ['timeline'] })
      notify.success(t('contact.gdpr.anonymized'))
    },
  })
  const failure = [download.error, anonymize.error].find((e) => e instanceof ApiError)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('contact.gdpr.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <FormMessage error={failure instanceof ApiError ? failure.code : null} />
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">{t('contact.gdpr.exportHint')}</p>
          <Button
            type="button"
            variant="outline"
            className="self-start"
            disabled={download.isPending}
            onClick={() => {
              download.mutate()
            }}
          >
            {t('contact.gdpr.export')}
          </Button>
        </div>
        {contact.anonymized_at ? null : (
          <form
            aria-label={t('contact.gdpr.anonymize')}
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (typed === CONFIRM_WORD) anonymize.mutate()
            }}
          >
            <p className="text-sm text-muted-foreground">{t('contact.gdpr.anonymizeHint')}</p>
            <FormField label={t('contact.gdpr.typeToConfirm', { word: CONFIRM_WORD })} required>
              {(control) => (
                <Input
                  {...control}
                  value={typed}
                  autoComplete="off"
                  onChange={(event) => {
                    setTyped(event.target.value)
                  }}
                />
              )}
            </FormField>
            <Button
              type="submit"
              variant="destructive"
              className="self-start"
              disabled={typed !== CONFIRM_WORD || anonymize.isPending}
            >
              {t('contact.gdpr.anonymize')}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
