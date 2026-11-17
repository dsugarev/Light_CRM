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

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createAppRouter()} />
    </QueryClientProvider>
  </StrictMode>,
)
