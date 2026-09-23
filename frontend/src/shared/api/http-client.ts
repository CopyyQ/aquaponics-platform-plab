import axios, { type InternalAxiosRequestConfig } from "axios"
import { getAccountAuthCode, isAccountAuthError } from "@/shared/api/auth-errors"
import type { AuthenticationFailureCode } from "@/shared/api/auth-events"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearStoredAccessToken,
  refreshAccessToken,
  shouldAttemptAuthRefresh,
  signalAuthenticationExpired,
} from "@/shared/api/auth-refresh"

export function resolveApiBaseUrl(value: string | undefined) {
  const baseUrl = (value?.trim() || "/api/v1").replace(/\/$/, "")
  return baseUrl.endsWith("/api/v1") ? baseUrl : `${baseUrl}/api/v1`
}

const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

type RetriableRequestConfig = InternalAxiosRequestConfig & { _authRetried?: boolean }

interface HttpClientOptions {
  getAccessToken?: () => string | null
  onAuthenticationFailure?: (code: AuthenticationFailureCode) => void
}

function notifyAuthenticationFailure(error: unknown, options: HttpClientOptions) {
  const code = getAccountAuthCode(error)
  const authCode = (code || "UNAUTHORIZED") as AuthenticationFailureCode
  if (options.onAuthenticationFailure) {
    clearStoredAccessToken()
    options.onAuthenticationFailure(authCode)
    return
  }
  signalAuthenticationExpired()
}

export function createHttpClient(options: HttpClientOptions = {}) {
  const client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 20_000,
    withCredentials: true,
  })
  client.interceptors.request.use((config) => {
    const token = options.getAccessToken?.() ?? (typeof localStorage === "undefined" ? null : localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY))
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const request = error.config as RetriableRequestConfig | undefined
      const canRefresh = error.response?.status === 401
        && request
        && !request._authRetried
        && shouldAttemptAuthRefresh(request.url)

      if (canRefresh) {
        request._authRetried = true
        try {
          const token = await refreshAccessToken()
          request.headers.Authorization = `Bearer ${token}`
          return await client.request(request)
        } catch (refreshError) {
          notifyAuthenticationFailure(refreshError, options)
          return Promise.reject(refreshError)
        }
      }

      if (error.response?.status === 401 || isAccountAuthError(error)) {
        notifyAuthenticationFailure(error, options)
      }
      return Promise.reject(error)
    },
  )
  return client
}

export const httpClient = createHttpClient()

export const apiBaseUrl = API_BASE_URL
