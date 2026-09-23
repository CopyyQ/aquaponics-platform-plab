import { describe, expect, it } from "vitest"
import { getNavigationItems } from "@/app/navigation/navigation-items"
import { catalogTabFromParam } from "./catalogs-activation"

describe("catalog device tab routing", () => {
  it("normalizes legacy templates tab to devices", () => {
    expect(catalogTabFromParam("templates")).toBe("devices")
    expect(catalogTabFromParam(null)).toBe("devices")
    expect(catalogTabFromParam("devices")).toBe("devices")
  })

  it("opens the catalog hub", () => {
    const items = getNavigationItems(() => true)
    const catalog = items.find((item) => item.label === "Danh mục")
    expect(catalog?.path).toBe("/catalogs")
  })
})
