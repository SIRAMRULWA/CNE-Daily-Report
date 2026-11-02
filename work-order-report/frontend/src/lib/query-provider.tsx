'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { isBackendUnavailableError } from '@/lib/api'

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => !isBackendUnavailableError(error) && failureCount < 2,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: (failureCount, error) => isBackendUnavailableError(error) && failureCount < 1,
      },
    },
  }))

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
