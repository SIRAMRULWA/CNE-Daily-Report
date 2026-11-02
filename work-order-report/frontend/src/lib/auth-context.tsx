'use client'

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  authApi, getToken, getUser, setToken, setUser, clearToken,
  isBackendUnavailableError,
} from '@/lib/api'
import type { User, LoginResponse } from '@/types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<LoginResponse>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    const stored = getUser()
    const token = getToken()
    setUserState(stored)

    if (!token) {
      setIsLoading(false)
      return
    }

    authApi.me()
      .then(currentUser => {
        if (!mounted) return
        setUser(currentUser)
        setUserState(currentUser)
        if (
          currentUser.must_change_password &&
          window.location.pathname !== '/admin/change-password' &&
          window.location.pathname !== '/login'
        ) {
          window.location.href = '/admin/change-password'
        }
      })
      .catch((error) => {
        if (!mounted) return
        if (isBackendUnavailableError(error)) return
        clearToken()
        setUserState(null)
      })
      .finally(() => {
        if (mounted) setIsLoading(false)
      })

    return () => { mounted = false }
  }, [])

  const login = useCallback(async (email: string, password: string): Promise<LoginResponse> => {
    const res = await authApi.login(email, password)
    setToken(res.access_token)
    setUser(res.user)
    setUserState(res.user)
    return res
  }, [])

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* ignore */ }
    clearToken()
    setUserState(null)
    window.location.href = '/login'
  }, [])

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
