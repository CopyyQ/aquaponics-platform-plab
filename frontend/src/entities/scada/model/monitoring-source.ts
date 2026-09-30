import type {
  Alert,
  MonitoringActuator,
  MonitoringDevice,
  MonitoringLatest,
  MonitoringSensor,
  ScadaFreshness,
  ScadaIssue,
  ScadaQuality,
  ScadaSynchronization,
} from "@/api/contracts"
import { isOpenAlert } from "@/entities/alert/model/alert-status"
import type { ScenarioSource } from "./scada-signals"

/**
 * Nguồn dữ liệu cho lớp phủ SCADA, dựng từ `monitoring/latest` thay cho `scada/runtime`.
 *
 * Lớp phủ vốn đọc `scada/runtime`, nhưng endpoint đó đã ngừng dùng. `monitoring/latest`
 * chở đủ mọi thứ lớp phủ cần và lại đang được thanh bên gọi sẵn mỗi 15 giây, nên dùng
 * chung một lượt gọi thay vì thêm một endpoint nữa.
 *
 * Giữ nguyên hình dạng cũ (`inventory` + `runtime` + `issues`) là có chủ ý: toàn bộ phần
 * đọc chỉ số, xếp hạng trạng thái và chọn ảnh nền không phải sửa gì.
 */
export interface MonitoringScadaSource extends ScenarioSource {
  aquaponics_system: { id: string }
  issues: ScadaIssue[]
}

/**
 * Thẻ trên sơ đồ gắn theo mã *mẫu* thiết bị, còn `monitoring/latest` chỉ trả mã của
 * cảm biến/cơ cấu đã lắp. Hai mã này luôn trùng nhau vì thiết bị được đúc từ khuôn,
 * khuôn chép thẳng mã mẫu xuống bản lắp đặt.
 */
function modelCode(item: { code: string }) {
  return item.code
}

const QUALITIES: ReadonlySet<string> = new Set(["VALID", "OUT_OF_RANGE", "INVALID", "UNVALIDATED"])
const FRESHNESSES: ReadonlySet<string> = new Set(["FRESH", "STALE", "NO_DATA"])
const SYNCHRONIZATIONS: ReadonlySet<string> = new Set(["IN_SYNC", "OUT_OF_SYNC", "UNKNOWN"])

// Backend có thể thêm mã mới; coi mã lạ là không đọc được còn hơn hiện số sai.
function toQuality(value: string | null | undefined): ScadaQuality {
  return QUALITIES.has(value ?? "") ? (value as ScadaQuality) : "INVALID"
}

function toFreshness(value: string | null | undefined): ScadaFreshness {
  return FRESHNESSES.has(value ?? "") ? (value as ScadaFreshness) : "NO_DATA"
}

function toSynchronization(value: string | null | undefined): ScadaSynchronization {
  return SYNCHRONIZATIONS.has(value ?? "") ? (value as ScadaSynchronization) : "UNKNOWN"
}

function eachSensor(monitoring: MonitoringLatest): { device: MonitoringDevice; sensor: MonitoringSensor }[] {
  return monitoring.devices.flatMap((device) => device.sensors.map((sensor) => ({ device, sensor })))
}

function eachActuator(monitoring: MonitoringLatest): { device: MonitoringDevice; actuator: MonitoringActuator }[] {
  return monitoring.devices.flatMap((device) => device.actuators.map((actuator) => ({ device, actuator })))
}

/** Mốc thời gian mới nhất có trong dữ liệu; dùng để chọn ảnh nền ngày/đêm. */
function latestTimestamp(monitoring: MonitoringLatest): string {
  const stamps = eachSensor(monitoring)
    .map(({ sensor }) => sensor.latest?.recorded_at)
    .filter((value): value is string => Boolean(value))
  return stamps.length ? stamps.reduce((latest, current) => (current > latest ? current : latest)) : new Date().toISOString()
}

const SEVERITY_ORDER: Record<ScadaIssue["severity"], number> = { CRITICAL: 0, HIGH: 1, WARNING: 2, INFO: 3 }

function issueFromAlert(alert: Alert, ownerName: string, deviceName: string, state: string): ScadaIssue {
  return {
    id: `alert-${alert.id}`,
    severity: alert.severity,
    title: alert.message,
    root_cause: ownerName,
    affected_entities: [deviceName, ownerName],
    current_state: state,
    timestamp: alert.started_at,
    // Backend cũ gắn cứng "Kiểm tra cảm biến, hiệu chuẩn và ngưỡng cảnh báo" cho mọi
    // cảnh báo, kể cả khi cảm biến không hề hỏng. Dẫn sang trang cảnh báo thì đúng hơn.
    suggested_action: "Xem chi tiết và cách xử lý trong trang cảnh báo.",
    device_id: alert.device_id,
    sensor_id: alert.sensor_id,
    actuator_id: alert.actuator_id,
  }
}

