import type { ScadaRuntimeResponse } from "@/api/contracts"

export type ScenarioSource = Pick<ScadaRuntimeResponse, "inventory" | "runtime" | "updated_at">
export type ScenarioSignalStatus = "AVAILABLE" | "NONE" | "STALE" | "INVALID" | "OFFLINE" | "DISABLED"
export type ScenarioSignal<T> = { value: T | null; status: ScenarioSignalStatus; sourceCode: string | null }

function timestamp(value: string | null | undefined) {
  return value ? Date.parse(value) || 0 : 0
}
export function readSensor(source: ScenarioSource, modelCode: string): ScenarioSignal<number> {
  const candidates = source.inventory.sensors.filter((sensor) => sensor.sensor_model_code === modelCode)
  if (!candidates.length) return { value: null, status: "NONE", sourceCode: modelCode }

  const evaluated = candidates.map((sensor) => {
    const device = source.inventory.devices.find((item) => item.id === sensor.device_id)
    if (!sensor.enabled || !device?.enabled) return { value: null, status: "DISABLED" as const, sourceCode: modelCode, at: 0 }
    const deviceRuntime = source.runtime.devices.find((item) => item.id === sensor.device_id)
    if ((deviceRuntime?.connectivity ?? device.connectivity) !== "ONLINE") return { value: null, status: "OFFLINE" as const, sourceCode: modelCode, at: 0 }
    const runtime = source.runtime.sensors.find((item) => item.id === sensor.id)
    if (!runtime || runtime.value === null || runtime.freshness === "NO_DATA") return { value: null, status: "NONE" as const, sourceCode: modelCode, at: timestamp(runtime?.recorded_at) }
    if (runtime.freshness === "STALE") return { value: null, status: "STALE" as const, sourceCode: modelCode, at: timestamp(runtime.recorded_at) }
    if (runtime.quality !== "VALID" || !Number.isFinite(runtime.value)) return { value: null, status: "INVALID" as const, sourceCode: modelCode, at: timestamp(runtime.recorded_at) }
    return { value: runtime.value, status: "AVAILABLE" as const, sourceCode: modelCode, at: timestamp(runtime.recorded_at) }
  })

  evaluated.sort((a, b) => Number(b.status === "AVAILABLE") - Number(a.status === "AVAILABLE") || b.at - a.at)
  const best = evaluated[0]
  return { value: best.value, status: best.status, sourceCode: best.sourceCode }
}
export function readActuator(source: ScenarioSource, modelCode: string): ScenarioSignal<boolean> {
  const candidates = source.inventory.actuators.filter((actuator) => actuator.actuator_model_code === modelCode)
  if (!candidates.length) return { value: null, status: "NONE", sourceCode: modelCode }

  const evaluated = candidates.map((actuator) => {
    const device = source.inventory.devices.find((item) => item.id === actuator.device_id)
    if (!actuator.enabled || !device?.enabled) return { value: null, status: "DISABLED" as const, sourceCode: modelCode, at: 0 }
    const deviceRuntime = source.runtime.devices.find((item) => item.id === actuator.device_id)
    if ((deviceRuntime?.connectivity ?? device.connectivity) !== "ONLINE") return { value: null, status: "OFFLINE" as const, sourceCode: modelCode, at: 0 }
    const runtime = source.runtime.actuators.find((item) => item.id === actuator.id)
    if (!runtime || runtime.reported_state === null) return { value: null, status: "NONE" as const, sourceCode: modelCode, at: timestamp(runtime?.last_ack_at ?? runtime?.command_time) }
    return { value: runtime.reported_state, status: "AVAILABLE" as const, sourceCode: modelCode, at: timestamp(runtime.last_ack_at ?? runtime.command_time) }
  })

  evaluated.sort((a, b) => Number(b.status === "AVAILABLE") - Number(a.status === "AVAILABLE") || b.at - a.at)
  const best = evaluated[0]
  return { value: best.value, status: best.status, sourceCode: best.sourceCode }
}
