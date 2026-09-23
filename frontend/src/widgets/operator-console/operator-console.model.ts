import type { Alert, AlertDeliveryRecipient, AquaponicsSystem, MonitoringActuator, MonitoringDevice, MonitoringLatest, MonitoringSensor } from "@/api/contracts"

export type OperatorValueStatus = "NORMAL" | "ATTENTION" | "NO_DATA"
export type OperatorSensorIcon = "ph" | "humidity" | "waterTemp" | "airTemp" | "level" | "light" | "tds" | "pressure" | "generic"

const OPEN_ALERT_STATUSES = new Set(["PENDING", "OPEN", "ACKNOWLEDGED"])
const RESOLVED_ALERT_STATUSES = new Set(["NORMALIZED", "RESOLVED"])

export interface OperatorSensorCard {
  id: string
  deviceId: string
  name: string
  unit: string
  value: number | null
  recordedAt: string | null
  status: OperatorValueStatus
  icon: OperatorSensorIcon
  rangeLabel: string | null
}

export interface OperatorActuatorChip {
  id: string
  deviceId: string
  name: string
  on: boolean | null
}

export interface OperatorActuatorRow extends OperatorActuatorChip {
  model: string | null
  voltageV: number | null
  currentA: number | null
  freshness: string
  lastReportedAt: string | null
  connectionStatus: string
}

export interface OperatorAlertCard {
  id: number
  title: string
  detail: string
  startedAt: string
  open: boolean
}

export interface OperatorOverviewModel {
  system: AquaponicsSystem
  sensors: OperatorSensorCard[]
  actuators: OperatorActuatorChip[]
  banner: string | null
  openAlertCount: number
  lastUpdatedAt: string | null
  online: boolean
}

export interface OperatorDevicesModel {
  actuators: OperatorActuatorRow[]
  sensors: OperatorSensorCard[]
}

function finiteOrNull(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? null : value
}

export function resolveSensorIcon(name: string, unit: string): OperatorSensorIcon {
  const haystack = `${name} ${unit}`.toLocaleLowerCase("vi")
  if (haystack.includes("ph")) return "ph"
  if (haystack.includes("ẩm") || haystack.includes("humidity") || haystack.includes("%rh")) return "humidity"
  if (haystack.includes("nước") && (haystack.includes("nhiệt") || haystack.includes("temp") || unit.toLowerCase() === "°c")) return "waterTemp"
  if ((haystack.includes("môi trường") || haystack.includes("không khí") || haystack.includes("air")) && (haystack.includes("nhiệt") || haystack.includes("temp"))) return "airTemp"
  if (haystack.includes("nhiệt") || haystack.includes("temp") || unit.toLowerCase() === "°c") return haystack.includes("nước") ? "waterTemp" : "airTemp"
  if (haystack.includes("mực") || haystack.includes("level") || haystack.includes("wl")) return "level"
  if (haystack.includes("sáng") || haystack.includes("lux") || haystack.includes("light")) return "light"
  if (haystack.includes("ppm") || haystack.includes("tds") || haystack.includes("hòa tan") || haystack.includes("ec")) return "tds"
  if (haystack.includes("áp") || haystack.includes("pressure") || unit.toLowerCase() === "kpa") return "pressure"
  return "generic"
}

export function sensorValueStatus(sensor: Pick<MonitoringSensor, "latest" | "data_status" | "threshold_state">): OperatorValueStatus {
  const value = finiteOrNull(sensor.latest?.value ?? null)
  if (value === null) return "NO_DATA"
  if (sensor.threshold_state === "ABOVE" || sensor.threshold_state === "BELOW") return "ATTENTION"
  if (sensor.data_status === "OUT_OF_RANGE") return "ATTENTION"
  return "NORMAL"
}

export function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: value >= 100 ? 0 : 2 }).format(value)
}

export function safeRangeLabel(lower: number | null, upper: number | null) {
  if (lower !== null && upper !== null) return `An toàn: ${formatCompactNumber(lower)} – ${formatCompactNumber(upper)}`
  if (upper !== null) return `An toàn: ≤ ${formatCompactNumber(upper)}`
  if (lower !== null) return `An toàn: ≥ ${formatCompactNumber(lower)}`
  return null
}

export function toSensorCard(deviceId: string, sensor: MonitoringSensor): OperatorSensorCard {
  return {
    id: String(sensor.id),
    deviceId,
    name: sensor.name,
    unit: sensor.unit,
    value: finiteOrNull(sensor.latest?.value ?? null),
    recordedAt: sensor.latest?.recorded_at ?? null,
    status: sensorValueStatus(sensor),
    icon: resolveSensorIcon(sensor.name, sensor.unit),
    rangeLabel: safeRangeLabel(sensor.lower_threshold, sensor.upper_threshold),
  }
}

export function actuatorIsOn(actuator: Pick<MonitoringActuator, "reported_state">) {
  return actuator.reported_state
}

function flattenDevices(latest: MonitoringLatest | undefined): MonitoringDevice[] {
  return latest?.devices ?? []
}

export function collectSensorCards(latest: MonitoringLatest | undefined) {
  return flattenDevices(latest).flatMap((device) => device.sensors.map((sensor) => toSensorCard(String(device.id), sensor)))
}

