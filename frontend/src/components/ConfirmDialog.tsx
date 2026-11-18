import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: ReactNode
  /** Defaults to "Confirm". */
  confirmLabel?: string | undefined
  variant?: 'default' | 'destructive'
  onConfirm: () => void
  onCancel: () => void
}

/**
 * FN-03: the controlled twin of ConfirmButton, for actions started from somewhere that
 * cannot hold a dialog trigger (a row menu). Escape and Cancel call onCancel.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation()
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel()
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        <AlertDialogDescription>{description}</AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('actions.cancel')}</AlertDialogCancel>
          <AlertDialogCancel variant={variant} onClick={onConfirm}>
            {confirmLabel ?? t('actions.confirm')}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
