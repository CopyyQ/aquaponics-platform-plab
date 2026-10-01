import { describe, expect, it } from "vitest"
import type { ScadaInventory, ScadaRuntimeState } from "@/api/contracts"
import {
  deriveScadaScenarioSignals,
  resolveScadaScenarioImage,
} from "./scenario-image"

function source(input?: {
  water?: { value: number | null; freshness?: "FRESH" | "STALE" | "NO_DATA"; quality?: "VALID" | "INVALID" | "OUT_OF_RANGE" | "UNVALIDATED" }
  growLight?: boolean | null
  deviceConnectivity?: string
}) {
  const inventory: ScadaInventory = {
    devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: 1, template_code: "AQUAPONICS_SYSTEM_DEVICE", enabled: true, connectivity: input?.deviceConnectivity ?? "ONLINE", last_seen_at: null }],
    sensors: [{ id: "sensor-water", code: "WATER_LEVELW2", name: "Mực nước bể cá", sensor_model_code: "WATER_LEVELW2", unit: "%", device_id: "dev-1", enabled: true }],
    actuators: [{ id: "act-light", code: "LIGHT", name: "Đèn", actuator_model_code: "GROW_LIGHT", device_id: "dev-1", enabled: true }],
  }
  const runtime: ScadaRuntimeState = {
    devices: [{ id: "dev-1", connectivity: input?.deviceConnectivity ?? "ONLINE", last_seen_at: null }],
    sensors: [{
      id: "sensor-water", value: input?.water?.value ?? null,
      recorded_at: "2026-09-25T02:00:00Z", received_at: "2026-09-25T02:00:01Z",
      freshness: input?.water?.freshness ?? "FRESH", quality: input?.water?.quality ?? "VALID", quality_reason: null,
    }],
    actuators: [{
      id: "act-light", desired_state: input?.growLight ?? null, reported_state: input?.growLight ?? null,
      synchronization: "IN_SYNC", command_status: null, command_time: null, last_ack_at: null, failure_reason: null,
    }],
    alerts: [],
  }
  return { inventory, runtime, updated_at: "2026-09-25T02:00:00Z" }
}

describe("SCADA scenario image mapping", () => {
  it("maps a fresh valid WATER_LEVELW2 fish-tank value to the 100% image bucket", () => {
    const signals = deriveScadaScenarioSignals(source({ water: { value: 100 } }), 9)
    const image = resolveScadaScenarioImage(signals)

    expect(signals.waterLevel).toMatchObject({ value: 100, status: "AVAILABLE", sourceCode: "WATER_LEVELW2" })
    expect(signals.feederOpen).toMatchObject({ value: null, status: "NONE" })
    expect(signals.raining).toMatchObject({ value: null, status: "NONE" })
    expect(image.filename).toBe("Máy cho cá ăn đóng nắp; Bể cá 100%; Buổi sáng.jpg")
    expect(image.fallbackDimensions).toEqual(["FEEDER", "WEATHER"])
  })

  it("uses WATER_LEVELW2 for the fish tank and ignores the biofilter WATER_LEVEL model", () => {
    const runtimeSource = source({ water: { value: 60 } })
    runtimeSource.inventory.sensors = [
      {
        ...runtimeSource.inventory.sensors[0],
        id: "sensor-biofilter",
        code: "WATER_LEVEL",
        name: "Mực nước bể lọc vi sinh",
        sensor_model_code: "WATER_LEVEL",
      },
      {
        ...runtimeSource.inventory.sensors[0],
        id: "sensor-fish-tank",
        code: "WATER_LEVELW2",
        name: "Mực nước bể cá",
        sensor_model_code: "WATER_LEVELW2",
      },
    ]
    runtimeSource.runtime.sensors = [
      { ...runtimeSource.runtime.sensors[0], id: "sensor-biofilter", value: 100 },
      { ...runtimeSource.runtime.sensors[0], id: "sensor-fish-tank", value: 60 },
    ]

    const signals = deriveScadaScenarioSignals(runtimeSource, 9)
    const image = resolveScadaScenarioImage(signals)

    expect(signals.waterLevel).toMatchObject({
      value: 60,
      status: "AVAILABLE",
      sourceCode: "WATER_LEVELW2",
    })
    expect(image.filename).toBe("Máy cho cá ăn đóng nắp; Bể cá 60%; Buổi sáng.jpg")
  })

  it("does not use stale or invalid telemetry as a visual state", () => {
    const stale = deriveScadaScenarioSignals(source({ water: { value: 100, freshness: "STALE" } }), 9)
    const invalid = deriveScadaScenarioSignals(source({ water: { value: 100, quality: "INVALID" } }), 9)

    expect(stale.waterLevel).toMatchObject({ value: null, status: "STALE" })
    expect(invalid.waterLevel).toMatchObject({ value: null, status: "INVALID" })
    expect(resolveScadaScenarioImage(stale).filename).toBeNull()
    expect(resolveScadaScenarioImage(invalid).filename).toBeNull()
  })

  it("does not treat telemetry from an offline Device as current", () => {
    const signals = deriveScadaScenarioSignals(source({ water: { value: 100 }, deviceConnectivity: "OFFLINE" }), 9)
    expect(signals.waterLevel).toMatchObject({ value: null, status: "OFFLINE" })
    expect(resolveScadaScenarioImage(signals).filename).toBeNull()
  })
  it("uses reported GROW_LIGHT state at night and keeps missing feeder/weather explicitly NONE", () => {
    const signals = deriveScadaScenarioSignals(source({ water: { value: 60 }, growLight: true }), 21)
    const image = resolveScadaScenarioImage(signals)

    expect(signals.growLightOn).toMatchObject({ value: true, status: "AVAILABLE", sourceCode: "GROW_LIGHT" })
    expect(image.filename).toBe("Máy cho cá ăn đóng nắp; Bể cá 60%; Buổi tối có đèn.jpg")
    expect(image.assetUrl).toContain(encodeURIComponent(image.filename ?? ""))
    expect(image.fallbackDimensions).toEqual(["FEEDER", "WEATHER"])
  })
})
