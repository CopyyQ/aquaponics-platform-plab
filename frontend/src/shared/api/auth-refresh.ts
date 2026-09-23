import axios from "axios"

import type { TokenResponse } from "@/api/contracts"
import { emitAuthenticationFailure } from "@/shared/api/auth-events"

export const ACCESS_TOKEN_STORAGE_KEY = "aquaponics_access_token"
const AUTH_REFRESH_PATH = "/auth/refresh"
const AUTH_FLOW_PATHS = new Set(["/auth/login", AUTH_REFRESH_PATH, "/auth/logout"])

function resolveApiBaseUrl(value: string | undefined) {
  const baseUrl = (value?.trim() || "/api/v1").replace(/\/$/, "")
  return baseUrl.endsWith("/api/v1") ? baseUrl : `${baseUrl}/api/v1`
}

const refreshClient = axios.create({
  baseURL: resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
  timeout: 20_000,
  withCredentials: true,
})

function browserStorage(): Storage | null {
  return typeof localStorage === "undefined" ? null : localStorage
}

export async function requestRefreshSession(): Promise<TokenResponse> {
  const response = await refreshClient.post<TokenResponse>(AUTH_REFRESH_PATH)
  return response.data
}

export function createRefreshCoordinator(
  request: () => Promise<Pick<TokenResponse, "access_token">>,
  storage: Storage | null = browserStorage(),
): () => Promise<string> {
  let inFlight: Promise<string> | null = null

  return () => {
    if (!inFlight) {
      inFlight = request()
        .then(({ access_token }) => {
          storage?.setItem(ACCESS_TOKEN_STORAGE_KEY, access_token)
          return access_token
        })
        .finally(() => {
          inFlight = null
        })
    }
    return inFlight
  }
}

export const refreshAccessToken = createRefreshCoordinator(requestRefreshSession)

export function shouldAttemptAuthRefresh(url: string | undefined): boolean {
  if (!url) return true
  const path = url.split("?", 1)[0]
  return !Array.from(AUTH_FLOW_PATHS).some((authPath) => path.endsWith(authPath))
}

export function clearStoredAccessToken(): void {
  browserStorage()?.removeItem(ACCESS_TOKEN_STORAGE_KEY)
}

export function signalAuthenticationExpired(): void {
  clearStoredAccessToken()
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("aquaponics-auth-expired"))
  }
  emitAuthenticationFailure("UNAUTHORIZED")
}
