import { describe, expect, it } from "vitest"
import { accountRoleLabel, isOperatorConsole, isPlatformAdmin, mustStayOnPasswordChange, readAccountRole } from "./operator-console"

function tokenWithRole(role: string) {
  const payload = btoa(JSON.stringify({ role })).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "")
  return `header.${payload}.sig`
}

describe("operator console role gate", () => {
  it("keeps ADMIN on the platform shell", () => {
    expect(isPlatformAdmin(["users.read"], "ADMIN")).toBe(true)
    expect(isOperatorConsole(["users.read"], "ADMIN")).toBe(false)
  })

  it("sends System Owner to the AquaMonitor console even if catalogs are readable", () => {
    expect(isPlatformAdmin(["aquaponics_systems.read", "device_templates.read"], "OWNER")).toBe(false)
    expect(isOperatorConsole(["aquaponics_systems.read", "device_templates.read"], "OWNER")).toBe(true)
    expect(accountRoleLabel("OWNER")).toBe("Chủ hệ thống")
  })

  it("uses AquaMonitor when the account cannot manage users, even if the token still says ADMIN", () => {
    expect(isOperatorConsole(["aquaponics_systems.read", "device_templates.read", "devices.read", "incidents.read"], "ADMIN")).toBe(true)
  })

  it("lets System Owner open overview, devices and alerts while a password change is still pending", () => {
    expect(mustStayOnPasswordChange(true, "/aquaponics-systems/1/overview", true)).toBe(false)
    expect(mustStayOnPasswordChange(true, "/profile", true)).toBe(false)
    expect(mustStayOnPasswordChange(true, "/aquaponics-systems", false)).toBe(true)
    expect(mustStayOnPasswordChange(true, "/profile", false)).toBe(false)
  })

  it("reads OWNER from the existing access token payload without calling backend", () => {
    expect(readAccountRole(tokenWithRole("OWNER"))).toBe("OWNER")
    expect(readAccountRole(tokenWithRole("ADMIN"))).toBe("ADMIN")
  })
})
