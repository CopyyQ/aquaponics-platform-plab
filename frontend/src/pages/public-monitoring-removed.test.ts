import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("public monitoring removal", () => {
  it("removes public monitoring from settings and routing", () => {
    const settings = source("./settings-canonical.tsx")
    const router = source("../app/router/canonical-router.tsx")
    expect(settings).not.toContain("Giám sát công khai")
    expect(settings).not.toContain("getPublicMonitoringSettings")
    expect(router).not.toContain("/public/:slug")
    expect(router).not.toContain("public-monitoring-canonical")
  })

  it("removes the canonical public monitoring API contract", () => {
    const resources = source("../api/resources.ts")
    const contracts = source("../api/contracts.ts")
    expect(resources).not.toContain("publicMonitoring")
    expect(contracts).not.toContain("PublicMonitoringSettings")
  })
})
