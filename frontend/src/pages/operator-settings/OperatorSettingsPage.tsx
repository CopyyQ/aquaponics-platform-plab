import { useQuery } from "@tanstack/react-query"
import { useOutletContext, useParams } from "react-router-dom"
import { getAlertDeliverySettings, queryKeys } from "@/api/resources"
import type { AquaponicsSystem } from "@/api/contracts"
import { useAuth } from "@/app/auth"
import { OperatorSettingsBoard, OperatorSettingsSkeleton } from "@/widgets/operator-console/OperatorSettingsBoard"

export function OperatorSettingsPage() {
  const systemId = useParams().systemId ?? ""
  const { system } = useOutletContext<{ system: AquaponicsSystem }>()
  const { can } = useAuth()
  const canReadDelivery = can("notifications.settings.read")
  const delivery = useQuery({
    queryKey: queryKeys.deliverySettings(systemId),
    queryFn: () => getAlertDeliverySettings(systemId),
    enabled: Boolean(systemId) && canReadDelivery,
  })
  if (canReadDelivery && delivery.isLoading) return <OperatorSettingsSkeleton />
  return (
    <OperatorSettingsBoard
      system={system}
      recipients={delivery.data?.recipients ?? []}
      telegramEnabled={Boolean(delivery.data?.telegram_enabled)}
    />
  )
}