/**
 * Dựng lại danh sách sự cố mà `scada/runtime` từng tính sẵn ở backend.
 *
 * Bốn loại đầu suy ra từ chính `monitoring/latest` (mất kết nối, không phản hồi lệnh,
 * lệch đồng bộ, dữ liệu ngoài miền hợp lệ). Loại thứ năm — vượt ngưỡng — lấy từ danh
 * sách cảnh báo, vì đó là thứ duy nhất được lưu thành bản ghi trong cơ sở dữ liệu.
 */
export function deriveScadaIssues(monitoring: MonitoringLatest, alerts: readonly Alert[]): ScadaIssue[] {
  const open = alerts.filter(isOpenAlert)
  const bySensor = new Map<string, Alert>()
  const byActuator = new Map<string, Alert>()
  for (const alert of open) {
    // Một cảm biến có thể vướng nhiều cảnh báo; thẻ chỉ đủ chỗ cho cái nặng nhất.
    const target = alert.sensor_id ? bySensor : alert.actuator_id ? byActuator : null
    const key = alert.sensor_id ?? alert.actuator_id
    if (!target || !key) continue
    const current = target.get(key)
    if (!current || (current.severity !== "CRITICAL" && alert.severity === "CRITICAL")) target.set(key, alert)
  }

  const issues: ScadaIssue[] = []

  for (const device of monitoring.devices) {
    if (!device.is_enabled) {
      issues.push({
        id: `device-${device.id}-disabled`,
        severity: "INFO",
        title: "Thiết bị đã vô hiệu hóa",
        root_cause: device.name,
        affected_entities: device.sensors.map((sensor) => sensor.name),
        current_state: `${device.sensors.length} phép đo bị ảnh hưởng.`,
        timestamp: device.last_seen_at,
        suggested_action: "Kiểm tra lý do vô hiệu hóa trong trang thiết bị.",
        device_id: device.id,
        sensor_id: null,
        actuator_id: null,
      })
    } else if (device.connection_status !== "ONLINE") {
      issues.push({
        id: `device-${device.id}-offline`,
        severity: "HIGH",
        title: "Thiết bị mất kết nối",
        root_cause: device.name,
        affected_entities: [...device.sensors, ...device.actuators].map((item) => item.name),
        current_state: `${device.sensors.length} phép đo gián đoạn, ${device.actuators.length} cơ cấu không thể điều khiển.`,
        timestamp: device.last_seen_at,
        suggested_action: "Kiểm tra nguồn, mạng LAN và kết nối MQTT của thiết bị.",
        device_id: device.id,
        sensor_id: null,
        actuator_id: null,
      })
    }
  }

  for (const { device, actuator } of eachActuator(monitoring)) {
    const alert = byActuator.get(actuator.id)
    if (alert) {
      issues.push(issueFromAlert(alert, actuator.name, device.name, `Mong muốn: ${actuator.desired_state}; thực tế: ${actuator.reported_state}.`))
      continue
    }
    const commandStatus = actuator.latest_command?.status
    if (commandStatus === "TIMEOUT" || commandStatus === "FAILED") {
      issues.push({
        id: `actuator-${actuator.id}-${commandStatus.toLowerCase()}`,
        severity: "CRITICAL",
        title: `${actuator.name} không phản hồi lệnh`,
        root_cause: `Lệnh gần nhất: ${commandStatus}`,
        affected_entities: [device.name, actuator.name],
        current_state: `Mong muốn: ${actuator.desired_state}; thực tế: ${actuator.reported_state}.`,
        timestamp: actuator.latest_command?.requested_at ?? null,
        suggested_action: "Kiểm tra kết nối Device và cơ cấu chấp hành trước khi gửi lại lệnh.",
        device_id: device.id,
        sensor_id: null,
        actuator_id: actuator.id,
      })
    } else if (toSynchronization(actuator.synchronization_status) === "OUT_OF_SYNC") {
      issues.push({
        id: `actuator-${actuator.id}-out-of-sync`,
        severity: "HIGH",
        title: "Trạng thái cơ cấu chưa đồng bộ",
        root_cause: actuator.name,
        affected_entities: [device.name, actuator.name],
        current_state: `Mong muốn: ${actuator.desired_state}; thực tế: ${actuator.reported_state}.`,
        timestamp: actuator.last_reported_at,
        suggested_action: "Kiểm tra trạng thái reported và kết nối điều khiển.",
        device_id: device.id,
        sensor_id: null,
        actuator_id: actuator.id,
      })
    }
  }

  for (const { device, sensor } of eachSensor(monitoring)) {
    if (!sensor.is_enabled) continue
    const state = sensor.latest?.value === null || sensor.latest === null
      ? "Chưa có dữ liệu mới."
      : `${sensor.latest.value} ${sensor.unit} · ${toFreshness(sensor.latest.freshness)} · ${toQuality(sensor.latest.quality)}`
    const alert = bySensor.get(sensor.id)
    if (alert) {
      issues.push(issueFromAlert(alert, sensor.name, device.name, state))
      continue
    }
    const quality = toQuality(sensor.latest?.quality)
    if (sensor.latest && (quality === "OUT_OF_RANGE" || quality === "INVALID")) {
      issues.push({
        id: `sensor-${sensor.id}-quality`,
        severity: "WARNING",
        title: "Dữ liệu ngoài miền hợp lệ",
        root_cause: sensor.name,
        affected_entities: [device.name, sensor.name],
        current_state: `${sensor.latest.value} ${sensor.unit}`,
        timestamp: sensor.latest.recorded_at,
        suggested_action: "Kiểm tra cảm biến, hiệu chuẩn và ngưỡng cấu hình.",
        device_id: device.id,
        sensor_id: sensor.id,
        actuator_id: null,
      })
    }
  }

  return issues.sort(
    (left, right) =>
      SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity] ||
      Date.parse(right.timestamp ?? "") - Date.parse(left.timestamp ?? ""),
  )
}

