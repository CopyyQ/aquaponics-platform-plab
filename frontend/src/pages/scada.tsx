import { Eye } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { errorMessage } from "@/api/client"
import { getScadaRuntime, queryKeys } from "@/api/resources"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"
import { ScadaScenarioImage } from "@/widgets/canonical-scada/ScadaScenarioImage"

export function ScadaPage() {
  const systemId = useParams().systemId ?? ""
  const runtime = useQuery({
    queryKey: queryKeys.scada(systemId),
    queryFn: () => getScadaRuntime(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })

  if (runtime.isLoading) return <div className="space-y-4"><Skeleton className="h-16" /><Skeleton className="h-[32rem]" /></div>
  if (runtime.isError || !runtime.data) return <EmptyState icon={Eye} title="Không thể tải sơ đồ vận hành" description={errorMessage(runtime.error)} />

  const value = runtime.data
  return <div className="space-y-5">
    <div>
      <h2 className="text-xl font-semibold">Sơ đồ vận hành</h2>
      <p className="text-sm text-muted-foreground">Ảnh SCADA được chọn từ dữ liệu runtime của Project {value.aquaponics_system.name} · cập nhật {new Date(value.updated_at).toLocaleString("vi-VN")}</p>
    </div>
    <ScadaScenarioImage runtime={value} />
  </div>
}
