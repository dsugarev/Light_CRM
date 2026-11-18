import { Menu } from '@base-ui/react/menu'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { buttonVariants } from '@/components/ui/button'
import { SUPPORTED_LOCALES, type Locale } from '@/i18n'
import { useChangeLocale } from '@/features/system/useChangeLocale'

const itemClass =
  'flex w-full cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-muted'

/** UX-02: the top-bar user menu: profile, language and sign out. */
export function UserMenu({ fullName, onSignOut }: { fullName: string; onSignOut: () => void }) {
  const { t, i18n } = useTranslation()
  const changeLocale = useChangeLocale()

  return (
    <Menu.Root>
      <Menu.Trigger
        className={buttonVariants({ variant: 'ghost', size: 'sm' })}
        aria-label={t('nav.accountMenu', { name: fullName })}
      >
        {fullName}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={4} className="z-50">
          <Menu.Popup className="min-w-48 rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10 outline-none">
            <Menu.LinkItem closeOnClick className={itemClass} render={<Link to="/profile" />}>
              {t('nav.profile')}
            </Menu.LinkItem>
            <Menu.Separator className="my-1 h-px bg-border" />
            <Menu.Group>
              <Menu.GroupLabel className="px-2 py-1 text-xs text-muted-foreground">
                {t('language.label')}
              </Menu.GroupLabel>
              <Menu.RadioGroup
                value={i18n.resolvedLanguage}
                onValueChange={(value: Locale) => {
                  changeLocale(value)
                }}
              >
                {SUPPORTED_LOCALES.map((locale) => (
                  <Menu.RadioItem key={locale} value={locale} lang={locale} className={itemClass}>
                    <span className="flex w-3 justify-center" aria-hidden="true">
                      <Menu.RadioItemIndicator className="block size-1.5 rounded-full bg-foreground" />
                    </span>
                    {t(`language.${locale}`)}
                  </Menu.RadioItem>
                ))}
              </Menu.RadioGroup>
            </Menu.Group>
            <Menu.Separator className="my-1 h-px bg-border" />
            <Menu.Item className={itemClass} onClick={onSignOut}>
              {t('nav.signOut')}
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  )
}
