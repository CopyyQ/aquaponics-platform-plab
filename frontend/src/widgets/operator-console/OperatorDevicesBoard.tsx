import { Droplets, Radio } from "lucide-react"
import type { OperatorActuatorRow, OperatorDevicesModel } from "./operator-console.model"
import { formatCompactNumber } from "./operator-console.model"
import { OperatorSensorCardView } from "./OperatorOverviewBoard"
import { formatRelative } from "@/shared/lib/date"
import { cn } from "@/shared/lib/utils"
import { Card } from "@/shared/ui/card"
import { EmptyState } from "@/shared/ui/empty-state"
import { Skeleton } from "@/shared/ui/skeleton"

function freshnessWidth(freshness: string) {
  if (freshness === "FRESH") return "100%"
  if (freshness === "STALE") return "45%"
  return "8%"
}

function freshnessTone(freshness: string) {
  if (freshness === "FRESH") return "bg-emerald-500"
  if (freshness === "STALE") return "bg-amber-500"
  return "bg-slate-300"
}

function freshnessLabel(freshness: string, lastReportedAt: string | null) {
  if (freshness === "FRESH") return lastReportedAt ? `Cập nhật ${formatRelative(lastReportedAt)}` : "Tín hiệu mới"
  if (freshness === "STALE") return "Tín hiệu chậm"
  return "Chưa có tín hiệu điện"
}

function OperatorToggle({ checked, disabled, label, onCheckedChange }: { checked: boolean; disabled: boolean; label: string; onCheckedChange: (checked: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn("relative h-7 w-12 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40", checked ? "bg-emerald-500" : "bg-slate-300", disabled && "cursor-not-allowed opacity-70")}
    >
      <span className={cn("absolute top-0.5 size-6 rounded-full bg-white shadow transition-transform", checked ? "left-5" : "left-0.5")} />
    </button>
  )
}

function ActuatorRow({ actuator, canCommand, onToggle }: { actuator: OperatorActuatorRow; canCommand: boolean; onToggle: (deviceId: string, actuatorId: string, next: boolean) => void }) {
  const on = actuator.on === true
  return (
    <div className="grid gap-4 border-b border-slate-100 py-4 last:border-b-0 lg:grid-cols-[minmax(12rem,1.1fr)_8rem_8rem_minmax(12rem,1.4fr)_auto] lg:items-center">
      <div className="flex items-start gap-3">
        <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", on ? "bg-emerald-500" : "bg-slate-300")} aria-hidden="true" />
        <div>
          <p className="font-semibold text-slate-800">{actuator.name}</p>
          <p className="text-xs text-slate-400">{actuator.model || "Cơ cấu chấp hành"}</p>
        </div>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wide text-slate-400">Điện áp</p>
        <p className="mt-1 font-medium text-slate-700">{actuator.voltageV === null ? "—" : `${formatCompactNumber(actuator.voltageV)} V`}</p>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wide text-slate-400">Dòng điện</p>
        <p className="mt-1 font-medium text-slate-700">{actuator.currentA === null ? "—" : `${formatCompactNumber(actuator.currentA)} A`}</p>
      </div>
      <div>
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="text-slate-400">Tín hiệu gần nhất</span>
          <span className={cn("font-medium", actuator.freshness === "STALE" ? "text-amber-600" : actuator.freshness === "FRESH" ? "text-emerald-700" : "text-slate-400")}>{freshnessLabel(actuator.freshness, actuator.lastReportedAt)}</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className={cn("h-full rounded-full", freshnessTone(actuator.freshness))} style={{ width: freshnessWidth(actuator.freshness) }} />
        </div>
      </div>
      <div className="flex items-center justify-end gap-3">
        <span className={cn("text-xs font-semibold", on ? "text-emerald-600" : "text-slate-400")}>{on ? "Đang bật" : actuator.on === false ? "Đang tắt" : "Chưa xác định"}</span>
        <OperatorToggle
          checked={on}
          disabled={!canCommand || actuator.on === null}
          label={`${on ? "Tắt" : "Bật"} ${actuator.name}`}
          onCheckedChange={(next) => onToggle(actuator.deviceId, actuator.id, next)}
        />
      </div>
    </div>
  )
}

export function OperatorDevicesBoard({
  model,
  canCommand,
  onToggle,
}: {
  model: OperatorDevicesModel
  canCommand: boolean
  onToggle: (deviceId: string, actuatorId: string, next: boolean) => void
}) {
  const reportingSensors = model.sensors.filter((sensor) => sensor.status !== "NO_DATA").length
  return (
    <div className="space-y-5">
      <Card className="rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
        <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Cơ cấu chấp hành</h2>
            <p className="text-sm text-slate-400">Bật / tắt · trạng thái lấy từ thiết bị báo về.</p>
          </div>
          <p className="text-sm font-medium text-emerald-700">{model.actuators.length} thiết bị</p>
        </div>
        {model.actuators.length ? model.actuators.map((actuator) => (
          <ActuatorRow key={actuator.id} actuator={actuator} canCommand={canCommand} onToggle={onToggle} />
        )) : <EmptyState icon={Radio} title="Chưa có cơ cấu chấp hành" description="Hệ thống này chưa có actuator runtime." />}
      </Card>

      <Card className="rounded-2xl border-0 p-5 shadow-[0_8px_30px_-18px_rgba(15,63,53,0.35)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Cảm biến</h2>
            <p className="text-sm text-slate-400">Giá trị đo được mới nhất</p>
          </div>
          <p className="text-sm font-medium text-amber-600">{reportingSensors} / {model.sensors.length} có dữ liệu</p>
        </div>
        {model.sensors.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {model.sensors.map((sensor) => <OperatorSensorCardView key={sensor.id} sensor={sensor} />)}
          </div>
        ) : (
          <EmptyState icon={Droplets} title="Chưa có cảm biến" description="Hệ thống này chưa có sensor runtime." />
        )}
      </Card>
    </div>
  )
}

export function OperatorDevicesSkeleton() {
  return <div className="space-y-4"><Skeleton className="h-80" /><Skeleton className="h-64" /></div>
}
