import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

interface ConfirmButtonProps {
  label: string
  title: string
  description: ReactNode
  onConfirm: () => void
  disabled?: boolean
  variant?: 'default' | 'destructive' | 'outline'
  size?: 'default' | 'sm'
}

/** UX-05: the one confirmation for destructive actions (never window.confirm). */
export function ConfirmButton({
  label,
  title,
  description,
  onConfirm,
  disabled = false,
  variant = 'outline',
  size = 'default',
}: ConfirmButtonProps) {
  const { t } = useTranslation()
  return (
    <AlertDialog>
      <AlertDialogTrigger render={<Button variant={variant} size={size} disabled={disabled} />}>
        {label}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        <AlertDialogDescription>{description}</AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('actions.cancel')}</AlertDialogCancel>
          <AlertDialogCancel
            variant={variant === 'destructive' ? 'destructive' : 'default'}
            onClick={onConfirm}
          >
            {t('actions.confirm')}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
