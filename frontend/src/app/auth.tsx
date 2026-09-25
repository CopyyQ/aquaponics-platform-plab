import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { loadSession, logout as logoutRequest } from "@/api/resources"
import type { Session } from "@/api/contracts"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearStoredAccessToken,
  refreshAccessToken,
} from "@/shared/api/auth-refresh"
import { queryClient } from "@/shared/api/query-client"

interface AuthState {
  session: Session | null
  loading: boolean
  can: (permission: string) => boolean
  has: (permission: string) => boolean
  reload: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = async () => {
    setLoading(true)
    try {
      if (!localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)) {
        await refreshAccessToken()
      }
      setSession(await loadSession())
    } catch {
      clearStoredAccessToken()
      setSession(null)
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    try {
      await logoutRequest()
    } finally {
      clearStoredAccessToken()
      queryClient.clear()
      setSession(null)
    }
  }

  useEffect(() => {
    void reload()
    const expired = () => { queryClient.clear(); setSession(null) }
    window.addEventListener("aquaponics-auth-expired", expired)
    window.addEventListener("aquaponics:authentication-failure", expired)
    return () => {
      window.removeEventListener("aquaponics-auth-expired", expired)
      window.removeEventListener("aquaponics:authentication-failure", expired)
    }
  }, [])

  const value = useMemo(() => {
    const can = (permission: string) => Boolean(session?.permissions.includes(permission))
    return { session, loading, can, has: can, reload, logout }
  }, [session, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error("AuthProvider is required")
  return value
}
