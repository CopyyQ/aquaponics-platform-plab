import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

describe("operator project lifecycle guard", () => {
  it("does not render a disabled cached project", () => {
    const source = readFileSync(join(process.cwd(), "src/app/layouts/operator-console-layout.tsx"), "utf8")
    const frame = source.slice(source.indexOf("export function OperatorSystemFrame"))
    expect(frame).toContain('system.data.status !== "ACTIVE"')
    expect(frame).toContain('Navigate to="/aquaponics-systems"')
    expect(frame).toContain('refetchInterval: 15_000')
  })
})
