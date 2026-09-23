import { AxiosError, type InternalAxiosRequestConfig } from "axios"
import { describe, expect, it, vi } from "vitest"

import { createHttpClient, resolveApiBaseUrl } from "@/shared/api/http-client"

describe("resolveApiBaseUrl", () => {
  it("không lặp /api/v1 khi Docker dùng Nginx proxy", () => {
    expect(resolveApiBaseUrl("/api/v1")).toBe("/api/v1")
    expect(resolveApiBaseUrl("/api/v1/")).toBe("/api/v1")
  })

  it("thêm API prefix cho host phát triển", () => {
    expect(resolveApiBaseUrl("http://localhost:8000")).toBe(
      "http://localhost:8000/api/v1",
    )
  })

  it("mặc định dùng cùng origin qua Nginx", () => {
    expect(resolveApiBaseUrl(undefined)).toBe("/api/v1")
  })
})

describe("authentication failure", () => {
  it("phát aquaponics-auth-expired khi một auth endpoint trả 401", async () => {
    vi.stubGlobal("window", new EventTarget())
    const client = createHttpClient()
    client.defaults.adapter = async (config) => {
      const requestConfig = config as InternalAxiosRequestConfig
      throw new AxiosError(
        "Unauthorized",
        "ERR_BAD_REQUEST",
        requestConfig,
        undefined,
        {
          data: { code: "UNAUTHORIZED", detail: "Phiên đã hết hạn." },
          status: 401,
          statusText: "Unauthorized",
          headers: {},
          config: requestConfig,
        },
      )
    }

    let expiredEvents = 0
    const listener = () => { expiredEvents += 1 }
    window.addEventListener("aquaponics-auth-expired", listener)
    try {
      await expect(client.get("/auth/refresh")).rejects.toBeInstanceOf(AxiosError)
      expect(expiredEvents).toBe(1)
    } finally {
      window.removeEventListener("aquaponics-auth-expired", listener)
    }
  })
})
