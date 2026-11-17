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
import { ProfilePage } from '@/features/profile/ProfilePage'

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
                    children: [{ path: 'settings', element: <SettingsPage /> }],
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
