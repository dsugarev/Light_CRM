import { useTranslation } from 'react-i18next'

import type { Schemas } from '@/api/client'

/** Record types the backend writes to the audit log (the filter's choices). */
export const AUDIT_ENTITY_TYPES = [
  'activity',
  'api_key',
  'chat_conversation',
  'contact',
  'external_reference',
  'import_batch',
  'integration_client',
  'lead',
  'opportunity',
  'organization',
  'pipeline_stage',
  'session',
  'settings',
  'user',
  'webhook_subscription',
] as const

/** Display names for audit actions and record types (known ones translated) and actors. */
export function useAuditLabels() {
  const { t, i18n } = useTranslation('admin')
  const action = (code: string) =>
    i18n.exists(`admin:audit.actions.${code}`) ? t(`audit.actions.${code}` as 'audit.title') : code
  const entityType = (code: string) =>
    i18n.exists(`admin:audit.entityTypes.${code}`)
      ? t(`audit.entityTypes.${code}` as 'audit.title')
      : code
  const actor = (a: Schemas['AuditActor']) =>
    a.name ?? (a.type === 'system' ? t('audit.actor.system') : t('audit.actor.anonymous'))
  return { action, entityType, actor }
}
