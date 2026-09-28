import type { ScadaRuntimeResponse } from "@/api/contracts"
import { ScadaOverlay } from "@/widgets/canonical-scada/ScadaOverlay"
import { Skeleton } from "@/shared/ui/skeleton"

type ScenarioRuntime = Pick<ScadaRuntimeResponse, "aquaponics_system" | "inventory" | "runtime" | "issues" | "updated_at">

// Tổng quan OWNER: sơ đồ SCADA kèm chỉ số phủ lên ảnh. Cảnh báo nằm ở chuông trên header.
// Lớp phủ đã tự có khung bo góc nên không bọc thêm Card, tránh hai khung lồng nhau.
export function OwnerOverviewBoard({ scadaRuntime, localHour }: { scadaRuntime?: ScenarioRuntime; localHour?: number }) {
  return scadaRuntime ? <ScadaOverlay runtime={scadaRuntime} localHour={localHour} /> : null
}

export function OwnerOverviewSkeleton() {
  return <Skeleton className="mx-auto aspect-3/2 rounded-2xl" style={{ width: "min(100%, calc((100dvh - 7.5rem) * 1.5))" }} />
}
