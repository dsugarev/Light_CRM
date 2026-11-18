import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { createQueryClient } from '@/app/queryClient'
import { routes } from '@/app/router'
import i18n, { type Locale } from '@/i18n'

export async function renderApp(path = '/', locale: Locale = 'en') {
  await i18n.changeLanguage(locale)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const queryClient = createQueryClient(() => {
    void router.navigate('/sign-in')
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...view, router, queryClient }
}
