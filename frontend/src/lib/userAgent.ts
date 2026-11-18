/** FN-02: a browser and operating system name from a user-agent string, for the sessions list. */
export interface DeviceName {
  browser: string | null
  os: string | null
}

// Order matters: Edge and Opera also say "Chrome", Chrome also says "Safari".
const BROWSERS: [RegExp, string][] = [
  [/Edg(e|A|iOS)?\//, 'Edge'],
  [/OPR\/|Opera/, 'Opera'],
  [/Firefox\/|FxiOS\//, 'Firefox'],
  [/Chrome\/|CriOS\//, 'Chrome'],
  [/Safari\//, 'Safari'],
]
const SYSTEMS: [RegExp, string][] = [
  [/Windows/, 'Windows'],
  [/iPhone|iPad|iPod/, 'iOS'],
  [/Android/, 'Android'],
  [/Mac OS X|Macintosh/, 'macOS'],
  [/CrOS/, 'ChromeOS'],
  [/Linux/, 'Linux'],
]

const first = (rules: [RegExp, string][], text: string) =>
  rules.find(([pattern]) => pattern.test(text))?.[1] ?? null

export function describeUserAgent(userAgent: string | null): DeviceName {
  if (!userAgent) return { browser: null, os: null }
  return { browser: first(BROWSERS, userAgent), os: first(SYSTEMS, userAgent) }
}
