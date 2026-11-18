import { Dialog } from '@base-ui/react/dialog'
import type { ReactNode } from 'react'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  /** Accessible label of the close button. */
  closeLabel: string
  side?: 'left' | 'right'
  className?: string
  children: ReactNode
}

/**
 * UX-09: a panel that slides in from the side, over the page (base-ui Dialog: focus is
 * trapped, Escape and the backdrop close it, focus returns to what opened it).
 */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  closeLabel,
  side = 'right',
  className,
  children,
}: SheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-overlay/20" />
        <Dialog.Popup
          className={cn(
            'fixed inset-y-0 z-50 flex w-full flex-col gap-4 overflow-y-auto bg-background p-4 shadow-lg outline-none',
            side === 'left' ? 'left-0 max-w-[85vw] sm:w-72' : 'right-0 max-w-[100vw] sm:w-[28rem]',
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="text-sm text-muted-foreground">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
              {closeLabel}
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
