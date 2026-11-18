import './lib/zodConfig'
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
// A 401 ends the session: RequireAuth sends the user to sign-in and back (FN-04).
const queryClient = createQueryClient()

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
