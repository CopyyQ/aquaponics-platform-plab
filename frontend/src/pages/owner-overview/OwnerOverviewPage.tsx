import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { getMonitoringLatest, listAlerts, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { toScadaSource } from "@/entities/scada/model/monitoring-source"
import { OwnerOverviewBoard, OwnerOverviewSkeleton } from "@/widgets/owner-console/OwnerOverviewBoard"
import { EmptyState } from "@/shared/ui/empty-state"

// Hai truy vấn dưới đây dùng chung queryKey với khung giao diện, nên React Query gộp lại:
// mở màn hình này không sinh thêm lượt gọi mạng nào.
const POLL = { refetchInterval: 15_000, staleTime: 10_000, gcTime: 60_000 } as const

export function OwnerOverviewPage() {
  const systemId = useParams().systemId ?? ""
  const monitoring = useQuery({
    queryKey: queryKeys.monitoringLatest(systemId),
    queryFn: () => getMonitoringLatest(systemId),
    enabled: Boolean(systemId),
    ...POLL,
  })
  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    ...POLL,
  })

  if (monitoring.isLoading) return <OwnerOverviewSkeleton />
  if (monitoring.isError) {
    return <EmptyState icon={AlertTriangle} title="Không thể tải tổng quan" description={errorMessage(monitoring.error)} />
  }
  if (!monitoring.data) return <OwnerOverviewSkeleton />

  // Cảnh báo chỉ bổ sung phần sự cố vượt ngưỡng; thiếu nó thì sơ đồ vẫn vẽ được
  // bằng dữ liệu đo, nên không chặn màn hình khi riêng truy vấn này hỏng.
  return <OwnerOverviewBoard source={toScadaSource(monitoring.data, alerts.data ?? [])} />
}
