import { AlertTriangle, Bell, CheckCircle2 } from "lucide-react"
import { Link } from "react-router-dom"
import type { Alert } from "@/api/contracts"
import { formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu"
import { latestOperatorAlerts } from "./operator-console.model"

export function OperatorAlertBell({
  alerts,
  alertsHref,
  openCount,
  isLoading,
}: {
  alerts: Alert[] | undefined
  alertsHref: string
  openCount: number
  isLoading: boolean
}) {
  const latest = latestOperatorAlerts(alerts ?? [])
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="relative rounded-xl border-rose-100 bg-white"
          aria-label="Thông báo cảnh báo"
          type="button"
        >
          <Bell className="size-4 text-rose-400" aria-hidden="true" />
          {openCount ? (
            <span className="absolute -right-1 -top-1 grid size-5 place-items-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
              {openCount}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0" onCloseAutoFocus={(event) => event.preventDefault()}>
        <DropdownMenuLabel className="px-3 py-2.5 text-sm font-semibold text-slate-800">Cảnh báo mới nhất</DropdownMenuLabel>
        <DropdownMenuSeparator className="m-0" />
        {isLoading ? (
          <p className="px-3 py-4 text-sm text-slate-500">Đang tải cảnh báo…</p>
        ) : latest.length === 0 ? (
          <p className="px-3 py-4 text-sm text-slate-500">Không có cảnh báo mới.</p>
        ) : (
          <ul className="max-h-80 overflow-y-auto py-1">
            {latest.map((alert) => (
              <li key={alert.id} className="border-b border-slate-100 px-3 py-2.5 last:border-b-0">
                <div className="flex items-start gap-2">
                  <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", alert.open ? "bg-amber-100 text-amber-600" : "bg-emerald-50 text-emerald-600")}>
                    {alert.open ? <AlertTriangle className="size-3.5" aria-hidden="true" /> : <CheckCircle2 className="size-3.5" aria-hidden="true" />}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium leading-5 text-slate-800">{alert.title}</p>
                    {alert.detail ? <p className="mt-0.5 text-xs text-slate-500">{alert.detail}</p> : null}
                    <p className="mt-1 text-[11px] text-slate-400">{formatRelative(alert.startedAt)}</p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <DropdownMenuSeparator className="m-0" />
        <div className="flex justify-end px-2 py-1.5">
          <DropdownMenuItem asChild className="cursor-pointer justify-end px-2 py-1.5 text-xs font-semibold text-[#0d5c4d] focus:bg-transparent focus:text-[#0a4a3e]">
            <Link to={alertsHref}>Xem tất cả cảnh báo</Link>
          </DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
