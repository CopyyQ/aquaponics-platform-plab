import { describe, expect, it } from "vitest"
import type { Alert, AquaponicsSystem } from "@/api/contracts"
import { createOwnerOverviewModel, prioritizedOwnerAlerts } from "./owner-overview.model"

const system = { id: "sys-1", name: "Hệ thống 1" } as AquaponicsSystem

const alerts = [
  { id: 1, status: "OPEN", severity: "WARNING", message: "pH cao", actual_value: 10.6, threshold_value: 8.5, started_at: "2026-09-18T01:00:00Z", last_triggered_at: "2026-09-18T01:00:00Z" },
  { id: 2, status: "OPEN", severity: "CRITICAL", message: "Mực nước thấp", actual_value: 40, threshold_value: 65, started_at: "2026-09-17T01:00:00Z", last_triggered_at: "2026-09-17T01:00:00Z" },
  { id: 3, status: "RESOLVED", severity: "CRITICAL", message: "Bơm lỗi", actual_value: null, threshold_value: null, started_at: "2026-09-18T05:00:00Z", last_triggered_at: "2026-09-18T05:00:00Z" },
  { id: 4, status: "ACKNOWLEDGED", severity: "WARNING", message: "Độ ẩm cao", actual_value: 95, threshold_value: 90, started_at: "2026-09-18T02:00:00Z", last_triggered_at: "2026-09-18T02:00:00Z" },
] as Alert[]

describe("owner overview model", () => {
  it("shows only open alerts: critical first, then warning (newest first); resolved hidden", () => {
    const cards = prioritizedOwnerAlerts(alerts)
    expect(cards.map((alert) => alert.id)).toEqual([2, 4, 1])
    expect(cards.some((alert) => !alert.open)).toBe(false)
  })

  it("marks critical and open flags and formats detail", () => {
    const [first] = prioritizedOwnerAlerts(alerts)
    expect(first?.critical).toBe(true)
    expect(first?.open).toBe(true)
    expect(first?.detail).toBe("Giá trị 40, ngưỡng 65.")
  })

  it("counts open alerts and respects the limit", () => {
    const model = createOwnerOverviewModel(system, alerts)
    expect(model.openAlertCount).toBe(3)
    expect(prioritizedOwnerAlerts(alerts, 2)).toHaveLength(2)
  })
})