export function toActuatorRow(deviceId: string, actuator: MonitoringActuator): OperatorActuatorRow {
  return {
    id: String(actuator.id),
    deviceId,
    name: actuator.name,
    on: actuatorIsOn(actuator),
    model: actuator.actuator_model,
    voltageV: finiteOrNull(actuator.electrical.voltage.value),
    currentA: finiteOrNull(actuator.electrical.current.value ?? actuator.electrical.current_a),
    freshness: actuator.electrical.freshness,
    lastReportedAt: actuator.last_reported_at,
    connectionStatus: actuator.connection_status,
  }
}

export function collectActuatorRows(latest: MonitoringLatest | undefined) {
  return flattenDevices(latest).flatMap((device) => device.actuators.map((actuator) => toActuatorRow(String(device.id), actuator)))
}

export function buildAlertBanner(sensors: OperatorSensorCard[], openAlertCount: number) {
  if (openAlertCount <= 0) return null
  const attention = sensors.filter((sensor) => sensor.status === "ATTENTION").map((sensor) => sensor.name)
  if (attention.length >= 2) return `${openAlertCount} cảnh báo: ${attention[0]} và ${attention[1]} vượt ngưỡng an toàn`
  if (attention.length === 1) return `${openAlertCount} cảnh báo: ${attention[0]} vượt ngưỡng an toàn`
  return `${openAlertCount} cảnh báo đang mở`
}

export function isOpenAlert(alert: Pick<Alert, "status">) {
  return OPEN_ALERT_STATUSES.has(alert.status)
}

export function isResolvedAlert(alert: Pick<Alert, "status">) {
  return RESOLVED_ALERT_STATUSES.has(alert.status)
}

export function toAlertCard(alert: Alert): OperatorAlertCard {
  const valueText = alert.actual_value === null ? null : formatCompactNumber(alert.actual_value)
  const thresholdText = alert.threshold_value === null ? null : formatCompactNumber(alert.threshold_value)
  let detail = ""
  if (valueText && thresholdText) detail = `Giá trị ${valueText}, ngưỡng ${thresholdText}.`
  else if (valueText) detail = `Giá trị hiện tại ${valueText}.`
  return {
    id: alert.id,
    title: alert.message,
    detail,
    startedAt: alert.started_at,
    open: isOpenAlert(alert),
  }
}

export function latestTimestamp(sensors: OperatorSensorCard[]) {
  const stamps = sensors.map((sensor) => sensor.recordedAt).filter((value): value is string => Boolean(value))
  return stamps.length ? stamps.reduce((latest, current) => (current > latest ? current : latest)) : null
}

export function createOperatorOverviewModel(system: AquaponicsSystem, latest: MonitoringLatest | undefined, alerts: Alert[]): OperatorOverviewModel {
  const sensors = collectSensorCards(latest)
  const actuators = collectActuatorRows(latest)
  const openAlertCount = alerts.filter(isOpenAlert).length
  const online = (latest?.devices ?? []).some((device) => device.connection_status === "ONLINE")
  return {
    system,
    sensors,
    actuators,
    banner: buildAlertBanner(sensors, openAlertCount),
    openAlertCount,
    lastUpdatedAt: latestTimestamp(sensors),
    online,
  }
}

export function createOperatorDevicesModel(latest: MonitoringLatest | undefined): OperatorDevicesModel {
  return {
    actuators: collectActuatorRows(latest),
    sensors: collectSensorCards(latest),
  }
}

export function splitOperatorAlerts(alerts: Alert[]) {
  return {
    open: alerts.filter(isOpenAlert).map(toAlertCard),
    resolved: alerts.filter(isResolvedAlert).map(toAlertCard),
  }
}

export function latestOperatorAlerts(alerts: Alert[], limit = 6): OperatorAlertCard[] {
  return [...alerts]
    .sort((left, right) => {
      const leftAt = left.last_triggered_at || left.started_at
      const rightAt = right.last_triggered_at || right.started_at
      if (leftAt !== rightAt) return rightAt.localeCompare(leftAt)
      return right.id - left.id
    })
    .slice(0, limit)
    .map(toAlertCard)
}

export function recipientStatusLabel(recipient: AlertDeliveryRecipient, telegramEnabled: boolean) {
  return recipient.enabled && telegramEnabled ? "Đang bật" : "Đã tắt"
}

export function operatorRoleLabel(userId: string, system: AquaponicsSystem | undefined) {
  if (system && system.owner_user_id === userId) return "Chủ hệ thống"
  return "Người vận hành"
}

export function formatHeaderDate(now = new Date()) {
  const formatted = new Intl.DateTimeFormat("vi-VN", {
    weekday: "long",
    day: "numeric",
    month: "numeric",
    year: "numeric",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(now)
  return formatted.charAt(0).toUpperCase() + formatted.slice(1)
}

export function pageTitleFromPath(pathname: string) {
  if (pathname.endsWith("/devices")) return "Thiết bị & Cảm biến"
  if (pathname.endsWith("/alerts")) return "Cảnh báo"
  if (pathname.endsWith("/settings")) return "Cài đặt"
  if (pathname.includes("/profile")) return "Hồ sơ"
  if (pathname === "/aquaponics-systems" || pathname === "/aquaponics-systems/") return "Hệ thống của bạn"
  return "Tổng quan"
}
