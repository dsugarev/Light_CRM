import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SUPPORTED_LOCALES } from '@/i18n'
import { applyServerErrors } from '@/lib/errors'

import { HUMAN_ROLES } from './roles'

const userSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .pipe(z.email({ error: 'validation.email' })),
  full_name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  role: z.enum(HUMAN_ROLES),
  locale: z.enum(SUPPORTED_LOCALES),
})
export type UserValues = z.infer<typeof userSchema>
const FIELDS = ['email', 'full_name', 'role', 'locale'] as const

interface UserFormProps {
  defaultValues: UserValues
  submitLabel: string
  pending: boolean
  /** Resolve on success; reject with the API error to show it. */
  onSubmit: (values: UserValues) => Promise<unknown>
}

export function UserForm({ defaultValues, submitLabel, pending, onSubmit }: UserFormProps) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const form = useForm<UserValues>({ resolver: zodResolver(userSchema), defaultValues })
  const formError = form.formState.errors.root?.message
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void form.handleSubmit(async (values) => {
          try {
            await onSubmit(values)
          } catch (error) {
            const code = applyServerErrors(error, form.setError, FIELDS)
            if (code) form.setError('root', { message: code })
          }
        })(event)
      }}
    >
      <FormMessage error={formError} />
      <FormField label={t('userForm.email')} required error={form.formState.errors.email?.message}>
        {(control) => <Input {...control} type="email" {...form.register('email')} />}
      </FormField>
      <FormField
        label={t('userForm.fullName')}
        required
        error={form.formState.errors.full_name?.message}
      >
        {(control) => <Input {...control} {...form.register('full_name')} />}
      </FormField>
      <FormField label={t('userForm.role')} required error={form.formState.errors.role?.message}>
        {(control) => (
          <NativeSelect {...control} {...form.register('role')}>
            {HUMAN_ROLES.map((role) => (
              <option key={role} value={role}>
                {tc(`roles.${role}`)}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <FormField label={t('userForm.language')}>
        {(control) => (
          <NativeSelect {...control} {...form.register('locale')}>
            {SUPPORTED_LOCALES.map((locale) => (
              <option key={locale} value={locale}>
                {tc(`language.${locale}`)}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <Button type="submit" className="self-start" disabled={pending}>
        {pending ? tc('actions.saving') : submitLabel}
      </Button>
    </form>
  )
}
