import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router'
import { api, ApiError, setUnauthenticatedHandler, type Me } from '@/api'

const REQUIRED_PERMISSION = 'document:review'

type Auth = {
  user: Me | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<Auth | null>(null)

async function authorizedUser() {
  const user = await api.me()
  if (user.permissions.includes(REQUIRED_PERMISSION)) return user
  await api.logout()
  return null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setUnauthenticatedHandler(() => setUser(null))
    api
      .restoreSession()
      .then((restored) => (restored ? authorizedUser() : null))
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [])

  const login = async (email: string, password: string) => {
    await api.login(email, password)
    const authorized = await authorizedUser()
    if (!authorized) throw new ApiError(401, 'UNAUTHENTICATED', 'Invalid email or password')
    setUser(authorized)
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

export function RequireAuth() {
  const { user } = useAuth()
  return user ? <Outlet /> : <Navigate to="/login" replace />
}
