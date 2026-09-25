import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8")
}

describe("user list layout", () => {
  it("puts the create button on the search row, not the title row", () => {
    const page = source("./users-canonical.tsx")
    expect(page).toContain('<div><h1 className="text-3xl font-bold">Quản lý người dùng</h1>')
    expect(page).toMatch(/Tìm theo tên, username, email hoặc vai trò[\s\S]{0,1600}Tạo tài khoản<\/Button>/)
  })

  it("adds an action column with a view button per row", () => {
    const page = source("./users-canonical.tsx")
    expect(page).toMatch(/<TableHead[^>]*>Hành động<\/TableHead>/)
    expect(page).toContain("onClick={() => setViewing(user.id)}")
    expect(page).toContain("aria-label={`Xem chi tiết ${user.full_name}`}")
  })
})

describe("user list filtering", () => {
  it("offers every account status plus an all option", () => {
    const page = source("./users-canonical.tsx")
    for (const label of ["Tất cả trạng thái", "Đang hoạt động", "Đã vô hiệu hóa", "Đã khóa", "Đã xóa mềm"]) {
      expect(page).toContain(`>${label}</SelectItem>`)
    }
    expect(page).toContain('status === "ALL" || user.status === status')
  })
})

describe("user detail layout", () => {
  it("splits into a profile column and a details column", () => {
    const detail = source("./user-detail-canonical.tsx")
    expect(detail).toContain("lg:grid-cols-[minmax(0,35fr)_minmax(0,65fr)]")
    expect(detail).toContain("<CardTitle>Thông tin chi tiết</CardTitle>")
    expect(detail).toContain("initialsOf(value.full_name)")
  })

  it("keeps every field and action after the redesign", () => {
    const detail = source("./user-detail-canonical.tsx")
    for (const label of ["Email", "Số điện thoại", "Ngày tạo", "Lần đăng nhập cuối"]) {
      expect(detail).toContain(`label="${label}"`)
    }
    expect(detail).toContain("<Label>Vai trò</Label>")
    expect(detail).toContain("Quản lý tài khoản</Button>")
    expect(detail).toContain("<UserAquaponicsSystems userId={userId}")
  })
})

describe("user detail is reachable without leaving the list", () => {
  it("opens the detail view inside a dialog instead of linking to its route", () => {
    const page = source("./users-canonical.tsx")
    expect(page).toContain("<UserDetailView userId={viewing} embedded />")
    expect(page).not.toContain("to={`/users/${user.id}`}")
  })

  it("keeps the standalone route working from the same view", () => {
    const detail = source("./user-detail-canonical.tsx")
    expect(detail).toContain("export function UserDetailView({ userId, embedded = false }")
    expect(detail).toContain('return <UserDetailView userId={useParams().userId ?? ""} />')
    expect(detail).toContain("{embedded ? null : <Link")
  })
})
