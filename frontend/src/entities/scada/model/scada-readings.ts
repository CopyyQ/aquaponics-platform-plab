import { DERIVED_POWER, SCADA_METRICS } from "./scada-cards"
import type { ScadaMetricKind } from "./scada-cards"
import { readActuator, readSensor } from "./scada-signals"
import type { ScenarioSignalStatus, ScenarioSource } from "./scada-signals"

export interface ScadaReading {
  code: string
  kind: ScadaMetricKind
  /** Tên ngắn, dùng trên mặt thẻ. */
  label: string
  /** Tên đầy đủ kèm thuật ngữ, dùng trong hộp chi tiết và danh sách. */
  fullLabel: string
  /** Giá trị đã định dạng kèm đơn vị, hoặc null khi không có số để hiển thị. */
  text: string | null
  /** Giá trị thô, dùng cho những chỗ vẽ theo số như cột đo mực nước. */
  value: number | null
  status: ScenarioSignalStatus
  /** true khi backend không xác nhận được miền hợp lệ của chỉ số. */
  unvalidated: boolean
  /** Id của cảm biến/cơ cấu đứng sau chỉ số, dùng để đối chiếu với issues. */
  entityId: string | null
  recordedAt: string | null
}

const STATUS_TEXT: Record<Exclude<ScenarioSignalStatus, "AVAILABLE">, string> = {
  NONE: "Chưa có dữ liệu",
  STALE: "Dữ liệu cũ",
  INVALID: "Không hợp lệ",
  OFFLINE: "Mất kết nối",
  DISABLED: "Đã tắt",
}

export function statusText(status: ScenarioSignalStatus) {
  return status === "AVAILABLE" ? "" : STATUS_TEXT[status]
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 1 }).format(value)
}

function findSensor(source: ScenarioSource, modelCode: string) {
  return source.inventory.sensors.find((sensor) => sensor.sensor_model_code === modelCode) ?? null
}

function sensorRuntime(source: ScenarioSource, modelCode: string) {
  const sensor = findSensor(source, modelCode)
  if (!sensor) return null
  return source.runtime.sensors.find((item) => item.id === sensor.id) ?? null
}

/**
 * Backend phân biệt INVALID (đo ra số sai) với UNVALIDATED (chưa khai báo miền hợp lệ để đối chiếu).
 * readSensor gộp cả hai thành INVALID cho mục đích chọn ảnh. Ở màn hình vận hành thì khác:
 * giấu số vì catalog thiếu cấu hình sẽ khiến người xem tưởng cảm biến hỏng, nên vẫn hiện số
 * kèm dấu cảnh báo.
 */
function unvalidatedValue(source: ScenarioSource, modelCode: string): number | null {
  const runtime = sensorRuntime(source, modelCode)
  if (!runtime || runtime.quality !== "UNVALIDATED") return null
  return typeof runtime.value === "number" && Number.isFinite(runtime.value) ? runtime.value : null
}

function readOne(source: ScenarioSource, code: string): ScadaReading {
  const metric = SCADA_METRICS.find((item) => item.code === code)
  const label = metric?.label ?? code
  const fullLabel = metric?.fullLabel ?? label
  const kind = metric?.kind ?? "SENSOR"

  if (kind === "ACTUATOR") {
    const signal = readActuator(source, code)
    const actuator = source.inventory.actuators.find((item) => item.actuator_model_code === code) ?? null
    const runtime = actuator ? source.runtime.actuators.find((item) => item.id === actuator.id) : null
    return {
      code,
      kind,
      label,
      // Tên thật trong cơ sở dữ liệu thắng tên cứng: hộp chi tiết còn in kèm sự cố,
      // mà sự cố gọi thiết bị theo tên trong DB — hai tên khác nhau trong cùng một
      // khung hình khiến người xem tưởng đang nói về hai thiết bị.
      fullLabel: actuator?.name ?? fullLabel,
      text: signal.status === "AVAILABLE" ? (signal.value ? "BẬT" : "TẮT") : null,
      value: null,
      status: signal.status,
      unvalidated: false,
      entityId: actuator?.id ?? null,
      recordedAt: runtime?.last_ack_at ?? runtime?.command_time ?? null,
    }
  }

  if (kind === "DERIVED" && code === DERIVED_POWER) {
    const voltage = readSensor(source, "VOLTAGE")
    const current = readSensor(source, "CURRENT")
    const ready = voltage.status === "AVAILABLE" && current.status === "AVAILABLE"
    const status = ready ? "AVAILABLE" : voltage.status !== "AVAILABLE" ? voltage.status : current.status
    return {
      code,
      kind,
      label,
      fullLabel,
      text: ready ? `${formatNumber((voltage.value ?? 0) * (current.value ?? 0))} ${metric?.unit ?? ""}`.trim() : null,
      value: ready ? (voltage.value ?? 0) * (current.value ?? 0) : null,
      status,
      unvalidated: false,
      entityId: null,
      recordedAt: sensorRuntime(source, "VOLTAGE")?.recorded_at ?? null,
    }
  }

  const signal = readSensor(source, code)
  const unvalidated = signal.status === "INVALID" ? unvalidatedValue(source, code) : null
  const value = signal.status === "AVAILABLE" ? signal.value : unvalidated
  const runtime = sensorRuntime(source, code)
  const sensor = findSensor(source, code)

  return {
    code,
    kind,
    label,
    fullLabel: sensor?.name ?? fullLabel,
    text: value !== null ? `${formatNumber(value)} ${sensor?.unit ?? ""}`.trim() : null,
    value,
    status: unvalidated !== null ? "AVAILABLE" : signal.status,
    unvalidated: unvalidated !== null,
    entityId: sensor?.id ?? null,
    recordedAt: runtime?.recorded_at ?? null,
  }
}

export function readScadaMetrics(source: ScenarioSource, codes: readonly string[]): ScadaReading[] {
  return codes.map((code) => readOne(source, code))
}
