import { useTranslation } from 'react-i18next'

import { SCOPES, type Scope } from './integrationValues'

/** Checkboxes for the scopes of API spec 19.3. */
export function ScopePicker({
  value,
  onChange,
}: {
  value: readonly Scope[]
  onChange: (scopes: Scope[]) => void
}) {
  const { t } = useTranslation('integrations')
  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="mb-2 text-sm font-medium">{t('fields.scopes')}</legend>
      {SCOPES.map((scope) => (
        <label key={scope} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.includes(scope)}
            onChange={(e) => {
              onChange(e.target.checked ? [...value, scope] : value.filter((s) => s !== scope))
            }}
          />
          <code>{scope}</code>
        </label>
      ))}
    </fieldset>
  )
}
