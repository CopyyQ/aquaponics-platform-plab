// Breadcrumb cho header admin: suy ra tu duong dan, khong goi API.
const systemTabs: Record<string, string> = {
  overview: "Tổng quan",
  scada: "Sơ đồ vận hành",
  monitoring: "Quan trắc",
  devices: "Thiết bị",
  alerts: "Cảnh báo",
  members: "Thành viên",
  activities: "Hoạt động",
  notifications: "Thông báo",
  settings: "Thiết lập",
}

// Moi trang deu bat dau tu goc "He thong > Aquaponics", roi noi them muc dang xem.
const root = ["Hệ thống", "Aquaponics"]

export function breadcrumbFromPath(pathname: string): string[] {
  const segments = pathname.split("/").filter(Boolean)
  if (!segments.length) return [...root]

  if (segments[0] === "aquaponics-systems") {
    // /aquaponics-systems/:systemId/<tab>/...
    const tab = segments[2]
    return tab && systemTabs[tab] ? [...root, systemTabs[tab]] : [...root]
  }
  if (segments[0] === "catalogs") return [...root, "Danh mục"]
  if (segments[0] === "users") return segments.length > 1 ? [...root, "Quản lý người dùng", "Chi tiết"] : [...root, "Quản lý người dùng"]
  if (segments[0] === "profile") return [...root, "Hồ sơ cá nhân"]
  return [...root]
}
