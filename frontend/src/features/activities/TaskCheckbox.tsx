import { useTranslation } from 'react-i18next'

import { api, call } from '@/api/client'
import { useMe } from '@/features/auth/useMe'
import { useCanEditOwned } from '@/features/auth/useOwnership'

import type { Activity } from './activityValues'
import { useActivityMutation } from './useActivityMutation'

/** FR-ACT-02: the owner (Owner+) or the assignee marks a task done or not done. */
export function TaskCheckbox({ task }: { task: Activity }) {
  const { t } = useTranslation('activities')
  const { data: me } = useMe()
  const canEdit = useCanEditOwned()
  const allowed = canEdit(task.owner.id) || (me !== undefined && task.assignee?.id === me?.id)
  const path = { params: { path: { activity_id: task.id } }, body: { version: task.version } }
  const toggle = useActivityMutation(
    () =>
      task.is_done
        ? call(api.POST('/api/v1/activities/{activity_id}/reopen', path))
        : call(api.POST('/api/v1/activities/{activity_id}/complete', path)),
    task.is_done ? t('toasts.reopened') : t('toasts.completed'),
  )
  return (
    <input
      type="checkbox"
      aria-label={t('task.done', { subject: task.subject })}
      checked={task.is_done}
      disabled={!allowed || toggle.isPending}
      onChange={() => {
        toggle.mutate(undefined)
      }}
    />
  )
}
