import { useQuery } from "@tanstack/react-query"
import { useOutletContext, useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { getMonitoringLatest, listAlerts, queryKeys } from "@/api/resources"
import type { AquaponicsSystem } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { createOperatorOverviewModel } from "@/widgets/operator-console/operator-console.model"
import { OperatorOverviewBoard, OperatorOverviewSkeleton } from "@/widgets/operator-console/OperatorOverviewBoard"
import { EmptyState } from "@/shared/ui/empty-state"

export function OperatorOverviewPage() {
  const systemId = useParams().systemId ?? ""
  const { system } = useOutletContext<{ system: AquaponicsSystem }>()
  const latest = useQuery({
    queryKey: queryKeys.monitoringLatest(systemId),
    queryFn: () => getMonitoringLatest(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  if (latest.isLoading || alerts.isLoading) return <OperatorOverviewSkeleton />
  if (latest.isError || alerts.isError) return <EmptyState icon={AlertTriangle} title="Không thể tải tổng quan" description={errorMessage(latest.error ?? alerts.error)} />
  return <OperatorOverviewBoard systemId={systemId} model={createOperatorOverviewModel(system, latest.data, alerts.data ?? [])} />
}
