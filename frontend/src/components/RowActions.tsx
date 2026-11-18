import { Menu } from '@base-ui/react/menu'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { buttonVariants } from '@/components/ui/button'

/** One entry of a row's action menu: a link to a page, or a callback. */
export type RowAction =
  { label: string; to: string } | { label: string; onSelect: () => void; disabled?: boolean }

const itemClass =
  'flex w-full cursor-default items-center rounded-md px-2 py-1.5 text-sm outline-none select-none data-disabled:opacity-50 data-highlighted:bg-muted'

/** UX-08: the "…" menu at the end of a table row. `name` labels it for screen readers. */
export function RowActions({ name, actions }: { name: string; actions: RowAction[] }) {
  const { t } = useTranslation()
  return (
    <Menu.Root>
      <Menu.Trigger
        className={buttonVariants({ variant: 'ghost', size: 'sm' })}
        aria-label={t('table.actionsFor', { name })}
      >
        <svg aria-hidden="true" viewBox="0 0 16 16" className="size-4" fill="currentColor">
          <circle cx="3" cy="8" r="1.5" />
          <circle cx="8" cy="8" r="1.5" />
          <circle cx="13" cy="8" r="1.5" />
        </svg>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={4} className="z-50">
          <Menu.Popup className="min-w-40 rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10 outline-none">
            {actions.map((action) =>
              'to' in action ? (
                <Menu.LinkItem
                  key={action.label}
                  closeOnClick
                  className={itemClass}
                  render={<Link to={action.to} />}
                >
                  {action.label}
                </Menu.LinkItem>
              ) : (
                <Menu.Item
                  key={action.label}
                  className={itemClass}
                  disabled={action.disabled ?? false}
                  onClick={action.onSelect}
                >
                  {action.label}
                </Menu.Item>
              ),
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  )
}
