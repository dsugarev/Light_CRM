import type { ComponentProps } from 'react'

import { cn } from 'cn'

/** A styled native <select>: accessible and keyboard friendly by default. */
export function NativeSelect({ className, ...props }: ComponentProps<'select'>) {
  return (
    <select
      className={cn(
        'h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  )
}
