import { describe, expect, it } from "vitest"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { resolveScadaActuatorTarget } from "./scada-actuator-target"

function source(overrides: { connectivity?: string; reported?: boolean | null; command?: string | null; enabled?: boolean } = {}): ScenarioSource {
  return {
    updated_at: "2026-10-01T03:00:00Z",
    inventory: {
      devices: [{ id: "d1", code: "D1", name: "Tủ", device_template_id: null, template_code: null, enabled: true, connectivity: "ONLINE", last_seen_at: null }],
      sensors: [],
      actuators: [{ id: "a1", code: "BIOFILTER_PUMP", name: "Bơm bể lọc", actuator_model_code: "BIOFILTER_PUMP", device_id: "d1", enabled: overrides.enabled ?? true }],
    },
    runtime: {
      devices: [{ id: "d1", connectivity: overrides.connectivity ?? "ONLINE", last_seen_at: null }],
      sensors: [],
      actuators: [{
        id: "a1",
        desired_state: true,
        reported_state: overrides.reported === undefined ? true : overrides.reported,
        synchronization: "IN_SYNC",
        command_status: overrides.command ?? "ACKNOWLEDGED",
        command_time: null,
        last_ack_at: "2026-10-01T03:00:00Z",
        failure_reason: null,
      }],
      alerts: [],
    },
  } as ScenarioSource
}

describe("resolveScadaActuatorTarget", () => {
  it("returns ids and state for an online actuator", () => {
    expect(resolveScadaActuatorTarget(source(), "BIOFILTER_PUMP")).toMatchObject({
      actuatorId: "a1",
      deviceId: "d1",
      on: true,
      pending: false,
      availability: { allowed: true },
    })
  })

  it("returns null when no actuator matches the model code", () => {
    expect(resolveScadaActuatorTarget(source(), "GROW_LIGHT")).toBeNull()
  })

  it("blocks commands and hides stale state when the device is offline", () => {
    expect(resolveScadaActuatorTarget(source({ connectivity: "OFFLINE" }), "BIOFILTER_PUMP")).toMatchObject({
      on: null,
      availability: { allowed: false, reason: "DEVICE_OFFLINE" },
    })
  })

  it("blocks a second command while the previous one is pending", () => {
    expect(resolveScadaActuatorTarget(source({ command: "PENDING" }), "BIOFILTER_PUMP")).toMatchObject({
      pending: true,
      availability: { allowed: false, reason: "COMMAND_PENDING" },
    })
  })
})
