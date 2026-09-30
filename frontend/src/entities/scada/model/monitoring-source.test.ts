import { describe, expect, it } from "vitest"
import type { Alert, MonitoringActuator, MonitoringLatest, MonitoringSensor } from "@/api/contracts"
import { deriveScadaIssues, toScadaSource } from "./monitoring-source"
import { readActuator, readSensor } from "./scada-signals"

function sensor(overrides: Partial<MonitoringSensor> & Pick<MonitoringSensor, "id" | "code">): MonitoringSensor {
  return {
    name: `Cảm biến ${overrides.code}`,
    unit: "%",
    is_enabled: true,
    connection_status: "ONLINE",
    data_status: "ONLINE",
    latest: { value: 42, recorded_at: "2026-09-29T02:00:00Z", quality: "VALID", freshness: "FRESH" },
    lower_threshold: null,
    upper_threshold: null,
    ...overrides,
  } as MonitoringSensor
}

function actuator(overrides: Partial<MonitoringActuator> & Pick<MonitoringActuator, "id" | "code">): MonitoringActuator {
  return {
    name: `Cơ cấu ${overrides.code}`,
    actuator_model: null,
    connection_status: "ONLINE",
    desired_state: true,
    reported_state: true,
    synchronization_status: "IN_SYNC",
    latest_command: null,
    last_reported_at: "2026-09-29T02:00:00Z",
    last_db_updated_at: "2026-09-29T02:00:00Z",
    electrical: {} as MonitoringActuator["electrical"],
    active_alert: null,
    ...overrides,
  } as MonitoringActuator
}

function monitoring(overrides: Partial<MonitoringLatest["devices"][number]> = {}): MonitoringLatest {
  return {
    aquaponics_system_id: "sys-1",
    devices: [
      {
        id: "dev-1",
        code: "D1",
        name: "Thiết bị chính",
        is_enabled: true,
        connection_status: "ONLINE",
        location: null,
        last_seen_at: "2026-09-29T02:00:00Z",
        sensors: [sensor({ id: "s-ph", code: "PH", unit: "pH" })],
        actuators: [actuator({ id: "a-pump", code: "FISH_TANK_PUMP" })],
        ...overrides,
      },
    ],
  }
}

function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 1,
    resource_type: "SENSOR",
    device_id: "dev-1",
    sensor_id: "s-ph",
    actuator_id: null,
    severity: "WARNING",
    status: "OPEN",
    message: "pH nước cao hơn ngưỡng cho phép.",
    started_at: "2026-09-28T11:49:17Z",
    ...overrides,
  } as Alert
}

describe("toScadaSource", () => {
  it("đọc được giá trị cảm biến theo mã mẫu", () => {
    const source = toScadaSource(monitoring(), [])
    expect(readSensor(source, "PH")).toMatchObject({ value: 42, status: "AVAILABLE" })
  })

  it("đọc được trạng thái cơ cấu chấp hành", () => {
    const source = toScadaSource(monitoring(), [])
    expect(readActuator(source, "FISH_TANK_PUMP")).toMatchObject({ value: true, status: "AVAILABLE" })
  })

  it("báo dữ liệu cũ khi freshness là STALE", () => {
    const stale = monitoring({
      sensors: [sensor({ id: "s-ph", code: "PH", latest: { value: 8.1, recorded_at: "2026-09-29T01:00:00Z", quality: "VALID", freshness: "STALE" } })],
    })
    expect(readSensor(toScadaSource(stale, []), "PH").status).toBe("STALE")
  })

  it("báo đã tắt khi cảm biến bị vô hiệu hóa", () => {
    const off = monitoring({ sensors: [sensor({ id: "s-ph", code: "PH", is_enabled: false })] })
    expect(readSensor(toScadaSource(off, []), "PH").status).toBe("DISABLED")
  })

  it("báo mất kết nối khi thiết bị ngoại tuyến", () => {
    const offline = monitoring({ connection_status: "OFFLINE" })
    expect(readSensor(toScadaSource(offline, []), "PH").status).toBe("OFFLINE")
  })

  it("trả về NONE cho mã không có thiết bị nào", () => {
    expect(readSensor(toScadaSource(monitoring(), []), "NO3").status).toBe("NONE")
  })

  it("lấy mốc thời gian mới nhất của dữ liệu làm updated_at", () => {
    expect(toScadaSource(monitoring(), []).updated_at).toBe("2026-09-29T02:00:00Z")
  })
})

