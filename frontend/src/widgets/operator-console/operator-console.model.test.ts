import { describe, expect, it } from "vitest"
import type { Alert, AquaponicsSystem, MonitoringLatest } from "@/api/contracts"
import {
  createOperatorOverviewModel,
  isOpenAlert,
  pageTitleFromPath,
  recipientStatusLabel,
  resolveSensorIcon,
  safeRangeLabel,
  sensorValueStatus,
  latestOperatorAlerts,
  splitOperatorAlerts,
} from "./operator-console.model"

const system: AquaponicsSystem = {
  id: "sys-1",
  code: "TB-0015",
  name: "Hệ thống cá trê",
  location: "An Khánh, Hà Nội",
  description: null,
  owner_user_id: "user-1",
  device_template_id: null,
  scenario_catalog_id: null,
  status: "ACTIVE",
}

function sensor(partial: Partial<MonitoringLatest["devices"][number]["sensors"][number]> & { id: string; name: string }) {
  return {
    code: partial.name,
    unit: "pH",
    is_enabled: true,
    connection_status: "ONLINE",
    data_status: "VALID",
    latest: { value: 7.2, recorded_at: "2026-09-18T01:12:00Z" },
    lower_threshold: 6.5,
    upper_threshold: 8.5,
    threshold_state: "IN_RANGE",
    ...partial,
  }
}

describe("operator console view model", () => {
  it("maps sensor names to icons without inventing values", () => {
    expect(resolveSensorIcon("Độ pH", "pH")).toBe("ph")
    expect(resolveSensorIcon("Độ ẩm môi trường", "%RH")).toBe("humidity")
    expect(resolveSensorIcon("Nhiệt độ nước", "°C")).toBe("waterTemp")
    expect(resolveSensorIcon("Ánh sáng", "lux")).toBe("light")
  })

  it("never treats missing telemetry as a normal zero reading", () => {
    expect(sensorValueStatus({ latest: null, data_status: "NO_DATA", threshold_state: null })).toBe("NO_DATA")
    expect(sensorValueStatus({ latest: { value: null, recorded_at: null }, data_status: "VALID", threshold_state: null })).toBe("NO_DATA")
    expect(sensorValueStatus({ latest: { value: 10.6, recorded_at: "2026-09-18T01:12:00Z" }, data_status: "VALID", threshold_state: "ABOVE" })).toBe("ATTENTION")
    expect(sensorValueStatus({ latest: { value: 7.2, recorded_at: "2026-09-18T01:12:00Z" }, data_status: "VALID", threshold_state: "IN_RANGE" })).toBe("NORMAL")
  })

  it("formats threshold copy like the operator dashboard", () => {
    expect(safeRangeLabel(6.5, 8.5)).toBe("An toàn: 6,5 – 8,5")
    expect(safeRangeLabel(null, 90)).toBe("An toàn: ≤ 90")
  })

  it("builds an attention banner from open alerts and out-of-range sensors", () => {
    const latest: MonitoringLatest = {
      aquaponics_system_id: "sys-1",
      devices: [{
        id: "dev-1", code: "GW-1", name: "Gateway", is_enabled: true, connection_status: "ONLINE", location: null, last_seen_at: "2026-09-18T01:12:00Z",
        sensors: [
          sensor({ id: "s1", name: "Độ pH", unit: "pH", latest: { value: 10.6, recorded_at: "2026-09-18T01:12:00Z" }, threshold_state: "ABOVE" }),
          sensor({ id: "s2", name: "Độ ẩm môi trường", unit: "%", latest: { value: 95.1, recorded_at: "2026-09-18T01:12:00Z" }, upper_threshold: 90, lower_threshold: null, threshold_state: "ABOVE" }),
        ],
        actuators: [],
      }],
    }
    const alerts = [
      { id: 1, status: "OPEN", message: "Độ pH cao bất thường" },
      { id: 2, status: "OPEN", message: "Độ ẩm môi trường hơi cao" },
      { id: 3, status: "RESOLVED", message: "Bơm tưới gián đoạn" },
    ] as Alert[]
    const model = createOperatorOverviewModel(system, latest, alerts)
    expect(model.banner).toBe("2 cảnh báo: Độ pH và Độ ẩm môi trường vượt ngưỡng an toàn")
    expect(model.openAlertCount).toBe(2)
    expect(model.sensors[0]?.value).toBe(10.6)
    expect(model.online).toBe(true)
  })

  it("splits open and resolved alerts without mixing status", () => {
    const grouped = splitOperatorAlerts([
      { id: 1, status: "OPEN", message: "pH cao", actual_value: 10.6, threshold_value: 8.5, started_at: "2026-09-18T01:15:00Z" },
      { id: 2, status: "RESOLVED", message: "Đã khôi phục", actual_value: null, threshold_value: null, started_at: "2026-09-18T03:07:00Z" },
    ] as Alert[])
    expect(grouped.open).toHaveLength(1)
    expect(grouped.resolved).toHaveLength(1)
    expect(isOpenAlert({ status: "ACKNOWLEDGED" })).toBe(true)
  })

  it("orders the bell list by newest trigger time without changing the alerts page grouping", () => {
    const latest = latestOperatorAlerts([
      { id: 1, status: "OPEN", message: "Cũ", started_at: "2026-09-18T01:00:00Z", last_triggered_at: "2026-09-18T01:00:00Z" },
      { id: 2, status: "RESOLVED", message: "Mới nhất", started_at: "2026-09-18T02:00:00Z", last_triggered_at: "2026-09-18T04:00:00Z" },
      { id: 3, status: "OPEN", message: "Giữa", started_at: "2026-09-18T03:00:00Z", last_triggered_at: "2026-09-18T03:00:00Z" },
    ] as Alert[], 2)
    expect(latest.map((alert) => alert.title)).toEqual(["Mới nhất", "Giữa"])
  })

  it("labels telegram recipients from stored enabled flags", () => {
    expect(recipientStatusLabel({ id: 1, system_id: "sys-1", name: "Anh Dũng", telegram_chat_id: "1", enabled: true, created_at: "", updated_at: "" }, true)).toBe("Đang bật")
    expect(recipientStatusLabel({ id: 2, system_id: "sys-1", name: "Quý", telegram_chat_id: "2", enabled: false, created_at: "", updated_at: "" }, true)).toBe("Đã tắt")
  })

  it("resolves operator page titles from the route", () => {
    expect(pageTitleFromPath("/aquaponics-systems/1/overview")).toBe("Tổng quan")
    expect(pageTitleFromPath("/aquaponics-systems/1/devices")).toBe("Thiết bị & Cảm biến")
    expect(pageTitleFromPath("/profile")).toBe("Hồ sơ")
    expect(pageTitleFromPath("/aquaponics-systems")).toBe("Hệ thống của bạn")
  })
})
