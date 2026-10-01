import type { ScenarioSource } from "@/entities/scada/model/scada-signals"
import { actuatorCommandAvailability } from "./actuator-control-policy"
import type { ActuatorCommandAvailability } from "./actuator-control-policy"

/**
 * Cơ cấu chấp hành đứng sau một chỉ số trên sơ đồ SCADA, kèm quyền gửi lệnh.
 *
 * Thẻ trên sơ đồ gắn theo mã *mẫu* thiết bị, còn lệnh điều khiển cần id thật của
 * device và actuator, nên phải tra ngược lại inventory.
 */
export interface ScadaActuatorTarget {
  actuatorId: string
  deviceId: string
  name: string
  /** Trạng thái thiết bị báo về; null khi chưa rõ (mất kết nối, chưa có phản hồi). */
  on: boolean | null
  /** Lệnh gần nhất còn đang chờ thiết bị xác nhận. */
  pending: boolean
  availability: ActuatorCommandAvailability
}

/** Lý do nút bật/tắt bị khóa, viết theo cách chủ hệ thống hiểu được. */
export const COMMAND_BLOCK_REASON: Record<"DEVICE_OFFLINE" | "ACTUATOR_DISABLED" | "COMMAND_PENDING", string> = {
  DEVICE_OFFLINE: "Thiết bị đang mất kết nối nên chưa gửi lệnh được",
  ACTUATOR_DISABLED: "Cơ cấu đã bị vô hiệu hóa",
  COMMAND_PENDING: "Đang chờ thiết bị xác nhận lệnh trước",
}

function timestamp(value: string | null | undefined) {
  return value ? Date.parse(value) || 0 : 0
}

/**
 * Chọn đúng cơ cấu mà thẻ đang hiển thị: cùng thứ tự ưu tiên với `readActuator`
 * (cái đang báo được trạng thái thắng, sau đó tới cái có phản hồi mới nhất), nếu
 * không nút bấm sẽ điều khiển một cơ cấu khác với cái đang hiện số.
 */
export function resolveScadaActuatorTarget(source: ScenarioSource, modelCode: string): ScadaActuatorTarget | null {
  const candidates = source.inventory.actuators.filter((actuator) => actuator.actuator_model_code === modelCode)
  if (!candidates.length) return null

  const ranked = candidates.map((actuator) => {
    const device = source.inventory.devices.find((item) => item.id === actuator.device_id)
    const deviceRuntime = source.runtime.devices.find((item) => item.id === actuator.device_id)
    const runtime = source.runtime.actuators.find((item) => item.id === actuator.id)
    const connectionStatus = deviceRuntime?.connectivity ?? device?.connectivity ?? "OFFLINE"
    const isEnabled = Boolean(actuator.enabled && device?.enabled)
    const online = isEnabled && connectionStatus === "ONLINE"
    const pending = runtime?.command_status === "PENDING"
    // Thiết bị offline thì con số cũ không còn đáng tin: coi như chưa rõ trạng thái.
    const on = online ? (runtime?.reported_state ?? null) : null

    return {
      ready: on !== null,
      at: timestamp(runtime?.last_ack_at ?? runtime?.command_time),
      target: {
        actuatorId: actuator.id,
        deviceId: actuator.device_id,
        name: actuator.name,
        on,
        pending,
        availability: actuatorCommandAvailability({
          connectionStatus,
          isEnabled,
          commandPending: pending,
          desiredState: runtime?.desired_state ?? null,
          reportedState: runtime?.reported_state ?? null,
          hasActiveAlert: false,
        }),
      } satisfies ScadaActuatorTarget,
    }
  })

  ranked.sort((left, right) => Number(right.ready) - Number(left.ready) || right.at - left.at)
  return ranked[0].target
}
