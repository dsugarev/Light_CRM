import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import type { paths } from '@/api/schema'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { RelativeTime } from '@/components/RelativeTime'
import { SearchInput } from '@/components/SearchInput'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { useListParams } from '@/lib/useListParams'
import { useNotify } from '@/lib/notify'

import { HUMAN_ROLES, type HumanRole } from './roles'
import { CreateUserSheet, EditUserSheet } from './UserSheets'

type User = Schemas['UserOut']
type UserSort = NonNullable<
  NonNullable<paths['/api/v1/users']['get']['parameters']['query']>['sort']
>
const PAGE_SIZE = 25
// The sort values GET /users accepts (API spec section 5); anything else falls back to name.
const USER_SORTS: readonly UserSort[] = [
  'name',
  '-name',
  'email',
  '-email',
  'role',
  '-role',
  'last_login_at',
  '-last_login_at',
]
const userSort = (sort: string): UserSort => USER_SORTS.find((value) => value === sort) ?? 'name'

export function UserStatus({ user }: { user: Schemas['UserOut'] }) {
  const { t } = useTranslation('admin')
  if (!user.is_active) return <Badge variant="outline">{t('users.status.inactive')}</Badge>
  if (user.is_locked) return <Badge variant="destructive">{t('users.status.locked')}</Badge>
  return <Badge variant="secondary">{t('users.status.active')}</Badge>
}

/**
 * FR-ADM-01, UX-08: search, filters and sort live in the URL so a view can be shared.
 * UX-09: `/admin/users/new` shows this list with the create sheet open.
 */
export function UsersPage({ creating = false }: { creating?: boolean }) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const notify = useNotify()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { search } = useLocation()
  const [editing, setEditing] = useState<User | null>(null)
  const list = useListParams({ sort: 'name', filters: ['role', 'status'] as const })
  const role = list.filters.role[0] ?? ''
  const status = list.filters.status[0] ?? ''

  const users = useQuery({
    queryKey: ['users', list.key],
    // Keep showing the current rows while the next page, sort or filter loads.
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/users', {
          params: {
            query: {
              page: list.page,
              page_size: PAGE_SIZE,
              sort: userSort(list.sort),
              ...(list.q ? { q: list.q } : {}),
              ...(role ? { role: role as HumanRole } : {}),
              ...(status ? { is_active: status === 'active' } : {}),
            },
          },
        }),
      ),
  })
  const unlock = useMutation({
    mutationFn: (userId: string) =>
      call(api.POST('/api/v1/users/{user_id}/unlock', { params: { path: { user_id: userId } } })),
    onSuccess: async () => {
      notify.success(t('userDetail.done.unlocked'))
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (error) => {
      notify.error(error)
    },
  })

  const columns: Column<User>[] = [
    {
      key: 'name',
      header: t('users.columns.name'),
      sortKey: 'name',
      cell: (user) => (
        <Link to={`/admin/users/${user.id}`} className="font-medium hover:underline">
          {user.full_name}
        </Link>
      ),
    },
    {
      key: 'email',
      header: t('users.columns.email'),
      sortKey: 'email',
      // On the detail page too; hidden on narrow screens so the table fits without scrolling.
      className: 'hidden lg:table-cell',
      cell: (user) => user.email,
    },
    {
      key: 'role',
      header: t('users.columns.role'),
      sortKey: 'role',
      cell: (user) => tc(`roles.${user.role}`),
    },
    {
      key: 'status',
      header: t('users.columns.status'),
      cell: (user) => <UserStatus user={user} />,
    },
    {
      key: 'lastLogin',
      header: t('users.columns.lastLogin'),
      sortKey: 'last_login_at',
      cell: (user) =>
        user.last_login_at ? <RelativeTime iso={user.last_login_at} /> : t('users.never'),
    },
  ]

  return (
    <section className="mx-auto max-w-5xl">
      <PageHeader
        title={t('users.title')}
        actions={
          <Link to={{ pathname: '/admin/users/new', search }} className={buttonVariants()}>
            {t('users.new')}
          </Link>
        }
      />
      <FilterBar>
        <SearchInput
          label={t('users.search')}
          value={list.q}
          onChange={(q) => {
            list.update({ q })
          }}
        />
        <NativeSelect
          aria-label={t('users.role')}
          value={role}
          onChange={(e) => {
            list.update({ role: e.target.value })
          }}
        >
          <option value="">{t('users.allRoles')}</option>
          {HUMAN_ROLES.map((r) => (
            <option key={r} value={r}>
              {tc(`roles.${r}`)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label={t('users.statusFilter')}
          value={status}
          onChange={(e) => {
            list.update({ status: e.target.value })
          }}
        >
          <option value="">{t('users.allStatuses')}</option>
          <option value="active">{t('users.status.active')}</option>
          <option value="inactive">{t('users.status.inactive')}</option>
        </NativeSelect>
      </FilterBar>
      {users.isError ? (
        <ErrorState
          error={users.error}
          onRetry={() => {
            void users.refetch()
          }}
        />
      ) : users.data ? (
        <>
          <div className="overflow-x-auto">
            <DataTable
              caption={t('users.title')}
              columns={columns}
              rows={users.data.items}
              rowKey={(user) => user.id}
              sort={list.sort}
              onSort={(sort) => {
                list.update({ sort })
              }}
              rowLabel={(user) => user.full_name}
              rowActions={(user) => [
                { label: t('users.open'), to: `/admin/users/${user.id}` },
                {
                  label: tc('actions.edit'),
                  onSelect: () => {
                    setEditing(user)
                  },
                },
                ...(user.is_locked && user.is_active
                  ? [
                      {
                        label: t('userDetail.unlock'),
                        disabled: unlock.isPending,
                        onSelect: () => {
                          unlock.mutate(user.id)
                        },
                      },
                    ]
                  : []),
              ]}
            />
          </div>
          <Pagination
            page={list.page}
            pageSize={PAGE_SIZE}
            total={users.data.total}
            onPageChange={(p) => {
              list.update({ page: String(p) })
            }}
          />
        </>
      ) : (
        <Loading variant="table" />
      )}
      <CreateUserSheet
        open={creating}
        onClose={() => {
          void navigate({ pathname: '/admin/users', search }, { replace: true })
        }}
      />
      <EditUserSheet
        user={editing}
        onClose={() => {
          setEditing(null)
        }}
      />
    </section>
  )
}
