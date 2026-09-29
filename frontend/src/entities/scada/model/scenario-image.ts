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
export type ScenarioFallbackDimension = "FEEDER" | "WEATHER" | "LIGHT" | "TANK"

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
  const fallbackDimensions: ScenarioFallbackDimension[] = []

  // Mực nước hỏng thì chỉ mất phần phụ thuộc vào mực nước, không kéo sập cả sơ đồ:
  // vẫn vẽ một bản ảnh và đánh dấu phần bể là minh hoạ, để những chỉ số còn sống
  // vẫn hiển thị được. Trước đây một cảm biến im lặng là cả màn hình trắng.
  const level = signals.waterLevel.status === "AVAILABLE" ? signals.waterLevel.value : null
  if (level === null) fallbackDimensions.push("TANK")
  const drawnLevel: 60 | 100 = level !== null && level >= TANK_FULL_THRESHOLD ? 100 : 60
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
  const slug = `feeder-${feederOpen ? "open" : "closed"}_tank-${drawnLevel}_${sceneSlug}.jpg`

  const scenePart = raining
    ? `trời mưa ${lightOn ? "có đèn" : "không đèn"}`
    : signals.timeOfDay === "DAY"
      ? "Buổi sáng"
      : `Buổi tối ${lightOn ? "có đèn" : "không đèn"}`
  const label = `Máy cho cá ăn ${feederOpen ? "mở nắp" : "đóng nắp"}; Bể cá ${drawnLevel}%; ${scenePart}`

  return {
    slug,
    label,
    assetUrl: `/scada/scenarios/${slug}`,
    // null nghĩa là không biết mực nước thật, dù ảnh vẫn phải vẽ ra một mức nào đó
    tankVisualLevel: level === null ? null : drawnLevel,
    fallbackDimensions,
  }
}
