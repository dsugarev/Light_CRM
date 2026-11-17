import { isLocale, type Locale } from '@/i18n'

// Phase 0 keeps the chosen language in the browser. Phase 1 stores it on the
// user profile (FR-I18N-01); this remains the default before sign-in.
const STORAGE_KEY = 'crm.locale'

export function detectLocale(
  stored: string | null = readStoredLocale(),
  browserLanguages: readonly string[] = navigator.languages,
): Locale {
  if (isLocale(stored)) return stored
  const preferred = browserLanguages.find((lang) => lang.toLowerCase().startsWith('bg'))
  return preferred ? 'bg' : 'en'
}

export function storeLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // Storage can be unavailable (private mode); the choice then lasts for the session.
  }
}

function readStoredLocale(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}
