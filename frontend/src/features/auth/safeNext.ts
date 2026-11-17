/** Only same-site paths are allowed as a post-sign-in destination (no open redirect). */
export function safeNext(value: string | null): string {
  if (!value?.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return '/'
  return value
}
