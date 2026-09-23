export type AccountRole = "ADMIN" | "OWNER" | "VIEWER" | "TECHNICIAN"

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const part = token.split(".")[1]
  if (!part) return null
  try {
    const normalized = part.replace(/-/g, "+").replace(/_/g, "/")
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=")
    return JSON.parse(atob(padded)) as Record<string, unknown>
  } catch {
    return null
  }
}

export function readAccountRole(token = typeof localStorage === "undefined" ? null : localStorage.getItem("aquaponics_access_token")): AccountRole | null {
  if (!token) return null
  const role = decodeJwtPayload(token)?.role
  if (role === "ADMIN" || role === "OWNER" || role === "VIEWER" || role === "TECHNICIAN") return role
  return null
}

export function isPlatformAdmin(permissions: readonly string[] | undefined, role?: string | null) {
  if (role === "OWNER" || role === "VIEWER" || role === "TECHNICIAN") return false
  return Boolean(permissions?.includes("users.read"))
}

export function isOperatorConsole(permissions: readonly string[] | undefined, role?: string | null) {
  return !isPlatformAdmin(permissions, role)
}

export function mustStayOnPasswordChange(mustChangePassword: boolean, pathname: string, isOperator: boolean) {
  if (!mustChangePassword) return false
  if (isOperator) return false
  return pathname !== "/profile"
}

export function accountRoleLabel(role?: string | null) {
  if (role === "VIEWER") return "Người xem"
  if (role === "TECHNICIAN") return "Kỹ thuật viên"
  if (role === "ADMIN") return "Quản trị viên"
  return "Chủ hệ thống"
}
