import { AlertTriangle, CheckCircle2 } from "lucide-react"
import { Link } from "react-router-dom"
import type { OwnerAlertCard, OwnerOverviewModel } from "./owner-overview.model"
import { formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Card } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"

const CARD = "rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]"

function AlertRow({ alert }: { alert: OwnerAlertCard }) {
  const critical = alert.open && alert.critical
  const rowTone = critical ? "bg-rose-50" : alert.open ? "bg-amber-50" : "bg-slate-50"
  const iconTone = critical ? "bg-rose-100 text-rose-600" : alert.open ? "bg-amber-100 text-amber-600" : "bg-emerald-50 text-emerald-600"
  const badgeTone = critical ? "bg-rose-100 text-rose-700" : alert.open ? "bg-amber-100 text-amber-700" : "bg-emerald-50 text-emerald-700"
  return (
    <li className={cn("flex items-start gap-3 rounded-xl px-3 py-3", rowTone)}>
      <div className={cn("grid size-8 shrink-0 place-items-center rounded-full", iconTone)}>
        {alert.open ? <AlertTriangle className="size-4" aria-hidden="true" /> : <CheckCircle2 className="size-4" aria-hidden="true" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-slate-800">{alert.title}</p>
        {alert.detail ? <p className="mt-0.5 text-xs text-slate-500">{alert.detail}</p> : null}
        <p className="mt-1 text-[11px] text-slate-400">{formatRelative(alert.startedAt)}</p>
      </div>
      <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", badgeTone)}>
        {critical ? "Nghiêm trọng" : alert.open ? "Chưa xử lý" : "Đã xử lý"}
      </span>
    </li>
  )
}

export function OwnerOverviewBoard({ model, systemId }: { model: OwnerOverviewModel; systemId: string }) {
  return (
    <div className="grid gap-5 lg:h-[calc(100vh-7.5rem)] lg:min-h-[480px] lg:grid-cols-[2fr_1fr]">
      {/* Cột trái (~67%): khu vực dành sẵn cho biểu đồ */}
      <Card className={cn(CARD, "flex min-h-[420px] flex-col")}>
        <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-900">Biểu đồ</h2>
        </div>
        <div className="grid flex-1 place-items-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
          Khu vực biểu đồ
        </div>
      </Card>

      {/* Cột phải (~33%): cảnh báo, chiều cao cố định, danh sách scroll bên trong */}
      <Card className={cn(CARD, "flex h-[420px] flex-col overflow-hidden lg:h-full")}>
        <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-slate-900">
            Cảnh báo
            {model.openAlertCount ? <span className="ml-2 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-700">{model.openAlertCount}</span> : null}
          </h2>
          <Link className="text-xs font-semibold text-emerald-700 hover:underline" to={`/aquaponics-systems/${systemId}/alerts`}>Xem tất cả →</Link>
        </div>
        {model.alerts.length ? (
          <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {model.alerts.map((alert) => <AlertRow key={alert.id} alert={alert} />)}
          </ul>
        ) : (
          <div className="grid flex-1 place-items-center"><EmptyState icon={CheckCircle2} title="Không có cảnh báo chưa xử lý" description="Hệ thống bình thường." /></div>
        )}
      </Card>
    </div>
  )
}

export function OwnerOverviewSkeleton() {
  return <div className="grid gap-5 lg:grid-cols-[2fr_1fr]"><Skeleton className="h-[420px]" /><Skeleton className="h-[420px]" /></div>
}