describe("deriveScadaIssues", () => {
  it("sinh sự cố mất kết nối cho thiết bị ngoại tuyến", () => {
    const issues = deriveScadaIssues(monitoring({ connection_status: "OFFLINE" }), [])
    expect(issues).toHaveLength(1)
    expect(issues[0]).toMatchObject({ severity: "HIGH", title: "Thiết bị mất kết nối", device_id: "dev-1" })
  })

  it("sinh sự cố vô hiệu hóa thay vì mất kết nối khi thiết bị bị tắt", () => {
    const issues = deriveScadaIssues(monitoring({ is_enabled: false, connection_status: "OFFLINE" }), [])
    expect(issues.map((issue) => issue.title)).toEqual(["Thiết bị đã vô hiệu hóa"])
  })

  it("sinh sự cố khi lệnh điều khiển hết hạn chờ", () => {
    const timeout = monitoring({
      actuators: [actuator({ id: "a-pump", code: "FISH_TANK_PUMP", latest_command: { status: "TIMEOUT", requested_at: "2026-09-29T01:00:00Z" } })],
    })
    expect(deriveScadaIssues(timeout, [])[0]).toMatchObject({ severity: "CRITICAL", actuator_id: "a-pump" })
  })

  it("sinh sự cố lệch đồng bộ khi trạng thái không khớp", () => {
    const outOfSync = monitoring({
      actuators: [actuator({ id: "a-pump", code: "FISH_TANK_PUMP", reported_state: false, synchronization_status: "OUT_OF_SYNC" })],
    })
    expect(deriveScadaIssues(outOfSync, [])[0]).toMatchObject({ severity: "HIGH", title: "Trạng thái cơ cấu chưa đồng bộ" })
  })

  it("chuyển cảnh báo đang mở thành sự cố gắn đúng cảm biến", () => {
    const issues = deriveScadaIssues(monitoring(), [alert()])
    expect(issues[0]).toMatchObject({ title: "pH nước cao hơn ngưỡng cho phép.", sensor_id: "s-ph", severity: "WARNING" })
  })

  it("bỏ qua cảnh báo đã khép lại", () => {
    expect(deriveScadaIssues(monitoring(), [alert({ status: "NORMALIZED" })])).toEqual([])
  })

  it("giữ cảnh báo nghiêm trọng khi một cảm biến vướng nhiều cảnh báo", () => {
    const issues = deriveScadaIssues(monitoring(), [alert(), alert({ id: 2, severity: "CRITICAL", message: "pH vượt ngưỡng nguy hiểm." })])
    expect(issues).toHaveLength(1)
    expect(issues[0].title).toBe("pH vượt ngưỡng nguy hiểm.")
  })

  it("sinh sự cố chất lượng khi dữ liệu ngoài miền hợp lệ", () => {
    const invalid = monitoring({
      sensors: [sensor({ id: "s-ph", code: "PH", latest: { value: 99, recorded_at: "2026-09-29T02:00:00Z", quality: "OUT_OF_RANGE", freshness: "FRESH" } })],
    })
    expect(deriveScadaIssues(invalid, [])[0]).toMatchObject({ title: "Dữ liệu ngoài miền hợp lệ", severity: "WARNING" })
  })

  it("xếp sự cố nặng lên trước", () => {
    const messy = monitoring({
      connection_status: "OFFLINE",
      actuators: [actuator({ id: "a-pump", code: "FISH_TANK_PUMP", latest_command: { status: "FAILED", requested_at: "2026-09-29T01:00:00Z" } })],
    })
    expect(deriveScadaIssues(messy, []).map((issue) => issue.severity)).toEqual(["CRITICAL", "HIGH"])
  })
})
