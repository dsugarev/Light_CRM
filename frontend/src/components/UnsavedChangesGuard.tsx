import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker } from 'react-router'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

/**
 * UX-11: while `when` is true, leaving the page asks first. In-app navigation shows a
 * dialog (stay or leave); closing the tab or reloading gets the browser's own prompt.
 * Forms pass `isDirty && !isSubmitting && !isSubmitSuccessful`, so saving never asks.
 */
export function UnsavedChangesGuard({ when }: { when: boolean }) {
  const { t } = useTranslation()
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      when &&
      // A lost session (FN-04) goes to sign-in regardless: the changes could not be saved.
      nextLocation.pathname !== '/sign-in' &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  )

  useEffect(() => {
    if (!when) return undefined
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
    }
  }, [when])

  return (
    <AlertDialog
      open={blocker.state === 'blocked'}
      onOpenChange={(open) => {
        if (!open && blocker.state === 'blocked') blocker.reset()
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>{t('form.unsavedTitle')}</AlertDialogTitle>
        <AlertDialogDescription>{t('form.unsavedText')}</AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('form.stay')}</AlertDialogCancel>
          <AlertDialogCancel
            variant="destructive"
            onClick={() => {
              if (blocker.state === 'blocked') blocker.proceed()
            }}
          >
            {t('form.leave')}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
