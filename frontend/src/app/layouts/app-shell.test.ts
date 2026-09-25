import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

import { getNavigationItems } from "@/app/navigation/navigation-items"

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("admin sidebar", () => {
  it("drops the profile entry even when every permission is granted", () => {
    const items = getNavigationItems(() => true)
    expect(items.map((item) => item.label)).not.toContain("Hồ sơ")
    expect(items.map((item) => item.path)).toEqual(["/aquaponics-systems", "/catalogs", "/users"])
  })

  it("no longer renders the operating-session card", () => {
    const shell = source("./app-shell.tsx")
    expect(shell).not.toContain("Phiên vận hành")
  })
})

describe("admin account menu", () => {
  it("opens the same profile dialog the owner console uses", () => {
    const shell = source("./app-shell.tsx")
    const owner = source("./owner-console-layout.tsx")
    expect(shell).toContain('import { OwnerProfileDialog } from "@/widgets/owner-console/OwnerProfileDialog"')
    expect(shell).toContain("onSelect={() => setProfileOpen(true)}><UserRound /> Hồ sơ cá nhân")
    expect(shell).not.toContain('navigate("/profile")')
    expect(owner).toContain("<OwnerProfileDialog")
  })
})
