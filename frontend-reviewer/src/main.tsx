import '@fontsource-variable/inter'
import { captureException, ErrorBoundary, init } from '@sentry/react'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { ThemeProvider } from 'next-themes'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router'
import { toast } from 'sonner'
import { ApiError } from '@/api'
import { AuthProvider, RequireAuth } from '@/auth'
import { ErrorFallback, Header } from '@/components/common'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import Login from '@/pages/Login'
import ReviewerPage from '@/pages/ReviewerPage'
import './index.css'

// 4xx API errors are expected (validation, auth, conflicts); only report 5xx and unexpected exceptions.
const isExpected = (error: unknown) => error instanceof ApiError && error.status < 500
const report = (error: Error) => !isExpected(error) && captureException(error)

if (import.meta.env.VITE_SENTRY_DSN)
  init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || 'development',
    // SDK v11 replaced `sendDefaultPii: false` with per-category switches; collect no personal data.
    dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
    tracesSampleRate: 0,
    initialScope: { tags: { app: 'reviewer' } },
    beforeSend: (event, hint) => (isExpected(hint.originalException) ? null : event),
  })

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
  queryCache: new QueryCache({
    onError: (error) => {
      report(error)
      toast.error(error.message)
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      report(error)
      if (!mutation.options.onError) toast.error(error.message)
    },
  }),
})

function Layout() {
  return (
    <div className="min-h-svh">
      <Header />
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <MotionConfig reducedMotion="user">
        <ErrorBoundary fallback={<ErrorFallback />}>
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <AuthProvider>
                <TooltipProvider delayDuration={300}>
                  <Routes>
                    <Route path="/login" element={<Login />} />
                    <Route element={<RequireAuth />}>
                      <Route element={<Layout />}>
                        <Route index element={<ReviewerPage />} />
                      </Route>
                    </Route>
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </TooltipProvider>
              </AuthProvider>
            </BrowserRouter>
            <Toaster />
          </QueryClientProvider>
        </ErrorBoundary>
      </MotionConfig>
    </ThemeProvider>
  </StrictMode>,
)
