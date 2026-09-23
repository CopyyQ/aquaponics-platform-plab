import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("scenario catalogs belong to device templates", () => {
  it("nests scenario management under a selected device on /catalogs", () => {
    const catalog = source("./catalog-hub.tsx")
    expect(catalog).toContain("Kịch bản của thiết bị")
    expect(catalog).toContain("deviceTemplateId")
    expect(catalog).not.toContain('title="Quản lý kịch bản"')
  })

  it("filters project scenarios after selecting the device template", () => {
    const userDetail = source("./user-detail-canonical.tsx")
    expect(userDetail).toContain("scenario.device_template_id === templateId")
    expect(userDetail).toContain("Chọn thiết bị trước")
  })
})
