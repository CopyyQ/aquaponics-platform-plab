import type { ScadaIssue } from "@/api/contracts"
import type { ScadaReading } from "./scada-readings"

/** Bậc sức khoẻ của một cụm thiết bị, xếp từ nhẹ đến nặng. */
export type ScadaHealth = "UNKNOWN" | "OK" | "CAUTION" | "WARNING" | "CRITICAL"

const RANK: Record<ScadaHealth, number> = { UNKNOWN: 0, OK: 1, CAUTION: 2, WARNING: 3, CRITICAL: 4 }

export const HEALTH_LABEL: Record<ScadaHealth, string> = {
  UNKNOWN: "Chưa có dữ liệu",
  OK: "Bình thường",
  CAUTION: "Cần chú ý",
  WARNING: "Cảnh báo",
  CRITICAL: "Nghiêm trọng",
}

export interface ScadaCardStatus {
  health: ScadaHealth
  label: string
  /** Sự cố backend đã gắn cho chính các thiết bị trong thẻ. */
  issues: ScadaIssue[]
}

function worst(a: ScadaHealth, b: ScadaHealth): ScadaHealth {
  return RANK[b] > RANK[a] ? b : a
}

function issueHealth(severity: ScadaIssue["severity"]): ScadaHealth {
  if (severity === "CRITICAL" || severity === "HIGH") return "CRITICAL"
  if (severity === "WARNING") return "WARNING"
  return "CAUTION"
}

/**
 * Sức khoẻ lấy mức nặng nhất trong hai nguồn:
 * sự cố backend đã tính sẵn, và chất lượng dữ liệu của từng chỉ số.
 * Mất kết nối hay dữ liệu cũ cũng là cảnh báo — không thể coi là bình thường
 * chỉ vì chưa có sự cố nào được ghi nhận.
 */
function combine(readings: ScadaReading[], issues: ScadaIssue[]): ScadaCardStatus {
  let health: ScadaHealth = readings.length === 0 && issues.length === 0 ? "UNKNOWN" : "OK"

  for (const reading of readings) {
    if (reading.status === "OFFLINE" || reading.status === "STALE" || reading.status === "INVALID") {
      health = worst(health, "WARNING")
    } else if (reading.status === "NONE" || reading.status === "DISABLED") {
      health = worst(health, "CAUTION")
    }
    // unvalidated KHÔNG hạ sức khoẻ: đó là catalog thiếu khai báo miền hợp lệ,
    // tức lỗi cấu hình chứ không phải thiết bị đang có vấn đề. Giá trị vẫn được
    // tô màu cảnh báo riêng và có ghi chú trong hộp chi tiết.
  }

  for (const issue of issues) health = worst(health, issueHealth(issue.severity))

  return { health, label: HEALTH_LABEL[health], issues }
}

export function resolveCardStatus(readings: ScadaReading[], allIssues: readonly ScadaIssue[]): ScadaCardStatus {
  const ids = new Set(readings.map((reading) => reading.entityId).filter((id): id is string => Boolean(id)))
  const issues = allIssues.filter((issue) =>
    (issue.sensor_id && ids.has(issue.sensor_id)) || (issue.actuator_id && ids.has(issue.actuator_id)),
  )
  return combine(readings, issues)
}

/**
 * Sức khoẻ toàn hệ thống: tính trên mọi sự cố, kể cả sự cố của thiết bị
 * chưa có chỗ trên sơ đồ — nếu không thì thẻ sẽ báo bình thường trong khi
 * hệ thống đang hỏng ở chỗ người dùng không nhìn thấy.
 */
export function resolveSystemStatus(readings: ScadaReading[], allIssues: readonly ScadaIssue[]): ScadaCardStatus {
  return combine(readings, [...allIssues])
}
