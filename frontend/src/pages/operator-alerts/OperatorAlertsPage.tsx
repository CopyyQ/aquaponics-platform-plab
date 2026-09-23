import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { listAlerts, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { splitOperatorAlerts } from "@/widgets/operator-console/operator-console.model"
import { OperatorAlertsBoard, OperatorAlertsSkeleton } from "@/widgets/operator-console/OperatorAlertsBoard"
import { EmptyState } from "@/shared/ui/empty-state"

export function OperatorAlertsPage() {
  const systemId = useParams().systemId ?? ""
  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  if (alerts.isLoading) return <OperatorAlertsSkeleton />
  if (alerts.isError) return <EmptyState icon={AlertTriangle} title="Không thể tải cảnh báo" description={errorMessage(alerts.error)} />
  const grouped = splitOperatorAlerts(alerts.data ?? [])
  return <OperatorAlertsBoard open={grouped.open} resolved={grouped.resolved} />
}
