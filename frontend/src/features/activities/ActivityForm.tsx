import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useMe } from '@/features/auth/useMe'
import { useUserLookup } from '@/features/auth/useUserLookup'

import { ACTIVITY_TYPES, toIso, type ActivityType, type RecordRef } from './activityValues'
import { useActivityMutation } from './useActivityMutation'

const LINK_FIELD = {
  lead: 'lead_id',
  opportunity: 'opportunity_id',
  organization: 'organization_id',
  contact: 'contact_id',
} as const

/** FR-ACT-01, 02: log an interaction or create a task on the record being viewed. */
export function ActivityForm({ record, onDone }: { record: RecordRef; onDone: () => void }) {
  const { t } = useTranslation('activities')
  const { t: tc } = useTranslation()
  const { data: me } = useMe()
  const users = useUserLookup(true)
  const [type, setType] = useState<ActivityType>('call')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [when, setWhen] = useState('')
  const [due, setDue] = useState('')
  const [assignee, setAssignee] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const isTask = type === 'task'
  const create = useActivityMutation(
    () =>
      call(
        api.POST('/api/v1/activities', {
          body: {
            type,
            subject: subject.trim(),
            body: body.trim() || null,
            occurred_at: isTask ? null : toIso(when),
            due_at: isTask ? toIso(due) : null,
            assignee_id: isTask && assignee ? assignee : null,
            [LINK_FIELD[record.kind]]: record.id,
          },
        }),
      ),
    isTask ? t('toasts.taskCreated') : t('toasts.logged'),
    { toastFieldErrors: false },
  )
  const submit = () => {
    const missing: Record<string, string> = {}
    if (!subject.trim()) missing['subject'] = 'validation.required'
    if (isTask && !due) missing['due_at'] = 'activity.due_required'
    setErrors(missing)
    if (Object.keys(missing).length > 0) return
    create.mutate(undefined, {
      onSuccess: onDone,
      onError: (error) => {
        if (error instanceof ApiError) {
          setErrors(Object.fromEntries(error.errors.map((e) => [e.field, e.code])))
        }
      },
    })
  }
  return (
    <form
      aria-label={t('form.title')}
      noValidate
      className="flex flex-col gap-3 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <FormField label={t('form.type')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={type}
              onChange={(e) => {
                setType(e.target.value as ActivityType)
              }}
            >
              {ACTIVITY_TYPES.map((value) => (
                <option key={value} value={value}>
                  {t(`type.${value}`)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('form.subject')} error={errors['subject']}>
          {(control) => (
            <Input
              {...control}
              value={subject}
              maxLength={200}
              onChange={(e) => {
                setSubject(e.target.value)
              }}
            />
          )}
        </FormField>
      </div>
      <FormField label={t('form.body')} error={errors['body']}>
        {(control) => (
          <Textarea
            {...control}
            rows={3}
            value={body}
            onChange={(e) => {
              setBody(e.target.value)
            }}
          />
        )}
      </FormField>
      {isTask ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label={t('form.due')} error={errors['due_at']}>
            {(control) => (
              <Input
                {...control}
                type="datetime-local"
                value={due}
                onChange={(e) => {
                  setDue(e.target.value)
                }}
              />
            )}
          </FormField>
          <FormField label={t('form.assignee')} error={errors['assignee_id']}>
            {(control) => (
              <NativeSelect
                {...control}
                value={assignee !== '' ? assignee : (me?.id ?? '')}
                onChange={(e) => {
                  setAssignee(e.target.value)
                }}
              >
                {(users.data?.items ?? []).map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
      ) : (
        <FormField label={t('form.when')} hint={t('form.whenHint')} error={errors['occurred_at']}>
          {(control) => (
            <Input
              {...control}
              type="datetime-local"
              value={when}
              onChange={(e) => {
                setWhen(e.target.value)
              }}
            />
          )}
        </FormField>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          {isTask ? t('form.createTask') : t('form.log')}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {tc('actions.cancel')}
        </Button>
      </div>
    </form>
  )
}
