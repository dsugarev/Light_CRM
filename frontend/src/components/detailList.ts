/**
 * Loop 2: classes for a record's `<dl>` of label/value pairs. Two columns (label, value)
 * from the `sm` breakpoint; on a narrower screen each label sits above its value, so a
 * long Bulgarian label does not squeeze the value. Long values (emails, URLs) wrap.
 * Works with `<dt>`/`<dd>` as direct children or inside `display: contents` wrappers.
 */
export function detailListClass(gap: 'compact' | 'normal' = 'normal'): string {
  return [
    'grid grid-cols-1 gap-y-0.5 text-sm',
    '[&_dd]:mb-2 [&_dd]:min-w-0 [&_dd]:break-words',
    'sm:grid-cols-[max-content_1fr] sm:gap-x-4 sm:[&_dd]:mb-0',
    gap === 'compact' ? 'sm:gap-y-1' : 'sm:gap-y-2',
  ].join(' ')
}
