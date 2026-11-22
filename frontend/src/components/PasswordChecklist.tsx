import { useTranslation } from 'react-i18next'

import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordStrength } from './passwordPolicy'

type Rule = 'length' | 'maxLength' | 'common' | 'match'

const STRENGTH_LABEL = ['', 'weak', 'fair', 'good', 'strong'] as const
const STRENGTH_TONE = ['', 'bg-destructive', 'bg-warning', 'bg-info', 'bg-success'] as const

function StrengthMeter({ password }: { password: string }) {
  const { t } = useTranslation()
  const strength = passwordStrength(password)
  if (strength === 0) return null
  return (
    <div className="flex items-center gap-2 text-sm" data-testid="password-strength">
      <div aria-hidden="true" className="flex gap-1">
        {[1, 2, 3, 4].map((step) => (
          <span
            key={step}
            className={`h-1.5 w-8 rounded-full ${step <= strength ? STRENGTH_TONE[strength] : 'bg-muted'}`}
          />
        ))}
      </div>
      <span aria-live="polite">
        {t('passwordRules.strength', { level: t(`passwordRules.${STRENGTH_LABEL[strength]}`) })}
      </span>
    </div>
  )
}

function Mark({ met }: { met: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`size-4 shrink-0 ${met ? 'text-success' : 'text-muted-foreground'}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {met ? <path d="m3.5 8.5 3 3 6-7" /> : <circle cx="8" cy="8" r="2" />}
    </svg>
  )
}

/**
 * UX-07: live checklist of the password rules while typing. Length and the repeat are
 * checked here; common passwords only on the server (the list stays there), so that rule
 * says when it is checked. Reused by the profile's password change (FN-01).
 */
export function PasswordChecklist({ password, confirm }: { password: string; confirm: string }) {
  const { t } = useTranslation()
  const rules: { rule: Rule; met: boolean | null }[] = [
    { rule: 'length', met: password.length >= PASSWORD_MIN_LENGTH },
    { rule: 'maxLength', met: password.length <= PASSWORD_MAX_LENGTH },
    { rule: 'common', met: null },
    { rule: 'match', met: confirm !== '' && password === confirm },
  ]
  return (
    <div className="flex flex-col gap-2">
      <StrengthMeter password={password} />
      <ul aria-label={t('passwordRules.label')} className="flex flex-col gap-1 text-sm">
        {rules.map(({ rule, met }) => (
          <li key={rule} className="flex items-center gap-2">
            <Mark met={met === true} />
            <span className={met === true ? '' : 'text-muted-foreground'}>
              {t(`passwordRules.${rule}`, { min: PASSWORD_MIN_LENGTH, max: PASSWORD_MAX_LENGTH })}
            </span>
            {met === null ? null : (
              <span className="sr-only">
                {met ? t('passwordRules.met') : t('passwordRules.notMet')}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
