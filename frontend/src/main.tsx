import './index.css'

import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'

import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { initI18n } from '@/i18n'
import { detectLocale } from '@/lib/locale'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Missing #root element')

await initI18n(detectLocale())

const router = createAppRouter()
// A 401 anywhere means the session ended: go to sign-in and come back afterwards.
const queryClient = createQueryClient(() => {
  const { pathname, search } = router.state.location
  if (pathname !== '/sign-in') {
    void router.navigate(`/sign-in?next=${encodeURIComponent(pathname + search)}`, {
      replace: true,
    })
  }
})

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
