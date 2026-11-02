import type { Metadata } from 'next'
import '@/styles/globals.css'
import { QueryProvider } from '@/lib/query-provider'
import { AuthProvider } from '@/lib/auth-context'
import { ReportDateProvider } from '@/lib/report-date-context'
import { BackendUnavailableDialog } from '@/components/ui/BackendUnavailableDialog'
import { Toaster } from 'sonner'

export const metadata: Metadata = {
  title: 'Vodacom INTEL Operations',
  description: 'ITIL Group Reports — Internal Operations Platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <QueryProvider>
          <AuthProvider>
            <ReportDateProvider>
              {children}
              <BackendUnavailableDialog />
              <Toaster
                position="bottom-right"
                toastOptions={{
                  style: {
                    background: '#fff',
                    border: '1px solid #E5E5E5',
                    color: '#1A1A1A',
                    fontSize: '13px',
                  },
                }}
              />
            </ReportDateProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
