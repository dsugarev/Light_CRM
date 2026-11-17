import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { SignInPage } from '@/features/auth/SignInPage'

import { AppLayout } from './AppLayout'
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
          // Until Phase 1 adds authentication, the start page is the sign-in page.
          { index: true, element: <Navigate to="/sign-in" replace /> },
          { path: 'sign-in', element: <SignInPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
