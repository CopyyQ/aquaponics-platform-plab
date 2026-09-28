import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import type { ScadaRuntimeResponse } from "@/api/contracts"
import { OwnerOverviewBoard } from "./OwnerOverviewBoard"

type ScenarioRuntime = Pick<ScadaRuntimeResponse, "aquaponics_system" | "inventory" | "runtime" | "issues" | "updated_at">

function scadaRuntime(): ScenarioRuntime {
  return {
    aquaponics_system: { id: "project-1", code: "AQS-1", name: "Hệ thống Aquaponics", status: "ACTIVE" },
    inventory: {
      devices: [{ id: "dev-1", code: "D1", name: "Thiết bị", device_template_id: 1, template_code: "AQUAPONICS_SYSTEM_DEVICE", enabled: true, connectivity: "ONLINE", last_seen_at: null }],
      sensors: [{ id: "sensor-water", code: "WATER_LEVELW2", name: "Mực nước bể cá", sensor_model_code: "WATER_LEVELW2", unit: "%", device_id: "dev-1", enabled: true }],
      actuators: [],
    },
    runtime: {
      devices: [{ id: "dev-1", connectivity: "ONLINE", last_seen_at: null }],
      sensors: [{
        id: "sensor-water",
        value: 100,
        recorded_at: "2026-09-25T04:40:00Z",
        received_at: "2026-09-25T04:40:01Z",
        freshness: "FRESH",
        quality: "VALID",
        quality_reason: null,
      }],
      actuators: [],
      alerts: [],
    },
    issues: [],
    updated_at: "2026-09-25T04:40:01Z",
  }
}

describe("OwnerOverviewBoard SCADA image", () => {
  it("replaces the chart placeholder with only the selected runtime image", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <OwnerOverviewBoard scadaRuntime={scadaRuntime()} localHour={12} />
      </MemoryRouter>,
    )

    expect(markup).toContain("<img")
    expect(markup).toContain("Bể cá 100%")
    // Cảnh báo đã chuyển lên header nên không còn nằm trong board
    expect(markup).not.toContain("Cảnh báo")
    expect(markup).not.toContain("Xem tất cả")
    expect(markup).not.toContain("Khu vực biểu đồ")
    expect(markup).not.toContain("Ánh xạ dữ liệu runtime")
    // Board chỉ bọc lớp phủ SCADA, không tự dựng bảng chỉ số riêng
    expect(markup).toContain("scada-overlay")
    expect(markup).not.toContain("Xem sơ đồ chi tiết")
  })
})
