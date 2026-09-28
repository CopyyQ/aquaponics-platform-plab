import { readActuator, readSensor } from "./scada-signals"
import type { ScenarioSignal, ScenarioSignalStatus, ScenarioSource } from "./scada-signals"

export type { ScenarioSignal, ScenarioSignalStatus, ScenarioSource }
/**
 * Mốc phần trăm mà ảnh nền chuyển từ bản vẽ bể vơi sang bản vẽ bể đầy.
 * Cột đo mực nước cũng ghi mốc này lên vạch chia, nên hai nơi phải dùng
 * chung một con số để không bao giờ nói khác nhau.
 */
export const TANK_FULL_THRESHOLD = 80

export type ScenarioTimeOfDay = "DAY" | "NIGHT"
export type ScenarioFallbackDimension = "FEEDER" | "WEATHER" | "LIGHT"

export interface ScadaScenarioSignals {
  waterLevel: ScenarioSignal<number>
  growLightOn: ScenarioSignal<boolean>
  feederOpen: ScenarioSignal<boolean>
  raining: ScenarioSignal<boolean>
  timeOfDay: ScenarioTimeOfDay
}

export interface ScadaScenarioImageSelection {
  slug: string | null
  label: string | null
  assetUrl: string | null
  tankVisualLevel: 60 | 100 | null
  fallbackDimensions: ScenarioFallbackDimension[]
}

export function deriveScadaScenarioSignals(source: ScenarioSource, localHour: number): ScadaScenarioSignals {
  return {
    waterLevel: readSensor(source, "WATER_LEVELW2"),
    growLightOn: readActuator(source, "GROW_LIGHT"),
    feederOpen: { value: null, status: "NONE", sourceCode: null },
    raining: { value: null, status: "NONE", sourceCode: null },
    timeOfDay: localHour >= 6 && localHour < 18 ? "DAY" : "NIGHT",
  }
}
export function resolveScadaScenarioImage(signals: ScadaScenarioSignals): ScadaScenarioImageSelection {
  if (signals.waterLevel.value === null || signals.waterLevel.status !== "AVAILABLE") {
    return { slug: null, label: null, assetUrl: null, tankVisualLevel: null, fallbackDimensions: [] }
  }

  const tankVisualLevel: 60 | 100 = signals.waterLevel.value >= TANK_FULL_THRESHOLD ? 100 : 60
  const fallbackDimensions: ScenarioFallbackDimension[] = []
  const feederOpen = signals.feederOpen.value ?? false
  if (signals.feederOpen.value === null) fallbackDimensions.push("FEEDER")

  const raining = signals.raining.value ?? false
  if (signals.raining.value === null) fallbackDimensions.push("WEATHER")

  const lightOn = signals.growLightOn.value ?? false
  const needsLightState = raining || signals.timeOfDay === "NIGHT"
  if (needsLightState && signals.growLightOn.value === null) fallbackDimensions.push("LIGHT")

  // Asset names stay ASCII: diacritics and ";" break static file serving in the Vite dev server
  // and do not survive copying this source tree between machines.
  const sceneSlug = raining
    ? `rain-${lightOn ? "light" : "dark"}`
    : signals.timeOfDay === "DAY"
      ? "morning"
      : `night-${lightOn ? "light" : "dark"}`
  const slug = `feeder-${feederOpen ? "open" : "closed"}_tank-${tankVisualLevel}_${sceneSlug}.jpg`

  const scenePart = raining
    ? `trời mưa ${lightOn ? "có đèn" : "không đèn"}`
    : signals.timeOfDay === "DAY"
      ? "Buổi sáng"
      : `Buổi tối ${lightOn ? "có đèn" : "không đèn"}`
  const label = `Máy cho cá ăn ${feederOpen ? "mở nắp" : "đóng nắp"}; Bể cá ${tankVisualLevel}%; ${scenePart}`

  return {
    slug,
    label,
    assetUrl: `/scada/scenarios/${slug}`,
    tankVisualLevel,
    fallbackDimensions,
  }
}
