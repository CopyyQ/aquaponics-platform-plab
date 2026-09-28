import { describe, expect, it } from "vitest"
import { DERIVED_POWER, SCADA_CARDS, SCADA_METRICS } from "./scada-cards"
import { readScadaMetrics } from "./scada-readings"
import type { ScenarioSource } from "./scada-signals"

function source(over: { value?: number | null; freshness?: string; quality?: string; connectivity?: string } = {}): ScenarioSource {
  return {
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: 1, template_code: "T", enabled: true, connectivity: over.connectivity ?? "ONLINE", last_seen_at: null }],
      sensors: [
        { id: "s-temp", code: "WATER_TEMPERATURE", name: "Nhiệt độ nước", sensor_model_code: "WATER_TEMPERATURE", unit: "°C", device_id: "dev-1", enabled: true },
        { id: "s-volt", code: "VOLTAGE", name: "Điện áp", sensor_model_code: "VOLTAGE", unit: "V", device_id: "dev-1", enabled: true },
        { id: "s-curr", code: "CURRENT", name: "Dòng điện", sensor_model_code: "CURRENT", unit: "A", device_id: "dev-1", enabled: true },
        { id: "s-no3", code: "NO3", name: "NO3", sensor_model_code: "NO3", unit: "mg/L", device_id: "dev-1", enabled: true },
      ],
      actuators: [{ id: "a-pump", code: "FISH_TANK_PUMP", name: "Bơm bể cá", actuator_model_code: "FISH_TANK_PUMP", device_id: "dev-1", enabled: true }],
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity: over.connectivity ?? "ONLINE", last_seen_at: null }],
      sensors: [
        { id: "s-temp", value: over.value === undefined ? 28.74 : over.value, recorded_at: "2026-09-25T04:40:00Z", received_at: "2026-09-25T04:40:01Z", freshness: over.freshness ?? "FRESH", quality: over.quality ?? "VALID", quality_reason: null },
        { id: "s-volt", value: 12, recorded_at: "2026-09-25T04:40:00Z", received_at: "2026-09-25T04:40:01Z", freshness: "FRESH", quality: "VALID", quality_reason: null },
        { id: "s-curr", value: 2.5, recorded_at: "2026-09-25T04:40:00Z", received_at: "2026-09-25T04:40:01Z", freshness: "FRESH", quality: "VALID", quality_reason: null },
        { id: "s-no3", value: 0, recorded_at: "2026-09-25T04:40:00Z", received_at: "2026-09-25T04:40:01Z", freshness: "FRESH", quality: "UNVALIDATED", quality_reason: "Chưa có miền hợp lệ cho SensorModel." },
      ],
      actuators: [{ id: "a-pump", desired_state: true, reported_state: true, synchronization: "IN_SYNC", command_status: "ACKED", command_time: null, last_ack_at: "2026-09-25T04:40:00Z", failure_reason: null }],
      alerts: [],
    },
    updated_at: "2026-09-25T04:40:01Z",
  } as unknown as ScenarioSource
}

describe("SCADA card layout", () => {
  it("declares every placed metric in the metric catalog", () => {
    const known = new Set(SCADA_METRICS.map((m) => m.code))

    for (const code of SCADA_CARDS.flatMap((c) => c.items)) expect(known.has(code)).toBe(true)
  })

  it("never places the same metric on two cards", () => {
    const placed = SCADA_CARDS.flatMap((c) => c.items)

    expect(new Set(placed).size).toBe(placed.length)
  })

  it("keeps every card box inside the image frame", () => {
    for (const card of SCADA_CARDS) {
      expect(card.box.x).toBeGreaterThanOrEqual(0)
      expect(card.box.y).toBeGreaterThanOrEqual(0)
      expect(card.box.x + card.box.w).toBeLessThanOrEqual(100)
      expect(card.box.y + card.box.h).toBeLessThanOrEqual(100)
    }
  })
})

describe("SCADA readings", () => {
  it("formats a fresh sensor value with its inventory unit", () => {
    const [temp] = readScadaMetrics(source(), ["WATER_TEMPERATURE"])

    expect(temp.text).toBe("28,7 °C")
    expect(temp.status).toBe("AVAILABLE")
    expect(temp.unvalidated).toBe(false)
  })

  it("computes power from voltage times current", () => {
    const [power] = readScadaMetrics(source(), [DERIVED_POWER])

    expect(power.text).toBe("30 W")
    expect(power.status).toBe("AVAILABLE")
  })

  it("flags a fresh value the backend could not validate", () => {
    const [no3] = readScadaMetrics(source(), ["NO3"])

    expect(no3.text).toBe("0 mg/L")
    expect(no3.unvalidated).toBe(true)
  })

  it("withholds the number instead of showing stale telemetry as current", () => {
    const [stale] = readScadaMetrics(source({ freshness: "STALE" }), ["WATER_TEMPERATURE"])

    expect(stale.text).toBeNull()
    expect(stale.status).toBe("STALE")
  })

  it("reports an offline device rather than its last known value", () => {
    const [offline] = readScadaMetrics(source({ connectivity: "OFFLINE" }), ["WATER_TEMPERATURE"])

    expect(offline.text).toBeNull()
    expect(offline.status).toBe("OFFLINE")
  })

  it("renders actuator state as BẬT or TẮT", () => {
    const [pump] = readScadaMetrics(source(), ["FISH_TANK_PUMP"])

    expect(pump.text).toBe("BẬT")
  })

  it("marks a metric with no sensor behind it as having no data", () => {
    const [missing] = readScadaMetrics(source(), ["TDS"])

    expect(missing.text).toBeNull()
    expect(missing.status).toBe("NONE")
  })
})
