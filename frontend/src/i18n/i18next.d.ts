import 'i18next'

import type { defaultNS, resources } from './index'

// Typed translation keys: t('missing.key') is a compile error.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: typeof defaultNS
    resources: (typeof resources)['en']
    // Keys such as auth.invalid_credentials contain underscores; contexts are not used.
    contextSeparator: '|'
  }
}
