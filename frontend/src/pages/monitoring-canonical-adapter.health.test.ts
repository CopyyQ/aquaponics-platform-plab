import { describe, expect, it } from "vitest"
import { deriveMonitoringHealthStatus } from "./monitoring-canonical-adapter"

describe("deriveMonitoringHealthStatus", () => {
  it("phân biệt toàn bộ NO_DATA với dữ liệu đã có nhưng bị cũ", () => {
    expect(
      deriveMonitoringHealthStatus({
        criticalAlertCount: 0,
        enabledSensorCount: 13,
        reportingSensorCount: 0,
        staleSensorCount: 12,
        noDataSensorCount: 1,
        hasReasons: true,
      }),
    ).toBe("WARNING")

    expect(
      deriveMonitoringHealthStatus({
        criticalAlertCount: 0,
        enabledSensorCount: 13,
        reportingSensorCount: 0,
        staleSensorCount: 0,
        noDataSensorCount: 13,
        hasReasons: true,
      }),
    ).toBe("NO_DATA")
  })

  it("ưu tiên CRITICAL và giữ HEALTHY khi không có lý do cảnh báo", () => {
    expect(
      deriveMonitoringHealthStatus({
        criticalAlertCount: 1,
        enabledSensorCount: 13,
        reportingSensorCount: 13,
        staleSensorCount: 0,
        noDataSensorCount: 0,
        hasReasons: true,
      }),
    ).toBe("CRITICAL")

    expect(
      deriveMonitoringHealthStatus({
        criticalAlertCount: 0,
        enabledSensorCount: 13,
        reportingSensorCount: 13,
        staleSensorCount: 0,
        noDataSensorCount: 0,
        hasReasons: false,
      }),
    ).toBe("HEALTHY")
  })
})
