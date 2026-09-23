import { AlertTriangle, CheckCircle2 } from "lucide-react"
import type { OperatorAlertCard } from "./operator-console.model"
import { formatDateTime, formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Card } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"

function AlertCard({ alert }: { alert: OperatorAlertCard }) {
  return (
    <Card className={cn("rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]", alert.open ? "bg-amber-50" : "bg-white")}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={cn("grid size-10 place-items-center rounded-full", alert.open ? "bg-amber-100 text-amber-600" : "bg-emerald-50 text-emerald-600")}>
            {alert.open ? <AlertTriangle className="size-5" aria-hidden="true" /> : <CheckCircle2 className="size-5" aria-hidden="true" />}
          </div>
          <div>
            <h3 className="font-semibold text-slate-800">{alert.title}</h3>
            {alert.detail ? <p className="mt-1 text-sm leading-6 text-slate-500">{alert.detail}</p> : null}
            <p className="mt-2 text-xs text-slate-400">{formatRelative(alert.startedAt)} · {formatDateTime(alert.startedAt)}</p>
          </div>
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide", alert.open ? "bg-amber-100 text-amber-700" : "bg-emerald-50 text-emerald-700")}>
          {alert.open ? "Đang mở" : "Đã xử lý"}
        </span>
      </div>
    </Card>
  )
}

export function OperatorAlertsBoard({ open, resolved }: { open: OperatorAlertCard[]; resolved: OperatorAlertCard[] }) {
  if (!open.length && !resolved.length) {
    return <EmptyState icon={CheckCircle2} title="Không có cảnh báo" description="Hệ thống chưa ghi nhận cảnh báo vận hành." />
  }
  return (
    <div className="space-y-6">
      {open.length ? (
        <div className="space-y-3">
          {open.map((alert) => <AlertCard key={alert.id} alert={alert} />)}
        </div>
      ) : null}
      {resolved.length ? (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Đã xử lý</h2>
          {resolved.map((alert) => <AlertCard key={alert.id} alert={alert} />)}
        </div>
      ) : null}
    </div>
  )
}

export function OperatorAlertsSkeleton() {
  return <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-24" /></div>
}
