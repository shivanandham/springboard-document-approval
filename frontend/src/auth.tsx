import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'
import { api, setUnauthenticatedHandler, type Me } from '@/api'

type Auth = {
  user: Me | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setUnauthenticatedHandler(() => setUser(null))
    api
      .restoreSession()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [])

  const login = async (email: string, password: string) => {
    await api.login(email, password)
    setUser(await api.me())
  }

  const logout = async () => {
    await api.logout()
    setUser(null)
    queryClient.clear()
  }

  if (!ready) return null
  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used within AuthProvider')
  return auth
}

export const homePath = (user: Me) => (user.permissions.includes('document:review') ? '/review' : '/submit')

export function RequireHome() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  if (!user) return <Navigate to="/login" replace />
  if (pathname !== homePath(user)) return <Navigate to={homePath(user)} replace />
  return <Outlet />
}
