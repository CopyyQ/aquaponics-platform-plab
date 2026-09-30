import type { AlertLifecycleStatus } from "@/api/contracts"

/**
 * Cách chia trạng thái cảnh báo thành "còn phải xử lý" và "đã khép lại".
 *
 * Đặt ở tầng entities vì cả bảng cảnh báo (widgets) lẫn lớp phủ SCADA (entities)
 * đều cần chung định nghĩa này; hai bản sao rời nhau sẽ trôi khỏi nhau theo thời gian.
 */
const OPEN_ALERT_STATUSES = new Set<string>(["PENDING", "OPEN", "ACKNOWLEDGED"])

// NORMALIZED là "tự trở lại bình thường", RESOLVED là "người xác nhận đã khắc phục".
// Hai thứ khác nhau về nghĩa nhưng giống nhau ở chỗ không còn chờ ai xử lý nữa.
const RESOLVED_ALERT_STATUSES = new Set<string>(["NORMALIZED", "RESOLVED"])

export function isOpenAlert(alert: { status: AlertLifecycleStatus | string }) {
  return OPEN_ALERT_STATUSES.has(alert.status)
}

export function isResolvedAlert(alert: { status: AlertLifecycleStatus | string }) {
  return RESOLVED_ALERT_STATUSES.has(alert.status)
}
