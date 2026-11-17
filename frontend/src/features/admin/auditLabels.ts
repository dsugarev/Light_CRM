import { useTranslation } from 'react-i18next'

import type { Schemas } from '@/api/client'

/** Display names for audit actions (known ones translated) and actors. */
export function useAuditLabels() {
  const { t, i18n } = useTranslation('admin')
  const action = (code: string) =>
    i18n.exists(`admin:audit.actions.${code}`) ? t(`audit.actions.${code}` as 'audit.title') : code
  const actor = (a: Schemas['AuditActor']) =>
    a.name ?? (a.type === 'system' ? t('audit.actor.system') : t('audit.actor.anonymous'))
  return { action, actor }
}
