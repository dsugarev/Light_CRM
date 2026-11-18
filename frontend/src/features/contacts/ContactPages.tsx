import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, asPage, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Pagination } from '@/components/Pagination'
import { SearchInput } from '@/components/SearchInput'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useCanEditOwned } from '@/features/auth/useOwnership'
import { formatDate } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useListParams } from '@/lib/useListParams'
import { useLocale } from '@/lib/useLocale'
import { RecordTimeline } from '@/features/activities/RecordTimeline'
import { ExternalReferences } from '@/features/integrations/ExternalReferences'
import { ExportMenu } from '@/features/reports/ExportMenu'

import { ContactForm } from './ContactForm'
import { contactDefaults, contactPayload, type ContactValues } from './contactValues'
import { PersonalData } from './PersonalData'

type Contact = Schemas['ContactOut']
const PAGE_SIZE = 25

export function ContactsPage() {
  const { t } = useTranslation('party')
  const can = useCan()
  const list = useListParams({ sort: 'last_name', filters: ['owner_id'] as const })
  const contacts = useQuery({
    queryKey: ['contacts', list.key],
    // Keep showing the current rows while the next page, sort or filter loads.
    placeholderData: keepPreviousData,
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/contacts', {
            params: { query: { ...list.apiQuery, page_size: PAGE_SIZE } },
          }),
        ),
      ),
  })
  const columns: Column<Contact>[] = [
    {
      key: 'name',
      header: t('contacts.columns.name'),
      sortKey: 'last_name',
      cell: (c) => (
        <span className="flex items-center gap-2">
          <Link to={`/contacts/${c.id}`} className="font-medium hover:underline">
            {c.full_name}
          </Link>
          {c.archived_at ? <Badge variant="outline">{t('organizations.archived')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'organization',
      header: t('contacts.columns.organization'),
      cell: (c) =>
        c.organization ? (
          <Link to={`/organizations/${c.organization.id}`} className="hover:underline">
            {c.organization.name}
          </Link>
        ) : (
          ''
        ),
    },
    { key: 'job', header: t('contacts.columns.jobTitle'), cell: (c) => c.job_title ?? '' },
    { key: 'email', header: t('contacts.columns.email'), cell: (c) => c.email ?? '' },
    { key: 'owner', header: t('contacts.columns.owner'), cell: (c) => c.owner.full_name },
  ]
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader
        title={t('contacts.title')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ExportMenu path="/api/v1/contacts/export" query={list.apiQuery} />
            {can('records.create') ? (
              <Link to="/contacts/new" className={buttonVariants()}>
                {t('contacts.new')}
              </Link>
            ) : null}
          </div>
        }
      />
      <div className="mb-4 grid items-center gap-3 sm:grid-cols-[2fr_1fr_auto]">
        <SearchInput
          label={t('contacts.search')}
          value={list.q}
          onChange={(q) => {
            list.update({ q })
          }}
        />
        <NativeSelect
          aria-label={t('organizations.filters.owner')}
          value={list.filters.owner_id[0] ?? ''}
          onChange={(e) => {
            list.update({ owner_id: e.target.value || null })
          }}
        >
          <option value="">{t('organizations.filters.everyone')}</option>
          <option value="me">{t('organizations.filters.mine')}</option>
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={list.archived}
            onChange={(e) => {
              list.update({ archived: e.target.checked ? '1' : null })
            }}
          />
          {t('organizations.filters.archived')}
        </label>
      </div>
      {contacts.isError ? (
        <ErrorState
          error={contacts.error}
          onRetry={() => {
            void contacts.refetch()
          }}
        />
      ) : null}
      {contacts.data ? (
        <>
          <DataTable
            caption={t('contacts.title')}
            columns={columns}
            rows={contacts.data.items}
            rowKey={(c) => c.id}
            sort={list.sort}
            onSort={(sort) => {
              list.update({ sort })
            }}
          />
          <Pagination
            page={list.page}
            pageSize={PAGE_SIZE}
            total={contacts.data.total}
            onPageChange={(page) => {
              list.update({ page: String(page) })
            }}
          />
        </>
      ) : contacts.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}

function useAfterSave() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return async (contact: Contact, message: string) => {
    await queryClient.invalidateQueries({ queryKey: ['contacts'] })
    await queryClient.invalidateQueries({ queryKey: ['organizations'] })
    toast.success(message)
    await navigate(`/contacts/${contact.id}`)
  }
}

export function ContactNewPage() {
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const [params] = useSearchParams()
  const organizationId = params.get('organization_id')
  const afterSave = useAfterSave()
  const organization = useQuery({
    queryKey: ['organizations', organizationId],
    queryFn: () =>
      call(
        api.GET('/api/v1/organizations/{org_id}', {
          params: { path: { org_id: organizationId ?? '' } },
        }),
      ),
    enabled: organizationId !== null,
  })
  const create = useMutation({
    mutationFn: ({ values, confirm }: { values: ContactValues; confirm: boolean }) =>
      call(
        api.POST('/api/v1/contacts', {
          body: { ...contactPayload(values), confirm_duplicate: confirm },
        }),
      ),
    onSuccess: (contact) => afterSave(contact, t('contact.toasts.created')),
  })
  if (organizationId && organization.isPending) return <Loading variant="form" />
  const preset = organization.data
    ? { id: organization.data.id, name: organization.data.name }
    : null
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={t('contact.createTitle')} breadcrumbs={[crumbs.contacts]} />
      <Card>
        <CardContent>
          <ContactForm
            defaultValues={contactDefaults(undefined, preset)}
            submitLabel={t('contact.create')}
            pending={create.isPending}
            isEdit={false}
            onSubmit={(values, confirm) => create.mutateAsync({ values, confirm })}
          />
        </CardContent>
      </Card>
    </section>
  )
}

export function ContactEditPage() {
  const { contactId = '' } = useParams()
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const afterSave = useAfterSave()
  const path = { params: { path: { contact_id: contactId } } }
  const contact = useQuery({
    queryKey: ['contacts', contactId],
    queryFn: () => call(api.GET('/api/v1/contacts/{contact_id}', path)),
  })
  const save = useMutation({
    mutationFn: ({ values, confirm }: { values: ContactValues; confirm: boolean }) =>
      call(
        api.PATCH('/api/v1/contacts/{contact_id}', {
          ...path,
          body: { ...contactPayload(values), confirm_duplicate: confirm },
        }),
      ),
    onSuccess: (c) => afterSave(c, t('contact.toasts.saved')),
  })
  if (contact.isError)
    return (
      <ErrorState
        error={contact.error}
        onRetry={() => {
          void contact.refetch()
        }}
      />
    )
  if (!contact.data) return <Loading variant="form" />
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader
        title={t('contact.editTitle')}
        breadcrumbs={[
          crumbs.contacts,
          { label: contact.data.full_name, to: `/contacts/${contactId}` },
        ]}
      />
      <Card>
        <CardContent>
          <ContactForm
            defaultValues={contactDefaults(contact.data)}
            submitLabel={tc('actions.save')}
            pending={save.isPending}
            isEdit
            onSubmit={(values, confirm) => save.mutateAsync({ values, confirm })}
          />
        </CardContent>
      </Card>
    </section>
  )
}

