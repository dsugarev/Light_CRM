import { useTranslation } from 'react-i18next'

/** The password policy the backend enforces (identity/passwords.py, FR-AUTH-03). */
export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_MAX_LENGTH = 128

type Rule = 'length' | 'maxLength' | 'common' | 'match'

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
  )
}
