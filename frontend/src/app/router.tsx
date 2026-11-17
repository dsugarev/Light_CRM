import { createBrowserRouter, type RouteObject } from 'react-router'

import { AuditEntryPage } from '@/features/admin/AuditEntryPage'
import { AuditLogPage } from '@/features/admin/AuditLogPage'
import { SettingsPage } from '@/features/admin/SettingsPage'
import { UserDetailPage } from '@/features/admin/UserDetailPage'
import { UserNewPage } from '@/features/admin/UserNewPage'
import { UsersPage } from '@/features/admin/UsersPage'
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage'
import { RequireAuth, RequirePermission } from '@/features/auth/RequireAuth'
import { SetPasswordPage } from '@/features/auth/SetPasswordPage'
import { SignInPage } from '@/features/auth/SignInPage'
import { ReferenceListPage } from '@/features/admin/ReferenceListPage'
import {
  ContactEditPage,
  ContactNewPage,
  ContactPage,
  ContactsPage,
} from '@/features/contacts/ContactPages'
import {
  OrganizationEditPage,
  OrganizationNewPage,
} from '@/features/organizations/OrganizationEditorPages'
import { OrganizationPage } from '@/features/organizations/OrganizationPage'
import { OrganizationsPage } from '@/features/organizations/OrganizationsPage'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { SearchPage } from '@/features/search/SearchPage'
import { MyTasksPage } from '@/features/activities/MyTasksPage'
import { WinLossPage } from '@/features/reports/WinLossPage'
import { ConvertPage } from '@/features/leads/ConvertPage'
import { LeadPage } from '@/features/leads/LeadPage'
import { LeadEditPage, LeadNewPage, LeadsPage } from '@/features/leads/LeadPages'
import { BoardPage } from '@/features/opportunities/BoardPage'
import {
  OpportunitiesPage,
  OpportunityEditPage,
  OpportunityNewPage,
} from '@/features/opportunities/OpportunityPages'
import { OpportunityPage } from '@/features/opportunities/OpportunityPage'
import { StagesPage } from '@/features/opportunities/StagesPage'

import { AppLayout } from './AppLayout'
import { HomePage } from './HomePage'
import { NotFoundPage } from './NotFoundPage'
import { RouteError } from './RouteError'

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { path: 'sign-in', element: <SignInPage /> },
          { path: 'set-password', element: <SetPasswordPage /> },
          { path: 'forgot-password', element: <ForgotPasswordPage /> },
          {
            element: <RequireAuth />,
            children: [
              { index: true, element: <HomePage /> },
              { path: 'profile', element: <ProfilePage /> },
              { path: 'search', element: <SearchPage /> },
              { path: 'organizations', element: <OrganizationsPage /> },
              { path: 'organizations/:orgId', element: <OrganizationPage /> },
              { path: 'contacts', element: <ContactsPage /> },
              { path: 'contacts/:contactId', element: <ContactPage /> },
              { path: 'leads', element: <LeadsPage /> },
              { path: 'leads/:leadId', element: <LeadPage /> },
              { path: 'tasks', element: <MyTasksPage /> },
              { path: 'reports/win-loss', element: <WinLossPage /> },
              { path: 'opportunities', element: <OpportunitiesPage /> },
              { path: 'opportunities/board', element: <BoardPage /> },
              { path: 'opportunities/:opportunityId', element: <OpportunityPage /> },
              {
                element: <RequirePermission permission="records.create" />,
                children: [
                  { path: 'organizations/new', element: <OrganizationNewPage /> },
                  { path: 'contacts/new', element: <ContactNewPage /> },
                  { path: 'leads/new', element: <LeadNewPage /> },
                  { path: 'opportunities/new', element: <OpportunityNewPage /> },
                ],
              },
              {
                element: <RequirePermission permission="records.edit_own" />,
                children: [
                  { path: 'organizations/:orgId/edit', element: <OrganizationEditPage /> },
                  { path: 'contacts/:contactId/edit', element: <ContactEditPage /> },
                  { path: 'leads/:leadId/edit', element: <LeadEditPage /> },
                  { path: 'leads/:leadId/convert', element: <ConvertPage /> },
                  { path: 'opportunities/:opportunityId/edit', element: <OpportunityEditPage /> },
                ],
              },
              {
                path: 'admin',
                children: [
                  {
                    element: <RequirePermission permission="users.manage" />,
                    children: [
                      { path: 'users', element: <UsersPage /> },
                      { path: 'users/new', element: <UserNewPage /> },
                      { path: 'users/:userId', element: <UserDetailPage /> },
                    ],
                  },
                  {
                    element: <RequirePermission permission="audit.read" />,
                    children: [
                      { path: 'audit-log', element: <AuditLogPage /> },
                      { path: 'audit-log/:entryId', element: <AuditEntryPage /> },
                    ],
                  },
                  {
                    element: <RequirePermission permission="settings.manage" />,
                    children: [
                      { path: 'settings', element: <SettingsPage /> },
                      { path: 'reference/:list', element: <ReferenceListPage /> },
                      { path: 'stages', element: <StagesPage /> },
                    ],
                  },
                ],
              },
            ],
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
