import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import type { MonitoringLatest } from "@/api/contracts"
import { toScadaSource } from "@/entities/scada/model/monitoring-source"
import { OwnerOverviewBoard } from "./OwnerOverviewBoard"

// Dựng từ monitoring/latest đúng như trang Tổng quan làm, để bài kiểm thử đi qua
// trọn đường dẫn dữ liệu mới thay vì chỉ kiểm phần hiển thị.
function monitoring(): MonitoringLatest {
  return {
    aquaponics_system_id: "project-1",
    devices: [
      {
        id: "dev-1",
        code: "D1",
        name: "Thiết bị",
        is_enabled: true,
        connection_status: "ONLINE",
        location: null,
        last_seen_at: null,
        sensors: [
          {
            id: "sensor-water",
            code: "WATER_LEVELW2",
            name: "Mực nước bể cá",
            unit: "%",
            is_enabled: true,
            connection_status: "ONLINE",
            data_status: "ONLINE",
            latest: { value: 100, recorded_at: "2026-09-25T04:40:00Z", quality: "VALID", freshness: "FRESH" },
            lower_threshold: null,
            upper_threshold: null,
          },
        ],
        actuators: [],
      },
    ],
  }
}

describe("OwnerOverviewBoard SCADA image", () => {
  it("replaces the chart placeholder with only the selected runtime image", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <OwnerOverviewBoard source={toScadaSource(monitoring(), [])} localHour={12} />
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
