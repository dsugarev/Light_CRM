import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import bgActivities from './bg/activities.json'
import bgAdmin from './bg/admin.json'
import bgAuth from './bg/auth.json'
import bgCommon from './bg/common.json'
import bgErrors from './bg/errors.json'
import bgLeads from './bg/leads.json'
import bgOpportunities from './bg/opportunities.json'
import bgParty from './bg/party.json'
import bgProfile from './bg/profile.json'
import enActivities from './en/activities.json'
import enAdmin from './en/admin.json'
import enAuth from './en/auth.json'
import enCommon from './en/common.json'
import enErrors from './en/errors.json'
import enLeads from './en/leads.json'
import enOpportunities from './en/opportunities.json'
import enParty from './en/party.json'
import enProfile from './en/profile.json'

export const SUPPORTED_LOCALES = ['en', 'bg'] as const
export type Locale = (typeof SUPPORTED_LOCALES)[number]

export const defaultNS = 'common'

// One namespace per feature; every key must exist in both languages
// (checked by `pnpm check:i18n`).
export const resources = {
  en: {
    common: enCommon,
    auth: enAuth,
    errors: enErrors,
    profile: enProfile,
    admin: enAdmin,
    party: enParty,
    leads: enLeads,
    opportunities: enOpportunities,
    activities: enActivities,
  },
  bg: {
    common: bgCommon,
    auth: bgAuth,
    errors: bgErrors,
    profile: bgProfile,
    admin: bgAdmin,
    party: bgParty,
    leads: bgLeads,
    opportunities: bgOpportunities,
    activities: bgActivities,
  },
} as const

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

export async function initI18n(locale: Locale): Promise<typeof i18n> {
  await i18n.use(initReactI18next).init({
    resources,
    lng: locale,
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LOCALES,
    defaultNS,
    ns: Object.keys(resources.en),
    interpolation: { escapeValue: false }, // React escapes output
    contextSeparator: '|',
    returnNull: false,
  })
  return i18n
}

export default i18n
