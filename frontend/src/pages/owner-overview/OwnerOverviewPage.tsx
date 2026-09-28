import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { getScadaRuntime, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { OwnerOverviewBoard, OwnerOverviewSkeleton } from "@/widgets/owner-console/OwnerOverviewBoard"
import { EmptyState } from "@/shared/ui/empty-state"

export function OwnerOverviewPage() {
  const systemId = useParams().systemId ?? ""
  const scada = useQuery({
    queryKey: queryKeys.scada(systemId),
    queryFn: () => getScadaRuntime(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  if (scada.isLoading) return <OwnerOverviewSkeleton />
  if (scada.isError) return <EmptyState icon={AlertTriangle} title="Không thể tải tổng quan" description={errorMessage(scada.error)} />
  return <OwnerOverviewBoard scadaRuntime={scada.data} />
}
