import type { Alert, AquaponicsSystem } from "@/api/contracts"

const OPEN_ALERT_STATUSES = new Set(["PENDING", "OPEN", "ACKNOWLEDGED"])

export interface OwnerAlertCard {
  id: number
  title: string
  detail: string
  startedAt: string
  open: boolean
  critical: boolean
}

export interface OwnerOverviewModel {
  system: AquaponicsSystem
  openAlertCount: number
  alerts: OwnerAlertCard[]
}

export function isOpenAlert(alert: Pick<Alert, "status">) {
  return OPEN_ALERT_STATUSES.has(alert.status)
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: value >= 100 ? 0 : 2 }).format(value)
}

export function toOwnerAlertCard(alert: Alert): OwnerAlertCard {
  const valueText = alert.actual_value === null ? null : formatCompactNumber(alert.actual_value)
  const thresholdText = alert.threshold_value === null ? null : formatCompactNumber(alert.threshold_value)
  let detail = ""
  if (valueText && thresholdText) detail = `Giá trị ${valueText}, ngưỡng ${thresholdText}.`
  else if (valueText) detail = `Giá trị hiện tại ${valueText}.`
  return {
    id: alert.id,
    title: alert.message,
    detail,
    startedAt: alert.started_at,
    open: isOpenAlert(alert),
    critical: alert.severity === "CRITICAL",
  }
}

function triggeredAt(alert: Alert) {
  return alert.last_triggered_at || alert.started_at
}

// Tổng quan chỉ hiện cảnh báo chưa xử lý (đã xử lý xem ở trang "Xem tất cả").
// Thứ tự ưu tiên: CRITICAL -> WARNING; trong cùng nhóm mới nhất trước.
export function prioritizedOwnerAlerts(alerts: Alert[], limit = 20): OwnerAlertCard[] {
  const rank = (alert: Alert) => (alert.severity === "CRITICAL" ? 0 : 1)
  return alerts
    .filter(isOpenAlert)
    .sort((left, right) => {
      const byRank = rank(left) - rank(right)
      if (byRank !== 0) return byRank
      const byTime = triggeredAt(right).localeCompare(triggeredAt(left))
      if (byTime !== 0) return byTime
      return right.id - left.id
    })
    .slice(0, limit)
    .map(toOwnerAlertCard)
}

export function createOwnerOverviewModel(system: AquaponicsSystem, alerts: Alert[]): OwnerOverviewModel {
  return {
    system,
    openAlertCount: alerts.filter(isOpenAlert).length,
    alerts: prioritizedOwnerAlerts(alerts),
  }
}
