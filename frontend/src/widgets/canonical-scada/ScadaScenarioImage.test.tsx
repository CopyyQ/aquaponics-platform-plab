import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { ScadaRuntimeResponse } from "@/api/contracts"
import { ScadaScenarioImage } from "./ScadaScenarioImage"

type ScenarioRuntime = Pick<ScadaRuntimeResponse, "aquaponics_system" | "inventory" | "runtime" | "updated_at">

function runtime(waterValue: number | null, freshness: "FRESH" | "STALE" | "NO_DATA" = "FRESH"): ScenarioRuntime {
  return {
    aquaponics_system: { id: "project-1", code: "AQS-1", name: "Hệ thống Aquaponics", status: "ACTIVE" },
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: 1, template_code: "AQUAPONICS_SYSTEM_DEVICE", enabled: true, connectivity: "ONLINE", last_seen_at: null }],
      sensors: [{ id: "sensor-water", code: "WATER_LEVELW2", name: "Mực nước bể cá", sensor_model_code: "WATER_LEVELW2", unit: "%", device_id: "dev-1", enabled: true }],
      actuators: [],
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity: "ONLINE", last_seen_at: null }],
      sensors: [{ id: "sensor-water", value: waterValue, recorded_at: "2026-09-25T02:00:00Z", received_at: "2026-09-25T02:00:01Z", freshness, quality: "VALID", quality_reason: null }],
      actuators: [],
      alerts: [],
    },
    updated_at: "2026-09-25T02:00:00Z",
  }
}

describe("ScadaScenarioImage", () => {
  it("shows the Project database WATER_LEVELW2 value and selects the matching 100% asset", () => {
    const markup = renderToStaticMarkup(<ScadaScenarioImage runtime={runtime(100)} localHour={9} />)

    expect(markup).toContain("Mực nước bể cá")
    expect(markup).toContain("100%")
    expect(markup).toContain("/scada/scenarios/feeder-closed_tank-100_morning.jpg")
    expect(markup).toContain("Máy cho cá ăn đóng nắp; Bể cá 100%; Buổi sáng")
    expect(markup).toContain("Chưa có dữ liệu")
  })
  it("still renders the diagram when WATER_LEVELW2 is stale, flagging the tank as illustrative", () => {
    const markup = renderToStaticMarkup(<ScadaScenarioImage runtime={runtime(100, "STALE")} localHour={9} />)

    // Số cũ không được trình bày như số đang sống
    expect(markup).toContain("Dữ liệu cũ")
    // Nhưng sơ đồ vẫn phải vẽ ra, kèm lời nói rõ phần bể chỉ là minh hoạ
    expect(markup).toContain("<img")
    expect(markup).toContain("mực nước bể cá")
  })
})
