import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
import { useParams, useSearchParams } from "react-router-dom"
import { listAlerts, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { splitOperatorAlerts } from "@/widgets/operator-console/operator-console.model"
import { OperatorAlertsBoard, OperatorAlertsSkeleton } from "@/widgets/operator-console/OperatorAlertsBoard"
import { EmptyState } from "@/shared/ui/empty-state"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select"

export type OwnerAlertFilter = "ALL" | "OPEN" | "RESOLVED"

/**
 * Chủ hệ thống không đọc được các mã trạng thái kỹ thuật (PENDING, NORMALIZED…),
 * nên chỉ chia ba nhóm theo đúng cách bảng cảnh báo vốn đã nhóm sẵn.
 */
export const OWNER_ALERT_FILTERS: readonly { value: OwnerAlertFilter; label: string }[] = [
  { value: "ALL", label: "Tất cả trạng thái" },
  { value: "OPEN", label: "Chưa xử lý" },
  { value: "RESOLVED", label: "Đã xử lý" },
]

/** Mặc định xem tất cả; chỉ khi đường dẫn nói rõ mới lọc hẹp lại. */
export function parseOwnerAlertFilter(value: string | null): OwnerAlertFilter {
  return OWNER_ALERT_FILTERS.some((item) => item.value === value) ? (value as OwnerAlertFilter) : "ALL"
}

const EMPTY_TEXT: Record<OwnerAlertFilter, string> = {
  ALL: "Hệ thống chưa ghi nhận cảnh báo vận hành.",
  OPEN: "Không còn cảnh báo nào đang chờ xử lý.",
  RESOLVED: "Chưa có cảnh báo nào được xác nhận khắc phục.",
}

export function OwnerAlertsPage() {
  const systemId = useParams().systemId ?? ""
  const [params, setParams] = useSearchParams()
  const filter = parseOwnerAlertFilter(params.get("status"))

  const alerts = useQuery({
    queryKey: queryKeys.alerts(systemId),
    queryFn: () => listAlerts(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })

  const picker = (
    <Select
      value={filter}
      onValueChange={(value) => {
        // Giữ bộ lọc trên URL để người dùng chia sẻ hoặc tải lại vẫn thấy đúng màn hình
        setParams(value === "ALL" ? {} : { status: value }, { replace: true })
      }}
    >
      <SelectTrigger className="w-48" aria-label="Lọc trạng thái cảnh báo">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {OWNER_ALERT_FILTERS.map((item) => (
          <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )

  if (alerts.isLoading) return <OperatorAlertsSkeleton />
  if (alerts.isError) {
    return <EmptyState icon={AlertTriangle} title="Không thể tải cảnh báo" description={errorMessage(alerts.error)} />
  }

  const grouped = splitOperatorAlerts(alerts.data ?? [])
  const open = filter === "RESOLVED" ? [] : grouped.open
  const resolved = filter === "OPEN" ? [] : grouped.resolved

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-slate-800">Cảnh báo</h2>
        {picker}
      </div>

      {open.length || resolved.length ? (
        <OperatorAlertsBoard open={open} resolved={resolved} />
      ) : (
        // Bảng dùng chung báo "chưa ghi nhận cảnh báo nào", sai ý khi đang lọc hẹp
        <EmptyState icon={CheckCircle2} title="Không có cảnh báo" description={EMPTY_TEXT[filter]} />
      )}
    </div>
  )
}
