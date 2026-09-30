import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
import { useParams, useSearchParams } from "react-router-dom"
import { getMonitoringLatest, listAlerts, queryKeys } from "@/api/resources"
import { errorMessage } from "@/api/client"
import { deriveScadaIssues } from "@/entities/scada/model/monitoring-source"
import { splitOperatorAlerts } from "@/widgets/operator-console/operator-console.model"
import { OperatorAlertsBoard, OperatorAlertsSkeleton } from "@/widgets/operator-console/OperatorAlertsBoard"
import { OperatorDeviceIssuesBoard } from "@/widgets/operator-console/OperatorDeviceIssuesBoard"
import { EmptyState } from "@/shared/ui/empty-state"
import { ToggleGroup, ToggleGroupItem } from "@/shared/ui/toggle-group"

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

/**
 * Sự cố thiết bị luôn là chuyện đang diễn ra, nên chỉ có nghĩa khi người dùng đang
 * xem phần chưa xử lý. Lọc "Đã xử lý" là xem lịch sử, mà chúng thì không có lịch sử.
 */
export function showsDeviceIssues(filter: OwnerAlertFilter) {
  return filter !== "RESOLVED"
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
  // Dùng chung queryKey với khung giao diện và trang Tổng quan nên không tốn thêm lượt gọi.
  const monitoring = useQuery({
    queryKey: queryKeys.monitoringLatest(systemId),
    queryFn: () => getMonitoringLatest(systemId),
    enabled: Boolean(systemId),
    refetchInterval: 15_000,
    staleTime: 10_000,
    gcTime: 60_000,
  })

  if (alerts.isLoading) return <OperatorAlertsSkeleton />
  if (alerts.isError) {
    return <EmptyState icon={AlertTriangle} title="Không thể tải cảnh báo" description={errorMessage(alerts.error)} />
  }

  const grouped = splitOperatorAlerts(alerts.data ?? [])
  const open = filter === "RESOLVED" ? [] : grouped.open
  const resolved = filter === "OPEN" ? [] : grouped.resolved
  // Truyền danh sách cảnh báo rỗng: phần vượt ngưỡng đã nằm trong bảng bên dưới rồi,
  // ở đây chỉ cần những sự cố không có bản ghi nào đại diện.
  const deviceIssues = monitoring.data && showsDeviceIssues(filter) ? deriveScadaIssues(monitoring.data, []) : []

  // Ba lựa chọn ngắn thì bày sẵn cả ba hơn là giấu trong danh sách thả xuống: đỡ một
  // cú bấm, và nhìn là biết đang lọc gì. Số bên cạnh "Chưa xử lý" cho biết còn bao
  // nhiêu việc phải làm mà không cần đổi bộ lọc.
  const picker = (
    <ToggleGroup
      type="single"
      value={filter}
      variant="outline"
      aria-label="Lọc trạng thái cảnh báo"
      className="rounded-full bg-white p-1 shadow-[0_2px_10px_-6px_rgba(15,63,53,0.4)]"
      onValueChange={(value) => {
        // Radix trả chuỗi rỗng khi bấm lại mục đang chọn; giữ nguyên bộ lọc thay vì bỏ trắng.
        if (!value) return
        // Giữ bộ lọc trên URL để người dùng chia sẻ hoặc tải lại vẫn thấy đúng màn hình
        setParams(value === "ALL" ? {} : { status: value }, { replace: true })
      }}
    >
      {OWNER_ALERT_FILTERS.map((item) => (
        <ToggleGroupItem
          key={item.value}
          value={item.value}
          className="gap-2 rounded-full! border-0 px-4 text-sm text-slate-500 data-[state=on]:bg-emerald-50 data-[state=on]:font-semibold data-[state=on]:text-emerald-800"
        >
          {item.label}
          {item.value === "OPEN" && grouped.open.length ? (
            <span className="rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-700 tabular-nums">
              {grouped.open.length}
            </span>
          ) : null}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-slate-800">Cảnh báo</h2>
        {picker}
      </div>

      <OperatorDeviceIssuesBoard issues={deviceIssues} />

      {open.length || resolved.length ? (
        <OperatorAlertsBoard open={open} resolved={resolved} />
      ) : (
        // Bảng dùng chung báo "chưa ghi nhận cảnh báo nào", sai ý khi đang lọc hẹp
        <EmptyState
          icon={CheckCircle2}
          title="Không có cảnh báo"
          description={
            deviceIssues.length
              ? "Không có cảnh báo ngưỡng nào. Sự cố thiết bị bên trên không được lưu thành bản ghi nên không xuất hiện trong danh sách này."
              : EMPTY_TEXT[filter]
          }
        />
      )}
    </div>
  )
}
