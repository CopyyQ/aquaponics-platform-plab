import type { MonitoringScadaSource } from "@/entities/scada/model/monitoring-source"
import { SCADA_IMAGE_ASPECT } from "@/entities/scada/model/scada-cards"
import { ScadaOverlay } from "@/widgets/canonical-scada/ScadaOverlay"
import { Skeleton } from "@/shared/ui/skeleton"

// Tổng quan OWNER: sơ đồ SCADA kèm chỉ số phủ lên ảnh. Cảnh báo nằm ở chuông trên header.
// Lớp phủ đã tự có khung bo góc nên không bọc thêm Card, tránh hai khung lồng nhau.
export function OwnerOverviewBoard({
  source,
  localHour,
  canCommand = false,
}: {
  source?: MonitoringScadaSource
  localHour?: number
  canCommand?: boolean
}) {
  return source ? <ScadaOverlay runtime={source} localHour={localHour} canCommand={canCommand} /> : null
}

export function OwnerOverviewSkeleton() {
  // Khớp đúng khung của lớp phủ để lúc tải xong bố cục không nhảy.
  return (
    <Skeleton
      className="mx-auto rounded-2xl"
      style={{
        width: `min(100%, calc((100dvh - 7.5rem) * ${SCADA_IMAGE_ASPECT}))`,
        aspectRatio: String(SCADA_IMAGE_ASPECT),
      }}
    />
  )
}
