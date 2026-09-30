import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { SCADA_AERATOR } from "@/entities/scada/model/scada-cards"
import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { ScadaAerator, isAerating } from "./ScadaAerator"

function source(state: { reported: boolean | null; connectivity?: string }): ScenarioSource {
  const connectivity = state.connectivity ?? "ONLINE"
  return {
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: null, template_code: null, enabled: true, connectivity, last_seen_at: null }],
      sensors: [],
      actuators: [{ id: "a-1", code: SCADA_AERATOR.code, name: "Máy sủi oxy", actuator_model_code: SCADA_AERATOR.code, device_id: "dev-1", enabled: true }],
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity, last_seen_at: null }],
      sensors: [],
      actuators: [{ id: "a-1", desired_state: true, reported_state: state.reported, synchronization: "IN_SYNC", command_status: null, command_time: null, last_ack_at: null, failure_reason: null }],
      alerts: [],
    },
    updated_at: "2026-09-30T02:00:00Z",
  } as unknown as ScenarioSource
}

describe("isAerating", () => {
  it("bubbles only while the aerator reports itself running", () => {
    expect(isAerating(source({ reported: true }))).toBe(true)
    expect(isAerating(source({ reported: false }))).toBe(false)
  })

  it("stays quiet when the device is unreachable, rather than implying oxygen is flowing", () => {
    expect(isAerating(source({ reported: true, connectivity: "OFFLINE" }))).toBe(false)
  })
})

describe("ScadaAerator", () => {
  it("draws nothing at all once the aerator stops", () => {
    expect(renderToStaticMarkup(<ScadaAerator source={source({ reported: false })} />)).toBe("")
  })

  it("rises the bubbles across the calibrated patch of water", () => {
    const markup = renderToStaticMarkup(<ScadaAerator source={source({ reported: true })} />)
    const rise = (SCADA_AERATOR.box.h / 100) * 1100
    expect(markup).toContain('viewBox="0 0 1750 1100"')
    expect(markup).toContain(`--scada-bubble-rise:-${rise}px`)
  })

  it("gives each bubble its own pace so the plume never pulses as one block", () => {
    const markup = renderToStaticMarkup(<ScadaAerator source={source({ reported: true })} />)
    const durations = new Set(markup.match(/--scada-bubble-duration:[\d.]+s/g))
    expect(durations.size).toBeGreaterThan(3)
  })
})