/** Chuyển `monitoring/latest` + danh sách cảnh báo thành nguồn cho lớp phủ SCADA. */
export function toScadaSource(monitoring: MonitoringLatest, alerts: readonly Alert[]): MonitoringScadaSource {
  return {
    aquaponics_system: { id: monitoring.aquaponics_system_id },
    inventory: {
      devices: monitoring.devices.map((device) => ({
        id: device.id,
        code: device.code,
        name: device.name,
        device_template_id: null,
        template_code: null,
        enabled: device.is_enabled,
        connectivity: device.connection_status,
        last_seen_at: device.last_seen_at,
      })),
      sensors: eachSensor(monitoring).map(({ device, sensor }) => ({
        id: sensor.id,
        code: sensor.code,
        name: sensor.name,
        sensor_model_code: modelCode(sensor),
        unit: sensor.unit,
        device_id: device.id,
        enabled: sensor.is_enabled,
      })),
      // monitoring/latest đã lọc bỏ cơ cấu bị tắt, nên cái nào còn ở đây là đang bật.
      actuators: eachActuator(monitoring).map(({ device, actuator }) => ({
        id: actuator.id,
        code: actuator.code,
        name: actuator.name,
        actuator_model_code: modelCode(actuator),
        device_id: device.id,
        enabled: true,
      })),
    },
    runtime: {
      devices: monitoring.devices.map((device) => ({
        id: device.id,
        connectivity: device.connection_status,
        last_seen_at: device.last_seen_at,
      })),
      sensors: eachSensor(monitoring).map(({ sensor }) => ({
        id: sensor.id,
        value: sensor.latest?.value ?? null,
        recorded_at: sensor.latest?.recorded_at ?? null,
        received_at: sensor.latest?.recorded_at ?? null,
        freshness: toFreshness(sensor.latest?.freshness),
        quality: toQuality(sensor.latest?.quality),
        quality_reason: sensor.latest?.quality_reason ?? null,
      })),
      actuators: eachActuator(monitoring).map(({ actuator }) => ({
        id: actuator.id,
        desired_state: actuator.desired_state,
        reported_state: actuator.reported_state,
        synchronization: toSynchronization(actuator.synchronization_status),
        command_status: actuator.latest_command?.status ?? null,
        command_time: actuator.latest_command?.requested_at ?? null,
        last_ack_at: actuator.last_reported_at,
        failure_reason: null,
      })),
      alerts: [],
    },
    issues: deriveScadaIssues(monitoring, alerts),
    updated_at: latestTimestamp(monitoring),
  }
}
