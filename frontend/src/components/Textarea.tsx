import type { ComponentProps } from 'react'

import { cn } from 'cn'

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      rows={4}
      className={cn(
        'w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  )
}
