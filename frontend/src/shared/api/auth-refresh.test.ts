import { describe, expect, it, vi } from "vitest"

import {
  ACCESS_TOKEN_STORAGE_KEY,
  createRefreshCoordinator,
  shouldAttemptAuthRefresh,
} from "@/shared/api/auth-refresh"

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => { values.delete(key) },
    setItem: (key, value) => { values.set(key, value) },
  }
}

describe("auth refresh coordinator", () => {
  it("coalesces concurrent refreshes into one request and stores the access token", async () => {
    let resolveRequest!: (value: { access_token: string }) => void
    const request = vi.fn(() => new Promise<{ access_token: string }>((resolve) => {
      resolveRequest = resolve
    }))
    const storage = memoryStorage()
    const refresh = createRefreshCoordinator(request, storage)

    const first = refresh()
    const second = refresh()
    expect(request).toHaveBeenCalledTimes(1)

    resolveRequest({ access_token: "new-access-token" })

    await expect(first).resolves.toBe("new-access-token")
    await expect(second).resolves.toBe("new-access-token")
    expect(storage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("new-access-token")
  })

  it("starts a new request after the previous refresh settles", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ access_token: "token-1" })
      .mockResolvedValueOnce({ access_token: "token-2" })
    const refresh = createRefreshCoordinator(request, memoryStorage())

    await expect(refresh()).resolves.toBe("token-1")
    await expect(refresh()).resolves.toBe("token-2")
    expect(request).toHaveBeenCalledTimes(2)
  })

  it("never recursively refreshes auth endpoints", () => {
    expect(shouldAttemptAuthRefresh("/aquaponics-systems")).toBe(true)
    expect(shouldAttemptAuthRefresh("/auth/login")).toBe(false)
    expect(shouldAttemptAuthRefresh("/auth/refresh")).toBe(false)
    expect(shouldAttemptAuthRefresh("/auth/logout")).toBe(false)
  })
})
