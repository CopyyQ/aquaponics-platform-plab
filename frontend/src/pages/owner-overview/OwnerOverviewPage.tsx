import { useQuery } from "@tanstack/react-query"
import { useOutletContext, useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { listAlerts, queryKeys } from "@/api/resources"
import type { AquaponicsSystem } from "@/api/contracts"
import { errorMessage } from "@/api/client"
import { createOwnerOverviewModel } from "@/widgets/owner-console/owner-overview.model"
import { OwnerOverviewBoard, OwnerOverviewSkeleton } from "@/widgets/owner-console/OwnerOverviewBoard"
import { EmptyState } from "@/shared/ui/empty-state"

export function OwnerOverviewPage() {
  const systemId = useParams().systemId ?? ""
  const { system } = useOutletContext<{ system: AquaponicsSystem }>()
  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  if (alerts.isLoading) return <OwnerOverviewSkeleton />
  if (alerts.isError) return <EmptyState icon={AlertTriangle} title="Không thể tải tổng quan" description={errorMessage(alerts.error)} />
  return <OwnerOverviewBoard systemId={systemId} model={createOwnerOverviewModel(system, alerts.data ?? [])} />
}