export function ContactPage() {
  const { contactId = '' } = useParams()
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const can = useCan()
  const canEdit = useCanEditOwned()
  const queryClient = useQueryClient()
  const path = { params: { path: { contact_id: contactId } } }
  const contact = useQuery({
    queryKey: ['contacts', contactId],
    queryFn: () => call(api.GET('/api/v1/contacts/{contact_id}', path)),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['contacts'] })
  const archive = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/contacts/{contact_id}', path)),
    onSuccess: async () => {
      await refresh()
      toast.success(t('contact.toasts.archived'))
    },
  })
  const restore = useMutation({
    mutationFn: () => call(api.POST('/api/v1/contacts/{contact_id}/restore', path)),
    onSuccess: async () => {
      await refresh()
      toast.success(t('contact.toasts.restored'))
    },
  })
  if (contact.isError)
    return (
      <ErrorState
        error={contact.error}
        onRetry={() => {
          void contact.refetch()
        }}
      />
    )
  if (!contact.data) return <Loading />
  const c = contact.data
  const mayManageGdpr = can('gdpr.manage')
  // An anonymized contact cannot be edited: that would add personal data back (FR-ADM-04).
  const editable = canEdit(c.owner.id) && !c.anonymized_at
  const actionError = [archive.error, restore.error].find((e) => e instanceof ApiError)
  const rows: [string, React.ReactNode][] = [
    [t('contact.fields.jobTitle'), c.job_title],
    [
      t('contact.fields.email'),
      c.email ? (
        <a href={`mailto:${c.email}`} className="hover:underline">
          {c.email}
        </a>
      ) : null,
    ],
    [
      t('contact.fields.phone'),
      c.phone ? (
        <a href={`tel:${c.phone}`} className="hover:underline">
          {c.phone}
        </a>
      ) : null,
    ],
    [
      t('contact.fields.preferredLocale'),
      c.preferred_locale ? tc(`language.${c.preferred_locale}`) : null,
    ],
    [
      t('contact.fields.organization'),
      c.organization ? (
        <Link to={`/organizations/${c.organization.id}`} className="hover:underline">
          {c.organization.name}
        </Link>
      ) : (
        t('contact.noOrganization')
      ),
    ],
  ]
  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title={c.full_name}
        breadcrumbs={[crumbs.contacts]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {c.archived_at ? (
              <Badge variant="outline">
                {t('organization.detail.archivedOn', { date: formatDate(c.archived_at, locale) })}
              </Badge>
            ) : null}
            {c.anonymized_at ? (
              <Badge variant="outline">
                {t('contact.gdpr.anonymizedOn', { date: formatDate(c.anonymized_at, locale) })}
              </Badge>
            ) : null}
            {editable && !c.archived_at ? (
              <Link
                to={`/contacts/${c.id}/edit`}
                className={buttonVariants({ variant: 'outline' })}
              >
                {t('contact.detail.edit')}
              </Link>
            ) : null}
            {editable && !c.archived_at ? (
              <ConfirmButton
                label={t('contact.detail.archive')}
                title={t('contact.detail.archive')}
                description={t('contact.detail.confirmArchive', { name: c.full_name })}
                variant="destructive"
                onConfirm={() => {
                  archive.mutate()
                }}
              />
            ) : null}
            {c.archived_at && can('records.restore') ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  restore.mutate()
                }}
              >
                {t('contact.detail.restore')}
              </Button>
            ) : null}
          </div>
        }
      />
      <FormMessage error={actionError instanceof ApiError ? actionError.code : null} />
      <Card>
        <CardContent>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd>{value ?? t('contact.notSet')}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">
            {t('contact.detail.ownerNote', { name: c.owner.full_name })}
          </p>
          {c.notes ? <p className="mt-4 whitespace-pre-wrap text-sm">{c.notes}</p> : null}
        </CardContent>
      </Card>
      <ExternalReferences resource="contacts" id={c.id} />
      {mayManageGdpr ? <PersonalData contact={c} /> : null}
      <RecordTimeline record={{ kind: 'contact', id: c.id }} canLog={!c.archived_at} />
    </section>
  )
}
