import { describe, expect, it } from "vitest"

import { breadcrumbFromPath } from "./breadcrumbs"

describe("admin header breadcrumb", () => {
  it("shows the section and the product on the systems list", () => {
    expect(breadcrumbFromPath("/aquaponics-systems")).toEqual(["Hệ thống", "Aquaponics"])
  })

  it("appends the workspace tab inside a system", () => {
    expect(breadcrumbFromPath("/aquaponics-systems/2efa5df4/overview")).toEqual(["Hệ thống", "Aquaponics", "Tổng quan"])
    expect(breadcrumbFromPath("/aquaponics-systems/2efa5df4/devices/12")).toEqual(["Hệ thống", "Aquaponics", "Thiết bị"])
  })

  it("keeps the trail short on a system route without a known tab", () => {
    expect(breadcrumbFromPath("/aquaponics-systems/2efa5df4")).toEqual(["Hệ thống", "Aquaponics"])
  })

  it("keeps the same root when moving to another admin section", () => {
    expect(breadcrumbFromPath("/catalogs")).toEqual(["Hệ thống", "Aquaponics", "Danh mục"])
    expect(breadcrumbFromPath("/users")).toEqual(["Hệ thống", "Aquaponics", "Quản lý người dùng"])
    expect(breadcrumbFromPath("/users/7")).toEqual(["Hệ thống", "Aquaponics", "Quản lý người dùng", "Chi tiết"])
    expect(breadcrumbFromPath("/profile")).toEqual(["Hệ thống", "Aquaponics", "Hồ sơ cá nhân"])
  })

  it("starts every trail from the same root", () => {
    const paths = ["/aquaponics-systems", "/aquaponics-systems/2efa5df4/alerts", "/catalogs", "/users", "/users/7", "/profile"]
    for (const path of paths) expect(breadcrumbFromPath(path).slice(0, 2)).toEqual(["Hệ thống", "Aquaponics"])
  })
})
