/** The address as stored, made absolute; anything but http(s) is shown as plain text. */
export function websiteHref(website: string): string | null {
  const candidate = /^[a-z][a-z\d+.-]*:/i.test(website) ? website : `https://${website}`
  try {
    const url = new URL(candidate)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}
