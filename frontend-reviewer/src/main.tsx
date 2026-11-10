import '@fontsource-variable/inter'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { ThemeProvider } from 'next-themes'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router'
import { toast } from 'sonner'
import { AuthProvider, RequireAuth } from '@/auth'
import { Header } from '@/components/common'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import Login from '@/pages/Login'
import ReviewerPage from '@/pages/ReviewerPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
  queryCache: new QueryCache({ onError: (error) => toast.error(error.message) }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
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
      </MotionConfig>
    </ThemeProvider>
  </StrictMode>,
)
