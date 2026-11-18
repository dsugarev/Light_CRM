import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { z } from 'zod'

import { AuthCard } from '@/components/AuthCard'
import { api, ApiError, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const schema = z.object({ email: z.string().trim().min(1, { error: 'validation.required' }) })
type Values = z.infer<typeof schema>

export function ForgotPasswordPage() {
  const { t } = useTranslation('auth')
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '' } })
  const request = useMutation({
    mutationFn: (values: Values) =>
      call(api.POST('/api/v1/auth/password/forgot', { body: values })),
  })

  return (
    <AuthCard title={t('forgot.title')}>
      {request.isSuccess ? (
        <FormMessage success={t('forgot.sent')} />
      ) : (
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              request.mutate(values)
            })(event)
          }}
        >
          <FormMessage error={request.error instanceof ApiError ? request.error.code : null} />
          <FormField
            label={t('forgot.email')}
            required
            error={form.formState.errors.email?.message}
          >
            {(control) => (
              <Input
                {...control}
                type="email"
                autoComplete="username"
                {...form.register('email')}
              />
            )}
          </FormField>
          <Button type="submit" disabled={request.isPending}>
            {t('forgot.submit')}
          </Button>
        </form>
      )}
      <Link
        className="mt-4 inline-block text-sm text-primary underline underline-offset-4"
        to="/sign-in"
      >
        {t('forgot.back')}
      </Link>
    </AuthCard>
  )
}
