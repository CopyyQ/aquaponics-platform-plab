import { describe, expect, it } from "vitest"
import type { ScadaIssue } from "@/api/contracts"
import type { ScadaReading } from "./scada-readings"
import { resolveCardStatus } from "./scada-status"

function reading(over: Partial<ScadaReading> = {}): ScadaReading {
  return {
    code: "PH",
    kind: "SENSOR",
    label: "Độ pH",
    fullLabel: "Độ pH (chua – kiềm)",
    text: "6,8 pH",
    value: 6.8,
    status: "AVAILABLE",
    unvalidated: false,
    entityId: "s-ph",
    recordedAt: "2026-09-25T04:40:00Z",
    ...over,
  }
}

function issue(over: Partial<ScadaIssue> = {}): ScadaIssue {
  return {
    id: "i-1",
    severity: "WARNING",
    title: "pH vượt ngưỡng",
    root_cause: "Cảm biến pH",
    affected_entities: [],
    current_state: "",
    timestamp: null,
    suggested_action: "",
    device_id: "dev-1",
    sensor_id: "s-ph",
    actuator_id: null,
    ...over,
  }
}

describe("SCADA card status", () => {
  it("reports a healthy group when every reading is current and valid", () => {
    expect(resolveCardStatus([reading()], []).health).toBe("OK")
  })

  it("does not call a group healthy while a device is offline", () => {
    expect(resolveCardStatus([reading({ status: "OFFLINE", text: null })], []).health).toBe("WARNING")
  })

  it("treats stale telemetry as a warning rather than a normal reading", () => {
    expect(resolveCardStatus([reading({ status: "STALE", text: null })], []).health).toBe("WARNING")
  })

  it("does not downgrade a group just because the catalog lacks a valid range", () => {
    // UNVALIDATED là lỗi cấu hình danh mục, không phải thiết bị đang hỏng.
    // Giá trị vẫn được tô cảnh báo riêng ở giao diện.
    expect(resolveCardStatus([reading({ unvalidated: true })], []).health).toBe("OK")
  })

  it("escalates to critical on a backend issue and keeps the issue for the detail view", () => {
    const status = resolveCardStatus([reading()], [issue({ severity: "CRITICAL" })])

    expect(status.health).toBe("CRITICAL")
    expect(status.issues).toHaveLength(1)
    expect(status.label).toBe("Nghiêm trọng")
  })

  it("ignores issues that belong to entities outside this card", () => {
    const status = resolveCardStatus([reading()], [issue({ sensor_id: "s-other" })])

    expect(status.health).toBe("OK")
    expect(status.issues).toHaveLength(0)
  })

  it("keeps the worst level when several problems overlap", () => {
    const status = resolveCardStatus(
      [reading({ status: "NONE", text: null }), reading({ code: "DO", entityId: "s-do", status: "OFFLINE", text: null })],
      [issue({ severity: "HIGH" })],
    )

    expect(status.health).toBe("CRITICAL")
  })

  it("matches an issue raised against an actuator, not only a sensor", () => {
    const status = resolveCardStatus(
      [reading({ code: "FISH_TANK_PUMP", kind: "ACTUATOR", entityId: "a-pump", text: "BẬT" })],
      [issue({ sensor_id: null, actuator_id: "a-pump", severity: "CRITICAL" })],
    )

    expect(status.health).toBe("CRITICAL")
  })

  it("says unknown when the card has nothing to show at all", () => {
    expect(resolveCardStatus([], []).health).toBe("UNKNOWN")
  })
})
