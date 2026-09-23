import { create } from "zustand"
import { queryClient } from "@/shared/api/query-client"
import { httpClient } from "@/shared/api/http-client"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearStoredAccessToken,
  refreshAccessToken,
} from "@/shared/api/auth-refresh"
import type { User } from "@/entities/user/model/types"

interface AuthState {
  user: User | null
  token: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  hydrate: () => Promise<void>
  logout: () => Promise<void>
  clear: () => void
  setUser: (user: User) => void
}

function clearLegacyAuthStorage() {
  clearStoredAccessToken()
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY),
  loading: true,
  login: async (username, password) => {
    await queryClient.cancelQueries()
    queryClient.clear()
    const { data } = await httpClient.post<{ access_token: string }>(
      "/auth/login",
      { username, password },
      { withCredentials: true },
    )
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, data.access_token)
    set({ token: data.access_token })
    try {
      const user = (await httpClient.get<User>("/auth/me")).data
      set({ user, loading: false })
    } catch (error) {
      clearLegacyAuthStorage()
      await queryClient.cancelQueries()
      queryClient.clear()
      set({ user: null, token: null, loading: false })
      throw error
    }
  },
  hydrate: async () => {
    let token = get().token ?? localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
    if (!token) {
      try {
        token = await refreshAccessToken()
        set({ token })
      } catch {
        clearLegacyAuthStorage()
        return set({ loading: false, user: null, token: null })
      }
    }
    try {
      const user = (await httpClient.get<User>("/auth/me")).data
      set({ user, token, loading: false })
    } catch {
      clearLegacyAuthStorage()
      await queryClient.cancelQueries()
      queryClient.clear()
      set({ user: null, token: null, loading: false })
    }
  },
  logout: async () => {
    try {
      await httpClient.post("/auth/logout", undefined, { withCredentials: true })
    } finally {
      clearLegacyAuthStorage()
      sessionStorage.clear()
      queryClient.clear()
      set({ user: null, token: null, loading: false })
    }
  },
  clear: () => set({ user: null, token: null, loading: false }),
  setUser: (user) => set({ user }),
}))
