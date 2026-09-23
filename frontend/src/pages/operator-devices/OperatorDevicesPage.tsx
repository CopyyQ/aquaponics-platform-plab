import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useParams } from "react-router-dom"
import { AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { createCommand, getMonitoringLatest, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { useAuth } from "@/app/auth"
import { createOperatorDevicesModel } from "@/widgets/operator-console/operator-console.model"
import { OperatorDevicesBoard, OperatorDevicesSkeleton } from "@/widgets/operator-console/OperatorDevicesBoard"
import { EmptyState } from "@/shared/ui/empty-state"

export function OperatorDevicesPage() {
  const systemId = useParams().systemId ?? ""
  const { can } = useAuth()
  const client = useQueryClient()
  const latest = useQuery({
    queryKey: queryKeys.monitoringLatest(systemId),
    queryFn: () => getMonitoringLatest(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })
  const command = useMutation({
    mutationFn: ({ deviceId, actuatorId, next }: { deviceId: string; actuatorId: string; next: boolean }) => createCommand(systemId, deviceId, actuatorId, { desired_state: next }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.monitoringLatest(systemId) })
      toast.success("Đã gửi lệnh tới thiết bị")
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
  if (latest.isLoading) return <OperatorDevicesSkeleton />
  if (latest.isError) return <EmptyState icon={AlertTriangle} title="Không thể tải thiết bị" description={errorMessage(latest.error)} />
  return (
    <OperatorDevicesBoard
      model={createOperatorDevicesModel(latest.data)}
      canCommand={can("actuators.commands.create") && !command.isPending}
      onToggle={(deviceId, actuatorId, next) => command.mutate({ deviceId, actuatorId, next })}
    />
  )
}
