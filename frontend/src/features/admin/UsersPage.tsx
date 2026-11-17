import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { HUMAN_ROLES, type HumanRole } from './roles'

const PAGE_SIZE = 25

export function UserStatus({ user }: { user: Schemas['UserOut'] }) {
  const { t } = useTranslation('admin')
  if (!user.is_active) return <Badge variant="outline">{t('users.status.inactive')}</Badge>
  if (user.is_locked) return <Badge variant="destructive">{t('users.status.locked')}</Badge>
  return <Badge variant="secondary">{t('users.status.active')}</Badge>
}

/** FR-ADM-01. Filters live in the URL so a view can be shared (generalised in Phase 2). */
export function UsersPage() {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const role = params.get('role') ?? ''
  const status = params.get('status') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: true })
  }

  const users = useQuery({
    queryKey: ['users', { q, role, status, page }],
    // Keep showing the current rows while the next page, sort or filter loads.
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/users', {
          params: {
            query: {
              page,
              page_size: PAGE_SIZE,
              ...(q ? { q } : {}),
              ...(role ? { role: role as HumanRole } : {}),
              ...(status ? { is_active: status === 'active' } : {}),
            },
          },
        }),
      ),
  })

  return (
    <section className="mx-auto max-w-5xl">
      <PageHeader
        title={t('users.title')}
        actions={
          <Link to="/admin/users/new" className={buttonVariants()}>
            {t('users.new')}
          </Link>
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-[2fr_1fr_1fr]">
        <Input
          type="search"
          aria-label={t('users.search')}
          placeholder={t('users.search')}
          defaultValue={q}
          onChange={(e) => {
            update({ q: e.target.value.trim() })
          }}
        />
        <NativeSelect
          aria-label={t('users.role')}
          value={role}
          onChange={(e) => {
            update({ role: e.target.value })
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
            update({ status: e.target.value })
          }}
        >
          <option value="">{t('users.allStatuses')}</option>
          <option value="active">{t('users.status.active')}</option>
          <option value="inactive">{t('users.status.inactive')}</option>
        </NativeSelect>
      </div>
      {users.data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('users.columns.name')}</TableHead>
                <TableHead>{t('users.columns.email')}</TableHead>
                <TableHead>{t('users.columns.role')}</TableHead>
                <TableHead>{t('users.columns.status')}</TableHead>
                <TableHead>{t('users.columns.lastLogin')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    {tc('states.empty')}
                  </TableCell>
                </TableRow>
              ) : (
                users.data.items.map((user) => (
                  <TableRow
                    key={user.id}
                    className="cursor-pointer"
                    onClick={() => void navigate(`/admin/users/${user.id}`)}
                  >
                    <TableCell>
                      <Link to={`/admin/users/${user.id}`} className="font-medium hover:underline">
                        {user.full_name}
                      </Link>
                    </TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>{tc(`roles.${user.role}`)}</TableCell>
                    <TableCell>
                      <UserStatus user={user} />
                    </TableCell>
                    <TableCell>
                      {user.last_login_at
                        ? formatDateTime(user.last_login_at, locale)
                        : t('users.never')}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={users.data.total}
            onPageChange={(p) => {
              update({ page: String(p) })
            }}
          />
        </>
      ) : (
        <Loading />
      )}
    </section>
  )
}
