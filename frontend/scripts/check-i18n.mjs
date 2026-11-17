// Fails when a translation key exists in one language and not the other
// (FR-I18N-02), or when a namespace file is missing in a language.
import { readdir, readFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '../src/i18n')
const LOCALES = ['en', 'bg']

function flatten(value, prefix = '') {
  if (value === null || typeof value !== 'object') return [prefix]
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  )
}

const keysByLocale = {}
for (const locale of LOCALES) {
  const keys = new Set()
  for (const file of (await readdir(join(ROOT, locale))).filter((f) => f.endsWith('.json'))) {
    const namespace = file.replace(/\.json$/, '')
    const content = JSON.parse(await readFile(join(ROOT, locale, file), 'utf8'))
    for (const key of flatten(content)) keys.add(`${namespace}:${key}`)
  }
  keysByLocale[locale] = keys
}

const problems = []
for (const locale of LOCALES) {
  for (const other of LOCALES.filter((l) => l !== locale)) {
    for (const key of keysByLocale[locale]) {
      if (!keysByLocale[other].has(key))
        problems.push(`${key} is in ${locale} but missing in ${other}`)
    }
  }
}

if (problems.length > 0) {
  console.error(`i18n check failed:\n  ${problems.join('\n  ')}`)
  process.exit(1)
}
console.log(`i18n check passed: ${keysByLocale.en.size} keys in ${LOCALES.join(', ')}`)
