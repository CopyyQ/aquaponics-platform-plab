import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("AppShell desktop sidebar", () => {
  const source = readFileSync(
    resolve(process.cwd(), "src/app/layouts/app-shell.tsx"),
    "utf8",
  )

  it("có hai trạng thái chiều rộng và nội dung tự bù khoảng trống", () => {
    expect(source).toContain('collapsed ? "w-20" : "w-72"')
    expect(source).toContain(
      'desktopCollapsed ? "lg:pl-20" : "lg:pl-72"',
    )
    expect(source).toContain('data-sidebar-collapsed=')
  })

  it("có nút thu nhỏ/mở rộng và lưu lựa chọn người dùng", () => {
    expect(source).toContain("aquaponics.sidebar.collapsed")
    expect(source).toContain("Thu nhỏ thanh bên")
    expect(source).toContain("Mở rộng thanh bên")
    expect(source).toContain("window.localStorage.setItem")
  })

  it("mobile drawer luôn dùng sidebar đầy đủ", () => {
    expect(source).toContain("{renderSidebar(false)}")
    expect(source).toContain('aria-label="Mở menu"')
  })
})
