import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("Aquaponics system lifecycle UI", () => {
  it("keeps lifecycle actions out of the system header", () => {
    const layout = source("../app/layouts/aquaponics-system-layout.tsx")
    expect(layout).not.toContain("LifecycleButton")
    expect(layout).not.toContain('>Vô hiệu hóa</Button>')
  })

  it("uses disable instead of delete in the settings danger zone", () => {
    const settings = source("./settings-canonical.tsx")
    expect(settings).toContain("Vùng nguy hiểm")
    expect(settings).toContain("Vô hiệu hóa hệ thống")
    expect(settings).toContain("disableSystem")
    expect(settings).not.toContain("Xoá hệ thống")
    expect(settings).not.toContain("deleteSystem")
    expect(settings).not.toContain("aquaponics_systems.delete")
  })
})
