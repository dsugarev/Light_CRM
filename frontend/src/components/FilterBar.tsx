import type { ReactNode } from 'react'

/**
 * UX-13: the filter row above a list. Items wrap instead of shrinking, so long labels
 * (Bulgarian especially) are never cut: the search box takes the free space but no less
 * than 20rem (or the full width on a narrower screen, loop 2), each select is as wide as its chosen option, checkbox labels do not break.
 */
export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 [&>input]:min-w-[min(20rem,100%)] [&>input]:flex-1 [&>label]:whitespace-nowrap [&>select]:w-auto [&>select]:max-w-full">
      {children}
    </div>
  )
}
